"""Versiegestuurde, transactionele migratie v1 -> v2 voor de broncatalogus.

Uitvoerbaar als module (naast `python -m app.db_init`):

    python -m app.db_migrate            # standaardpad (/app/data/news.db)
    APP_DB_PATH=/x/news.db python -m app.db_migrate
    python -m app.db_migrate /pad/naar/news.db

Exit codes: 0 = gemigreerd of noop, 1 = fout/weigering.

Gedrag (delta-spec `source-catalog`, taak 1.1 t/m 1.3):
* versie 1 (of ontbrekend op een bootstrap-database) -> migratie;
* versie 2 -> noop: geen enkele schrijfactie;
* versie > 2 of onbekend -> weigering, zonder een enkele schrijfactie;
* alles binnen `BEGIN IMMEDIATE`; `schema_version` gaat pas als laatste stap
  binnen dezelfde transactie naar 2, dus een fout rolt volledig terug.

De classificatie gebeurt, net als in `app.db.init_database`, twee keer: eerst
allereerst read-only (`app.db.classificeer_database`), zodat een weigering plaats
heeft vóór elke verbinding die kan schrijven, en daarna — zodra er een
`BEGIN IMMEDIATE`-write-lock ligt — opnieuw binnen de transactie
(`app.db.classificeer_onder_slot`). Dat sluit de TOCTOU-race uit: een snapshot
van vóór het slot mag nooit tot een write leiden op een inmiddels v2/nieuwere
database.
"""

from __future__ import annotations

import sqlite3
import sys

from .db import (
    SCHEMA_VERSION,
    MigrationError,
    classificeer_database,
    classificeer_onder_slot,
    get_db_path,
)
from .sources_validation import TOPICS

# Additieve DDL voor de broncatalogus. `IF NOT EXISTS` maakt elke herhaling
# veilig; de tabel `app_meta` wordt alleen aangevuld voor het geval de
# migratie op een nog niet geïnitialiseerde database draait (versie schrijven).
CATALOG_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sources (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT    NOT NULL CHECK (length(trim(name)) > 0),
        feed_url      TEXT    NOT NULL,
        feed_url_key  TEXT    NOT NULL,
        website_url   TEXT,
        type          TEXT    NOT NULL CHECK (type IN ('rss', 'atom')),
        language      TEXT    NOT NULL CHECK (language <> '' AND language = lower(language)),
        reliability   INTEGER CHECK (reliability IS NULL
                                     OR (typeof(reliability) = 'integer'
                                         AND reliability BETWEEN 1 AND 5)),
        is_active     INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1))
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_sources_feed_url_key ON sources (feed_url_key)",
    "CREATE INDEX IF NOT EXISTS ix_sources_is_active ON sources (is_active)",
    "CREATE INDEX IF NOT EXISTS ix_sources_website_url ON sources (website_url)",
    """
    CREATE TABLE IF NOT EXISTS topics (
        slug TEXT PRIMARY KEY,
        name TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_topics (
        source_id  INTEGER NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
        topic_slug TEXT    NOT NULL REFERENCES topics (slug),
        PRIMARY KEY (source_id, topic_slug)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_source_topics_slug ON source_topics (topic_slug)",
    """
    CREATE TABLE IF NOT EXISTS source_cloud_labels (
        source_id   INTEGER NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
        cloud_label TEXT    NOT NULL
                        CHECK (cloud_label IN ('azure', 'aws', 't-cloud',
                                               'otc', 'multi-cloud', 'sovereign-cloud')),
        PRIMARY KEY (source_id, cloud_label)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_source_cloud_labels_label ON source_cloud_labels (cloud_label)",
)


def migrate(path: str | None = None) -> str:
    """Voert de migratie v1 -> v2 uit en retourneert `migrated` of `noop`.

    De versie wordt eerst read-only geclassificeerd (snelle weigering/noop) en
    daarna, zodra er een `BEGIN IMMEDIATE`-write-lock ligt, **opnieuw** binnen de
    transactie geclassificeerd: een classificatie van vóór het slot mag nooit
    leiden tot een write op een inmiddels v2/nieuwere database (TOCTOU).
    """
    from .db import connect  # lokaal importeren: `connect` hoort bij db.py

    db_path = path if path is not None else get_db_path()

    # 1. Snelle read-only classificatie: `MigrationError` (nieuwer/ongekend) of
    #    `noop` (v2) vóór elke verbinding die kan schrijven.
    status = classificeer_database(db_path)
    if status == "v2":
        return "noop"

    # 2. Beschermde migratiefase voor `leeg`/`v1`: slot nemen, herclassificeren
    #    en dán pas de additieve DDL uitvoeren.
    with connect(db_path) as connection:
        # Handmatige transactie-aansturing: de versie wordt pas na succes vastgelegd.
        connection.isolation_level = None

        connection.execute("BEGIN IMMEDIATE")
        try:
            # TOCTOU-hercheck onder het slot.
            status = classificeer_onder_slot(connection)
            if status == "v2":
                connection.execute("ROLLBACK")
                return "noop"

            for statement in CATALOG_SCHEMA_STATEMENTS:
                connection.execute(statement)
            for slug, naam in TOPICS:
                connection.execute(
                    "INSERT OR IGNORE INTO topics (slug, name) VALUES (?, ?)",
                    (slug, naam),
                )
            overtredingen = connection.execute("PRAGMA foreign_key_check").fetchall()
            if overtredingen:
                raise MigrationError("foreign_key_check meldt overtredingen")
            # Laatste stap binnen dezelfde transactie: versie na succes.
            connection.execute(
                "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )
            connection.execute("COMMIT")
        except BaseException:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass  # de oorspronkelijke fout is leidend
            raise

    return "migrated"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = args[0] if args else get_db_path()

    try:
        uitkomst = migrate(path)
    except Exception as exc:  # noqa: BLE001 - meldt en sluit af met exit != 0
        print(f"FOUT: migratie mislukt: {exc}", file=sys.stderr)
        return 1

    print(f"database: {path}")
    print(f"schema-versie: {SCHEMA_VERSION}")
    print(f"migratie: {uitkomst}")
    print("OK: broncatalogus-schema aanwezig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
