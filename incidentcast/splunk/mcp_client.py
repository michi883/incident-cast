"""Splunk MCP Server-backed implementation of ``QueryInterface``.

Runs SPL through the official **Splunk MCP Server** (Splunkbase app 7931) by calling its
``splunk_run_query`` tool over an MCP/SSE session — the same surface the agentic specialists
use in ``incidentcast.specialists.runtime._investigate_mcp``. This lets the replay's evidence
be sourced live "via MCP" while the cinematic narrative stays authored.

The MCP session is opened lazily and held open across calls via an ``AsyncExitStack`` (one
``cast`` run issues ~9 queries), and closed with :meth:`aclose`. ``mcp`` is imported lazily so
importing this module never fails when the optional dependency isn't installed (offline/tests).
"""

from __future__ import annotations

import json
import os
from contextlib import AsyncExitStack
from typing import Any

from .interface import QueryInterface, QueryResult

SPLUNK_RUN_QUERY = "splunk_run_query"


class SplunkMCPQueryClient(QueryInterface):
    def __init__(
        self,
        *,
        url: str | None = None,
        token: str | None = None,
        row_limit: int = 200,
        verify: bool | None = None,
    ):
        self.url = (url or os.environ.get("SPLUNK_MCP_URL", "")).strip()
        self.token = (token or os.environ.get("SPLUNK_MCP_TOKEN", "")).strip()
        self.row_limit = row_limit
        # Local Splunk Enterprise serves a self-signed cert; mirror the SDK client's
        # SPLUNK_VERIFY_TLS handling so the SSE/HTTPS connection doesn't fail verification.
        if verify is None:
            verify = os.environ.get("SPLUNK_VERIFY_TLS", "false").lower() in ("1", "true", "yes")
        self.verify = verify
        if not self.url or not self.token:
            raise RuntimeError(
                "SPLUNK_MCP_URL / SPLUNK_MCP_TOKEN must be set for the MCP backend. "
                "Run ./scripts/setup_splunk_mcp.sh."
            )
        self._stack: AsyncExitStack | None = None
        self._session: Any = None

    async def _ensure_session(self) -> Any:
        if self._session is not None:
            return self._session
        # Imported lazily: keeps module import safe without the optional `mcp` dependency.
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        verify = self.verify

        def _client_factory(headers=None, timeout=None, auth=None):  # type: ignore[no-untyped-def]
            return httpx.AsyncClient(
                headers=headers, timeout=timeout, auth=auth, verify=verify, follow_redirects=True
            )

        # The Splunk MCP Server (v1.1.x) speaks the Streamable HTTP transport, not HTTP+SSE.
        self._stack = AsyncExitStack()
        read_stream, write_stream, _ = await self._stack.enter_async_context(
            streamablehttp_client(
                url=self.url,
                headers={"Authorization": f"Bearer {self.token}"},
                httpx_client_factory=_client_factory,
            )
        )
        self._session = await self._stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self._session.initialize()
        return self._session

    async def aclose(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self._session = None

    @staticmethod
    def _parse(tool_result: Any) -> tuple[list[dict[str, Any]], str | None]:
        rows: list[dict[str, Any]] = []
        job_id: str | None = None
        for block in tool_result.content:
            if getattr(block, "type", None) != "text":
                continue
            try:
                payload = json.loads(block.text)
            except (json.JSONDecodeError, AttributeError):
                continue
            if isinstance(payload, dict):
                if "results" in payload and isinstance(payload["results"], list):
                    rows.extend(r for r in payload["results"] if isinstance(r, dict))
                job_id = job_id or payload.get("sid") or payload.get("job_id")
        return rows, job_id

    async def run(
        self,
        *,
        query_name: str,
        spl: str,
        earliest: str,
        latest: str,
        params: dict[str, Any] | None = None,
    ) -> QueryResult:
        session = await self._ensure_session()
        tool_result = await session.call_tool(
            SPLUNK_RUN_QUERY,
            arguments={
                "query": spl,
                "earliest_time": earliest,
                "latest_time": latest,
                "row_limit": self.row_limit,
            },
        )
        rows, job_id = self._parse(tool_result)
        return QueryResult(spl=spl, earliest=earliest, latest=latest, rows=rows, job_id=job_id)
