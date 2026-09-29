"""Expliciete, lokale en idempotente seed van de officiële startbronnen.

Uitvoerbaar als module (nooit tijdens applicatie-start, nooit als onderdeel
van de schema-migratie):

    python -m app.source_seed             # standaardpad (/app/data/news.db)
    APP_DB_PATH=/x/news.db python -m app.source_seed
    python -m app.source_seed /pad/naar/news.db

Exit codes: 0 = uitgevoerd, 1 = fout.

Gedrag (delta-spec `source-catalog`, taak 6.1 t/m 6.3):
* de starter-set komt uit het in de repo opgenomen `source_seed.json` met
  vooraf handmatig beoordeelde officiële feed-URL's;
* insert-only op `feed_url_key`: ontbrekende starters worden toegevoegd,
  bestaande records (inclusief gebruikerswijzigingen) nooit gewijzigd of
  overschreven;
* volledig offline: er worden geen sockets geopend, geen URL's opgehaald en
  geen DNS-resoluties uitgevoerd.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from .db import connect, get_db_path
from .sources_repository import insert_if_absent
from .sources_validation import (
    SOURCE_FIELDS,
    SourceValidationError,
    validate_source,
    with_defaults,
)

DEFAULT_SEED_FILE = Path(__file__).with_name("source_seed.json")

# Metadata in het seedbestand die naast de catalogusvelden zijn toegestaan.
_METADATA = frozenset({"reviewed"})


class SeedError(RuntimeError):
    """Het seedbestand of de databasestatus staat een seed niet toe."""


def load_seed(path: str | Path | None = None) -> dict[str, Any]:
    """Leest en toetst de structuur van het lokale seedbestand (geen netwerk)."""
    bestand = Path(path) if path is not None else DEFAULT_SEED_FILE
    try:
        inhoud = json.loads(bestand.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SeedError(f"seedbestand ontbreekt: {bestand.name}") from None
    except (OSError, ValueError) as exc:
        raise SeedError(f"seedbestand is niet leesbaar: {bestand.name}") from None

    if not isinstance(inhoud, dict) or not isinstance(inhoud.get("sources"), list):
        raise SeedError("seedbestand mist de lijst `sources`")
    if not inhoud["sources"]:
        raise SeedError("seedbestand bevat geen starters")
    for entry in inhoud["sources"]:
        if not isinstance(entry, dict):
            raise SeedError("seed-entry is geen object")
        onbekend = sorted(set(entry) - set(SOURCE_FIELDS) - _METADATA)
        if onbekend:
            raise SeedError(f"seed-entry bevat onbekende velden: {onbekend}")
        if "reviewed" not in entry:
            raise SeedError("seed-entry mist de handmatige beoordelingsdatum")
    return inhoud


def _payload(entry: Mapping[str, Any]) -> dict[str, Any]:
    return with_defaults({k: entry[k] for k in SOURCE_FIELDS if k in entry})


def seed(
    db_path: str | None = None,
    *,
    seed_file: str | Path | None = None,
    entries: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, list[str]]:
    """Voert de seed uit: alleen ontbrekende starters toevoegen, nooit wijzigen."""
    doel = db_path if db_path is not None else get_db_path()
    bron = list(entries) if entries is not None else load_seed(seed_file)["sources"]

    # Eerst alles valideren: één ongeldige entry mag geen halve seed achterlaten.
    records = [validate_source(_payload(entry)) for entry in bron]

    toegevoegd: list[str] = []
    aanwezig: list[str] = []
    for record in records:
        if insert_if_absent(doel, record):
            toegevoegd.append(record.name)
        else:
            aanwezig.append(record.name)
    return {"added": toegevoegd, "existing": aanwezig}


def _schema_versie(db_path: str) -> str | None:
    try:
        with connect(db_path) as connection:
            try:
                row = connection.execute(
                    "SELECT value FROM app_meta WHERE key = ?", ("schema_version",)
                ).fetchone()
            except sqlite3.OperationalError:
                return None
    except sqlite3.Error as exc:
        raise SeedError("database onbereikbaar") from exc
    return None if row is None else str(row[0])


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    doel = args[0] if args else get_db_path()

    try:
        versie = _schema_versie(doel)
        if versie != "2":
            print(
                "FOUT: de database is niet op schema-versie 2; voer eerst "
                "`python -m app.db_migrate` uit",
                file=sys.stderr,
            )
            return 1
        resultaat = seed(doel)
    except (SeedError, SourceValidationError) as exc:
        print(f"FOUT: seed mislukt: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - meldt en sluit af met exit != 0
        print(f"FOUT: seed mislukt: {exc}", file=sys.stderr)
        return 1

    print(f"database: {doel}")
    print(f"toegevoegd: {len(resultaat['added'])}")
    print(f"reeds aanwezig: {len(resultaat['existing'])}")
    print("OK: seed uitgevoerd (insert-only, offline)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
