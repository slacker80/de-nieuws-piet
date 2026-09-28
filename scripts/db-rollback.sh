#!/usr/bin/env bash
# Data-safe rollback/restore voor de SQLite database (sectie 2, taak 2.9).
#
# Exacte identiteit:
#   volume    nieuws_piet_sqlite_data   (named volume, zonder Compose-projectprefix)
#   mount     /app/data                 (backend)
#   database  /app/data/news.db
#   backup    ./backups/news.db.<UTC timestamp>.bak  (host, buiten het named volume)
#
# Vaste regels (data-safe):
#   * Standaard is non-destructief: `docker compose down` (zonder -v).
#   * `docker compose down -v` is uitsluitend opt-in via --allow-volume-removal
#     en draait ALLÉN na geslaagde backup + PRAGMA integrity_check == ok.
#   * Volgorde op het destructive pad: backup -> integriteitsvalidatie ->
#     opt-in `docker compose down -v` -> restore in het opnieuw aangemaakte
#     volume -> verificatie (integriteit, data-marker, /health).
#     Restore staat NOOIT vóór `docker compose down -v`.
#   * De backup wordt altijd read-only geopend (`mode=ro`, `:ro`-mounts); er wordt
#     niets in de backup of in het volume geschreven vóór validatie.
#
# Subcommando's:
#   scripts/db-rollback.sh backup
#       Backend stoppen, niet-destructieve read-only backup maken, valideren.
#   scripts/db-rollback.sh validate [backupnaam]
#       PRAGMA integrity_check op de backup; exact `ok` is vereist.
#   scripts/db-rollback.sh restore [backupnaam]
#       Backup (na validatie) feitelijk terugzetten naar /app/data/news.db.
#   scripts/db-rollback.sh preserve [--data-only]
#       backup (of bestaande backup wanneer de DB ontbreekt/ongeldig is) ->
#       validatie -> `docker compose down` (volume behouden) -> restore wanneer
#       /app/data/news.db ontbreekt of faalt op integriteit, vóórdat de backend
#       die kan initialiseren -> `docker compose up -d --build` -> verificatie.
#   scripts/db-rollback.sh reset --allow-volume-removal [--data-only]
#       Opt-in destructieve reset: backup -> validatie -> `docker compose down -v`
#       -> restore in het opnieuw aangemaakte volume -> verificatie.
#
#   --data-only   TESTOPTIE: sla `docker compose up -d --build` en de
#                 stack-verificatie (`docker compose exec` + /health) over en
#                 verifieer uitsluitend data (integriteit + data-marker).
#                 Bedoeld om de datamechaniek te toetsen wanneer de stack nog
#                 niet volledig kan starten; de standaardpaden verifiëren altijd
#                 integriteit, data-marker én /health.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

VOLUME="nieuws_piet_sqlite_data"
BACKUP_DIR="backups"
ALPINE_IMAGE="alpine:3.20" # tag-adres, geen digest-pin (bootstrap-afhankelijkheid)

MODE=""
BACKUP_ARG=""
ALLOW_VOLUME_REMOVAL=false
DATA_ONLY=false
BACKUP_NAME=""

usage() {
  cat <<'EOF'
Gebruik: scripts/db-rollback.sh <backup|validate|restore|preserve|reset> [opties]

  backup                                        backup maken + valideren
  validate [backupnaam]                         PRAGMA integrity_check (exact ok)
  restore  [backupnaam]                         backup terugzetten (na validatie)
  preserve [--data-only]                        non-destructief pad (volume behouden)
  reset     --allow-volume-removal [--data-only] destructief pad (opt-in)

Vaste volgorde destructive pad:
  backup -> validatie -> opt-in `docker compose down -v` -> restore -> verificatie
EOF
}

die() {
  echo "FOUT: $*" >&2
  exit 1
}

# Nieuwste backup in ./backups (anders exit met melding).
resolve_backup_name() {
  if [ -n "${BACKUP_ARG}" ]; then
    BACKUP_NAME="${BACKUP_ARG}"
  else
    local latest="" f
    for f in "${BACKUP_DIR}"/news.db.*.bak; do
      [ -e "${f}" ] || continue
      if [ -z "${latest}" ] || [ "${f}" -nt "${latest}" ]; then
        latest="${f}"
      fi
    done
    [ -n "${latest}" ] || die "geen backup gevonden in ./${BACKUP_DIR}"
    BACKUP_NAME="$(basename "${latest}")"
  fi
  [ -f "${BACKUP_DIR}/${BACKUP_NAME}" ] || die "backup ontbreekt: ${BACKUP_DIR}/${BACKUP_NAME}"
}

# 1-3. Backend stoppen, backup-directory op de host, niet-destructieve backup
# vanaf een READ-ONLY volume mount. Zet BACKUP_NAME.
make_backup() {
  local stamp
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP_NAME="news.db.${stamp}.bak"

  echo "==> Backend stoppen (geen schrijvers naar de database)"
  docker compose stop backend

  echo "==> Backup-directory op de host, buiten het named volume"
  mkdir -p "${BACKUP_DIR}"

  echo "==> Niet-destructieve backup; bron is READ-ONLY (:ro)"
  docker run --rm \
    -e BACKUP_NAME="${BACKUP_NAME}" \
    -v "${VOLUME}:/source:ro" \
    -v "$(pwd)/${BACKUP_DIR}":/backup \
    "${ALPINE_IMAGE}" sh -c 'set -eu; cp /source/news.db "/backup/${BACKUP_NAME}"'

  echo "backup: ./${BACKUP_DIR}/${BACKUP_NAME}"
}

# Backup read-only openen en `PRAGMA integrity_check` uitvoeren; exact `ok`
# is vereist voor elke vervolgactie. Bij elk ander resultaat: exit != 0.
validate_backup() {
  local name="$1" code
  echo "==> Integriteitsvalidatie van ./${BACKUP_DIR}/${name} (PRAGMA integrity_check)"
  docker compose build backend >/dev/null
  code="$(cat <<'PY'
import os, sqlite3, sys

path = '/backups/' + os.environ['BACKUP_NAME']
try:
    conn = sqlite3.connect('file:' + path + '?mode=ro', uri=True)
    row = conn.execute('PRAGMA integrity_check').fetchone()
    conn.close()
    result = row[0] if row else 'none'
except sqlite3.Error as exc:
    result = 'error: %s' % exc
print('integrity_check:', result)
sys.exit(0 if result == 'ok' else 1)
PY
)"
  docker compose run --rm --no-deps -T \
    --entrypoint python \
    -e BACKUP_NAME="${name}" \
    -v "$(pwd)/${BACKUP_DIR}":/backups:ro \
    backend -c "${code}"
}

# Feitelijke restore: backup terugzetten naar /app/data/news.db in het named
# volume. De backup is AL gecreëerd én gevalideerd in dezelfde uitvoering.
copy_backup_into_volume() {
  local name="$1"
  echo "==> Feitelijk restore naar /app/data/news.db (backupbron read-only)"
  docker compose stop backend
  docker run --rm \
    -e BACKUP_NAME="${name}" \
    -v "${VOLUME}:/target" \
    -v "$(pwd)/${BACKUP_DIR}":/backup:ro \
    "${ALPINE_IMAGE}" sh -c 'set -eu; cp "/backup/${BACKUP_NAME}" /target/news.db'
}

# Data-verificatie in het volume (integriteit + ten minste één tabel),
# uitgevoerd vanuit een verse container.
verify_data() {
  local code
  code="$(cat <<'PY'
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
)"
  echo "==> Verificatie: integriteit + data-marker"
  docker compose run --rm --no-deps -T --entrypoint python backend -c "${code}"
}

# Read-only check of /app/data/news.db bestaat én geldig is (geen creatie bij
# ontbrekend bestand).
db_ok() {
  local code
  code="$(cat <<'PY'
import sqlite3, sys

path = '/app/data/news.db'
try:
    conn = sqlite3.connect('file:' + path + '?mode=ro', uri=True)
    integrity = conn.execute('PRAGMA integrity_check').fetchone()
    conn.close()
except Exception as exc:  # ontbrekend bestand of onleesbaar
    print('db-check gefaald:', exc)
    sys.exit(1)

print('integrity_check:', integrity[0] if integrity else 'none')
sys.exit(0 if integrity and integrity[0] == 'ok' else 1)
PY
)"
  docker compose run --rm --no-deps -T --entrypoint python backend -c "${code}" >/dev/null 2>&1
}

# Volledige verificatie na herstel: integriteit + data-marker + /health.
verify_full() {
  echo "==> Wachten op backend-readiness na herstart (max 30 pogingen, sleep 1, curl --max-time 5)"
  # Dezelfde readiness-conditie als de Compose acceptatie: de backend heeft
  # na `docker compose up -d --build` enige tijd nodig tot /health antwoordt.
  # Zonder deze wachtfase zou de verificatie hieronder racen met de startup.
  local attempt ready=false
  for attempt in $(seq 1 30); do
    if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:8000/health)" = "200" ]; then
      ready=true
      break
    fi
    sleep 1
  done
  if [ "${ready}" != true ]; then
    echo "FOUT: backend /health niet bereikbaar na 30 pogingen" >&2
    return 1
  fi
  echo "==> Verificatie: integriteit + data-marker (docker compose exec) + /health"
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
  echo "/health: HTTP 200 met JSON status: healthy"
}

verify() {
  if [ "${DATA_ONLY}" = true ]; then
    verify_data
  else
    verify_full
  fi
}

start_stack() {
  if [ "${DATA_ONLY}" = false ]; then
    echo "==> Stack (opnieuw) starten: docker compose up -d --build"
    docker compose up -d --build
  fi
}

cmd_backup() {
  make_backup
  validate_backup "${BACKUP_NAME}"
  echo "OK: backup gemaakt en gevalideerd: ./${BACKUP_DIR}/${BACKUP_NAME}"
}

cmd_validate() {
  resolve_backup_name
  validate_backup "${BACKUP_NAME}"
  echo "OK: backup geldig: ./${BACKUP_DIR}/${BACKUP_NAME}"
}

cmd_restore() {
  resolve_backup_name
  validate_backup "${BACKUP_NAME}"
  copy_backup_into_volume "${BACKUP_NAME}"
  verify_data
  echo "OK: backup teruggezet in volume ${VOLUME}: ./${BACKUP_DIR}/${BACKUP_NAME}"
}

cmd_preserve() {
  echo "==== Preserve pad (volume behouden, GEEN -v) ===="

  # Backend-image voor de read-only databeoordeling hieronder (idempotent;
  # cache-hit wanneer het image al bestaat).
  docker compose build backend >/dev/null

  # Stap 1: DB-status beoordelen VÓÓR de backup (read-only, maakt niets aan).
  # Bij een ontbrekende of ongeldige DB is er niets te back-uppen en valt
  # preserve terug op de bestaande backup. Beide uitkomsten worden hieronder
  # gevalideerd vóór elke schrijfactie; bij falen breekt set -e af.
  if db_ok; then
    make_backup
  else
    echo "==> /app/data/news.db ontbreekt of faalt op integriteit: bestaande backup hergebruiken"
    resolve_backup_name
  fi
  validate_backup "${BACKUP_NAME}" # bij falen breekt set -e af: GEEN schrijfactie

  echo "==> Non-destructive down (docker compose down, volume blijft behouden)"
  docker compose down

  # Stap 2: DB-status opnieuw beoordelen NA down en VÓÓR `docker compose up`.
  # De backend initialiseert een ontbrekende database bij startup (taak 5.1);
  # controleren ná de start zou de verse, lege database goedkeuren en de
  # gevalideerde backup nooit terugzetten (stil dataverlies).
  if ! db_ok; then
    echo "==> /app/data/news.db ontbreekt of faalt op integriteit: restore vóór backend-start"
    copy_backup_into_volume "${BACKUP_NAME}"
    verify_data
  fi

  start_stack

  verify
  echo "OK: preserve-pad voltooid (volume ${VOLUME} behouden)"
}

cmd_reset() {
  if [ "${ALLOW_VOLUME_REMOVAL}" != true ]; then
    cat >&2 <<'MSG'
GEWEIGERD: `docker compose down -v` is uitsluitend een expliciete opt-in.

Herhaal het commando met --allow-volume-removal (alléén na geslaagde backup en
PRAGMA integrity_check == ok):
  scripts/db-rollback.sh reset --allow-volume-removal
MSG
    exit 2
  fi

  echo "==== Destructief pad (opt-in: --allow-volume-removal) ===="
  # 1-2. Backup + integriteitsvalidatie: GEEN destructieve actie vóór `ok`.
  make_backup
  validate_backup "${BACKUP_NAME}"

  # 3. Opt-in destructief; uitsluitend ná geslaagde backup + validatie.
  echo "==> Opt-in: docker compose down -v"
  docker compose down -v

  # 4. Restore DIRECT NA down -v (nooit ervóór), in het opnieuw aangemaakte volume.
  copy_backup_into_volume "${BACKUP_NAME}"

  # 5. Verificatie van integriteit, data-marker en health direct na restore.
  start_stack
  verify

  echo "OK: destructieve reset voltooid (backup ./${BACKUP_DIR}/${BACKUP_NAME} hersteld)"
}

# ---- argumenten ----
if [ "$#" -eq 0 ]; then
  usage >&2
  exit 2
fi
MODE="$1"
shift

for arg in "$@"; do
  case "${arg}" in
    --allow-volume-removal) ALLOW_VOLUME_REMOVAL=true ;;
    --data-only) DATA_ONLY=true ;;
    -h | --help)
      usage
      exit 0
      ;;
    --*)
      echo "FOUT: onbekende optie: ${arg}" >&2
      usage >&2
      exit 2
      ;;
    *)
      [ -z "${BACKUP_ARG}" ] || die "te veel argumenten: ${arg}"
      BACKUP_ARG="${arg}"
      ;;
  esac
done

case "${MODE}" in
  backup) cmd_backup ;;
  validate) cmd_validate ;;
  restore) cmd_restore ;;
  preserve) cmd_preserve ;;
  reset) cmd_reset ;;
  -h | --help | help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    echo "FOUT: onbekend subcommando: ${MODE}" >&2
    exit 2
    ;;
esac
