"""Read generate.py's stream of HEC payloads from stdin and POST them to Splunk.

Batches into 1000-event POSTs against the HEC ``/services/collector/event``
endpoint. Configurable via env: SPLUNK_HEC_URL, SPLUNK_HEC_TOKEN, SPLUNK_VERIFY_TLS.

Usage:
    python -m data.scenarios.cloud_run_secret_loss.generate \\
      | python -m data.scenarios.cloud_run_secret_loss.ingest
"""

from __future__ import annotations

import json
import os
import sys
from typing import Iterable

import httpx
from dotenv import load_dotenv


BATCH_SIZE = 1000


def _post_batch(client: httpx.Client, url: str, headers: dict[str, str], lines: list[str]) -> None:
    payload = "".join(lines)
    r = client.post(url, content=payload, headers=headers)
    if r.status_code != 200:
        sys.stderr.write(f"HEC POST failed [{r.status_code}]: {r.text}\n")
        r.raise_for_status()


def _chunked(lines: Iterable[str], n: int) -> Iterable[list[str]]:
    buf: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        buf.append(line if line.endswith("\n") else line + "\n")
        if len(buf) >= n:
            yield buf
            buf = []
    if buf:
        yield buf


def main() -> None:
    load_dotenv()
    base = os.environ.get("SPLUNK_HEC_URL", "https://localhost:8088").rstrip("/")
    token = os.environ.get("SPLUNK_HEC_TOKEN", "").strip()
    verify = os.environ.get("SPLUNK_VERIFY_TLS", "false").lower() in ("1", "true", "yes")
    if not token:
        sys.stderr.write(
            "SPLUNK_HEC_TOKEN is empty. Run ./scripts/setup_splunk.sh first.\n"
        )
        sys.exit(2)

    url = f"{base}/services/collector/event"
    headers = {"Authorization": f"Splunk {token}", "Content-Type": "application/json"}

    total = 0
    with httpx.Client(verify=verify, timeout=30.0) as client:
        for batch in _chunked(sys.stdin, BATCH_SIZE):
            _post_batch(client, url, headers, batch)
            total += len(batch)
            sys.stderr.write(f"  posted {total} events…\r")
    sys.stderr.write(f"\n✓ posted {total} events to {base}\n")


if __name__ == "__main__":
    main()
