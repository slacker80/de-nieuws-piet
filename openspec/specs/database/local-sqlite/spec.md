# Spec

## Purpose

Configureert SQLite database voor lokale ontwikkeling met minimale configuratie, connectie lifecycle, connectiviteit, persistentie en een uitvoerbare data-safe rollback/restore op named volume.

## Requirements

### Requirement: SQLite database initialisatie
Het systeem SHALL SQLite database initialiseren met minimale configuratie wanneer applicatie start.

#### Scenario: Database connectiviteit setup
- **Given** applicatie start
- **When** applicatie SQLite database connectiviteit activeert
- **Then** wordt SQLite database geconfigureerd voor connectiviteit en persistentie

### Requirement: Database connectie management
Het systeem SHALL SQLite database connecties beheren met eenvoudige connectie lifecycle.

#### Scenario: Database connectie handling
- **Given** applicatie database requests maakt
- **When** applicatie SQLite database connecties activeert
- **Then** worden connecties correct geopend en gesloten

### Requirement: Database persistentie
Het systeem SHALL SQLite database persistentie garanderen met backend-mounted volume/path.

#### Scenario: Database persistentie verificatie
- **Given** backend container gerecreateerd wordt
- **When** backend container opnieuw gestart wordt
- **Then** blijft SQLite database toegankelijk met persistentie verificatie

### Requirement: Volume identiteit
Het systeem SHALL het SQLite named volume declareren met exacte Docker volume identiteit `nieuws_piet_sqlite_data`, zodat Compose commando's en losse `docker run` commando's altijd naar hetzelfde volume wijzen.

#### Scenario: Volume identiteit zonder Compose project prefix
- **Given** Docker Compose configuratie wordt geladen
- **When** het named volume wordt gedefinieerd met `name: nieuws_piet_sqlite_data`
- **Then** is de daadwerkelijke Docker volume naam exact `nieuws_piet_sqlite_data` (zonder Compose project prefix)
- **And** wordt het volume in de backend gemount op `/app/data`
- **And** staat de database file op `/app/data/news.db`

#### Scenario: Zelfde volume in Compose en losse container
- **Given** een losse `docker run` container het volume mount
- **When** `-v nieuws_piet_sqlite_data:...` wordt gebruikt
- **Then** wordt exact hetzelfde volume gebruikt dat Compose ook gebruikt

### Requirement: Data-safe rollback plan
Het systeem SHALL een uitvoerbare data-safe rollback/restore procedure bieden die onderscheid maakt tussen preserve (volume behouden) en destructive reset (volume verwijderen), met niet-destructieve backup voorafgaand aan elke destructieve actie, backup-integriteitsvalidatie vóór elke destructieve actie, feitelijk uitgevoerde restore voor zowel preserve als destructive pad, en verificatie na herstel. Op het destructive pad geldt de vaste volgorde: backup en integriteitsvalidatie → opt-in `docker compose down -v` → restore in het opnieuw aangemaakte volume → verificatie van integriteit, data-marker en health. Restore vindt nooit vóór `docker compose down -v` plaats.

#### Scenario: Backup vóór elke destructieve actie
- **Given** een destructieve actie op database of volume staat gepland
- **When** de rollback procedure start
- **Then** wordt eerst een niet-destructieve backup naar `./backups` gemaakt buiten het named volume
- **And** wordt die backup gevalideerd met `PRAGMA integrity_check`
- **And** wordt bij een ongeldige backup GEEN enkele destructieve actie uitgevoerd

#### Scenario: Preserve pad zonder volume verlies
- **Given** backend draait met SQLite database in named volume `nieuws_piet_sqlite_data`
- **When** rollback wordt uitgevoerd zonder `-v`
- **Then** wordt backend gestopt, wordt de backup gemaakt vanaf een read-only volume mount, wordt de backup gevalideerd
- **And** wordt `docker compose down` (zonder `-v`) uitgevoerd waarna het volume behouden blijft
- **And** wordt de service herstart met `docker compose up -d --build`
- **And** wordt restore uitgevoerd wanneer `/app/data/news.db` ontbreekt of faalt op integriteit
- **And** worden integriteit en `/health` na herstel geverifieerd

#### Scenario: Destructieve reset met opt-in `docker compose down -v`
- **Given** een bestaande backup bestaat en `PRAGMA integrity_check` op die backup exact `ok` retourneert
- **When** operator expliciet kiest voor volume reset
- **Then** wordt `docker compose down -v` ALLÉN na geslaagde backup en validatie uitgevoerd
- **And** wordt de backup DIRECT NA `docker compose down -v` (dus nooit ervóór) feitelijk teruggezet in het opnieuw aangemaakte volume `nieuws_piet_sqlite_data`
- **And** worden direct daarna integriteit (`PRAGMA integrity_check`), data-marker (ten minste één tabel) en `/health` na herstel geverifieerd

#### Scenario: Opt-in only voor `docker compose down -v`
- **Given** rollback procedure wordt uitgevoerd
- **When** naar `docker compose down -v` wordt gezocht in de standaardprocedure
- **Then** is `docker compose down -v` uitsluitend een expliciete opt-in stap
- **And** is de standaard stap altijd `docker compose down` zonder `-v`

### Requirement: Concrete rollback implementation
Het systeem SHALL de rollback/restore uitvoeren met de volgende exacte identiteit en uitvoerbare commando's:

- **DB rollback named volume**: `nieuws_piet_sqlite_data`
- **Backend mount**: `/app/data`
- **Database file**: `/app/data/news.db`
- **Host backup**: `./backups/news.db.<UTC timestamp>.bak` (buiten het named volume, op de host)

#### Scenario: Backup met read-only bron
- **Given** backend gestopt is en named volume `nieuws_piet_sqlite_data` bestaat
- **When** backup wordt gemaakt
- **Then** wordt volgende exacte shell sequence uitgevoerd:

```bash
set -euo pipefail

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_NAME="news.db.${STAMP}.bak"

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

#### Scenario: Backup integriteitsvalidatie
- **Given** backup `./backups/news.db.<UTC timestamp>.bak` bestaat op de host
- **When** integriteitsvalidatie wordt uitgevoerd
- **Then** wordt de backup read-only geopend en `PRAGMA integrity_check` uitgevoerd
- **And** is exact resultaat `ok` vereist voor elke vervolgactie
- **And** wordt bij elk ander resultaat de procedure afgebroken met exit code ongelijk aan 0

```bash
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

#### Scenario: Preserve herstel met niet-destructieve Compose opdrachten
- **Given** backup gemaakt en gevalideerd is
- **When** preserve rollback wordt uitgevoerd
- **Then** worden de niet-destructieve stappen uitgevoerd:

```bash
# Non-destructive down (volume blijft behouden)
docker compose down

# Service opnieuw starten
docker compose up -d --build
```

#### Scenario: Feitelijk restore van backup naar named volume
- **Given** backend gestopt is en een gevalideerde backup bestaat
- **When** restore wordt uitgevoerd
- **Then** wordt de backup feitelijk teruggezet in het named volume:

```bash
docker compose stop backend

docker run --rm \
  -e BACKUP_NAME="${BACKUP_NAME}" \
  -v nieuws_piet_sqlite_data:/target \
  -v "$(pwd)/backups":/backup:ro \
  alpine:3.20 sh -c 'set -eu; cp "/backup/${BACKUP_NAME}" /target/news.db'
```

#### Scenario: Destructieve reset na geldige backup
- **Given** backup bestaat en validatie retourneert exact `ok`
- **When** operator expliciet `docker compose down -v` kiest
- **Then** wordt volgende exacte sequence uitgevoerd:

```bash
# ALLEEN opt-in, ALLÉN na geslaagde backup + integriteitsvalidatie
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
```

#### Scenario: Verificatie na herstel
- **Given** service herstart is na backup, restore of preserve
- **When** verificatie na herstel wordt uitgevoerd
- **Then** worden database integriteit (`PRAGMA integrity_check`), data-marker (ten minste één tabel) en de health endpoint geverifieerd:

```bash
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

**Note:** Alle commando's gebruiken uitsluitend `docker compose`, `docker`, `curl` en standaard shell. Geen accounts, geen betaalde diensten, geen externe API's en geen runtime externe services. De enige publieke netwerkafhankelijkheid is het eenmalig pullen van publieke OCI images (bijv. `alpine:3.20` en de backend/Node basisbeelden) uit een publieke registry: dat is uitsluitend een bootstrap-afhankelijkheid, geen runtime-afhankelijkheid, geen account, geen kost en geen externe dienst — na de eerste pull zijn de beelden lokaal beschikbaar. Er wordt geen digest gepind zolang de feitelijke digest niet bekend is; images worden bij tag geadresseerd (`alpine:3.20`).

(End of file - total 218 lines)