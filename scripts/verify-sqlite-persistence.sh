#!/usr/bin/env bash
# Persistentie-verificatie voor de SQLite database (sectie 2, taak 2.7).
#
# Bewijst dat /app/data/news.db in named volume `nieuws_piet_sqlite_data`
# (exacte volume-identiteit, zonder Compose-projectprefix) een volledige
# backend-containerherstart overleeft:
#   1. backend-image bouwen (backend/requirements.txt, ongewijzigd)
#   2. marker-database schrijven in /app/data/news.db vanuit een verse container
#   3. volume-identiteit controleren (exact `nieuws_piet_sqlite_data`)
#   4. non-destructieve `docker compose down` (zonder -v: volume blijft)
#   5. in opnieuw opgebouwde containers: PRAGMA integrity_check == ok
#      én de data-marker terugvinden
#
# Data-safe: deze verificatie gebruikt GEEN `docker compose down -v`, raakt geen
# andere volumes en schrijft uitsluitend in de eigen project-volume.
#
# Gebruik: scripts/verify-sqlite-persistence.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

VOLUME="nieuws_piet_sqlite_data"

# Verse container met dezelfde mounts als de backend-service (geen TTY nodig).
run_backend_python() {
  docker compose run --rm --no-deps -T --entrypoint python backend -c "$1"
}

echo "==> 1/4 Backend-image bouwen"
docker compose build backend

echo "==> 2/4 Marker-database schrijven in /app/data/news.db"
run_backend_python '
import sqlite3
path = "/app/data/news.db"
conn = sqlite3.connect(path)
conn.execute(
    "CREATE TABLE IF NOT EXISTS persistence_marker ("
    "k TEXT PRIMARY KEY, v TEXT NOT NULL)"
)
conn.execute(
    "INSERT OR REPLACE INTO persistence_marker VALUES (?, ?)",
    ("bootstrapped", "nieuws-piet"),
)
conn.commit()
conn.close()
print("marker geschreven in", path)
'

echo "==> 3/4 Volume-identiteit controleren (exact, zonder projectprefix)"
actual_volume="$(docker volume inspect "${VOLUME}" --format '{{.Name}}')"
if [ "${actual_volume}" != "${VOLUME}" ]; then
  echo "FOUT: onverwachte volume-naam: ${actual_volume}" >&2
  exit 1
fi
echo "volume: ${actual_volume}"

echo "==> 4/4 Non-destructieve down (docker compose down, GEEN -v) en hercontrole"
docker compose down

run_backend_python '
import sqlite3
import sys

path = "/app/data/news.db"
conn = sqlite3.connect(path)
integrity = conn.execute("PRAGMA integrity_check").fetchone()
row = conn.execute(
    "SELECT v FROM persistence_marker WHERE k = ?", ("bootstrapped",)
).fetchone()
conn.close()

integrity_ok = integrity is not None and integrity[0] == "ok"
marker_ok = row is not None and row[0] == "nieuws-piet"
print(
    "integrity_check:",
    integrity[0] if integrity else "none",
    "| marker:",
    row[0] if row else "ontbreekt",
)
sys.exit(0 if integrity_ok and marker_ok else 1)
'

echo "OK: SQLite persistentie geverifieerd in volume ${VOLUME}"
