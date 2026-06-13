"""Investigation replay — the artifact the live workspace plays back.

DIRECTION: IncidentCast should feel like *guiding an investigation*, not advancing a slide
deck. The user does not control time; the user influences **what the room investigates
next**. So the recording is not a linear timeline — it is a small **graph of steps** joined
by **choices** ("Investigate recent deployment", "Inspect permission anomalies", …). The
chosen option decides which specialist speaks / which evidence surfaces next; the branches
rejoin and the narrative always converges on one explanation.

Each step carries **deltas**, not a full snapshot: the theory-status changes, witness
updates, and newly revealed findings it introduces. The UI folds the deltas along the path
the user has taken, so the board accumulates and stays monotonic no matter which branch was
chosen. Theories are the primary on-screen object; specialists are one-line witnesses that
support or weaken a theory.

The recording is built deterministically from an **authored case definition**
(`data/cases/*.yaml`). Findings cite real fixture SPL + rows so evidence stays honest, and
the rule-based :func:`incidentcast.aggregator.aggregate` still backs the convergence climax
(a build-time guardrail), even though the per-step narrative is authored.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from .aggregator import aggregate
from .deck import build_deck
from .splunk.interface import QueryInterface
from .specialists.base import (
    Deck,
    DeckMetadata,
    Finding,
    IncidentContext,
    Severity,
    SpecialistName,
    SpecialistSpec,
)

TheoryStatus = Literal[
    "forming",
    "possible",
    "weakening",
    "strengthening",
    "leading",
    "eliminated",
    "confirmed",
]
Stance = Literal["supports", "weakens", "neutral"]
Activity = Literal["idle", "investigating", "posting", "revising"]


# --------------------------------------------------------------------------- #
# Authored case definition (input)                                            #
# --------------------------------------------------------------------------- #


class Theory(BaseModel):
    """A candidate explanation the room weighs. The primary object on screen."""

    id: str
    label: str


class AuthoredFinding(BaseModel):
    """A finding to materialize against real fixture SPL + rows.

    ``source_query_name`` resolves to the owning specialist's ``QueryTemplate`` (literal
    SPL) and to ``<fixture_dir>/<source_query_name>.json`` (the cited rows). ``id`` lets
    steps reference the finding for progressive evidence disclosure.
    """

    id: str
    specialist: SpecialistName
    timestamp: datetime
    claim: str = Field(max_length=240)
    severity: Severity = "notable"
    entities: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    source_query_name: str
    row_indexes: list[int] | None = Field(
        default=None, description="Indices into the fixture rows to cite. Default: first."
    )


class TheoryDelta(BaseModel):
    id: str
    status: TheoryStatus
    reason: str = Field(default="", description="One line on why the theory stands here.")


class WitnessDelta(BaseModel):
    specialist: SpecialistName
    thought: str = Field(default="", description="One-line current read.")
    supports: str | None = Field(default=None, description="Theory id this witness backs.")
    stance: Stance = "neutral"
    activity: Activity = "idle"
    finding: str | None = Field(default=None, description="Authored finding id for evidence.")


class Consensus(BaseModel):
    text: str
    remaining: int = 0
    converged: bool = False
    leading_theory: str | None = None


class Choice(BaseModel):
    """A way the user can steer the room. Use operational verbs, never Next/Prev."""

    label: str
    goto: str = Field(description="Step id this choice leads to.")


class AuthoredStep(BaseModel):
    id: str
    phase: str = Field(default="", description="Short label, used only by demo controls.")
    headline: str = Field(default="", description="One sentence on what just happened.")
    question: str = Field(default="Why is checkout failing?")
    theories: list[TheoryDelta] = Field(default_factory=list)
    witnesses: list[WitnessDelta] = Field(default_factory=list)
    consensus: Consensus
    reveal: list[str] = Field(default_factory=list, description="Authored finding ids now inspectable.")
    prompt: str = Field(default="", description="The steering question. Empty on auto/terminal steps.")
    choices: list[Choice] = Field(default_factory=list)
    next: str | None = Field(
        default=None,
        description="Auto-advance target. The room moves here on its own after `dwell`. "
        "Mutually exclusive with `choices`.",
    )
    dwell: float = Field(default=3.0, description="Seconds the room lingers on an auto step.")


class CaseDefinition(BaseModel):
    """Authored incident case: gallery metadata + the steerable investigation graph."""

    id: str
    title: str
    blurb: str
    summary: str
    fixture_dir: str
    incident: IncidentContext
    theories: list[Theory]
    findings: list[AuthoredFinding] = Field(default_factory=list)
    start: str = Field(description="Id of the opening step.")
    steps: list[AuthoredStep]
    specialists: list[SpecialistName]


# --------------------------------------------------------------------------- #
# Replay artifact (output)                                                     #
# --------------------------------------------------------------------------- #


class TheoryState(BaseModel):
    id: str
    label: str
    status: TheoryStatus
    reason: str = ""


class WitnessState(BaseModel):
    specialist: SpecialistName
    thought: str = ""
    supports: str | None = None
    stance: Stance = "neutral"
    activity: Activity = "idle"
    finding_specialist: SpecialistName | None = None
    finding_index: int | None = None


class ConsensusState(BaseModel):
    text: str
    remaining: int = 0
    converged: bool = False
    leading_theory: str | None = None


class FindingRef(BaseModel):
    specialist: SpecialistName
    finding_index: int


class Step(BaseModel):
    """One node in the investigation graph. Carries deltas the UI folds along the path."""

    id: str
    phase: str = ""
    headline: str = ""
    question: str = "Why is checkout failing?"
    theories: list[TheoryState] = Field(default_factory=list)
    witnesses: list[WitnessState] = Field(default_factory=list)
    consensus: ConsensusState
    revealed_findings: list[FindingRef] = Field(default_factory=list)
    prompt: str = ""
    choices: list[Choice] = Field(default_factory=list)
    # The room advances to `next` on its own after `dwell` seconds; decision steps (those
    # with `choices`) instead wait for the user. Exactly one of the two, or neither (terminal).
    next: str | None = None
    dwell: float = 3.0


class InvestigationReplay(BaseModel):
    """The end-to-end recording the live workspace plays back, steered by the user."""

    case_id: str
    title: str
    blurb: str
    summary: str
    incident: IncidentContext
    specialists: list[SpecialistName]
    theories: list[Theory]
    start: str
    steps: list[Step]
    deck: Deck = Field(description="Evidence substrate: sections, shared evidence, citations.")


# --------------------------------------------------------------------------- #
# Builder                                                                      #
# --------------------------------------------------------------------------- #

_PARAM_RE = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)\$")


def _substitute(spl: str, incident: IncidentContext) -> str:
    """Fill ``$param$`` placeholders from incident hints + earliest/latest.

    Mirrors ``incidentcast.specialists.runtime._substitute`` without pulling in the LLM
    client dependency, so the replay builder stays import-light.
    """
    sources: dict[str, Any] = {
        **incident.hints,
        "earliest": incident.earliest,
        "latest": incident.latest,
    }

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return str(sources[key]) if key in sources else m.group(0)

    return _PARAM_RE.sub(repl, spl)


def load_case(path: str | Path) -> CaseDefinition:
    raw = yaml.safe_load(Path(path).read_text())
    return CaseDefinition.model_validate(raw)


def _materialize_findings(
    case: CaseDefinition,
    specs_by_name: dict[SpecialistName, SpecialistSpec],
) -> tuple[dict[SpecialistName, list[Finding]], dict[str, FindingRef]]:
    """Turn authored findings into real, evidence-cited ``Finding`` objects.

    Returns the per-specialist findings (for ``build_deck``) and a map from each authored
    finding's ``id`` to its ``(specialist, finding_index)`` location, so steps can reference
    findings for progressive disclosure.
    """
    fixture_dir = Path(case.fixture_dir)
    templates: dict[str, Any] = {}
    for spec in specs_by_name.values():
        for tpl in spec.query_repertoire:
            templates[tpl.name] = tpl

    by_specialist: dict[SpecialistName, list[Finding]] = {name: [] for name in specs_by_name}
    ref_by_id: dict[str, FindingRef] = {}

    for af in case.findings:
        tpl = templates.get(af.source_query_name)
        if tpl is None:
            raise ValueError(
                f"Authored finding cites unknown query '{af.source_query_name}'. "
                f"Known: {sorted(templates)}"
            )
        if tpl.owned_by != af.specialist:
            raise ValueError(
                f"Query '{af.source_query_name}' is owned by {tpl.owned_by}, not "
                f"{af.specialist}; specialists may only cite their own repertoire."
            )
        fixture_path = fixture_dir / f"{af.source_query_name}.json"
        if not fixture_path.exists():
            raise FileNotFoundError(
                f"No fixture rows for '{af.source_query_name}' at {fixture_path}."
            )
        payload = json.loads(fixture_path.read_text())
        all_rows: list[dict[str, Any]] = payload.get("rows", [])
        idxs = af.row_indexes if af.row_indexes is not None else [0]
        rows = [all_rows[i] for i in idxs if 0 <= i < len(all_rows)]

        finding = Finding(
            specialist=af.specialist,
            timestamp=af.timestamp,
            claim=af.claim,
            severity=af.severity,
            entities=af.entities,
            source_query_name=af.source_query_name,
            source_query_spl=_substitute(tpl.spl, case.incident),
            source_rows=rows,
            tags=af.tags,
        )
        lst = by_specialist[af.specialist]
        ref_by_id[af.id] = FindingRef(specialist=af.specialist, finding_index=len(lst))
        lst.append(finding)

    return by_specialist, ref_by_id


def _aggregator_anchor(by_specialist: dict[SpecialistName, list[Finding]]) -> dict[str, str]:
    """The entity the rule-based aggregator's strongest cluster lands on (guardrail)."""
    clusters = aggregate(by_specialist)
    return clusters[0].entities if clusters else {}


def _select_rows(
    rows: list[dict[str, Any]], row_indexes: list[int] | None, *, cap: int = 5
) -> list[dict[str, Any]]:
    """Pick the rows to cite. Honor authored ``row_indexes`` only when every index is in
    range (keeps the fixture path byte-stable); otherwise cite the first ``cap`` rows, which
    is robust when live Splunk returns a different count/order than the fixtures."""
    if row_indexes and all(0 <= i < len(rows) for i in row_indexes):
        return [rows[i] for i in row_indexes]
    return rows[:cap]


async def materialize_via_backend(
    case: CaseDefinition,
    specs_by_name: dict[SpecialistName, SpecialistSpec],
    client: "QueryInterface",
    backend: str,
) -> tuple[dict[SpecialistName, list[Finding]], dict[str, FindingRef]]:
    """Like ``_materialize_findings`` but runs each authored query LIVE through a
    ``QueryInterface`` (Splunk SDK or MCP), binding the real returned rows + backend source.

    The authored SPL (from each owning ``QueryTemplate``) and the narrative scaffold are
    unchanged — only the *evidence* now comes from a real Splunk query.
    """
    templates: dict[str, Any] = {}
    for spec in specs_by_name.values():
        for tpl in spec.query_repertoire:
            templates[tpl.name] = tpl

    by_specialist: dict[SpecialistName, list[Finding]] = {name: [] for name in specs_by_name}
    ref_by_id: dict[str, FindingRef] = {}

    for af in case.findings:
        tpl = templates.get(af.source_query_name)
        if tpl is None:
            raise ValueError(
                f"Authored finding cites unknown query '{af.source_query_name}'. "
                f"Known: {sorted(templates)}"
            )
        if tpl.owned_by != af.specialist:
            raise ValueError(
                f"Query '{af.source_query_name}' is owned by {tpl.owned_by}, not "
                f"{af.specialist}; specialists may only cite their own repertoire."
            )
        spl = _substitute(tpl.spl, case.incident)
        result = await client.run(
            query_name=af.source_query_name,
            spl=spl,
            earliest=case.incident.earliest,
            latest=case.incident.latest,
        )
        rows = _select_rows(result.rows, af.row_indexes)

        finding = Finding(
            specialist=af.specialist,
            timestamp=af.timestamp,
            claim=af.claim,
            severity=af.severity,
            entities=af.entities,
            source_query_name=af.source_query_name,
            source_query_spl=spl,
            source_rows=rows,
            tags=af.tags,
            backend=backend,  # type: ignore[arg-type]
            job_id=result.job_id,
        )
        lst = by_specialist[af.specialist]
        ref_by_id[af.id] = FindingRef(specialist=af.specialist, finding_index=len(lst))
        lst.append(finding)

    return by_specialist, ref_by_id


def build_replay(
    case: CaseDefinition,
    specs_by_name: dict[SpecialistName, SpecialistSpec],
    *,
    findings_by_specialist: dict[SpecialistName, list[Finding]] | None = None,
    ref_by_id: dict[str, FindingRef] | None = None,
    backend: str = "fixture",
) -> InvestigationReplay:
    """Assemble the deterministic, steerable step graph from an authored case definition.

    By default findings are materialized synchronously from fixtures (offline). For a live
    Splunk run, pass pre-materialized ``findings_by_specialist``/``ref_by_id`` from
    :func:`materialize_via_backend` plus the matching ``backend`` label.
    """
    theory_ids = {t.id for t in case.theories}
    label_by_id = {t.id: t.label for t in case.theories}

    if findings_by_specialist is None or ref_by_id is None:
        by_specialist, ref_by_id = _materialize_findings(case, specs_by_name)
    else:
        by_specialist = findings_by_specialist

    metadata = DeckMetadata(
        backend=backend,  # type: ignore[arg-type]
        data_kind="fixture_json" if backend == "fixture" else "synthetic_splunk",
        scenario=case.id,
        specialists_included=list(case.specialists),
        command=f"incidentcast cast data/cases/{case.id}.yaml --backend {backend}",
        model=None,
    )
    deck = build_deck(
        incident=case.incident,
        specs_by_name=specs_by_name,
        findings_by_specialist=by_specialist,
        shared_evidence=aggregate(by_specialist),
        metadata=metadata,
    )

    step_ids = {s.id for s in case.steps}
    if case.start not in step_ids:
        raise ValueError(f"start '{case.start}' is not a defined step.")

    steps: list[Step] = []
    for s in case.steps:
        theories: list[TheoryState] = []
        for td in s.theories:
            if td.id not in theory_ids:
                raise ValueError(f"Step '{s.id}' references unknown theory '{td.id}'.")
            theories.append(
                TheoryState(id=td.id, label=label_by_id[td.id], status=td.status, reason=td.reason)
            )

        witnesses: list[WitnessState] = []
        for w in s.witnesses:
            if w.supports is not None and w.supports not in theory_ids:
                raise ValueError(f"Step '{s.id}' witness backs unknown theory '{w.supports}'.")
            ref = ref_by_id.get(w.finding) if w.finding else None
            if w.finding and ref is None:
                raise ValueError(f"Step '{s.id}' witness cites unknown finding id '{w.finding}'.")
            witnesses.append(
                WitnessState(
                    specialist=w.specialist,
                    thought=w.thought,
                    supports=w.supports,
                    stance=w.stance,
                    activity=w.activity,
                    finding_specialist=ref.specialist if ref else None,
                    finding_index=ref.finding_index if ref else None,
                )
            )

        if s.consensus.leading_theory and s.consensus.leading_theory not in theory_ids:
            raise ValueError(f"Step '{s.id}' leads unknown theory '{s.consensus.leading_theory}'.")

        for c in s.choices:
            if c.goto not in step_ids:
                raise ValueError(f"Step '{s.id}' choice '{c.label}' goes to unknown step '{c.goto}'.")
        if s.next is not None and s.next not in step_ids:
            raise ValueError(f"Step '{s.id}' auto-advances to unknown step '{s.next}'.")
        if s.choices and s.next is not None:
            raise ValueError(f"Step '{s.id}' has both choices and an auto-advance 'next'.")

        revealed: list[FindingRef] = []
        for fid in s.reveal:
            ref = ref_by_id.get(fid)
            if ref is None:
                raise ValueError(f"Step '{s.id}' reveals unknown finding id '{fid}'.")
            revealed.append(ref)

        steps.append(
            Step(
                id=s.id,
                phase=s.phase,
                headline=s.headline,
                question=s.question,
                theories=theories,
                witnesses=witnesses,
                consensus=ConsensusState(**s.consensus.model_dump()),
                revealed_findings=revealed,
                prompt=s.prompt,
                choices=s.choices,
                next=s.next,
                dwell=s.dwell,
            )
        )

    # Every path must be able to reach a converged terminal — the room always converges.
    terminals = [s for s in steps if not s.choices and s.next is None]
    converged_terminals = [s for s in terminals if s.consensus.converged]
    if not converged_terminals:
        raise ValueError("No converged terminal step — the investigation never resolves.")

    goto = {
        s.id: [c.goto for c in s.choices] + ([s.next] if s.next else []) for s in steps
    }
    can_converge = {s.id for s in converged_terminals}
    changed = True
    while changed:
        changed = False
        for s in steps:
            if s.id in can_converge:
                continue
            if any(nxt in can_converge for nxt in goto[s.id]):
                can_converge.add(s.id)
                changed = True
    dead_ends = [s.id for s in steps if s.id not in can_converge]
    if dead_ends:
        raise ValueError(f"Steps cannot reach convergence: {dead_ends}")

    return InvestigationReplay(
        case_id=case.id,
        title=case.title,
        blurb=case.blurb,
        summary=case.summary,
        incident=case.incident,
        specialists=list(case.specialists),
        theories=case.theories,
        start=case.start,
        steps=steps,
        deck=deck,
    )
