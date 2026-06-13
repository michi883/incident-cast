"""Cross-specialist evidence aggregation.

Clusters ``Finding``s into ``SharedEvidence`` by:

1. **Time proximity** — findings within ``time_window_minutes`` of each other
   are eligible to share a cluster.
2. **Entity overlap** — findings that share any (key, value) entity pair are
   joined. E.g. two findings both referencing ``revision: rev-abc-123``.
3. **Tag overlap** — findings that share any tag are joined.

The aggregator is intentionally **rule-based**, not LLM-judged. Per
``CLAUDE.md``, cross-agent agreement is the confidence signal, and that signal
must come from structural overlap of evidence — not from a model's self-report.

With a single specialist (M1), each finding becomes its own single-supporter
``SharedEvidence``. The same code path handles 2-, 3-, and 4-way agreement at
M4/M5 without changes.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Iterable

from .specialists.base import Finding, SharedEvidence, SpecialistName


def _overlaps(a: Finding, b: Finding, *, window: timedelta) -> bool:
    """True if two findings should share a cluster."""
    if abs(a.timestamp - b.timestamp) > window:
        return False
    shared_entities = any(
        b.entities.get(k) == v for k, v in a.entities.items() if v
    )
    if shared_entities:
        return True
    if set(a.tags) & set(b.tags):
        return True
    return False


def _cluster(
    findings: list[Finding], *, window: timedelta
) -> list[list[Finding]]:
    """Union-find clustering on (time, entities, tags) overlap."""
    parent = list(range(len(findings)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(len(findings)):
        for j in range(i + 1, len(findings)):
            if _overlaps(findings[i], findings[j], window=window):
                union(i, j)

    groups: dict[int, list[Finding]] = defaultdict(list)
    for idx, f in enumerate(findings):
        groups[find(idx)].append(f)
    return list(groups.values())


# Entity keys we surface in the narrative, in priority order. The first key
# that appears anywhere in the cluster's findings becomes the anchor.
NARRATIVE_PRIORITY = (
    "revision",
    "principal",
    "service_account",
    "secret",
    "resource",
    "role",
    "build_id",
    "error_type",
    "service",
    "endpoint",
    "region",
    "tenant",
)


def _pick_anchor(cluster: list[Finding]) -> tuple[str, str] | None:
    """Pick a single (key, value) to anchor the narrative on.

    Prefers high-signal entities (revision, principal, etc.) over generic ones
    (service, region). Among entities at the same priority level, picks the
    most frequent.
    """
    by_key: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for f in cluster:
        for k, v in f.entities.items():
            if v:
                by_key[k][v] += 1
    for key in NARRATIVE_PRIORITY:
        if key in by_key and by_key[key]:
            value = max(by_key[key].items(), key=lambda kv: kv[1])[0]
            return (key, value)
    # fall back to the most frequent entity of any key
    flat: dict[tuple[str, str], int] = defaultdict(int)
    for f in cluster:
        for k, v in f.entities.items():
            if v:
                flat[(k, v)] += 1
    if flat:
        return max(flat.items(), key=lambda kv: kv[1])[0]
    return None


def _narrate(cluster: list[Finding]) -> str:
    """Compose a one-sentence narrative for a cluster.

    Reads as story, not statistics. For multi-specialist clusters, names the
    specialists and the anchoring entity. Designed to make the deck UI's
    SharedEvidenceCard read like "Here's what they all saw together."
    """
    specialists = sorted({f.specialist for f in cluster})
    s_list_human = [s.replace("_", " ") for s in specialists]
    anchor = _pick_anchor(cluster)
    anchor_phrase = (
        f"{anchor[0].replace('_', ' ')} `{anchor[1]}`" if anchor else None
    )

    if len(specialists) == 1:
        who = s_list_human[0]
        if anchor_phrase:
            return f"{who.capitalize()} flagged evidence around {anchor_phrase}."
        return f"{who.capitalize()} surfaced an observation here."

    if len(specialists) == len({"reliability", "deployment", "access", "blast_radius"}):
        # All four
        if anchor_phrase:
            return (
                f"All four specialists — reliability, deployment, access, blast radius — "
                f"converged on {anchor_phrase} in the same window."
            )
        return "All four specialists converged on the same evidence in this window."

    list_str = ", ".join(s_list_human[:-1]) + f" and {s_list_human[-1]}"
    if anchor_phrase:
        return f"{list_str.capitalize()} all pointed at {anchor_phrase} in the same window."
    return f"{list_str.capitalize()} surfaced overlapping evidence in this window."


def aggregate(
    findings_by_specialist: dict[SpecialistName, list[Finding]],
    *,
    time_window_minutes: int = 5,
) -> list[SharedEvidence]:
    """Cluster findings into ``SharedEvidence``, sorted by support strength."""

    all_findings: list[Finding] = []
    for f_list in findings_by_specialist.values():
        all_findings.extend(f_list)
    if not all_findings:
        return []

    window = timedelta(minutes=time_window_minutes)
    clusters = _cluster(all_findings, window=window)

    evidence: list[SharedEvidence] = []
    for cluster in clusters:
        cluster.sort(key=lambda f: f.timestamp)
        # Merge entities across cluster — keep values that don't conflict.
        merged_entities: dict[str, str] = {}
        seen_conflicts: set[str] = set()
        for f in cluster:
            for k, v in f.entities.items():
                if k in seen_conflicts:
                    continue
                if k in merged_entities and merged_entities[k] != v:
                    seen_conflicts.add(k)
                    merged_entities.pop(k, None)
                else:
                    merged_entities[k] = v
        specialists_in_cluster = sorted({f.specialist for f in cluster})
        evidence.append(
            SharedEvidence(
                text=_narrate(cluster),
                window=(cluster[0].timestamp, cluster[-1].timestamp),
                entities=merged_entities,
                supporting_findings=cluster,
                supporting_specialists=specialists_in_cluster,
            )
        )

    evidence.sort(
        key=lambda e: (len(e.supporting_specialists), len(e.supporting_findings)),
        reverse=True,
    )
    return evidence
