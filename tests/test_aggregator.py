"""Aggregator clustering behavior."""

from __future__ import annotations

from datetime import datetime, timezone

from incidentcast.aggregator import aggregate
from incidentcast.specialists.base import Finding


def _f(
    specialist: str,
    minute: int,
    *,
    entities: dict[str, str] | None = None,
    tags: list[str] | None = None,
    claim: str = "obs",
) -> Finding:
    return Finding(
        specialist=specialist,  # type: ignore[arg-type]
        timestamp=datetime(2026, 5, 26, 14, minute, 0, tzinfo=timezone.utc),
        claim=claim,
        severity="notable",
        entities=entities or {},
        source_query_name=f"{specialist}_q",
        source_query_spl="search index=x",
        source_rows=[{"x": 1}],
        tags=tags or [],
    )


def test_empty_returns_empty() -> None:
    assert aggregate({}) == []


def test_single_finding_becomes_single_supporter_evidence() -> None:
    f = _f("reliability", 2, entities={"service": "checkout"})
    out = aggregate({"reliability": [f]})
    assert len(out) == 1
    assert out[0].supporting_specialists == ["reliability"]
    assert out[0].entities == {"service": "checkout"}


def test_shared_entity_clusters_across_specialists() -> None:
    a = _f("reliability", 2, entities={"revision": "rev-abc"})
    b = _f("deployment", 4, entities={"revision": "rev-abc"})
    out = aggregate({"reliability": [a], "deployment": [b]})
    assert len(out) == 1
    assert sorted(out[0].supporting_specialists) == ["deployment", "reliability"]


def test_shared_tag_clusters_when_no_entity_overlap() -> None:
    a = _f("reliability", 2, tags=["error_type:PermissionDenied"])
    b = _f("access", 3, tags=["error_type:PermissionDenied"])
    out = aggregate({"reliability": [a], "access": [b]})
    assert len(out) == 1
    assert sorted(out[0].supporting_specialists) == ["access", "reliability"]


def test_no_overlap_means_no_cluster() -> None:
    a = _f("reliability", 2, entities={"service": "checkout"})
    b = _f("deployment", 4, entities={"revision": "rev-xyz"})
    out = aggregate({"reliability": [a], "deployment": [b]})
    assert len(out) == 2  # two separate single-supporter clusters


def test_time_window_excludes_far_findings_even_with_shared_entity() -> None:
    a = _f("reliability", 2, entities={"revision": "rev-abc"})
    b = _f("deployment", 30, entities={"revision": "rev-abc"})  # 28 min later
    out = aggregate({"reliability": [a], "deployment": [b]}, time_window_minutes=5)
    assert len(out) == 2


def test_results_sorted_by_support_strength_descending() -> None:
    a = _f("reliability", 2, entities={"revision": "rev-abc"})
    b = _f("deployment", 3, entities={"revision": "rev-abc"})
    c = _f("access", 4, entities={"revision": "rev-abc"})
    isolated = _f("reliability", 50, entities={"service": "noise"})
    out = aggregate(
        {"reliability": [a, isolated], "deployment": [b], "access": [c]},
        time_window_minutes=5,
    )
    # Cluster of (a, b, c) should come first (3 specialists).
    assert len(out) == 2
    assert len(out[0].supporting_specialists) == 3
    assert len(out[1].supporting_specialists) == 1
