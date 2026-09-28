# Data-Safe Rollback en Restore Documentatie

## Overzicht

Dit document beschrijft de data-safe rollback/restore procedures voor Nieuws Piet. Het dekt alle stappen af voor zowel preserve (volume behouden) als destructive (volume verwijderen) paden met exacte shell commando's, backup-integriteitsvalidatie en feitelijk restore.

## Doel

- Implementeer data-safe rollback/restore met exacte Docker volume identiteit `nieuws_piet_sqlite_data`
- Zorg ervoor dat backup-integriteitsvalidatie vóór elke destructieve actie plaatsvindt
- Implementeer feitelijk restore voor zowel preserve als destructive pad
- Zorg ervoor dat restore DIRECT NA `docker compose down -v` plaatsvindt (nooit ervóór)
- Documenteer exacte shell commando's en volgorde

## Vereisten

### Systeemvereisten

- **Docker**: Versie 20.10 of hoger (Compose v2 plugin)
- **Docker Compose**: V2 plugin (inclusief met Docker Desktop)
- **Bash**: Shell voor script uitvoering
- **Python**: >= 3.10 (voor integriteitsvalidatie)

### Aanbevolen Tools

- **VS Code** met Docker extensie
- **GitHub Desktop** (optioneel) voor Git GUI
- **Postman** of **Insomnia** voor API testing (optioneel)

## Installatie

### 1. Docker Installatie

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y docker.io docker-compose-plugin

# macOS
brew install --cask docker

# Windows
# Download van https://www.docker.com/products/docker-desktop/
```

## Backup en Restore Overzicht

### 1. Volume Identiteit

- **Named Volume**: `nieuws_piet_sqlite_data` (exacte Docker volume identiteit)
- **Backend Mount**: `/app/data`
- **Database File**: `/app/data/news.db`
- **Host Backup**: `./backups/news.db.<UTC timestamp>.bak`

### 2. Backup Process

```bash
# 1. Backend stoppen (geen schrijvers naar de database)
docker compose stop backend

# 2. Backup directory op de host, buiten het named volume
mkdir -p backups

# 3. Niet-destructieve backup; de bron is READ-ONLY (:ro)
docker run --rm \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v nieuws_piet_sqlite_data:/source:ro \
  -v "$(pwd)/backups":/backup \
  alpine:3.20 sh -c 'set -eu; cp /source/news.db "/backup/${BACKUP_NAME}"'
```

### 3. Integriteitsvalidatie

```bash
# Backup integriteitsvalidatie met `PRAGMA integrity_check` (exact `ok`)
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
```

## Preserve Pad (Volume Behouden)

### 1. Preserve Rollback Procedure

```bash
#!/bin/bash
# preserve-rollback.sh

set -euo pipefail

# 1. Backup maken (niet-destructief)
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_NAME="news.db.${STAMP}.bak"

echo "=== Data-Safe Rollback: Preserve Pad ==="
echo "Backup naam: $BACKUP_NAME"

# 2. Backend stoppen
docker compose stop backend

# 3. Backup directory op de host
mkdir -p backups

# 4. Niet-destructieve backup; de bron is READ-ONLY (:ro)
docker run --rm \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v nieuws_piet_sqlite_data:/source:ro \
  -v "$(pwd)/backups":/backup \
  alpine:3.20 sh -c 'set -eu; cp /source/news.db "/backup/${BACKUP_NAME}"'

echo "✓ Backup gemaakt: ./backups/${BACKUP_NAME}"

# 5. Backup integriteitsvalidatie
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

echo "✓ Backup integriteit gevalideerd"

# 6. Non-destructive down (volume blijft behouden)
echo "=== Uitvoeren: Non-destructive down ==="
docker compose down

# 7. Service opnieuw starten
echo "=== Uitvoeren: Service opnieuw starten ==="
docker compose up -d --build

# 8. Restore wanneer `/app/data/news.db` ontbreekt of corrupt is
echo "=== Uitvoeren: Restore ==="
docker compose stop backend

docker run --rm \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v nieuws_piet_sqlite_data:/target \
  -v "$(pwd)/backups":/backup:ro \
  alpine:3.20 sh -c 'set -eu; cp "/backup/${BACKUP_NAME}" /target/news.db'

echo "✓ Restore voltooid"

# 9. Verificatie na herstel
echo "=== Uitvoeren: Verificatie na herstel ==="
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

echo "✓ Verificatie na herstel geslaagd"
echo "=== Preserve rollback voltooid ==="
```

## Destructive Pad (Volume Verwijderen)

### 1. Destructive Reset Procedure

```bash
#!/bin/bash
# destructive-reset.sh

set -euo pipefail

# 1. Backup maken (niet-destructief)
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_NAME="news.db.${STAMP}.bak"

echo "=== Data-Safe Rollback: Destructive Pad ==="
echo "Backup naam: $BACKUP_NAME"

# 2. Backend stoppen
docker compose stop backend

# 3. Backup directory op de host
mkdir -p backups

# 4. Niet-destructieve backup; de bron is READ-ONLY (:ro)
docker run --rm \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v nieuws_piet_sqlite_data:/source:ro \
  -v "$(pwd)/backups":/backup \
  alpine:3.20 sh -c 'set -eu; cp /source/news.db "/backup/${BACKUP_NAME}"'

echo "✓ Backup gemaakt: ./backups/${BACKUP_NAME}"

# 5. Backup integriteitsvalidatie
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

echo "✓ Backup integriteit gevalideerd"

# 6. ALLEEN opt-in, ALLEEN na geslaagde backup + integriteitsvalidatie
echo "=== Uitvoeren: Opt-in destructive reset ==="
echo "WAARSCHUWING: Dit zal het SQLite volume verwijderen!"
echo "Typ 'DELETE' om door te gaan, of Ctrl+C om te annuleren."
read -p "Bevestiging: " confirmation

if [ "$confirmation" != "DELETE" ]; then
    echo "Annuleren: bevestiging niet ontvangen."
    exit 1
fi

# Restore volgt DIRECT NA down -v (nooit ervóór)
echo "=== Uitvoeren: Destructive reset ==="
docker compose down -v

# Volume opnieuw aanmaken door de restore zelf (exact dezelfde volume naam)
echo "=== Uitvoeren: Restore in opnieuw aangemaakte volume ==="
docker run --rm \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v nieuws_piet_sqlite_data:/target \
  -v "$(pwd)/backups":/backup:ro \
  alpine:3.20 sh -c 'set -eu; cp "/backup/${BACKUP_NAME}" /target/news.db'

# Starten en verifiëren
echo "=== Uitvoeren: Service opnieuw starten ==="
docker compose up -d --build

# Verificatie na herstel
echo "=== Uitvoeren: Verificatie na herstel ==="
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

echo "✓ Verificatie na herstel geslaagd"
echo "=== Destructive reset voltooid ==="
```

## Shell Commando Referentie

### 1. Volledige Preserve Rollback

```bash
#!/bin/bash
# Volledige preserve rollback commando

set -euo pipefail

# 1. Backup maken
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_NAME="news.db.${STAMP}.bak"

# 2. Backend stoppen
docker compose stop backend

# 3. Backup directory maken
mkdir -p backups

# 4. Backup maken met read-only volume mount
docker run --rm \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v nieuws_piet_sqlite_data:/source:ro \
  -v "$(pwd)/backups":/backup \
  alpine:3.20 sh -c 'set -eu; cp /source/news.db "/backup/${BACKUP_NAME}"'

# 5. Integriteitsvalidatie
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

# 6. Non-destructive down
docker compose down

# 7. Service opnieuw starten
docker compose up -d --build

# 8. Restore
docker compose stop backend

docker run --rm \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v nieuws_piet_sqlite_data:/target \
  -v "$(pwd)/backups":/backup:ro \
  alpine:3.20 sh -c 'set -eu; cp "/backup/${BACKUP_NAME}" /target/news.db'

# 9. Verificatie na herstel
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

### 2. Volledige Destructive Reset

```bash
#!/bin/bash
# Volledige destructive reset commando

set -euo pipefail

# 1. Backup maken
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_NAME="news.db.${STAMP}.bak"

# 2. Backend stoppen
docker compose stop backend

# 3. Backup directory maken
mkdir -p backups

# 4. Backup maken met read-only volume mount
docker run --rm \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v nieuws_piet_sqlite_data:/source:ro \
  -v "$(pwd)/backups":/backup \
  alpine:3.20 sh -c 'set -eu; cp /source/news.db "/backup/${BACKUP_NAME}"'

# 5. Integriteitsvalidatie
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

# 6. Opt-in destructive reset (vereist bevestiging)
read -p "Type 'DELETE' om het SQLite volume te verwijderen: " confirmation
if [ "$confirmation" != "DELETE" ]; then
    echo "Annuleren: bevestiging niet ontvangen."
    exit 1
fi

docker compose down -v

# 7. Restore in opnieuw aangemaakte volume
docker run --rm \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v nieuws_piet_sqlite_data:/target \
  -v "$(pwd)/backups":/backup:ro \
  alpine:3.20 sh -c 'set -eu; cp "/backup/${BACKUP_NAME}" /target/news.db'

# 8. Service opnieuw starten
docker compose up -d --build

# 9. Verificatie na herstel
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

## Foutopsporing

### 1. Backup Problemen

**Symptom**: `Error response from daemon: driver failed programming external connectivity: mkdir /var/lib/docker/volumes/...: permission denied`

**Oplossing**:

```bash
# Controleer volume permissies
ls -la /var/lib/docker/volumes/

# Maak volume met sudo
docker volume create nieuws_piet_sqlite_data

# Of gebruik bind mount in plaats van named volume
volumes:
  - ./data:/app/data
```

### 2. Integriteitsvalidatie Problemen

**Symptom**: `integrity_check: not ok` of `integrity_check: none`

**Oplossing**:

```bash
# Controleer of backup bestaat
ls -la ./backups/

# Controleer backup bestandsgrootte
ls -lh ./backups/

# Probeer backup opnieuw te maken
# (volg preserve rollback stappen)
```

### 3. Restore Problemen

**Symptom**: `Error: source /backup/news.db.20240115T100000Z.bak not found`

**Oplossing**:

```bash
# Controleer of backup bestaat
ls -la ./backups/

# Controleer of volume bestaat
docker volume ls | grep nieuws_piet_sqlite_data

# Controleer volume mount
docker inspect nieuws_piet_sqlite_data
```

### 4. Verificatie Problemen

**Symptom**: `Error: Connection refused` of `HTTP 000`

**Oplossing**:

```bash
# Controleer of services draaien
docker ps

# Controleer backend status
curl -v http://localhost:8000/health

# Controleer frontend status
curl -v http://localhost:3000
```

## Automatisering

### 1. Cron Job voor Back-up

```bash
# Voeg toe aan crontab
crontab -e

# Voeg deze regel toe voor dagelijkse backup
0 2 * * * /path/to/preserve-rollback.sh
```

### 2. Health Check Script

```bash
#!/bin/bash
# health-check.sh

HEALTH_URL="http://localhost:8000/health"
LOG_FILE="/var/log/health-check.log"

check_health() {
    response=$(curl -s -w "%{http_code}" -o /tmp/health_check.json "$HEALTH_URL")
    status_code=${response: -3}
    
    if [ "$status_code" = "200" ]; then
        echo "$(date): Health check PASSED" >> "$LOG_FILE"
        return 0
    else
        echo "$(date): Health check FAILED - HTTP $status_code" >> "$LOG_FILE"
        return 1
    fi
}

check_health
```

## Snelstartgids

### 1. Preserve Rollback

```bash
# Voer preserve rollback uit
cd /home/peter/git/de-nieuws-piet
./scripts/preserve-rollback.sh
```

### 2. Destructive Reset

```bash
# Voer destructive reset uit (vereist bevestiging)
cd /home/peter/git/de-nieuws-piet
./scripts/destructive-reset.sh
```

### 3. Backup Alleen

```bash
# Maak alleen backup (voor handmatige verificatie)
cd /home/peter/git/de-nieuws-piet
./scripts/backup-only.sh
```

## Ondersteuning

### 1. Problemen

- Open een issue op GitHub
- Geef reproduceerbare stappen
- Voeg logs toe
- Voeg backup bestanden toe

### 2. Documentatie

- Lees deze documentatie
- Controleer backup scripts
- Raadpleeg bijvallen in de code

## Referenties

- Docker volume documentatie: https://docs.docker.com/engine/reference/commandline/volume/
- SQLite documentatie: https://www.sqlite.org/docs.html
- Docker Compose documentatie: https://docs.docker.com/compose/

---

*Data-safe rollback/restore documentatie gegenereerd door OpenSpec bootstrap-local-news-dashboard change*