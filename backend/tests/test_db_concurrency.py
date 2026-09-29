"""Deterministische TOCTOU-/concurrentietests voor bootstrap- en migratiefase.

Het te bewijzen contract (blocker B1, derde ronde): een instantie die de database
read-only als `v1` of `leeg` heeft geclassificeerd mag **niet meer schrijven**
zodra een andere actor intussen `2` (noop) of nieuwer/ongekend (weigering) heeft
gecommit. Daarom classificeren `init_database()` én `migrate()` opnieuw zodra er
een `BEGIN IMMEDIATE`-write-lock ligt, vóór de eerste DDL/DML.

Alle races hieronder zijn deterministisch geforceerd:

* **hooks**: een eenmalige actie van actor B draait precies ná A's snelle
  read-only classificatie en vóór A's schrijffase (A classificeert op de oude
  waarde, B commit't, A hercheckt onder het slot);
* **twee verbindingen**: actor X houdt een écht `BEGIN IMMEDIATE`-slot met een
  ongecommitte markerwijziging; A classificeert eerst, X commit't daarna, en A
  kan het slot pas ná die commit bemachtigen.

Het extern waarneembare contract na afloop: eindmarker en `sqlite_master` kloppen,
er blijft **geen** ongewenste `bootstrap_marker` (of catalogustabel) achter bij een
weigering, `news.db` is byte-identiek ten opzichte van de situatie ná actor B en er
staat geen journal-/shm-sidecar meer naast het bestand.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db as db_module
from app.db import MigrationError, connect, init_database
from app.db_migrate import migrate
from app.main import create_app

pytestmark = pytest.mark.usefixtures("socket_guard")

CATALOG_TABLES = {"sources", "topics", "source_topics", "source_cloud_labels"}


# ==== Hulpmiddelen ===========================================================


def _hash(db: str) -> str:
    return hashlib.sha256(Path(db).read_bytes()).hexdigest()


def _versie(db: str) -> str | None:
    with connect(db) as connection:
        rij = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'schema_version'"
        ).fetchone()
    return None if rij is None else rij[0]


def _tabellen(db: str) -> list[str]:
    with connect(db) as connection:
        return sorted(
            rij[0]
            for rij in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        )


def _snapshot(db: str) -> dict:
    with connect(db) as connection:
        ddl = connection.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
        tabellen = sorted(
            rij[0]
            for rij in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        )
        rijen = {
            naam: connection.execute(f"SELECT * FROM {naam} ORDER BY rowid").fetchall()
            for naam in tabellen
        }
    return {"ddl": ddl, "tabellen": tabellen, "rijen": rijen}


def _bestanden(map_) -> list[str]:
    return sorted(pad.name for pad in Path(map_).iterdir())


def _minimale_database(tmp_path, naam: str, versie: str = "1") -> str:
    """Bestaande database met alléén `app_meta` (geen `bootstrap_marker`)."""
    db = str(tmp_path / naam)
    with connect(db) as connection:
        connection.execute(
            "CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO app_meta (key, value) VALUES ('schema_version', ?)", (versie,)
        )
    return db


def _zet_marker(db: str, waarde: str) -> None:
    with connect(db) as connection:
        connection.execute(
            "UPDATE app_meta SET value = ? WHERE key = 'schema_version'", (waarde,)
        )


def _installeer_race_haak(monkeypatch, actie) -> None:
    """Laat `actie` exact één keer draaien ná A's eerste read-only classificatie.

    De gehaakte lezing retourneert de waarde die **vóór** actor B is gelezen, dus
    A classificeert als `v1`/`leeg` terwijl de database intussen al veranderd is.
    """
    origineel = db_module.read_schema_version
    te_doen = [actie]

    def gehaakt(connection: sqlite3.Connection) -> str | None:
        waarde = origineel(connection)  # momentopname vóór actor B
        if te_doen:
            te_doen.pop()()
        return waarde

    monkeypatch.setattr(db_module, "read_schema_version", gehaakt)


# ==== Race: actor B zet nieuwer/ongekend =====================================


def test_lifespan_weigert_na_race_met_nieuwere_marker(tmp_path, monkeypatch) -> None:
    """A classificeert v1; B commit't `3`; A mag na het slot niet meer schrijven."""
    db = _minimale_database(tmp_path, "race-3.db")
    na_b: dict = {}

    def actor_b() -> None:
        _zet_marker(db, "3")
        na_b["hash"] = _hash(db)
        na_b["snapshot"] = _snapshot(db)

    _installeer_race_haak(monkeypatch, actor_b)
    bestanden_voor = _bestanden(tmp_path)

    with pytest.raises(MigrationError):
        with TestClient(create_app(db_path=db)):
            pass

    assert _versie(db) == "3", "de marker van actor B moet leidend zijn"
    assert _hash(db) == na_b["hash"], "A mag na de race geen enkele byte schrijven"
    assert _snapshot(db) == na_b["snapshot"], "geen tabel/index/rij mag veranderen"
    assert _tabellen(db) == ["app_meta"], "geen ongewenste bootstrap_marker/tabel"
    assert "bootstrap_marker" not in _tabellen(db)
    assert _bestanden(tmp_path) == bestanden_voor, "geen sidecar achterlaten"


def test_migrate_weigert_na_race_met_ongekende_marker(tmp_path, monkeypatch) -> None:
    """Ook de migratiefase herclassificeert onder het slot en rolt dan terug."""
    db = _minimale_database(tmp_path, "race-onbekend.db")
    na_b: dict = {}

    def actor_b() -> None:
        _zet_marker(db, "onbekend")
        na_b["hash"] = _hash(db)
        na_b["snapshot"] = _snapshot(db)

    _installeer_race_haak(monkeypatch, actor_b)

    with pytest.raises(MigrationError):
        migrate(db)

    assert _versie(db) == "onbekend"
    assert _hash(db) == na_b["hash"], "migrate mag na de race niets schrijven"
    assert _snapshot(db) == na_b["snapshot"], "geen catalogustabel mag ontstaan"
    assert _tabellen(db) == ["app_meta"]


# ==== Race: actor B is al naar v2 gegaan =====================================


def test_init_blijft_noop_na_race_waarbij_actor_b_migreert(tmp_path, monkeypatch) -> None:
    """A ziet v1, B migreert naar v2: A voert geen bootstrap meer uit."""
    db = _minimale_database(tmp_path, "race-v2-init.db")
    na_b: dict = {}

    def actor_b() -> None:
        assert migrate(db) == "migrated"
        na_b["hash"] = _hash(db)
        na_b["tabellen"] = _tabellen(db)

    _installeer_race_haak(monkeypatch, actor_b)

    assert init_database(db) == db

    assert _versie(db) == "2"
    assert "bootstrap_marker" not in _tabellen(db), (
        "init mag op een al-gemigreerde database geen bootstrap_marker toevoegen"
    )
    assert _tabellen(db) == na_b["tabellen"]
    assert _hash(db) == na_b["hash"], "de noop-fase mag niets schrijven"


def test_migrate_is_noop_na_race_waarbij_actor_b_migreert(tmp_path, monkeypatch) -> None:
    """A classificeert v1, B voltooit de migratie: A keert terug als noop."""
    db = _minimale_database(tmp_path, "race-v2-migrate.db")
    na_b: dict = {}

    def actor_b() -> None:
        assert migrate(db) == "migrated"
        na_b["hash"] = _hash(db)
        na_b["snapshot"] = _snapshot(db)

    _installeer_race_haak(monkeypatch, actor_b)

    assert migrate(db) == "noop", "A mag de migratie niet opnieuw uitvoeren"

    assert _versie(db) == "2"
    assert CATALOG_TABLES <= set(_tabellen(db))
    assert _snapshot(db) == na_b["snapshot"]
    assert _hash(db) == na_b["hash"], "de slot-noop mag niets schrijven"


# ==== Race met een écht write-lock (twee verbindingen) =======================


def test_twee_verbindingen_slot_voorkomt_writes_op_verouderde_classificatie(
    tmp_path, monkeypatch
) -> None:
    """X houdt `BEGIN IMMEDIATE` met ongecommitte `3`; A classificeert eerst als v1.

    Pas nadat X gecommit heeft, kan A het slot bemachtigen en herclassificeert die
    onder het slot naar nieuwer -> `MigrationError` + rollback, zonder writes.
    De uitkomst is voor elke interleave identiek; de hook bewijst dat A de database
    daadwerkelijk als `v1` geclassificeerd heeft.
    """
    db = _minimale_database(tmp_path, "race-slot.db")
    bestanden_na_b = {}

    x = sqlite3.connect(db, timeout=5.0)
    x.isolation_level = None
    x.execute("BEGIN IMMEDIATE")
    x.execute("UPDATE app_meta SET value = '3' WHERE key = 'schema_version'")

    geclassificeerd = threading.Event()
    statussen: list[str] = []
    origineel = db_module.classificeer_database

    def gehaakt(pad: str | None = None) -> str:
        status = origineel(pad)
        statussen.append(status)
        geclassificeerd.set()
        return status

    monkeypatch.setattr(db_module, "classificeer_database", gehaakt)

    uitkomst: dict = {}

    def actor_a() -> None:
        try:
            uitkomst["pad"] = init_database(db)
        except BaseException as exc:  # noqa: BLE001 - de weigering zelf wordt getoond
            uitkomst["fout"] = exc

    draad = threading.Thread(target=actor_a, name="actor-a")
    draad.start()

    assert geclassificeerd.wait(timeout=10), "A moet eerst read-only classificeren"
    # X is nog niet gecommit: A kan het write-lock nog niet hebben bemachtigd.
    x.execute("COMMIT")
    x.close()
    bestanden_na_b["hash"] = _hash(db)
    bestanden_na_b["bestanden"] = _bestanden(tmp_path)

    draad.join(timeout=10)
    assert not draad.is_alive(), "A moet na X's commit doorgelopen zijn"

    assert statussen == ["v1"], "A moet vóór B's commit als v1 geclassificeerd zijn"
    assert isinstance(uitkomst.get("fout"), MigrationError), (
        f"verwacht weigering na hercheck, kreeg {uitkomst!r}"
    )
    assert "pad" not in uitkomst, "A mag niet als voltooide bootstrap terugkeren"
    assert _versie(db) == "3"
    assert _tabellen(db) == ["app_meta"], "geen bootstrap_marker na de weigering"
    assert _hash(db) == bestanden_na_b["hash"], "A mag na X's commit niets schrijven"
    assert _bestanden(tmp_path) == bestanden_na_b["bestanden"], "geen sidecar achterlaten"


# ==== Gewone parallelle starters (rooktest) ==================================


def test_parallelle_starters_leveren_consistente_v2_op(tmp_path) -> None:
    """Twee starters op hetzelfde (nieuwe) pad: eindtoestand is altijd schoon v2."""
    db = str(tmp_path / "parallel.db")
    fouten: list[BaseException] = []
    slot = threading.Lock()

    def starter() -> None:
        try:
            init_database(db)
            migrate(db)
        except BaseException as exc:  # noqa: BLE001 - gedeeld met de andere starter
            with slot:
                fouten.append(exc)

    draden = [threading.Thread(target=starter, name=f"starter-{n}") for n in range(2)]
    for draad in draden:
        draad.start()
    for draad in draden:
        draad.join(timeout=30)
        assert not draad.is_alive(), "geen van beide starters mag blijven hangen"

    assert fouten == [], f"geen starter mag falen: {fouten!r}"
    assert _versie(db) == "2"
    assert CATALOG_TABLES <= set(_tabellen(db))
    with connect(db) as connection:
        marker = connection.execute(
            "SELECT value FROM bootstrap_marker WHERE key = 'initialized'"
        ).fetchone()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert marker is not None and marker[0] == "nieuws-piet"
    assert _bestanden(tmp_path) == ["parallel.db"], "geen journal-/shm-sidecar"
