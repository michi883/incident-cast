"""JSON-emitting Splunk introspection helper for the in-app Settings panel.

The Next.js admin API routes shell out to this (it reuses the SDK client's TLS/auth + the
case's authored SPL), so the browser never talks to Splunk directly. Two subcommands, both
print a single JSON object to stdout:

    python -m scripts.splunk_admin status
        → {reachable, host, web_url, indexes:[{name,count}], error?}

    python -m scripts.splunk_admin query --name <query_name> [--case <case.yaml>]
        → {ok, name, spl, earliest, latest, sid, count, rows, error?}

    python -m scripts.splunk_admin mcp-query --name <query_name> [--case <case.yaml>]
        → {ok, backend:"mcp", tool_name, source, name, spl, earliest, latest,
           count, rows, executed_at, sid, error?}

`query` runs the SPL directly via the Splunk SDK; `mcp-query` runs the *same* owned SPL at
runtime through the **Splunk MCP Server**'s ``splunk_run_query`` tool — a real Splunk AI
capability invocation, not a fixture replay. Both only run a query the case's specialists
actually own (validated against the repertoire), so there is no free-form SPL execution path.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

# Indexes provisioned by scripts/setup_splunk.sh (the scenario's data lands here).
SCENARIO_INDEXES = ["app_logs", "app_metrics", "deploys", "cloud_audit", "iam_changes"]

DEFAULT_CASE = REPO_ROOT / "data" / "cases" / "cloud_run_secret_loss.yaml"


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))


def _service():
    """A connected splunklib Service, reusing the SDK client's env + TLS handling."""
    from incidentcast.splunk.sdk_client import SplunkSDKQueryClient

    client = SplunkSDKQueryClient()
    return client._connect(), client


def _read_rows(stream) -> list[dict]:
    import splunklib.results as splunk_results

    raw = stream.read() if hasattr(stream, "read") else stream
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    rows: list[dict] = []
    for item in splunk_results.JSONResultsReader(io.BytesIO(raw)):
        if isinstance(item, dict):
            rows.append(item)
    return rows


def cmd_status() -> None:
    import os

    host = os.environ.get("SPLUNK_HOST", "localhost")
    web_url = f"http://{host}:8000"
    try:
        svc, _ = _service()
    except Exception as e:  # noqa: BLE001 — surface any connect failure to the UI
        _emit({"reachable": False, "host": host, "web_url": web_url, "indexes": [], "error": str(e)})
        return

    counts: dict[str, int] = {idx: 0 for idx in SCENARIO_INDEXES}
    try:
        where = " OR ".join(f"index={idx}" for idx in SCENARIO_INDEXES)
        spl = f"| tstats count where {where} by index"
        body = svc.jobs.oneshot(spl, earliest_time="0", latest_time="now", output_mode="json", count=0)
        for r in _read_rows(body):
            name = r.get("index")
            if name in counts:
                counts[name] = int(r.get("count", 0))
    except Exception as e:  # noqa: BLE001
        _emit({
            "reachable": True, "host": host, "web_url": web_url,
            "indexes": [{"name": n, "count": c} for n, c in counts.items()],
            "error": f"index count query failed: {e}",
        })
        return

    _emit({
        "reachable": True,
        "host": host,
        "web_url": web_url,
        "indexes": [{"name": n, "count": counts[n]} for n in SCENARIO_INDEXES],
    })


def _find_template(case_path: Path, name: str):
    from incidentcast.cli import ALL_SPECS
    from incidentcast.replay import load_case

    case = load_case(case_path)
    for spec_name in case.specialists:
        spec = ALL_SPECS.get(spec_name)
        if spec is None:
            continue
        for tpl in spec.query_repertoire:
            if tpl.name == name:
                return case, tpl
    return case, None


def cmd_query(name: str, case_path: Path) -> None:
    from incidentcast.replay import _substitute

    case, tpl = _find_template(case_path, name)
    if tpl is None:
        _emit({"ok": False, "error": f"'{name}' is not a query owned by this case's specialists."})
        return

    spl = _substitute(tpl.spl, case.incident)
    earliest, latest = case.incident.earliest, case.incident.latest
    try:
        svc, _ = _service()
        # exec_mode=normal yields a persistent job (sid) the user can open in Splunk Web.
        job = svc.jobs.create(spl, earliest_time=earliest, latest_time=latest, exec_mode="normal")
        for _ in range(150):  # ~30s ceiling
            if job.is_done():
                break
            time.sleep(0.2)
        sid = job.sid
        rows = _read_rows(job.results(output_mode="json", count=100))
        _emit({
            "ok": True, "name": name, "spl": spl, "earliest": earliest, "latest": latest,
            "sid": sid, "count": len(rows), "rows": rows,
        })
    except Exception as e:  # noqa: BLE001
        _emit({"ok": False, "name": name, "spl": spl, "earliest": earliest, "latest": latest, "error": str(e)})


def cmd_mcp_query(name: str, case_path: Path) -> None:
    """Run one owned query at runtime through the Splunk MCP Server's splunk_run_query tool.

    This is the live "Splunk AI capability" path: it opens an MCP session, invokes the MCP
    tool, and returns the rows Splunk produced — distinct from the fixture/SDK replay paths.
    Any failure (MCP unset/unreachable) is reported as ok=false so the UI can fall back to
    captured evidence without breaking the demo.
    """
    import asyncio
    from datetime import datetime, timezone

    from incidentcast.replay import _substitute
    from incidentcast.splunk.mcp_client import SPLUNK_RUN_QUERY, SplunkMCPQueryClient

    case, tpl = _find_template(case_path, name)
    if tpl is None:
        _emit({"ok": False, "backend": "mcp", "error": f"'{name}' is not a query owned by this case's specialists."})
        return

    spl = _substitute(tpl.spl, case.incident)
    earliest, latest = case.incident.earliest, case.incident.latest

    async def _run():
        client = SplunkMCPQueryClient()
        try:
            return await client.run(query_name=name, spl=spl, earliest=earliest, latest=latest)
        finally:
            await client.aclose()

    base = {"backend": "mcp", "name": name, "spl": spl, "earliest": earliest, "latest": latest}
    try:
        result = asyncio.run(_run())
    except Exception as e:  # noqa: BLE001 — surface MCP unset/unreachable to the UI as a fallback
        print(f"Splunk MCP evidence query failed: {e}", file=sys.stderr)
        _emit({"ok": False, **base, "error": str(e)})
        return

    print(f"Splunk MCP evidence query executed: {name} ({len(result.rows)} rows)", file=sys.stderr)
    _emit({
        "ok": True,
        "tool_name": SPLUNK_RUN_QUERY,
        "source": "Splunk MCP Server",
        **base,
        "count": len(result.rows),
        "rows": result.rows[:100],
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "sid": result.job_id,
    })


def main() -> None:
    load_dotenv(str(REPO_ROOT / ".env"))
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    q = sub.add_parser("query")
    q.add_argument("--name", required=True)
    q.add_argument("--case", default=str(DEFAULT_CASE))
    m = sub.add_parser("mcp-query")
    m.add_argument("--name", required=True)
    m.add_argument("--case", default=str(DEFAULT_CASE))
    args = parser.parse_args()

    if args.cmd == "status":
        cmd_status()
    elif args.cmd == "query":
        cmd_query(args.name, Path(args.case))
    elif args.cmd == "mcp-query":
        cmd_mcp_query(args.name, Path(args.case))


if __name__ == "__main__":
    main()
