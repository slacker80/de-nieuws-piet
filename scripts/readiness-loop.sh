#!/bin/bash
# Frontend/backend readiness loop (sectie 8.8; contract uit spec
# local-development/setup: max 30 pogingen, sleep 1, curl --max-time 5).
#
# Controleert uitsluitend frontend `http://localhost:3000/` (exact HTTP 200 én
# body-marker `Nieuws Piet`) en backend `http://localhost:8000/health` (exact
# HTTP 200 én JSON `status: healthy`). SQLite is nooit een service en wordt
# dus niet gecheckt. Alleen succes als BEIDE flags `true` zijn.
#
# Het pad van het tijdelijke responsebestand gaat via de OMGEVING naar Python
# (argv/env), nooit als code in een Python-bronstring: zo blijft de interpolatie
# veilig, ook wanneer het pad spaties of aanhalingstekens bevat.
set -u

MAX_ATTEMPTS=30
SLEEP_SECONDS=1
CURL_MAX_TIME=5

FRONTEND_URL="http://localhost:3000/"
BACKEND_URL="http://localhost:8000/health"

# Responsebestanden: éénmalig aangemaakt vóór de loop en altijd opgeruimd.
frontend_bodyfile="$(mktemp)"
backend_bodyfile="$(mktemp)"
frontend_ready=false
backend_ready=false
frontend_http_code="000"
backend_http_code="000"

cleanup() {
    rm -f "$frontend_bodyfile" "$backend_bodyfile"
}
trap cleanup EXIT

# Backend-body als JSON valideren zonder het pad in code te interpoleren.
backend_body_healthy() {
    BACKEND_BODY_FILE="$backend_bodyfile" python3 - <<'PY'
import json
import os
import sys

try:
    with open(os.environ["BACKEND_BODY_FILE"], encoding="utf-8") as handle:
        payload = json.load(handle)
except Exception:
    sys.exit(1)

sys.exit(
    0
    if isinstance(payload, dict) and payload.get("status") == "healthy"
    else 1
)
PY
}

for ((i = 1; i <= MAX_ATTEMPTS; i++)); do
    frontend_ready=false
    backend_ready=false

    # Frontend: exact HTTP 200 én marker-tekst in de body.
    frontend_http_code="$(curl --connect-timeout 2 --max-time "${CURL_MAX_TIME}" \
        -sS -o "$frontend_bodyfile" -w '%{http_code}' "$FRONTEND_URL" 2>/dev/null || true)"
    if [ "$frontend_http_code" = "200" ] && grep -q "Nieuws Piet" "$frontend_bodyfile"; then
        frontend_ready=true
    fi

    # Backend: exact HTTP 200 én JSON `status: healthy`.
    backend_http_code="$(curl --connect-timeout 2 --max-time "${CURL_MAX_TIME}" \
        -sS -o "$backend_bodyfile" -w '%{http_code}' "$BACKEND_URL" 2>/dev/null || true)"
    if [ "$backend_http_code" = "200" ] && backend_body_healthy; then
        backend_ready=true
    fi

    if [ "$frontend_ready" = true ] && [ "$backend_ready" = true ]; then
        echo "Readiness geslaagd na $i pogingen: zowel frontend als backend zijn toegankelijk"
        exit 0
    fi

    if [ "$i" -eq "$MAX_ATTEMPTS" ]; then
        echo "Fout: Readiness niet bereikt na $MAX_ATTEMPTS pogingen"
        echo "Frontend ready: $frontend_ready (HTTP ${frontend_http_code})"
        echo "Backend ready: $backend_ready (HTTP ${backend_http_code})"
        exit 1
    fi

    echo "Poging $i/$MAX_ATTEMPTS: Frontend ready=$frontend_ready (HTTP ${frontend_http_code}), Backend ready=$backend_ready (HTTP ${backend_http_code}), wachten..."
    sleep "$SLEEP_SECONDS"
done
