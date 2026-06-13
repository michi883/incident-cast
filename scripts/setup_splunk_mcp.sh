#!/usr/bin/env bash
# scripts/setup_splunk_mcp.sh — mint a Splunk auth token with audience=mcp and
# verify the Splunk MCP Server (Splunkbase app 7931) is reachable.
#
# Prereqs:
#   - Splunk MCP Server app installed in Splunk (Splunkbase app 7931)
#   - SPLUNK_USERNAME / SPLUNK_PASSWORD in .env
#   - Token auth enabled in Splunk (admin → tokens) — default in 9.x+
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

SPLUNK_HOST="${SPLUNK_HOST:-localhost}"
SPLUNK_PORT="${SPLUNK_PORT:-8089}"
SPLUNK_USERNAME="${SPLUNK_USERNAME:-admin}"
MCP_URL="${SPLUNK_MCP_URL:-https://${SPLUNK_HOST}:${SPLUNK_PORT}/services/mcp}"

if [[ -z "${SPLUNK_PASSWORD:-}" ]]; then
  echo "→ SPLUNK_PASSWORD not set." >&2
  exit 1
fi

AUTH=(-sk -u "${SPLUNK_USERNAME}:${SPLUNK_PASSWORD}")

echo "→ minting Splunk auth token (audience=mcp) for ${SPLUNK_USERNAME}"
TOKEN_RESP=$(curl "${AUTH[@]}" -X POST \
  "https://${SPLUNK_HOST}:${SPLUNK_PORT}/services/authorization/tokens" \
  -d "name=${SPLUNK_USERNAME}" -d "audience=mcp" -d "output_mode=json")
TOKEN=$(echo "$TOKEN_RESP" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if 'entry' in d:
    print(d['entry'][0]['content'].get('token',''))
else:
    sys.stderr.write(json.dumps(d, indent=2) + '\n')
    sys.exit(1)
")

if [[ -z "${TOKEN}" ]]; then
  echo "→ token creation failed; see response above" >&2
  exit 2
fi
echo "   token len=${#TOKEN}"

echo "→ probing MCP server at ${MCP_URL}"
INIT_RESP=$(curl -sk -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"incidentcast","version":"0.1.0"}}}' \
  "${MCP_URL}")
SERVER_NAME=$(echo "$INIT_RESP" | python3 -c "
import json,sys
try:
    d = json.load(sys.stdin)
    print(d['result']['serverInfo']['name'])
except Exception:
    print('FAILED')
")

if [[ "${SERVER_NAME}" != "Splunk_MCP_Server" ]]; then
  echo "   ✗ MCP server did not initialize cleanly. Response:"
  echo "$INIT_RESP" | head -c 400; echo
  exit 3
fi
echo "   ✓ ${SERVER_NAME} responded to initialize"

# Persist to .env
if [[ ! -f .env ]]; then cp .env.example .env; fi
if grep -q '^SPLUNK_MCP_TOKEN=' .env; then
  sed -i.bak "s|^SPLUNK_MCP_TOKEN=.*|SPLUNK_MCP_TOKEN=${TOKEN}|" .env && rm .env.bak
else
  echo "SPLUNK_MCP_TOKEN=${TOKEN}" >> .env
fi
if ! grep -q '^SPLUNK_MCP_URL=' .env; then
  echo "SPLUNK_MCP_URL=${MCP_URL}" >> .env
fi

echo
echo "✓ Splunk MCP wired"
echo "  URL:   ${MCP_URL}"
echo "  token saved to .env (SPLUNK_MCP_TOKEN)"
