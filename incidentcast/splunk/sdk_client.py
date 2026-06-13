"""splunk-sdk-backed implementation of ``QueryInterface`` for M2.

Runs SPL searches against a live Splunk Enterprise instance using the official
``splunklib`` SDK. Wraps the blocking SDK calls in ``asyncio.to_thread`` so the
orchestrator can still drive specialists concurrently.
"""

from __future__ import annotations

import asyncio
import io
import os
from typing import Any

import splunklib.client as splunk_client
import splunklib.results as splunk_results

from .interface import QueryInterface, QueryResult


class SplunkSDKQueryClient(QueryInterface):
    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        scheme: str = "https",
        verify: bool | None = None,
    ):
        self.host = host or os.environ.get("SPLUNK_HOST", "localhost")
        self.port = int(port or os.environ.get("SPLUNK_PORT", "8089"))
        self.username = username or os.environ.get("SPLUNK_USERNAME", "")
        self.password = password or os.environ.get("SPLUNK_PASSWORD", "")
        self.scheme = scheme
        if verify is None:
            verify = os.environ.get("SPLUNK_VERIFY_TLS", "false").lower() in ("1", "true", "yes")
        self.verify = verify
        if not self.username or not self.password:
            raise RuntimeError(
                "SPLUNK_USERNAME / SPLUNK_PASSWORD must be set for the SDK backend."
            )
        self._service: splunk_client.Service | None = None

    def _connect(self) -> splunk_client.Service:
        if self._service is None:
            self._service = splunk_client.connect(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                scheme=self.scheme,
                verify=self.verify,
            )
        return self._service

    def _oneshot(self, *, spl: str, earliest: str, latest: str) -> tuple[list[dict[str, Any]], str | None]:
        svc = self._connect()
        # Splunk requires SPL to start with "search" or "|" / pipe-friendly verb.
        # Our templates already start with "search ...", leave them as-is.
        kwargs = {
            "earliest_time": earliest,
            "latest_time": latest,
            "output_mode": "json",
            "count": 0,  # no row cap
        }
        body = svc.jobs.oneshot(spl, **kwargs)
        raw = body.read() if hasattr(body, "read") else body
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        # JSONResultsReader needs a binary stream.
        rows: list[dict[str, Any]] = []
        for item in splunk_results.JSONResultsReader(io.BytesIO(raw)):
            if isinstance(item, dict):
                rows.append(item)
            # Messages (warnings, diagnostics) are non-dict; ignore for now.
        return rows, None

    async def run(
        self,
        *,
        query_name: str,
        spl: str,
        earliest: str,
        latest: str,
        params: dict[str, Any] | None = None,
    ) -> QueryResult:
        rows, job_id = await asyncio.to_thread(
            self._oneshot, spl=spl, earliest=earliest, latest=latest
        )
        return QueryResult(
            spl=spl, earliest=earliest, latest=latest, rows=rows, job_id=job_id
        )
