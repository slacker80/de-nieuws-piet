# Spec

## Purpose

Vestigt de complete lokale ontwikkelomgeving met Docker Compose, Next.js PWA, FastAPI backend en SQLite database voor het persoonlijke nieuwssite-project.

## Requirements

### Requirement: Docker Compose configuratie
Het systeem SHALL een Docker Compose configuratie bevatten die alle applicatieservices met hun afhankelijkheden en netwerken definieert.

#### Scenario: Docker Compose service definitie
- **Given** Docker Compose geïnitialiseerd wordt
- **When** Docker Compose configuratie wordt geladen
- **Then** worden alle vereiste services (frontend, backend) gedefinieerd met juiste poorttoewijzingen en service afhankelijkheden
- **And** wordt het SQLite named volume gedeclareerd met `name: nieuws_piet_sqlite_data` zodat volume identiteit exact is

### Requirement: Docker Compose acceptatie
Het systeem SHALL reproduceerbare Compose acceptatie bieden met exacte `docker compose` commando's, service namen, frontend/backend URLs/ports, readiness conditions en curl/assertie commando's.

#### Scenario: Docker Compose acceptatie
- **Given** Docker Compose startup wordt uitgevoerd
- **When** `docker compose up -d --build` wordt uitgevoerd
- **Then** worden frontend en backend services gestart met exacte service namen, poorttoewijzingen (frontend:3000, backend:8000), readiness conditions en curl/assertie commando's voor verificatie

**Note:** Compose acceptatie is implementatie-neutral maar concreet en actionable. SQLite is backend-volume mounted, niet een aparte service. Alle Compose commando's gebruiken de v2 syntax `docker compose`; de v1 syntax `docker-compose` is verboden.

### Requirement: Exact compose command
Het systeem SHALL exact `docker compose up -d --build` gebruiken voor start, herstart na wijzigingen en als precondition voor readiness verificatie, en dit commando EXCLUSIEF laten starten op frontend en backend services.

#### Scenario: Exact compose command
- **Given** Docker Compose startup wordt uitgevoerd
- **When** het exacte startcommando wordt uitgevoerd
- **Then** wordt `docker compose up -d --build` gebruikt
- **And** worden volgende services gestart:
  - `frontend` service op poort 3000
  - `backend` service op poort 8000
  - SQLite is backend-volume mounted (`nieuws_piet_sqlite_data`), nooit een service

#### Scenario: Consistent commando gebruik
- **Given** services moeten worden gestart of herstart
- **When** het commando wordt opgezocht in de procedure
- **Then** wordt altijd `docker compose up -d --build` gebruikt
- **And** wordt nooit `docker-compose up -d`, `docker compose up -d` zonder `--build` of een andere variatie gebruikt

### Requirement: Frontend en backend readiness verificatie
Het systeem SHALL een copyable shell loop bieden dat frontend en backend onafhankelijk verifieert met exacte HTTP status assertions én body assertions, en dat uitsluitend deze twee services controleert.

#### Scenario: Frontend readiness met status en body assertie
- **Given** Docker Compose startup voltooid is
- **When** readiness verificatie wordt uitgevoerd
- **Then** wordt frontend `http://localhost:3000/` gecontroleerd op exact HTTP status 200 EN body marker `Nieuws Piet`

#### Scenario: Backend readiness met status en body assertie
- **Given** Docker Compose startup voltooid is
- **When** readiness verificatie wordt uitgevoerd
- **Then** wordt backend `http://localhost:8000/health` gecontroleerd op exact HTTP status 200 EN JSON body met `status` waarde `healthy`

#### Scenario: Exacte readiness shell loop
- **Given** Docker Compose startup voltooid is
- **When** readiness verificatie commando wordt uitgevoerd
- **Then** wordt volgende exacte shell loop uitgevoerd:

```bash
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
```

#### Scenario: Alleen frontend en backend worden gecheckt
- **Given** readiness verificatie draait
- **When** naar andere checks wordt gezocht
- **Then** worden uitsluitend frontend en backend gecontroleerd
- **And** is SQLite nooit een service en wordt deze niet gecheckt
- **And** wordt de loop alleen succesvol als BEIDE flags `true` zijn
- **And** wordt na 30 mislukte pogingen exit code 1 geretourneerd

**Note:** Max 30 attempts, `sleep 1`, `curl --max-time 5`. Frontend wordt gecheckt op HTTP 200 exact én marker-tekst in de body; backend op HTTP 200 exact én JSON body `status: healthy`.

### Requirement: Frontend externe smoke verificatie
Het systeem SHALL een frontend smoke verificatie bieden die uitsluitend de externe frontend URL `http://localhost:3000/` gebruikt en NOOIT `/health`; `/health` is uitsluitend een backend endpoint.

#### Scenario: Frontend smoke via externe URL
- **Given** Docker Compose services draaien
- **When** frontend smoke verificatie wordt uitgevoerd
- **Then** wordt `http://localhost:3000/` geverifieerd op exact HTTP status 200 én marker-tekst `Nieuws Piet` in de body
- **And** wordt `/health` niet gebruikt als frontend controle

#### Scenario: Backend health verificatie apart
- **Given** Docker Compose services draaien
- **When** backend health verificatie wordt uitgevoerd
- **Then** wordt uitsluitend `http://localhost:8000/health` gebruikt

(End of file - total 141 lines)