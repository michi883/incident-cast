#!/usr/bin/env bash
# scripts/setup_splunk.sh — provision IncidentCast indexes + HEC on a Splunk
# Enterprise trial. Idempotent: re-running is safe.
#
# Reads connection info from .env (or env vars):
#   SPLUNK_HOST, SPLUNK_PORT (mgmt, default 8089)
#   SPLUNK_USERNAME, SPLUNK_PASSWORD
#   SPLUNK_HEC_URL (default https://localhost:8088)
#
# On success, writes/updates the HEC token in .env as SPLUNK_HEC_TOKEN.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

SPLUNK_HOST="${SPLUNK_HOST:-localhost}"
SPLUNK_PORT="${SPLUNK_PORT:-8089}"
SPLUNK_USERNAME="${SPLUNK_USERNAME:-admin}"
SPLUNK_HEC_URL="${SPLUNK_HEC_URL:-https://localhost:8088}"

if [[ -z "${SPLUNK_PASSWORD:-}" ]]; then
  echo "→ SPLUNK_PASSWORD not set. Add it to .env or export it." >&2
  exit 1
fi

MGMT="https://${SPLUNK_HOST}:${SPLUNK_PORT}"
AUTH=(-sk -u "${SPLUNK_USERNAME}:${SPLUNK_PASSWORD}")
INDEXES=(app_logs app_metrics deploys cloud_audit iam_changes)

echo "→ creating indexes"
for idx in "${INDEXES[@]}"; do
  status=$(curl "${AUTH[@]}" -o /tmp/icast-mkidx.json -w "%{http_code}" \
    -X POST "${MGMT}/services/data/indexes" \
    -d "name=${idx}" -d "datatype=event" || true)
  if [[ "${status}" == "201" ]]; then
    echo "   created  ${idx}"
  elif [[ "${status}" == "409" ]]; then
    echo "   exists   ${idx}"
  else
    echo "   ! unexpected status ${status} for index ${idx}:"
    cat /tmp/icast-mkidx.json; echo
  fi
done

echo "→ pinning ${SPLUNK_USERNAME}'s timezone to UTC"
curl "${AUTH[@]}" -o /dev/null \
  -X POST "${MGMT}/servicesNS/${SPLUNK_USERNAME}/search/admin/user-prefs/general" \
  -d "tz=UTC" >/dev/null || true

echo "→ configuring sourcetypes for JSON auto-extraction"
SOURCETYPES=(access_log app_log cloud_run_deploy iam_binding_change cloud_audit)
for st in "${SOURCETYPES[@]}"; do
  curl "${AUTH[@]}" -o /tmp/icast-st.json \
    -X POST "${MGMT}/servicesNS/nobody/search/configs/conf-props" \
    -d "name=${st}" -d "KV_MODE=json" >/dev/null || true
done

echo "→ enabling HEC (global)"
curl "${AUTH[@]}" -o /tmp/icast-hec-global.json \
  -X POST "${MGMT}/services/data/inputs/http/http" \
  -d "disabled=0" >/dev/null || true

INDEX_LIST=$(IFS=,; echo "${INDEXES[*]}")
TOKEN_NAME="incidentcast"

echo "→ ensuring HEC token '${TOKEN_NAME}'"
get_status=$(curl "${AUTH[@]}" -o /tmp/icast-hec-get.json -w "%{http_code}" \
  "${MGMT}/servicesNS/nobody/splunk_httpinput/data/inputs/http/${TOKEN_NAME}?output_mode=json" || true)

if [[ "${get_status}" == "200" ]]; then
  echo "   token exists; updating allowed indexes"
  curl "${AUTH[@]}" -o /tmp/icast-hec-upd.json \
    -X POST "${MGMT}/servicesNS/nobody/splunk_httpinput/data/inputs/http/${TOKEN_NAME}" \
    -d "indexes=${INDEX_LIST}" -d "index=app_logs" >/dev/null
else
  echo "   creating token"
  curl "${AUTH[@]}" -o /tmp/icast-hec-new.json \
    -X POST "${MGMT}/servicesNS/nobody/splunk_httpinput/data/inputs/http" \
    -d "name=${TOKEN_NAME}" \
    -d "indexes=${INDEX_LIST}" \
    -d "index=app_logs" >/dev/null
fi

TOKEN_VALUE=$(curl "${AUTH[@]}" \
  "${MGMT}/servicesNS/nobody/splunk_httpinput/data/inputs/http/${TOKEN_NAME}?output_mode=json" \
  | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['entry'][0]['content']['token'])")

echo "   token = ${TOKEN_VALUE}"

# Update .env (idempotent: replace or append SPLUNK_HEC_TOKEN line)
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
if grep -q '^SPLUNK_HEC_TOKEN=' .env; then
  # macOS sed needs ''
  sed -i.bak "s|^SPLUNK_HEC_TOKEN=.*|SPLUNK_HEC_TOKEN=${TOKEN_VALUE}|" .env && rm .env.bak
else
  echo "SPLUNK_HEC_TOKEN=${TOKEN_VALUE}" >> .env
fi

echo
echo "✓ Splunk provisioned"
echo "  indexes: ${INDEX_LIST}"
echo "  HEC URL: ${SPLUNK_HEC_URL}"
echo "  HEC token written to .env"
