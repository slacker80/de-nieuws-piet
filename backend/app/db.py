"""SQLite database configuratie, connectie lifecycle en initialisatie (sectie 5).

Ontwerpregels:
* Minimale configuratie: alleen wat de bootstrap nodig heeft; het volledige
  artikel-datamodel volgt in latere wijzigingen (zie design.md).
* Connectie management ZONDER pooling: elke operatie opent een verse connectie
  en sluit die weer af (contextmanager met commit/rollback + close).
* Persistentie via named volume `nieuws_piet_sqlite_data`, backend mount
  `/app/data`, database file `/app/data/news.db`.
* `init_database()` is idempotent: veilig bij elke start opnieuw uit te voeren.
* Classificatie vóór schrijven: een bestaande database wordt allereerst
  **read-only** geclassificeerd op `app_meta.schema_version`; pas daarna volgt
  eventuele DDL/DML. Nieuwere of onbekende versies worden geweigerd zonder één
  schrijfactie (delta-spec `source-catalog`).
* Geen TOCTOU: elke schrijffase neemt een `BEGIN IMMEDIATE`-slot en classificeert
  **opnieuw binnen die transactie**, zodat gelijktijdige starters/migrators niet
  naast elkaar kunnen schrijven op een verouderde classificatie.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Exacte paden (overeenkomstig compose.yaml en de delta-spec database/local-sqlite).
DEFAULT_DB_PATH = "/app/data/news.db"
VOLUME_NAME = "nieuws_piet_sqlite_data"

# Ondersteunde schema-versie (broncatalogus = 2). De classificatie in dit module
# en `app.db_migrate` delen deze constante, zodat bootstrap en migratie nooit
# verschillende grenzen hanteren.
SCHEMA_VERSION = 2

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
        # Delta-spec `source-catalog`: FK-integriteit mag niet afhangen van de
        # standaardwaarde 0 van SQLite, dus elke verse verbinding zet deze PRAGMA.
        connection.execute("PRAGMA foreign_keys=ON")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def read_schema_version(connection: sqlite3.Connection) -> str | None:
    """Leest `app_meta.schema_version`; `None` wanneer tabel of rij ontbreekt.

    Gedeeld met `app.db_migrate`: de bootstrap en de migratie moeten dezelfde
    marker lezen, zodat de bootstrap nooit een bestaande status kan missen.
    """
    try:
        row = connection.execute(
            "SELECT value FROM app_meta WHERE key = ?", ("schema_version",)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return None if row is None else str(row[0])


class MigrationError(RuntimeError):
    """Migratie geweigerd of mislukt; er is niets permanents gewijzigd."""


def classificeer_schema_versie(waarde: str | None) -> str:
    """Vertaalt een gemeten marker naar `leeg`, `v1` of `v2`.

    Elke andere waarde (nieuwer dan `SCHEMA_VERSION` of niet-numeriek) gooit
    hier al een `MigrationError`, zodat de aanroeper vóór die terugval geen enkele
    schrijfactie meer kan uitvoeren. De meldingen zijn exact de meldingen die
    `app.db_migrate` altijd al gebruikte.
    """
    if waarde is None:
        return "leeg"
    try:
        versie = int(waarde)
    except ValueError:
        raise MigrationError("onbekende schema-versie geweigerd") from None
    if versie == 1:
        return "v1"
    if versie == SCHEMA_VERSION:
        return "v2"
    raise MigrationError(f"schema-versie {versie} is nieuwer dan ondersteund")


def classificeer_database(path: str | None = None) -> str:
    """Snelle **read-only** classificatie, vóór elke schrijfactie (momentsnapshot).

    * bestand ontbreekt of is 0 bytes -> `leeg` (bootstrap mag v1 opbouwen);
    * leesbare marker `1`/`2` -> `v1`/`v2`;
    * nieuwer dan `2` of onbekend -> `MigrationError` zonder één write;
    * onleesbare/corrupte database -> de SQLite-fout zelf, eveneens zonder write.

    Het bestand wordt met `mode=ro` geopend: de classificatie kan dus per
    constructie niets wijzigen (ook geen journal-/shm-sidecar).

    Deze uitslag is een snapshot en niet heilig: tussen dit moment en de
    schrijffase mag een andere actor commit'en. Daarom volgt in `init_database`
    én `migrate()` altijd nog een `classificeer_onder_slot()`-hercheck zodra er
    een `BEGIN IMMEDIATE`-write-lock ligt (TOCTOU-bescherming).
    """
    db_path = path if path is not None else get_db_path()
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        return "leeg"

    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5.0)
    try:
        waarde = read_schema_version(connection)
    finally:
        connection.close()
    return classificeer_schema_versie(waarde)


def classificeer_onder_slot(connection: sqlite3.Connection) -> str:
    """Tweede, beslissende classificatie binnen een gehouden `BEGIN IMMEDIATE`.

    De snelle read-only classificatie is een momentopname en kan verouderd zijn
    zodra een andere starter/migrator ertussen komt (TOCTOU). Deze hercheck draait
    mét het schrijfslot: alle normale SQLite-writers worden daardoor geserialiseerd
    en de uitkomst kan niet meer veranderen tot wij commit'en of rollback'en.

    * `v2` -> aanroeper rolt terug en keert terug als noop;
    * nieuwer/ongekend -> `MigrationError`; de aanroeper rolt terug zonder één write;
    * `leeg`/`v1` -> aanroeper mag binnen dezelfde transactie bootstrappen/migreren.
    """
    return classificeer_schema_versie(read_schema_version(connection))


def _rollback_stil(connection: sqlite3.Connection) -> None:
    """Rol een openstaande transactie terug; negeer een al gesloten transactie."""
    if connection.in_transaction:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass  # de oorspronkelijke fout is leidend


def init_database(path: str | None = None) -> str:
    """Initialiseert de database (minimale configuratie) en retourneert het pad.

    Idempotent: `CREATE TABLE IF NOT EXISTS` maakt herhaalde starts veilig.
    Schrijft uitsluitend naar de database file zelf (geen sidecar-bestanden
    buiten de backend mount).

    Volgorde (delta-spec `source-catalog`, blocker B1): eerst wordt de database
    read-only geclassificeerd; pas daarna volgt DDL/DML.

    * `v2` -> direct terug, **geen enkele** schrijfactie (noop);
    * nieuwer/ongekend -> `MigrationError`, **geen enkele** schrijfactie: er
      draait geen `CREATE TABLE`, er komt geen `bootstrap_marker` bij;
    * `leeg` -> bootstrap: v1-tabellen, data-marker en `schema_version = 1`;
    * `v1` -> alleen de noodzakelijke, contractconforme bootstrap (tabellen en
      data-marker wanneer die ontbreken); de bestaande marker blijft `1`.

    TOCTOU-bescherming (derde blocker): de snelle classificatie is niet heilig.
    De schrijffase neemt eerst een SQLite-write-lock (`BEGIN IMMEDIATE`) en
    classificeert **opnieuw binnen die transactie** vóór de eerste DDL/DML:

    * hercheck `v2` -> `ROLLBACK` en terugkeren, geen persistente write;
    * hercheck nieuwer/ongekend -> `ROLLBACK` + `MigrationError`, geen persistente
      write (ook geen `bootstrap_marker`);
    * hercheck `leeg`/`v1` -> bootstrap onder exact dezelfde beschermde
      transactie, met `schema_version` als laatste stap en atomische rollback.

    Zij-effect van het nemen van een schrijfslot: SQLite mag een **tijdelijk**
    rollback-journal aanmaken dat bij rollback/commit weer verdwijnt. Het
    extern waarneembare contract is: `news.db` byte-identiek, `sqlite_master` en
    rijen ongewijzigd, en geen sidecar die achterblijft.

    De versiemarker wordt nooit overschreven en `migrate()` blijft de
    enige eigenaar van de overgang 1 -> 2. `PRAGMA foreign_keys=ON` in
    `connect()` is connection-lokaal en dus geen persistente schrijfactie.
    """
    db_path = path if path is not None else get_db_path()

    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    # 1. Snelle read-only classificatie: weigert nieuwer/ongekend vóór elke
    #    DDL/DML en slaat de (dure) schrijffase over bij een bestaande v2.
    status = classificeer_database(db_path)
    if status == "v2":
        return db_path

    # 2. Beschermde schrijffase (alleen voor `leeg` en `v1`): eerst het
    #    SQLite-write-lock, dan de verplichte herclassificatie, pas dán DDL/DML.
    #    Handmatige transactie-aansturing (`isolation_level = None`) voorkomt
    #    nested-transactiefouten met Python's eigen impliciete BEGIN.
    with connect(db_path) as connection:
        connection.isolation_level = None
        connection.execute("BEGIN IMMEDIATE")
        try:
            # TOCTOU-hercheck onder het slot: een andere actor kan intussen v2
            # (of nieuwer/ongekend) gecommited hebben.
            status = classificeer_onder_slot(connection)
            if status == "v2":
                connection.execute("ROLLBACK")
                return db_path

            # Minimale configuratie: standaard journal mode (rollback-journal,
            # geen WAL). WAL zou `-shm`/`-wal` sidecar-bestanden nodig hebben,
            # waardoor het read-only openen van een backup (`mode=ro` in de
            # integriteitsvalidatie) zou falen.
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)

            # Data-marker (rollback-verificatie): alleen plaatsen wanneer die
            # ontbreekt; een gezonde database blijft bij een herstart onaangeroerd.
            marker = connection.execute(
                "SELECT value FROM bootstrap_marker WHERE key = ?", ("initialized",)
            ).fetchone()
            if marker is None:
                connection.execute(
                    "INSERT OR REPLACE INTO bootstrap_marker (key, value) VALUES (?, ?)",
                    ("initialized", "nieuws-piet"),
                )

            # Versiemarker: alleen initialiseren wanneer de *slot*-status `leeg`
            # is, zodat een bestaande v1-status bewaard blijft.
            if status == "leeg":
                connection.execute(
                    "INSERT INTO app_meta (key, value) VALUES (?, ?)",
                    ("schema_version", "1"),
                )
            connection.execute("COMMIT")
        except BaseException:
            _rollback_stil(connection)
            raise
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
