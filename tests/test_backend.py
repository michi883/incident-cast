"""Tests for the live-backend materialization path (SDK/MCP via ``QueryInterface``).

These guard the M3 backbone without needing a live Splunk: a fake ``QueryInterface`` stands in
for the SDK/MCP clients, so we can assert that running a case through ``materialize_via_backend``
binds the real returned rows, tags each finding with its backend + job id, substitutes the SPL,
and round-trips the backend label all the way into the assembled replay/deck.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from incidentcast.replay import (
    _select_rows,
    build_replay,
    load_case,
    materialize_via_backend,
)
from incidentcast.specialists.access import ACCESS_SPEC
from incidentcast.specialists.blast_radius import BLAST_RADIUS_SPEC
from incidentcast.specialists.deployment import DEPLOYMENT_SPEC
from incidentcast.specialists.reliability import RELIABILITY_SPEC
from incidentcast.splunk.interface import QueryResult

CASE_PATH = Path("data/cases/cloud_run_secret_loss.yaml")

ALL_SPECS = {
    "reliability": RELIABILITY_SPEC,
    "deployment": DEPLOYMENT_SPEC,
    "blast_radius": BLAST_RADIUS_SPEC,
    "access": ACCESS_SPEC,
}


def _specs_for(case):
    return {name: ALL_SPECS[name] for name in case.specialists}


class FakeQueryClient:
    """A ``QueryInterface`` that returns canned rows and records every call.

    Returns enough rows that any authored ``row_indexes`` stays in range, so the fixture-style
    selection path is exercised (rather than the ``rows[:cap]`` fallback).
    """

    def __init__(self, *, rows_per_query: int = 30, job_id: str | None = "sid-12345"):
        self.rows_per_query = rows_per_query
        self.job_id = job_id
        self.calls: list[dict[str, Any]] = []

    async def run(
        self,
        *,
        query_name: str,
        spl: str,
        earliest: str,
        latest: str,
        params: dict[str, Any] | None = None,
    ) -> QueryResult:
        self.calls.append({"query_name": query_name, "spl": spl, "earliest": earliest, "latest": latest})
        rows = [{"query": query_name, "i": i} for i in range(self.rows_per_query)]
        return QueryResult(spl=spl, earliest=earliest, latest=latest, rows=rows, job_id=self.job_id)


# --------------------------------------------------------------------------- _select_rows


def test_select_rows_honors_in_range_indexes() -> None:
    rows = [{"i": i} for i in range(10)]
    assert _select_rows(rows, [0, 3, 9]) == [{"i": 0}, {"i": 3}, {"i": 9}]


def test_select_rows_clamps_out_of_range_to_cap() -> None:
    # Live data returned fewer rows than the authored indexes expect → fall back to rows[:cap].
    rows = [{"i": i} for i in range(3)]
    assert _select_rows(rows, [0, 13, 14], cap=5) == rows  # all 3, not an IndexError
    assert _select_rows(rows, [0, 13, 14], cap=2) == rows[:2]


def test_select_rows_none_indexes_uses_cap() -> None:
    rows = [{"i": i} for i in range(10)]
    assert _select_rows(rows, None, cap=3) == rows[:3]
    assert _select_rows([], None) == []


# ------------------------------------------------------------- materialize_via_backend


@pytest.fixture()
def case():
    return load_case(CASE_PATH)


def test_materialize_binds_rows_and_backend(case) -> None:
    client = FakeQueryClient()
    by_specialist, ref_by_id = asyncio.run(
        materialize_via_backend(case, _specs_for(case), client, "mcp")
    )

    findings = [f for fs in by_specialist.values() for f in fs]
    assert len(findings) == len(case.findings)
    # One live query per authored finding.
    assert len(client.calls) == len(case.findings)

    for f in findings:
        assert f.backend == "mcp"
        assert f.job_id == "sid-12345"
        assert f.source_rows, "expected real rows bound from the backend"
        # rows came from the fake client, keyed by the query name it was asked for.
        assert all(r["query"] == f.source_query_name for r in f.source_rows)

    # Every authored finding id resolves to a (specialist, index) location.
    assert set(ref_by_id) == {af.id for af in case.findings}


def test_materialize_substitutes_spl(case) -> None:
    client = FakeQueryClient()
    asyncio.run(materialize_via_backend(case, _specs_for(case), client, "sdk"))
    for call in client.calls:
        assert "$" not in call["spl"], f"unsubstituted placeholder in {call['query_name']}: {call['spl']}"
    # The incident window bounds are passed through to the backend.
    assert all(c["earliest"] == case.incident.earliest for c in client.calls)
    assert all(c["latest"] == case.incident.latest for c in client.calls)


def test_backend_round_trips_into_replay(case) -> None:
    client = FakeQueryClient()
    by_specialist, ref_by_id = asyncio.run(
        materialize_via_backend(case, _specs_for(case), client, "sdk")
    )
    replay = build_replay(
        case,
        _specs_for(case),
        findings_by_specialist=by_specialist,
        ref_by_id=ref_by_id,
        backend="sdk",
    )
    assert replay.deck.metadata.backend == "sdk"
    assert replay.deck.metadata.data_kind == "synthetic_splunk"
    deck_findings = [f for sp in replay.deck.specialists for f in sp.findings]
    assert deck_findings and all(f.backend == "sdk" for f in deck_findings)


def test_unknown_query_name_is_rejected(case) -> None:
    # Corrupt one authored finding to cite a non-existent query; materialization must refuse.
    case.findings[0].source_query_name = "nope_not_a_query"
    client = FakeQueryClient()
    with pytest.raises(ValueError, match="unknown query"):
        asyncio.run(materialize_via_backend(case, _specs_for(case), client, "sdk"))
