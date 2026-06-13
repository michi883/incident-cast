#!/usr/bin/env bash
# scripts/demo.sh — build the cinematic investigation replay and open the workspace.
#
#   ./scripts/demo.sh                 # fixture backend, no Splunk required (offline; how judges run it)
#   ./scripts/demo.sh sdk             # evidence pulled live from Splunk via the splunk-sdk
#   ./scripts/demo.sh mcp             # evidence pulled live via the Splunk MCP Server
#   ./scripts/demo.sh mcp my_case     # a different case id (data/cases/<case>.yaml)
#
# For sdk|mcp this provisions Splunk (indexes + HEC, and an MCP token for mcp), ingests the
# scenario's synthetic events, then runs `incidentcast cast`. Re-ingest is skipped if the
# index already has events (set FORCE_INGEST=1 to wipe-and-reload via setup + ingest).
set -euo pipefail

cd "$(dirname "$0")/.."

BACKEND="${1:-fixture}"
CASE="${2:-cloud_run_secret_loss}"
SCENARIO_MOD="data.scenarios.${CASE}"
CASE_YAML="data/cases/${CASE}.yaml"

if [[ ! -f "${CASE_YAML}" ]]; then
  echo "✗ no case at ${CASE_YAML}" >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "→ creating .venv"
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -e ".[dev]"
fi
PY=.venv/bin/python

# ----------------------------------------------------------------------------- live backends
if [[ "${BACKEND}" == "sdk" || "${BACKEND}" == "mcp" ]]; then
  if [[ -f .env ]]; then set -a; source .env; set +a; fi

  # Splunk daemon up?
  if ! curl -sk -o /dev/null "https://${SPLUNK_HOST:-localhost}:${SPLUNK_PORT:-8089}/services/server/info"; then
    echo "✗ Splunk management API not reachable at ${SPLUNK_HOST:-localhost}:${SPLUNK_PORT:-8089}." >&2
    echo "  Start it (e.g. /Applications/Splunk/bin/splunk start) and retry." >&2
    exit 1
  fi

  if [[ ! -f .env ]] || ! grep -q '^SPLUNK_HEC_TOKEN=.\+' .env; then
    echo "→ provisioning Splunk indexes + HEC (one-time)"
    ./scripts/setup_splunk.sh
    set -a; source .env; set +a
  fi
  if [[ "${BACKEND}" == "mcp" ]] && { [[ ! -f .env ]] || ! grep -q '^SPLUNK_MCP_TOKEN=.\+' .env; }; then
    echo "→ wiring Splunk MCP Server token (one-time)"
    ./scripts/setup_splunk_mcp.sh
    set -a; source .env; set +a
  fi

  # Ingest the scenario unless the index already holds events (idempotency guard).
  EVENT_COUNT=$(curl -sk -u "${SPLUNK_USERNAME:-admin}:${SPLUNK_PASSWORD}" \
    --data-urlencode 'search=search index=app_logs | stats count' \
    --data-urlencode 'earliest_time=0' --data-urlencode 'output_mode=json' \
    "https://${SPLUNK_HOST:-localhost}:${SPLUNK_PORT:-8089}/services/search/jobs/export" \
    2>/dev/null | "${PY}" -c "import sys,json
c=0
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    try: c=int(json.loads(line)['result']['count'])
    except Exception: pass
print(c)" 2>/dev/null || echo 0)

  if [[ "${FORCE_INGEST:-0}" == "1" || "${EVENT_COUNT}" == "0" ]]; then
    echo "→ ingesting scenario '${CASE}' into Splunk via HEC"
    "${PY}" -m "${SCENARIO_MOD}.generate" | "${PY}" -m "${SCENARIO_MOD}.ingest"
    echo "→ waiting for Splunk to index events"
    sleep 5
  else
    echo "→ index already populated (${EVENT_COUNT} events); skipping ingest (FORCE_INGEST=1 to reload)"
  fi
fi

# ----------------------------------------------------------------------------- cast the replay
echo "→ casting investigation replay (backend=${BACKEND}) from ${CASE_YAML}"
.venv/bin/incidentcast cast "${CASE_YAML}" --backend "${BACKEND}"

echo
echo "✓ wrote web/public/cases/${CASE}.json (evidence: ${BACKEND})"
echo
echo "Next:"
echo "  cd web && npm install && npm run dev"
echo "  open http://localhost:3000/cases/${CASE}"
