"""Deck builder.

Takes the orchestrator's findings + aggregator's ``SharedEvidence`` and produces
a ``Deck`` ready to serialize to JSON for the Next.js UI.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .specialists.base import (
    Deck,
    DeckMetadata,
    Finding,
    IncidentContext,
    SharedEvidence,
    SpecialistName,
    SpecialistSection,
    SpecialistSpec,
    TimelineEvent,
)


def _summarize_findings(spec: SpecialistSpec, findings: list[Finding]) -> str:
    """Stub per-specialist summary.

    M1: simple template based on the count and the highest severity.
    M4 upgrade: replace with a constrained LLM call that grounds the summary in
    only the specialist's own findings (no cross-specialist contamination).
    """
    if not findings:
        return f"{spec.title} did not surface notable findings in this window."

    severities = [f.severity for f in findings]
    if "critical" in severities:
        sev_word = "critical"
    elif "notable" in severities:
        sev_word = "notable"
    else:
        sev_word = "informational"

    return (
        f"{spec.title} surfaced {len(findings)} {sev_word} "
        f"finding{'s' if len(findings) != 1 else ''} addressing: "
        f"{spec.lead_question.lower().rstrip('?')}."
    )


def _build_timeline(
    findings_by_specialist: dict[SpecialistName, list[Finding]],
) -> list[TimelineEvent]:
    timeline: list[TimelineEvent] = []
    for specialist, findings in findings_by_specialist.items():
        for i, f in enumerate(findings):
            timeline.append(
                TimelineEvent(
                    specialist=specialist,
                    timestamp=f.timestamp,
                    label=f.claim[:80],
                    severity=f.severity,
                    entities=f.entities,
                    finding_index=i,
                )
            )
    timeline.sort(key=lambda e: e.timestamp)
    return timeline


def _draft_review_prompts(
    shared_evidence: list[SharedEvidence],
    findings_by_specialist: dict[SpecialistName, list[Finding]],
) -> list[str]:
    """Draft 'what to review next' prompts.

    Hard rule from CLAUDE.md: framed as review prompts ("Review …", "Check …"),
    never as imperative remediation actions.

    M1: templated from the top shared evidence and the most-cited entities.
    M4+ may swap in a constrained LLM call with an output schema that rejects
    imperative verbs.
    """
    prompts: list[str] = []

    for ev in shared_evidence[:3]:
        if ev.entities:
            for k, v in ev.entities.items():
                prompts.append(
                    f"Review {k.replace('_', ' ')} `{v}` and the events near "
                    f"{ev.window[0].isoformat()}."
                )
                break
        else:
            prompts.append(
                f"Review the {ev.supporting_specialists[0].replace('_', ' ')} "
                f"finding around {ev.window[0].isoformat()}: {ev.text}"
            )

    # Always include a high-severity-finding follow-up.
    critical: list[Finding] = []
    for findings in findings_by_specialist.values():
        critical.extend(f for f in findings if f.severity == "critical")
    if critical:
        f = critical[0]
        prompts.append(
            f"Check whether the '{f.claim[:80]}' observation at "
            f"{f.timestamp.isoformat()} reproduces in adjacent services."
        )

    seen: set[str] = set()
    deduped: list[str] = []
    for p in prompts:
        if p not in seen:
            seen.add(p)
            deduped.append(p)
    return deduped[:5]


def build_deck(
    *,
    incident: IncidentContext,
    specs_by_name: dict[SpecialistName, SpecialistSpec],
    findings_by_specialist: dict[SpecialistName, list[Finding]],
    shared_evidence: list[SharedEvidence],
    metadata: DeckMetadata | None = None,
) -> Deck:
    sections: list[SpecialistSection] = []
    for name, spec in specs_by_name.items():
        findings = findings_by_specialist.get(name, [])
        sections.append(
            SpecialistSection(
                spec=spec,
                findings=findings,
                summary=_summarize_findings(spec, findings),
            )
        )

    return Deck(
        incident=incident,
        generated_at=datetime.now(timezone.utc),
        timeline=_build_timeline(findings_by_specialist),
        specialists=sections,
        shared_evidence=shared_evidence,
        review_prompts=_draft_review_prompts(shared_evidence, findings_by_specialist),
        metadata=metadata,
    )
