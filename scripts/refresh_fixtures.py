"""Regenerate the committed fixtures from live Splunk so fixture == live.

For every ``QueryTemplate`` owned by the case's specialists, this runs the (substituted)
SPL against a live Splunk backend (SDK by default, MCP optional) over the case's incident
window and writes the **full result set** to ``<fixture_dir>/<query_name>.json`` in the
fixture schema ``{description, job_id, rows}``.

Why full result sets: the offline fixture path (``replay._materialize_findings``) indexes the
authored ``row_indexes`` directly into the stored rows, while the live path uses
``_select_rows`` over the live result. Storing the complete live result here makes the two
paths select identical rows — so the committed offline artifact judges run matches what the
live demo shows.

Usage:
    python -m scripts.refresh_fixtures                       # default case, sdk backend
    python -m scripts.refresh_fixtures --backend mcp
    python -m scripts.refresh_fixtures --case data/cases/<id>.yaml

Requires a live, populated Splunk (run scripts/setup_splunk.sh + ingest the scenario first)
and the backend env vars (SPLUNK_* / SPLUNK_MCP_*). Existing ``description`` text in each
fixture is preserved.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from dotenv import load_dotenv

from incidentcast.cli import ALL_SPECS, _build_query_client
from incidentcast.replay import _substitute, load_case

app = typer.Typer(add_completion=False)

REPO_ROOT = Path(__file__).resolve().parent.parent


async def _refresh(case_path: Path, backend: str) -> int:
    case = load_case(case_path)
    fixture_dir = REPO_ROOT / case.fixture_dir
    fixture_dir.mkdir(parents=True, exist_ok=True)

    # Every query owned by a specialist this case uses (not just the cited ones) so the
    # offline fixture backend can serve the full repertoire, including the agentic path.
    templates = []
    for name in case.specialists:
        spec = ALL_SPECS.get(name)
        if spec is None:
            raise typer.BadParameter(f"Case references unknown specialist '{name}'.")
        templates.extend(spec.query_repertoire)

    client = _build_query_client(backend)
    written = 0
    try:
        for tpl in templates:
            spl = _substitute(tpl.spl, case.incident)
            result = await client.run(
                query_name=tpl.name,
                spl=spl,
                earliest=case.incident.earliest,
                latest=case.incident.latest,
            )
            path = fixture_dir / f"{tpl.name}.json"
            # Preserve a human-authored description if one already exists.
            description = ""
            if path.exists():
                try:
                    description = json.loads(path.read_text()).get("description", "")
                except (json.JSONDecodeError, OSError):
                    description = ""
            payload = {
                "description": description,
                "job_id": result.job_id or f"{backend}-live-{tpl.name}",
                "rows": result.rows,
            }
            path.write_text(json.dumps(payload, indent=2) + "\n")
            typer.echo(f"  {tpl.name}: {len(result.rows)} rows -> {path.name}")
            written += 1
    finally:
        aclose = getattr(client, "aclose", None)
        if aclose is not None:
            await aclose()
    return written


@app.command()
def main(
    case: str = typer.Option(
        "data/cases/cloud_run_secret_loss.yaml", "--case", help="Case YAML to refresh fixtures for."
    ),
    backend: str = typer.Option("sdk", "--backend", help="Live backend: sdk | mcp."),
) -> None:
    load_dotenv(str(REPO_ROOT / ".env"))
    if backend not in ("sdk", "mcp"):
        raise typer.BadParameter("--backend must be 'sdk' or 'mcp' (fixture is the target, not a source).")
    case_path = Path(case)
    if not case_path.is_absolute():
        case_path = REPO_ROOT / case_path
    typer.echo(f"Refreshing fixtures for {case_path.name} via {backend} …")
    written = asyncio.run(_refresh(case_path, backend))
    typer.echo(f"Done — refreshed {written} fixtures from live Splunk.")


if __name__ == "__main__":
    app()
