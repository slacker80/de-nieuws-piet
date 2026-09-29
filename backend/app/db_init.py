"""Database initialisatiescript (sectie 5, taak 5.2).

Uitvoerbaar als module zodat de backend-container de database kan initialiseren
vóór of tijdens de start, zonder externe afhankelijkheden:

    python -m app.db_init            # standaardpad (/app/data/news.db)
    APP_DB_PATH=/x/news.db python -m app.db_init
    python -m app.db_init /pad/naar/news.db

Exit codes: 0 = geïnitialiseerd, 1 = fout. Het script is idempotent en voert
geen destructieve acties uit (alleen `IF NOT EXISTS` + upsert van de marker).
"""

from __future__ import annotations

import sys

from .db import get_db_path, init_database, integrity_ok, read_marker


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = args[0] if args else get_db_path()

    try:
        init_database(path)
    except Exception as exc:  # noqa: BLE001 - meldt en sluit af met exit != 0
        print(f"FOUT: database initialisatie mislukt: {exc}", file=sys.stderr)
        return 1

    marker = read_marker(path)
    healthy = integrity_ok(path)

    print(f"database: {path}")
    print(f"marker: {marker}")
    print(f"integrity_check: {'ok' if healthy else 'niet-ok'}")

    if not healthy:
        print("FOUT: PRAGMA integrity_check niet 'ok'", file=sys.stderr)
        return 1

    print("OK: database geïnitialiseerd")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
