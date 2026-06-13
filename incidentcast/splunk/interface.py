"""Abstract query interface that decouples specialists from a specific Splunk backend.

Three backends implement this interface:
- ``FixtureQueryClient`` (M1): canned responses from JSON files. No Splunk required.
- ``SplunkSDKQueryClient`` (M2): direct ``splunk-sdk`` calls against a live Splunk instance.
- ``SplunkMCPQueryClient`` (M3): routes through the Splunk MCP Server.

Specialists depend only on ``QueryInterface``, so swapping backends does not
require changes to specialist code.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class QueryResult(BaseModel):
    """The materialized result of a single SPL search."""

    spl: str = Field(description="The literal SPL that was executed.")
    earliest: str = Field(description="Earliest time bound (Splunk time modifier).")
    latest: str = Field(description="Latest time bound (Splunk time modifier).")
    rows: list[dict[str, Any]] = Field(default_factory=list)
    job_id: str | None = Field(default=None, description="Splunk job/sid for citation.")


class QueryInterface(Protocol):
    """Anything that can answer a named SPL query."""

    async def run(
        self,
        *,
        query_name: str,
        spl: str,
        earliest: str,
        latest: str,
        params: dict[str, Any] | None = None,
    ) -> QueryResult:
        """Execute ``spl`` against the backend and return a ``QueryResult``.

        ``query_name`` is the canonical name of the owned ``QueryTemplate`` that
        produced this SPL. Backends use it for fixture lookup and for binding
        results back to their template in the deck UI.
        """
        ...
