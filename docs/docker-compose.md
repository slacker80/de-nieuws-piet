# Docker Compose Documentatie

## Overzicht

Dit document beschrijft de Docker Compose configuratie voor Nieuws Piet, een lokale, mobiele persoonlijke nieuwswebsite. De configuratie volgt de v2 syntax (`docker compose`) en is reproduceerbaar op elke standaard Linux ontwikkelmachine met Docker geïnstalleerd.

## Installatievereisten

### Systeemvereisten

- **Docker**: Versie 20.10 of hoger
- **Docker Compose**: V2 plugin (inclusief met Docker Desktop)
- **Node.js**: >= 20 (voor frontend)
- **Python**: >= 3.10 (voor backend)

### Installatie

#### Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

#### macOS

```bash
brew install --cask docker
open /Applications/Docker.app
```

#### Windows

Download en installeer Docker Desktop van https://www.docker.com/products/docker-desktop/

## Docker Compose Configuratie

### Hoofdcompose.yaml

Het hoofdcompose.yaml bestand bevat de productieopstelling. Het laadt **geen** ontwikkelingsoverrides automatisch.

```yaml
# Nieuws Piet — lokale Docker Compose-opstelling (Compose v2).
#
# Alleen `frontend` en `backend` zijn services; SQLite is NOOIT een service.
# De database staat als bestand /app/data/news.db in de named volume
# `nieuws_piet_sqlite_data` (exacte Docker-volume-identiteit, zonder
# Compose-projectprefix), uitsluitend gemount aan de backend.
#
# Starten:  docker compose up -d --build
# De v1-syntax `docker-compose` is verboden.
# Ontwikkelvariant: docker compose -f compose.yaml -f compose.dev.yaml up -d --build
# (compose.dev.yaml is met opzet géén auto-geladen `compose.override.yaml`,
#  zodat de acceptatie `docker compose up -d --build` productiegedrag houdt.)

services:
  frontend:
    # Next.js build- en run-opzet staat in frontend/Dockerfile
    # (stages: deps -> builder -> runner; zie taak 2.2).
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "127.0.0.1:3000:3000"
    depends_on:
      # Readiness-condition: backend start vóór frontend (take 2.5, ongewijzigd).
      # De /health healthcheck van de backend staat hieronder (taak 4.5);
      # de feitelijke readiness-verificatie gebeurt via de readiness loop.
      backend:
        condition: service_started
    networks:
      - nieuws_piet

  backend:
    # FastAPI-afhankelijkheden komen uit backend/requirements.txt (gepind,
    # ongewijzigd); de startopdracht (`uvicorn app.main:app`) staat als CMD
    # in backend/Dockerfile (zie taak 2.3).
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      # Backend mount /app/data; database file /app/data/news.db (taak 2.4).
      - nieuws_piet_sqlite_data:/app/data
    healthcheck:
      # /health endpoint als Compose health check (sectie 4, taak 4.5).
      # Alleen backend-component; SQLite is onderdeel van ditzelfde contract.
      # python:3.12-slim bevat geen curl, daarom een Python-check op exact
      # HTTP 200 + JSON `status: healthy` (net als de readiness loop).
      test:
        [
          "CMD",
          "python",
          "-c",
          "import json,urllib.request;r=urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4);d=json.load(r);assert r.status==200 and d.get('status')=='healthy',d",
        ]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    networks:
      - nieuws_piet

volumes:
  nieuws_piet_sqlite_data:
    # Exacte volume-identiteit: geen Compose-projectprefix, zodat Compose en
    # losse `docker -v nieuws_piet_sqlite_data:...` commando's hetzelfde volume raken.
    name: nieuws_piet_sqlite_data

networks:
  nieuws_piet:
    name: nieuws_piet_net
    driver: bridge
```

### Ontwikkelingsopstelling (compose.dev.yaml)

De ontwikkelingsopstelling is **expliciet te laden** en wordt **nooit automatisch geladen**. Dit zorgt ervoor dat de acceptatie `docker compose up -d --build` altijd het productiegedrag houdt.

```yaml
# Ontwikkelingsopstelling (taak 2.2) — expliciet laden:
#
#   docker compose -f compose.yaml -f compose.dev.yaml up -d --build
#
# Niet auto-geladen (bewust géén `compose.override.yaml`),
# zodat de acceptatie `docker compose up -d --build` altijd de productieopstelling is.

services:
  frontend:
    build:
      # Dependencies-stage (npm ci uit package-lock.json); de bron komt
      # via de bind mount hieronder de container in.
      target: deps
    command: ["npm", "run", "dev", "--", "-H", "0.0.0.0"]
    volumes:
      - ./frontend:/app
      # Container-lockfile-afhankelijkheden blijven leidend (niet de host-map).
      - /app/node_modules
```

## Service Details

### Frontend Service

- **Naam**: `frontend`
- **Poort**: 3000 (gebonden aan localhost:3000)
- **Build**: Next.js met multi-stage Dockerfile (dependencies -> builder -> runner)
- **Afhankelijkheden**: Backend service (start voorwaarde)
- **Netwerk**: `nieuws_piet`

### Backend Service

- **Naam**: `backend`
- **Poort**: 8000 (gebonden aan localhost:8000)
- **Build**: FastAPI met Python afhankelijkheden uit `backend/requirements.txt`
- **Volumes**: SQLite database volume `nieuws_piet_sqlite_data` gemount op `/app/data`
- **Healthcheck**: `/health` endpoint met Python client, 10s interval, 5s timeout, 5 retries
- **Netwerk**: `nieuws_piet`

### SQLite Database Volume

- **Volume naam**: `nieuws_piet_sqlite_data` (exacte Docker volume identiteit)
- **Mount pad**: `/app/data` in backend container
- **Database file**: `/app/data/news.db`
- **Belangrijk**: SQLite is **nooit** een service; het is backend-volume mounted

## Startup Commando's

### Productieopstelling (aanbevolen voor acceptatie)

```bash
# Start de volledige opstelling met builds
docker compose up -d --build
```

### Ontwikkelingsopstelling

```bash
# Voor ontwikkeling met hot-reload en bind mounts
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

### Readiness Verificatie

Na het starten, voer de readiness verificatie loop uit:

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

## Service Status Controle

### Controleer of services draaien

```bash
# Toon draaiende containers
docker ps

# Controleer frontend
 curl -s http://localhost:3000/ | grep "Nieuws Piet"

# Controleer backend health
curl -s http://localhost:8000/health | jq .
```

### Health Status

- **Frontend**: HTTP 200 met "Nieuws Piet" in body
- **Backend**: HTTP 200 met JSON body met `status: healthy`

## Stoppen en Opruimen

### Stoppen (preserve pad)

```bash
# Stop services, behoud volumes
docker compose down
```

### Stoppen en Volumes Verwijderen (destructive pad)

```bash
# Stop services en verwijder volumes (data verlies!)
docker compose down -v
```

## Data-safe Rollback en Restore

### Overzicht

Het systeem biedt een data-safe rollback/restore procedure met exacte commando's voor zowel preserve (volume behouden) als destructive (volume verwijderen) paden.

### Preserve Pad (volume behouden)

```bash
# 1. Backup maken (niet-destructief)
set -euo pipefail

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_NAME="news.db.${STAMP}.bak"

# Backend stoppen
docker compose stop backend

# Backup directory op de host
mkdir -p backups

# Backup met read-only volume mount
docker run --rm \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v nieuws_piet_sqlite_data:/source:ro \
  -v "$(pwd)/backups":/backup \
  alpine:3.20 sh -c 'set -eu; cp /source/news.db "/backup/${BACKUP_NAME}"'

# Integriteitsvalidatie
docker compose run --rm --no-deps -T \
  --entrypoint python \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v "$(pwd)/backups":/backups:ro \
  backend -c "
import os, sqlite3, sys
path = '/backups/' + os.environ['BACKUP_NAME']
conn = sqlite3.connect('file:' + path + '?mode=ro', uri=True)
row = conn.execute('PRAGMA integrity_check').fetchone()
conn.close()
result = row[0] if row else 'none'
print('integrity_check:', result)
sys.exit(0 if result == 'ok' else 1)
"

# Non-destructive down (volume blijft behouden)
docker compose down

# Service opnieuw starten
docker compose up -d --build

# Restore wanneer `/app/data/news.db` ontbreekt of corrupt is
docker compose stop backend

docker run --rm \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v nieuws_piet_sqlite_data:/target \
  -v "$(pwd)/backups":/backup:ro \
  alpine:3.20 sh -c 'set -eu; cp "/backup/${BACKUP_NAME}" /target/news.db'

# Verificatie na herstel
docker compose exec -i backend python - <<'PY'
import sqlite3, sys

conn = sqlite3.connect('/app/data/news.db')
integrity = conn.execute('PRAGMA integrity_check').fetchone()
tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()
conn.close()

integrity_ok = integrity is not None and integrity[0] == 'ok'
tables_ok = tables is not None and tables[0] > 0
print('integrity_check:', integrity[0] if integrity else 'none', '| tables:', tables[0] if tables else 0)
sys.exit(0 if integrity_ok and tables_ok else 1)
PY

test "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:8000/health)" = "200"
curl -s --max-time 5 http://localhost:8000/health | grep -Eq '"status"[[:space:]]*:[[:space:]]*"healthy"'
```

### Destructive Pad (volume verwijderen)

```bash
# ALLEEN opt-in, ALLEEN na geslaagde backup + integriteitsvalidatie
# Restore volgt DIRECT NA down -v (nooit ervóór) in het opnieuw aangemaakte volume

docker compose down -v

# Volume opnieuw aanmaken door de restore zelf (exact dezelfde volume naam)
docker run --rm \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v nieuws_piet_sqlite_data:/target \
  -v "$(pwd)/backups":/backup:ro \
  alpine:3.20 sh -c 'set -eu; cp "/backup/${BACKUP_NAME}" /target/news.db'

# Starten en verifiëren
docker compose up -d --build

# Verificatie na herstel (zelfde als preserve pad)
```

## Foutopsporing

### Gemeenschappelijke Problemen

1. **Docker niet geïnstalleerd**: Volg de installatie-instructies voor uw platform.
2. **Poortconflicten**: Controleer of poorten 3000 en 8000 vrij zijn.
3. **Volume identiteit**: Zorg ervoor dat het volume `nieuws_piet_sqlite_data` exact is (geen projectprefix).
4. **Docker Compose syntax**: Gebruik altijd `docker compose` (v2), nooit `docker-compose` (v1).

### Readiness Problemen

- **Frontend niet bereikbaar**: Controleer `docker logs frontend`
- **Backend health faalt**: Controleer `docker logs backend`
- **SQLite database ontbreekt**: Controleer volume mount en backend logs

## Mobiele Acceptatie

Voor mobiele acceptatie (360x800 viewport) met Playwright:

```bash
# Installeer dependencies
cd frontend
npm ci

# Installeer lokale browser
npx playwright install chromium

# Voer e2e tests uit
npm run test:e2e
```

### Playwright Test Configuratie

De Playwright tests:
- Gebruiken uitsluitend localhost (geen externe API's)
- Zetten viewport 360x800 vóór navigatie
- Controleren marker "Nieuws Piet", zichtbare nav/main landmarks
- Verifiëren tekst "Nog geen nieuws beschikbaar" en scrollWidth <= clientWidth

## Veelgestelde Vragen

### Waarom is SQLite nooit een service?

SQLite is backend-volume mounted voor data-safe rollback en reproduceerbare tests. Als SQLite een service was, zou het moeilijk te beveiligen en te testen zijn.

### Wat is het verschil tussen `docker compose down` en `docker compose down -v`?

- `docker compose down`: Stopt services, behoudt volumes (preserve pad)
- `docker compose down -v`: Stopt services EN verwijdert volumes (destructive pad)

### Waarom is `compose.dev.yaml` niet automatisch geladen?

Om reproduceerbare acceptatie te garanderen, laadt de productieopstelling (`docker compose up -d --build`) altijd het hoofdcompose.yaml. Ontwikkelingsoverrides moeten expliciet worden geladen.

### Wat als Docker niet beschikbaar is?

Het systeem biedt alternatieve setup instructies in de documentatie voor systemen zonder Docker. Dit omvat directe Python/Next.js installatie en SQLite database setup.

## Referenties

- Docker Compose v2 documentatie: https://docs.docker.com/compose/compose-v2/
- Next.js PWA documentatie: https://nextjs.org/docs/advanced-features/progressive-web-app
- FastAPI documentatie: https://fastapi.tiangolo.com/
- Playwright documentatie: https://playwright.dev/

## Geschiedenis

- **Versie 1.0**: Eerste release met volledige Docker Compose configuratie
- **Versie 1.1**: Toegevoegd healthcheck en readiness verificatie
- **Versie 1.2**: Toegevoegd data-safe rollback/restore documentatie
- **Versie 1.3**: Toegevoegd mobiele acceptatie instructies

---

*Docker Compose documentatie gegenereerd door OpenSpec bootstrap-local-news-dashboard change*