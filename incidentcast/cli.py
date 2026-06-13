"""CLI entry point. Wires backend → specialists → orchestrator → aggregator → deck."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

import typer
import yaml
from dotenv import load_dotenv
from rich.console import Console

from .aggregator import aggregate
from .deck import build_deck
from .orchestrator import run_specialists
from .replay import build_replay, load_case, materialize_via_backend
from .specialists.base import DeckMetadata, IncidentContext, SpecialistName, SpecialistSpec
from .specialists.access import ACCESS_SPEC
from .specialists.blast_radius import BLAST_RADIUS_SPEC
from .specialists.deployment import DEPLOYMENT_SPEC
from .specialists.reliability import RELIABILITY_SPEC
from .specialists.runtime import Specialist
from .splunk.fixture_client import FixtureQueryClient
from .splunk.interface import QueryInterface
from .splunk.mcp_client import SplunkMCPQueryClient
from .splunk.sdk_client import SplunkSDKQueryClient

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


def _build_query_client(backend: str) -> QueryInterface:
    """A ``QueryInterface`` for the replay's evidence source (sdk | mcp; fixture handled inline)."""
    if backend == "sdk":
        return SplunkSDKQueryClient()
    if backend == "mcp":
        return SplunkMCPQueryClient()
    raise typer.BadParameter(f"Unknown query client backend: {backend}")


ALL_SPECS: dict[SpecialistName, SpecialistSpec] = {
    "reliability": RELIABILITY_SPEC,
    "deployment": DEPLOYMENT_SPEC,
    "blast_radius": BLAST_RADIUS_SPEC,
    "access": ACCESS_SPEC,
}


def _build_gateway_backend(backend: str) -> QueryInterface:
    if backend == "fixture":
        fixture_dir = os.environ.get(
            "INCIDENTCAST_FIXTURE_DIR", "data/fixtures/cloud_run_secret_loss"
        )
        return FixtureQueryClient(fixture_dir)
    if backend == "sdk":
        return SplunkSDKQueryClient()
    raise typer.BadParameter(f"Unknown gateway backend: {backend}")


def _build_specialist(
    spec: SpecialistSpec,
    backend: str,
    *,
    model: str,
    debug: bool,
) -> Specialist:
    if backend == "mcp":
        url = os.environ.get("SPLUNK_MCP_URL", "").strip()
        token = os.environ.get("SPLUNK_MCP_TOKEN", "").strip()
        if not url or not token:
            raise typer.BadParameter(
                "SPLUNK_MCP_URL / SPLUNK_MCP_TOKEN must be set for --backend mcp. "
                "Run ./scripts/setup_splunk_mcp.sh."
            )
        return Specialist(spec, mcp_url=url, mcp_token=token, model=model, debug=debug)
    backend_client = _build_gateway_backend(backend)
    return Specialist(spec, backend_client, model=model, debug=debug)


def _load_incident(path: Path) -> IncidentContext:
    raw = yaml.safe_load(path.read_text())
    return IncidentContext.model_validate(raw)


@app.command()
def investigate(
    incident_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    backend: str = typer.Option(
        os.environ.get("INCIDENTCAST_BACKEND", "fixture"),
        "--backend",
        help="Query backend: fixture | sdk | mcp",
    ),
    specialists: Optional[list[str]] = typer.Option(
        None,
        "--specialist",
        help="Specialist(s) to enable. Repeat for multiple. Default: all available.",
    ),
    out: Path = typer.Option(
        Path("web/public/decks/demo.json"),
        "--out",
        help="Path to write the deck JSON to.",
    ),
    model: str = typer.Option(
        os.environ.get("INCIDENTCAST_MODEL", "gemini-3.1-pro-preview"),
        "--model",
        help="Model used by the specialists.",
    ),
    debug: bool = typer.Option(False, "--debug", help="Print specialist text output."),
):
    """Run the incident room over an incident and emit a deck JSON for the UI."""
    load_dotenv()
    incident = _load_incident(incident_path)

    requested: list[SpecialistName]
    if specialists:
        for s in specialists:
            if s not in ALL_SPECS:
                raise typer.BadParameter(
                    f"Unknown specialist '{s}'. Available: {list(ALL_SPECS)}"
                )
        requested = list(specialists)  # type: ignore[assignment]
    else:
        requested = list(ALL_SPECS.keys())

    runners = [
        _build_specialist(ALL_SPECS[name], backend, model=model, debug=debug)
        for name in requested
    ]
    specs_by_name = {name: ALL_SPECS[name] for name in requested}

    console.print(
        f"[bold]incidentcast[/bold] — incident [cyan]{incident.id}[/cyan] · "
        f"backend=[yellow]{backend}[/yellow] · specialists={requested}"
    )

    findings_by_specialist = asyncio.run(run_specialists(runners, incident))

    for name, findings in findings_by_specialist.items():
        console.print(f"  [{name}] → {len(findings)} finding(s)")

    shared = aggregate(findings_by_specialist)
    console.print(f"  shared_evidence → {len(shared)} cluster(s)")

    data_kind = {
        "fixture": "fixture_json",
        "sdk": "synthetic_splunk",
        "mcp": "synthetic_splunk",
    }[backend]
    metadata = DeckMetadata(
        backend=backend,  # type: ignore[arg-type]
        data_kind=data_kind,  # type: ignore[arg-type]
        scenario="cloud_run_secret_loss",
        specialists_included=requested,
        command=(
            f"incidentcast {incident_path} --backend {backend} --out {out}"
            + ("".join(f" --specialist {s}" for s in specialists) if specialists else "")
        ),
        model=model,
    )

    deck = build_deck(
        incident=incident,
        specs_by_name=specs_by_name,
        findings_by_specialist=findings_by_specialist,
        shared_evidence=shared,
        metadata=metadata,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(deck.model_dump_json(indent=2))
    console.print(f"[green]wrote[/green] {out}")


@app.command()
def cast(
    case_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    backend: str = typer.Option(
        os.environ.get("INCIDENTCAST_BACKEND", "fixture"),
        "--backend",
        help="Evidence source: fixture (offline) | sdk (live Splunk SDK) | mcp (Splunk MCP).",
    ),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Replay JSON path. Default: web/public/cases/<case id>.json.",
    ),
):
    """Build an investigation *replay* from an authored case.

    The replay is the artifact the live workspace plays back: divergent theories, specialist
    witnesses, evidence landing over time, and the convergence climax. The narrative scaffold
    is authored; the **evidence** comes from ``--backend``:

    - ``fixture`` (default, offline): findings cite canned rows. No Splunk needed.
    - ``sdk`` / ``mcp`` (live): each authored SPL runs against local Splunk Enterprise via the
      splunklib SDK or the Splunk MCP Server, binding the real returned rows + source.
    """
    load_dotenv()
    case = load_case(case_path)

    missing = [name for name in case.specialists if name not in ALL_SPECS]
    if missing:
        raise typer.BadParameter(f"Case references unknown specialists: {missing}")
    specs_by_name = {name: ALL_SPECS[name] for name in case.specialists}

    if backend == "fixture":
        replay = build_replay(case, specs_by_name)
    elif backend in ("sdk", "mcp"):
        client = _build_query_client(backend)

        async def _run():
            try:
                return await materialize_via_backend(case, specs_by_name, client, backend)
            finally:
                aclose = getattr(client, "aclose", None)
                if aclose is not None:
                    await aclose()

        console.print(f"[bold]querying Splunk[/bold] via [yellow]{backend}[/yellow] …")
        by_specialist, ref_by_id = asyncio.run(_run())
        replay = build_replay(
            case,
            specs_by_name,
            findings_by_specialist=by_specialist,
            ref_by_id=ref_by_id,
            backend=backend,
        )
    else:
        raise typer.BadParameter(f"Unknown backend: {backend}. Use fixture | sdk | mcp.")

    target = out or Path("web/public/cases") / f"{case.id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(replay.model_dump_json(indent=2))

    # Also emit the underlying deck so the workspace's "Open incident deck" link (the
    # secondary, forensic deep-dive at /decks/<id>) has something to render.
    deck_path = Path("web/public/decks") / f"{case.id}.json"
    deck_path.parent.mkdir(parents=True, exist_ok=True)
    deck_path.write_text(replay.deck.model_dump_json(indent=2))

    n_findings = sum(len(s.findings) for s in replay.deck.specialists)
    n_decisions = sum(1 for s in replay.steps if s.choices)
    converged = [
        s.consensus.leading_theory
        for s in replay.steps
        if s.consensus.converged and not s.choices and s.next is None
    ]
    console.print(
        f"[bold]incidentcast cast[/bold] — case [cyan]{case.id}[/cyan] · "
        f"{len(replay.steps)} steps · {n_decisions} decisions · "
        f"{len(replay.theories)} theories · {n_findings} findings · "
        f"converges → [cyan]{', '.join(sorted(set(c for c in converged if c)))}[/cyan]"
    )
    console.print(f"[green]wrote[/green] {target}")


if __name__ == "__main__":
    app()
