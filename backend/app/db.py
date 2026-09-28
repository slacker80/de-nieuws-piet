"""SQLite database configuratie, connectie lifecycle en initialisatie (sectie 5).

Ontwerpregels:
* Minimale configuratie: alleen wat de bootstrap nodig heeft; het volledige
  artikel-datamodel volgt in latere wijzigingen (zie design.md).
* Connectie management ZONDER pooling: elke operatie opent een verse connectie
  en sluit die weer af (contextmanager met commit/rollback + close).
* Persistentie via named volume `nieuws_piet_sqlite_data`, backend mount
  `/app/data`, database file `/app/data/news.db`.
* `init_database()` is idempotent: veilig bij elke start opnieuw uit te voeren.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

# Exacte paden (overeenkomstig compose.yaml en de delta-spec database/local-sqlite).
DEFAULT_DB_PATH = "/app/data/news.db"
VOLUME_NAME = "nieuws_piet_sqlite_data"

# Minimale bootstrap-tabel: bewijst connectiviteit/persistentie en levert de
# "data-marker (ten minste één tabel)" die de rollback-verificatie controleert.
SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bootstrap_marker (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
)


def get_db_path() -> str:
    """Databasepad: `APP_DB_PATH` overschrijft de containerstandaard."""
    return os.environ.get("APP_DB_PATH", DEFAULT_DB_PATH)


@contextmanager
def connect(path: str | None = None, *, timeout: float = 5.0) -> Iterator[sqlite3.Connection]:
    """Opent een verse connectie, voert werk uit en sluit die altijd af.

    Geen pooling: bij elke aanroep een nieuwe verbinding, na afloop `close()`.
    Fouten rollback'en de openstaande transactie; successen worden gecommit.
    """
    db_path = path if path is not None else get_db_path()
    connection = sqlite3.connect(db_path, timeout=timeout)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database(path: str | None = None) -> str:
    """Initialiseert de database (minimale configuratie) en retourneert het pad.

    Idempotent: `CREATE TABLE IF NOT EXISTS` maakt herhaalde starts veilig.
    Schrijft uitsluitend naar de database file zelf (geen sidecar-bestanden
    buiten de backend mount).
    """
    db_path = path if path is not None else get_db_path()

    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with connect(db_path) as connection:
        # Minimale configuratie: standaard journal mode (rollback-journal, geen
        # WAL). WAL zou `-shm`/`-wal` sidecar-bestanden nodig hebben, waardoor
        # het read-only openen van een backup (`mode=ro` in de
        # integriteitsvalidatie) zou falen.
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.execute(
            "INSERT OR REPLACE INTO bootstrap_marker (key, value) VALUES (?, ?)",
            ("initialized", "nieuws-piet"),
        )
        connection.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)",
            ("schema_version", "1"),
        )
    return db_path


def read_marker(path: str | None = None) -> str | None:
    """Leest de data-marker terug (persistentieverificatie zonder pooling)."""
    target = path if path is not None else get_db_path()
    with connect(target, timeout=2.0) as connection:
        row = connection.execute(
            "SELECT value FROM bootstrap_marker WHERE key = ?", ("initialized",)
        ).fetchone()
    return row[0] if row else None


def integrity_ok(path: str | None = None) -> bool:
    """`PRAGMA integrity_check` op de database (read-only beoordeling)."""
    target = path if path is not None else get_db_path()
    with connect(target, timeout=2.0) as connection:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    return row is not None and row[0] == "ok"
