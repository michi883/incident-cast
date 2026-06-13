"""Fixture-backed ``QueryInterface`` for M1.

Reads canned ``QueryResult`` payloads from a directory of JSON files keyed by
``query_name``. Lets the entire investigation/aggregation/deck pipeline run
end-to-end without a live Splunk instance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .interface import QueryInterface, QueryResult


class FixtureQueryClient(QueryInterface):
    """Returns canned ``QueryResult``s from ``<fixture_dir>/<query_name>.json``."""

    def __init__(self, fixture_dir: str | Path):
        self.fixture_dir = Path(fixture_dir)
        if not self.fixture_dir.exists():
            raise FileNotFoundError(f"Fixture directory does not exist: {self.fixture_dir}")

    async def run(
        self,
        *,
        query_name: str,
        spl: str,
        earliest: str,
        latest: str,
        params: dict[str, Any] | None = None,
    ) -> QueryResult:
        path = self.fixture_dir / f"{query_name}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"No fixture for query '{query_name}' at {path}. "
                f"Author one to enable this query against the fixture backend."
            )
        payload = json.loads(path.read_text())
        rows = payload.get("rows", [])
        return QueryResult(
            spl=spl,
            earliest=earliest,
            latest=latest,
            rows=rows,
            job_id=payload.get("job_id"),
        )
