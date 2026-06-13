"""Core specialist contracts.

Each specialist is constructed from a ``SpecialistSpec`` (declarative: goal,
lead question, sub-questions, owned query repertoire, output tags) plus a
``QueryInterface`` backend and an LLM. The system prompt is generated from the
spec so the spec stays the source of truth for "what this specialist asks and
how it answers."

Specialists emit structured ``Finding`` objects via tool-use. The aggregator
then clusters findings across specialists into ``SharedEvidence``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SpecialistName = Literal["reliability", "deployment", "access", "blast_radius"]
Severity = Literal["info", "notable", "critical"]


class QueryTemplate(BaseModel):
    """A parameterized SPL query that belongs to exactly one specialist."""

    name: str = Field(description="Canonical, lowercase, snake_case identifier.")
    purpose: str = Field(description="One-sentence description of what this answers.")
    spl: str = Field(description="SPL with $earliest$ / $latest$ / param placeholders.")
    owned_by: SpecialistName = Field(description="The single specialist that owns this template.")
    expected_columns: list[str] = Field(
        default_factory=list,
        description="Columns the specialist should expect in the result rows.",
    )


class SpecialistSpec(BaseModel):
    """Declarative description of a specialist.

    The runtime ``Specialist`` is constructed from a spec — the spec drives the
    system prompt, the tool repertoire, and the per-specialist deck section.
    """

    name: SpecialistName
    title: str = Field(description="Human-readable title for the deck section.")
    goal: str = Field(description="One-sentence north star.")
    lead_question: str = Field(description="The single question this specialist answers.")
    sub_questions: list[str] = Field(
        description="3–5 concrete questions the specialist pursues. Drives ordering."
    )
    query_repertoire: list[QueryTemplate] = Field(
        description="SPL templates owned by this specialist."
    )
    output_tags: list[str] = Field(
        description=(
            "Tag namespaces this specialist emits on Findings — e.g. 'revision:*', "
            "'service_account:*'. Used by the aggregator to cluster across specialists."
        )
    )


class Finding(BaseModel):
    """A single, evidence-citing observation from one specialist."""

    specialist: SpecialistName
    timestamp: datetime = Field(description="Event time (not investigation time).")
    claim: str = Field(max_length=240, description="Human-readable, ≤240 chars.")
    severity: Severity = "notable"
    entities: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Identifying entities, e.g. {'revision': 'rev-abc-123', "
            "'service_account': 'rt@proj.iam.gserviceaccount.com'}."
        ),
    )
    source_query_name: str = Field(description="Canonical name of the QueryTemplate.")
    source_query_spl: str = Field(description="The literal SPL that ran.")
    source_rows: list[dict[str, Any]] = Field(
        description="The row(s) cited by this finding. Renders in the EvidenceDrawer."
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Cluster tags like 'revision:rev-abc-123'. Used by the aggregator.",
    )
    backend: Literal["fixture", "sdk", "mcp"] = Field(
        default="fixture",
        description="Where the cited rows came from: canned fixture, Splunk SDK, or Splunk MCP.",
    )
    job_id: str | None = Field(
        default=None, description="Splunk search job/sid when run live (SDK/MCP)."
    )


class SharedEvidence(BaseModel):
    """A claim supported by one or more specialists.

    "Convergence" deliberately not used in the type name — this models a piece
    of evidence multiple specialists independently surfaced, which is what we
    want to *narrate* in the deck.
    """

    text: str = Field(description="One-sentence narrative of what was shared.")
    window: tuple[datetime, datetime]
    entities: dict[str, str] = Field(default_factory=dict)
    supporting_findings: list[Finding]
    supporting_specialists: list[SpecialistName] = Field(
        description="Distinct specialist names. ``len()`` is the strength of agreement."
    )


class IncidentContext(BaseModel):
    """The incident handed to each specialist as starting context."""

    id: str
    title: str
    triggered_at: datetime
    earliest: str = Field(description="Splunk earliest time modifier for the investigation.")
    latest: str = Field(description="Splunk latest time modifier for the investigation.")
    hints: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional starting hints, e.g. {'service': 'cart', 'env': 'prod'}.",
    )


class TimelineEvent(BaseModel):
    """A point on the unified deck timeline. Renders as a dot in SharedTimeline."""

    specialist: SpecialistName
    timestamp: datetime
    label: str
    severity: Severity
    entities: dict[str, str] = Field(default_factory=dict)
    finding_index: int = Field(
        description="Index into the per-specialist findings list, for click→drawer."
    )


class SpecialistSection(BaseModel):
    spec: SpecialistSpec
    findings: list[Finding]
    summary: str


class DeckMetadata(BaseModel):
    """Provenance for a deck — what backend, what data, what command produced it.

    Surfaced in the workspace/deck UI so a reviewer can tell at a glance whether
    a deck came from fixture data, live Splunk, or Splunk MCP, and what command
    was used to generate it.
    """

    backend: Literal["fixture", "sdk", "mcp"]
    data_kind: Literal["fixture_json", "synthetic_splunk", "real_cloud_run"]
    scenario: str = Field(description="Scenario id, e.g. 'cloud_run_secret_loss'.")
    specialists_included: list[SpecialistName]
    command: str = Field(description="The shell-equivalent command that produced this deck.")
    model: str | None = Field(default=None, description="Model used by the specialists.")


class Deck(BaseModel):
    """The end-to-end deck artifact rendered by the Next.js UI."""

    incident: IncidentContext
    generated_at: datetime
    timeline: list[TimelineEvent]
    specialists: list[SpecialistSection]
    shared_evidence: list[SharedEvidence]
    review_prompts: list[str] = Field(
        description="Phrased as review prompts ('Review …'), never as actions."
    )
    metadata: DeckMetadata | None = Field(
        default=None,
        description="Provenance for the deck (backend, data source, command). Pre-M5 decks may omit this.",
    )
