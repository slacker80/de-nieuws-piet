#!/usr/bin/env bash
# Externe frontend smoke verificatie (sectie 4, taak 4.14).
#
# Controleert uitsluitend de FRONTEND via de externe URL http://localhost:3000/
# op exact HTTP 200 én marker-tekst `Nieuws Piet` in de body.
#
# NOOIT /health: /health is uitsluitend een backend-endpoint op
# http://localhost:8000/health en wordt hier niet als frontend controle gebruikt.
#
# Verwacht een draaiende stack (`docker compose up -d --build`).
#
# Gebruik: scripts/frontend-smoke.sh
set -uo pipefail

FRONTEND_URL="http://localhost:3000/"
CURL_MAX_TIME=5

# Ontvang body + status in één request (geen aparte /health-aanroep).
response="$(curl -s -w $'\n%{http_code}' --max-time "${CURL_MAX_TIME}" "${FRONTEND_URL}" 2>/dev/null || true)"
status="$(printf '%s' "${response}" | tail -n 1)"
body="$(printf '%s' "${response}" | sed '$d')"
[ -n "${status}" ] || status="000"

echo "frontend: ${FRONTEND_URL} -> HTTP ${status}"

if [ "${status}" != "200" ]; then
  echo "FOUT: exacte HTTP 200 vereist, kreeg ${status}" >&2
  exit 1
fi

if ! printf '%s' "${body}" | grep -q "Nieuws Piet"; then
  echo "FOUT: marker-tekst 'Nieuws Piet' ontbreekt in de frontend body" >&2
  exit 1
fi

# Bescherming tegen het per ongeluk gebruiken van het backend-endpoint als
# frontend controle: de frontend-URL mag nooit /health zijn.
case "${FRONTEND_URL}" in
  */health*)
    echo "FOUT: frontend smoke mag NOOIT /health gebruiken" >&2
    exit 1
    ;;
esac

echo "OK: frontend smoke geslaagd (HTTP 200 + marker 'Nieuws Piet', geen /health)"
