"""App-start integraal: bootstrap én migratie via de echte lifespan (blocker B1).

`create_app()` binnen een `TestClient` voert de volledige startsequentie uit
(`init_database` gevolgd door `migrate`) op een tijdelijk databasepad. De tests
bewijzen de markerregel uit de delta-spec `source-catalog`:

* een nieuwe/lege database wordt eenmaal op 1 gezet en daarna naar 2 gemigreerd;
* een bestaande versie-2 database start als echte noop (bestand byte-identiek);
* een bestaande nieuwer/ongekende marker wordt vóór `migrate()` niet overschreven
  en levert een weigering zonder één schrijfactie;
* ook een **minimalistische** bestaande database (alleen `app_meta`, geen
  `bootstrap_marker`) wordt vóór elke DDL/DML read-only geclassificeerd: de
  weigering laat `sqlite_master` en de bytes exact zoals ze waren;
* een mislukte migratie laat marker én schema atomair intact.

Alle tests draaien offline onder de socket-guard en raken nooit de echte database.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import connect, init_database, read_schema_version
from app.db_migrate import (
    CATALOG_SCHEMA_STATEMENTS,
    SCHEMA_VERSION,
    MigrationError,
    migrate,
)
from app.main import create_app

pytestmark = pytest.mark.usefixtures("socket_guard")

CATALOG_TABLES = {"sources", "topics", "source_topics", "source_cloud_labels"}


# ==== Hulpmiddelen ===========================================================


def _start(db: str) -> None:
    """Voert de volledige startsequentie van de applicatie uit (lifespan)."""
    with TestClient(create_app(db_path=db)):
        pass


def _start_met_migrate_spy(monkeypatch, db: str) -> tuple[dict, Exception | None]:
    """Start de app en legt vast wélke versiemarker `migrate()` aantreft."""
    from app import main

    origineel = main.migrate
    gezien: dict[str, str | None] = {}

    def _spy(pad: str | None = None) -> str:
        doel = pad if pad is not None else db
        gezien["versie"] = _versie(doel)
        return origineel(pad)

    monkeypatch.setattr("app.main.migrate", _spy)
    fout: Exception | None = None
    try:
        _start(db)
    except Exception as exc:  # noqa: BLE001 - de weigering zelf wordt getoond
        fout = exc
    return gezien, fout


def _versie(db: str) -> str | None:
    with connect(db) as connection:
        return read_schema_version(connection)


def _tabellen(db: str) -> set[str]:
    with connect(db) as connection:
        return {
            rij[0]
            for rij in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }


def _hash(db: str) -> str:
    """SHA-256 van de database file: bewijst of er ook maar één byte veranderde."""
    return hashlib.sha256(Path(db).read_bytes()).hexdigest()


def _snapshot(db: str) -> dict:
    """Volledige statische vingerafdruk: DDL én alle rijen van alle tabellen."""
    with connect(db) as connection:
        ddl = connection.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
        tabellen = [
            rij[0]
            for rij in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        rijen = {
            naam: connection.execute(f"SELECT * FROM {naam} ORDER BY rowid").fetchall()
            for naam in tabellen
        }
    return {"ddl": ddl, "tabellen": tabellen, "rijen": rijen}


def _bestanden(tmp_path) -> list[str]:
    """Bestandsnamen in de testmap (vangt ook journal-/shm-sidecars)."""
    return sorted(pad.name for pad in tmp_path.iterdir())


def _minimale_database(tmp_path, naam: str, versie: str | None = None) -> str:
    """Bestaande database met alléén `app_meta` (geen `bootstrap_marker`)."""
    db = str(tmp_path / naam)
    with connect(db) as connection:
        connection.execute(
            "CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        if versie is not None:
            connection.execute(
                "INSERT INTO app_meta (key, value) VALUES ('schema_version', ?)",
                (versie,),
            )
    return db


def _v1_database(tmp_path, naam: str) -> str:
    db = str(tmp_path / naam)
    init_database(db)
    assert _versie(db) == "1"
    return db


def _zet_marker(db: str, waarde: str) -> None:
    with connect(db) as connection:
        connection.execute(
            "UPDATE app_meta SET value = ? WHERE key = 'schema_version'", (waarde,)
        )


def _bron_toevoegen(db: str) -> None:
    with connect(db) as connection:
        connection.execute(
            "INSERT INTO sources (name, feed_url, feed_url_key, type, language, is_active) "
            "VALUES ('Voorbeeld', 'https://example.com/feed.xml', "
            "'https://example.com/feed.xml', 'rss', 'nl', 1)"
        )


# ==== Nieuwe en bestaande database bij start ================================


def test_start_migreert_nieuwe_database_van_1_naar_2(tmp_path) -> None:
    """B1: een nieuwe database gaat bij de eerste start van 1 naar 2."""
    db = str(tmp_path / "nieuw.db")

    _start(db)

    assert _versie(db) == str(SCHEMA_VERSION) == "2"
    assert CATALOG_TABLES <= _tabellen(db)
    with connect(db) as connection:
        marker = connection.execute(
            "SELECT value FROM bootstrap_marker WHERE key = 'initialized'"
        ).fetchone()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert marker is not None and marker[0] == "nieuws-piet"


def test_bootstrap_zet_marker_op_1_voordat_migrate_draait(tmp_path, monkeypatch) -> None:
    """B1: de bootstrap initialiseert een ontbrekende marker op 1 vóór `migrate`."""
    db = str(tmp_path / "nieuw.db")

    gezien, fout = _start_met_migrate_spy(monkeypatch, db)

    assert fout is None, f"start mocht niet falen: {fout!r}"
    assert gezien["versie"] == "1", "de bootstrap zet een ontbrekende marker op 1"
    assert _versie(db) == str(SCHEMA_VERSION)


def test_start_op_bestaande_versie_1_blijft_en_migreert(tmp_path) -> None:
    """B1: een bestaande v1-marker wordt niet overschreven en wordt gemigreerd."""
    db = _v1_database(tmp_path, "bestaand.db")

    _start(db)

    assert _versie(db) == str(SCHEMA_VERSION)
    assert CATALOG_TABLES <= _tabellen(db)


def test_start_op_bestaande_versie_2_is_byte_identieke_noop(tmp_path, monkeypatch) -> None:
    """B1: herstart van een v2-database laat marker, rijen én bestand ongemoeid."""
    db = _v1_database(tmp_path, "v2.db")
    assert migrate(db) == "migrated"
    _bron_toevoegen(db)
    vooraf = _hash(db)

    gezien, fout = _start_met_migrate_spy(monkeypatch, db)

    assert fout is None, f"start mocht niet falen: {fout!r}"
    assert gezien["versie"] == "2", "init_database mag de v2-marker niet herzetten"
    assert _versie(db) == "2"
    assert _hash(db) == vooraf, "herstart van een v2-database mag niets schrijven"
    with connect(db) as connection:
        rij = connection.execute("SELECT count(*) FROM sources").fetchone()
    assert rij[0] == 1, "bestaande rijen blijven behouden"


# ==== Weigering van nieuwer/ongekend zonder schrijfactie ====================


@pytest.mark.parametrize("versie", ["3", "99", "onbekend"])
def test_start_weigert_nieuwere_of_ongekende_versie_zonder_schrijfactie(
    tmp_path, monkeypatch, versie: str
) -> None:
    """B1: nieuwer/ongekend -> weigering vóór `migrate`; marker en bytes intact."""
    db = _v1_database(tmp_path, f"versie-{versie}.db")
    assert migrate(db) == "migrated"
    _zet_marker(db, versie)
    vooraf = _hash(db)
    snapshot = _snapshot(db)

    gezien, fout = _start_met_migrate_spy(monkeypatch, db)

    assert isinstance(fout, MigrationError), f"verwacht weigering, kreeg {fout!r}"
    assert gezien == {}, "de classificatie moet weigeren vóórdat `migrate` draait"
    assert _versie(db) == versie, "de marker moet ongewijzigd blijven"
    assert _hash(db) == vooraf, "een weigering mag geen enkele byte schrijven"
    assert _snapshot(db) == snapshot, "schema en rijen moeten identiek blijven"
    assert CATALOG_TABLES <= _tabellen(db), "de bestaande schema's blijven staan"


@pytest.mark.parametrize("versie", ["3", "onbekend"])
def test_minimale_app_meta_weigert_zonder_enige_write(tmp_path, versie: str) -> None:
    """B1: bestaande DB met alleen `app_meta` (geen `bootstrap_marker`) -> reject.

    De classificatie gebeurt read-only vóór enige DDL/DML: er komt dus geen
    `bootstrap_marker`-tabel bij, `sqlite_master` blijft identiek en het bestand
    byte-identiek. De app-lifespan faalt met `MigrationError`.
    """
    db = _minimale_database(tmp_path, f"mini-{versie}.db", versie)
    vooraf = _hash(db)
    snapshot = _snapshot(db)
    bestanden_voor = _bestanden(tmp_path)
    assert snapshot["tabellen"] == ["app_meta"]

    with pytest.raises(MigrationError):
        _start(db)

    assert _versie(db) == versie, "de marker moet ongewijzigd blijven"
    assert _hash(db) == vooraf, "de weigering mag geen enkele byte schrijven"
    assert _snapshot(db) == snapshot, "geen enkele tabel/index/rij mag toegevoegd zijn"
    assert "bootstrap_marker" not in _tabellen(db), (
        "de weigering mag geen bootstrap_marker aanmaken"
    )
    assert _bestanden(tmp_path) == bestanden_voor, "geen journal-/shm-sidecar toegestaan"


def test_minimale_app_meta_met_versie_3_bereikt_migrate_niet(tmp_path, monkeypatch) -> None:
    """B1: de weigering gebeurt in `init_database`; `migrate` wordt nooit aangeroepen."""
    db = _minimale_database(tmp_path, "mini-spy.db", "3")

    gezien, fout = _start_met_migrate_spy(monkeypatch, db)

    assert isinstance(fout, MigrationError)
    assert gezien == {}, "init_database weigert read-only vóór `migrate`"


# ==== Minimalistische databases die wél mogen doorgroeien ===================


def test_werkelijk_leeg_bestand_wordt_bij_start_v2(tmp_path) -> None:
    """B1: een bestand van 0 bytes is `leeg` en mag v1 opbouwen + migreren."""
    db = str(tmp_path / "heel_leeg.db")
    Path(db).touch()
    assert Path(db).stat().st_size == 0

    _start(db)

    assert _versie(db) == str(SCHEMA_VERSION) == "2"
    assert CATALOG_TABLES <= _tabellen(db)
    with connect(db) as connection:
        marker = connection.execute(
            "SELECT value FROM bootstrap_marker WHERE key = 'initialized'"
        ).fetchone()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert marker is not None and marker[0] == "nieuws-piet"


def test_minimale_versie_1_krijgt_bootstrap_en_wordt_v2(tmp_path) -> None:
    """B1: ondersteunde v1 mag de contractconforme bootstrap uitvoeren."""
    db = _minimale_database(tmp_path, "mini-v1.db", "1")
    assert _tabellen(db) == {"app_meta"}

    _start(db)

    assert _versie(db) == str(SCHEMA_VERSION)
    assert {"bootstrap_marker"} <= _tabellen(db)
    assert CATALOG_TABLES <= _tabellen(db)
    with connect(db) as connection:
        marker = connection.execute(
            "SELECT value FROM bootstrap_marker WHERE key = 'initialized'"
        ).fetchone()
    assert marker is not None and marker[0] == "nieuws-piet"


def test_minimale_versie_2_blijft_onaangeroerd(tmp_path, monkeypatch) -> None:
    """B1: ook een minimalistische v2-database start als byte-identieke noop."""
    db = _minimale_database(tmp_path, "mini-v2.db", str(SCHEMA_VERSION))
    vooraf = _hash(db)
    snapshot = _snapshot(db)

    gezien, fout = _start_met_migrate_spy(monkeypatch, db)

    assert fout is None, f"start mocht niet falen: {fout!r}"
    assert gezien["versie"] == str(SCHEMA_VERSION), "migrate draait als noop"
    assert _hash(db) == vooraf, "een v2-start mag niets schrijven"
    assert _snapshot(db) == snapshot
    assert "bootstrap_marker" not in _tabellen(db), "noop betekent: niets aanmaken"


# ==== Migratiefout: marker en schema atomisch intact ========================


def test_mislukte_migratie_laat_marker_en_schema_intact_bij_start(
    tmp_path, monkeypatch
) -> None:
    """B1: een fout midden in de migratie rolt volledig terug tijdens de start."""
    db = _v1_database(tmp_path, "kapot.db")
    monkeypatch.setattr(
        "app.db_migrate.CATALOG_SCHEMA_STATEMENTS",
        CATALOG_SCHEMA_STATEMENTS + ("INSERT INTO bestaat_niet (kolom) VALUES (1)",),
    )
    vooraf = _hash(db)

    with pytest.raises(sqlite3.Error):
        _start(db)

    assert _versie(db) == "1", "versie mag pas na succes naar 2 gaan"
    assert _hash(db) == vooraf, "de terugrol mag niets in de database achterlaten"
    assert CATALOG_TABLES & _tabellen(db) == set(), "geen halve tabellen achterlaten"


def test_start_na_mislukte_migratie_is_herstelbaar(tmp_path, monkeypatch) -> None:
    """B1: na een fout start de applicatie opnieuw en migreert alsnog."""
    db = _v1_database(tmp_path, "herstel.db")
    monkeypatch.setattr(
        "app.db_migrate.CATALOG_SCHEMA_STATEMENTS",
        CATALOG_SCHEMA_STATEMENTS + ("INSERT INTO bestaat_niet (kolom) VALUES (1)",),
    )
    with pytest.raises(sqlite3.Error):
        _start(db)
    monkeypatch.undo()

    _start(db)

    assert _versie(db) == str(SCHEMA_VERSION)
    assert CATALOG_TABLES <= _tabellen(db)


# ==== Gedeelde exports en read-only classificatie (niet regressief) ==========


def test_gedeelde_exception_en_versieconstante_zijn_identiek() -> None:
    """B1: `app.db_migrate` deelt `MigrationError`/`SCHEMA_VERSION` met `app.db`."""
    from app import db, db_migrate

    assert db_migrate.MigrationError is db.MigrationError
    assert issubclass(db_migrate.MigrationError, RuntimeError)
    assert db.MigrationError.__module__ == "app.db"
    assert db_migrate.SCHEMA_VERSION is db.SCHEMA_VERSION == 2
    # De imports in dit testmodule blijven dezelfde objecten.
    assert MigrationError is db.MigrationError
    assert SCHEMA_VERSION == db.SCHEMA_VERSION


def test_classificatie_opent_de_database_met_mode_ro_uri(tmp_path, monkeypatch) -> None:
    """B1: de snelle classificatie opent strikt read-only (`mode=ro`-URI)."""
    import sqlite3 as sqlite_module

    from app import db as db_module

    db = str(tmp_path / "ro.db")
    init_database(db)

    verbindingen: list[tuple[object, object]] = []
    origineel = sqlite_module.connect

    def spion(database, *args, **kwargs):
        verbindingen.append((database, kwargs.get("uri")))
        return origineel(database, *args, **kwargs)

    monkeypatch.setattr(sqlite_module, "connect", spion)

    assert db_module.classificeer_database(db) == "v1"

    geopend = [(d, u) for d, u in verbindingen if u]
    assert geopend, "de classificatie moet een URI-connectie openen"
    for database, uri in geopend:
        assert uri is True
        assert str(database).startswith("file:")
        assert "mode=ro" in str(database), "classificatie hoort read-only te openen"
