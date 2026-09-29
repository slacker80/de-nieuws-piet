#!/usr/bin/env bash
# Reproduceerbare Docker Compose acceptatie (sectie 2, taak 2.8).
#
# - Start exact met `docker compose up -d --build` (v2-syntax, nooit `docker-compose`).
# - Controleert uitsluitend `frontend` en `backend`; SQLite is nooit een service.
# - Frontend: http://localhost:3000/        -> exact HTTP 200 én body marker `Nieuws Piet`
#   (NOOIT /health; /health is uitsluitend een backend-endpoint).
# - Backend:  http://localhost:8000/health  -> exact HTTP 200 én JSON `status: healthy`
# - Max 30 attempts, `sleep 1`, `curl --max-time 5`; alleen succes als BEIDE
#   flags `true` zijn, anders exit 1 na de loop.
#
# Gebruik: scripts/compose-acceptance.sh
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Exacte startopdracht (v2-syntax; de v1-syntax `docker-compose` is verboden).
docker compose up -d --build || exit 1

# ==== Exacte readiness loop (copieerbaar, conform spec local-development/setup) ====
#!/bin/bash
# Exacte frontend en backend readiness verificatie (alleen frontend en backend)
set -u

FRONTEND_URL="http://localhost:3000/"
BACKEND_URL="http://localhost:8000/health"
MAX_ATTEMPTS=30
SLEEP_SECONDS=1
CURL_MAX_TIME=5

fetch() {
  local url="$1"
  local response
  response=$(curl -s -w $'\n%{http_code}' --max-time "${CURL_MAX_TIME}" "${url}" 2>/dev/null || true)
  LAST_STATUS=$(printf '%s' "${response}" | tail -n 1)
  LAST_BODY=$(printf '%s' "${response}" | sed '$d')
  [ -n "${LAST_STATUS}" ] || LAST_STATUS="000"
}

FRONTEND_OK=false
BACKEND_OK=false

for i in $(seq 1 "${MAX_ATTEMPTS}"); do
  fetch "${FRONTEND_URL}"
  f_status="${LAST_STATUS}"
  f_body="${LAST_BODY}"
  if [ "${f_status}" = "200" ] && printf '%s' "${f_body}" | grep -q "Nieuws Piet"; then
    FRONTEND_OK=true
  else
    FRONTEND_OK=false
  fi

  fetch "${BACKEND_URL}"
  b_status="${LAST_STATUS}"
  b_body="${LAST_BODY}"
  if [ "${b_status}" = "200" ] && printf '%s' "${b_body}" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"healthy"'; then
    BACKEND_OK=true
  else
    BACKEND_OK=false
  fi

  if [ "${FRONTEND_OK}" = "true" ] && [ "${BACKEND_OK}" = "true" ]; then
    echo "Both frontend and backend are ready"
    exit 0
  fi

  echo "Attempt ${i}/${MAX_ATTEMPTS}: Frontend=${FRONTEND_OK} (${f_status}), Backend=${BACKEND_OK} (${b_status})"
  sleep "${SLEEP_SECONDS}"
done

echo "Error: Frontend or backend not ready after ${MAX_ATTEMPTS} attempts"
exit 1
