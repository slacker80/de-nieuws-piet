"""Migratie v1 -> v2 van de broncatalogus (taken 1.1 t/m 1.4).

Dekt: transactionele additieve DDL met `schema_version` als laatste stap, noop
op versie 2, weigering van nieuwere/ongekende versies, rollback bij een fout en
`PRAGMA foreign_keys=ON` per verse verbinding. Alle tests werken op een
tijdelijk pad en openen nooit een socket.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.db import connect, init_database
from app.db_migrate import (
    CATALOG_SCHEMA_STATEMENTS,
    SCHEMA_VERSION,
    MigrationError,
    main as migrate_main,
    migrate,
)
from app.sources_validation import TOPIC_SLUGS
pytestmark = pytest.mark.usefixtures("socket_guard")

CATALOG_TABLES = {"sources", "topics", "source_topics", "source_cloud_labels"}


def _v1_database(tmp_path) -> str:
    db_file = tmp_path / "news.db"
    init_database(str(db_file))
    return str(db_file)


def _versie(db: str) -> str | None:
    with connect(db) as connection:
        rij = connection.execute(
            "SELECT value FROM app_meta WHERE key = ?", ("schema_version",)
        ).fetchone()
    return None if rij is None else rij[0]


def _tabellen(db: str) -> set[str]:
    with connect(db) as connection:
        return {
            rij[0]
            for rij in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }


def _snapshot(db: str) -> dict:
    """Volledige statische vingerafdruk: DDL, app_meta én alle rijen."""
    with connect(db) as connection:
        ddl = connection.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
        app_meta = connection.execute(
            "SELECT key, value FROM app_meta ORDER BY key"
        ).fetchall()
        tellen = {
            naam: connection.execute(f"SELECT count(*) FROM {naam}").fetchone()[0]
            for naam in sorted(_tabellen(db))
        }
    return {"ddl": ddl, "app_meta": app_meta, "tellen": tellen}


# ==== 1.1 Migratie v1 -> v2 ==================================================


def test_migratie_v1_naar_v2(tmp_path) -> None:
    """1.1: versie 2, alle catalogustabellen en een schoon `foreign_key_check`."""
    db = _v1_database(tmp_path)
    assert _versie(db) == "1"

    assert migrate(db) == "migrated"
    assert _versie(db) == str(SCHEMA_VERSION) == "2"

    tabellen = _tabellen(db)
    assert CATALOG_TABLES <= tabellen, f"catalogustabellen ontbreken: {tabellen}"

    with connect(db) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        slugs = {
            rij[0]
            for rij in connection.execute("SELECT slug FROM topics").fetchall()
        }
        uniek = connection.execute(
            "SELECT count(*) FROM pragma_index_list('sources') "
            "WHERE name = 'ux_sources_feed_url_key'"
        ).fetchone()[0]
    assert slugs == set(TOPIC_SLUGS), "woordenlijst niet volledig gevuld"
    assert uniek == 1, "UNIQUE-index op feed_url_key ontbreekt"


def test_migratie_kent_pk_fk_en_check_constraints(tmp_path) -> None:
    """1.1: PK's, FK's en CHECK's uit het ontwerp zijn daadwerkelijk aangebracht."""
    db = _v1_database(tmp_path)
    migrate(db)

    with connect(db) as connection:
        bron_ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'sources'"
        ).fetchone()[0]
        relatie_ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'source_topics'"
        ).fetchone()[0]
        labels_ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'source_cloud_labels'"
        ).fetchone()[0]
        fk_tabel = connection.execute("PRAGMA foreign_key_list('source_topics')").fetchall()
        fk_labels = connection.execute(
            "PRAGMA foreign_key_list('source_cloud_labels')"
        ).fetchall()

    for fragment in (
        "PRIMARY KEY",
        "feed_url_key",
        "CHECK (length(trim(name)) > 0)",
        "CHECK (type IN ('rss', 'atom'))",
        "BETWEEN 1 AND 5",
        "is_active IN (0, 1)",
    ):
        assert fragment in bron_ddl, f"CHECK ontbreekt in sources: {fragment}"
    assert "ON DELETE CASCADE" in relatie_ddl
    assert "REFERENCES topics (slug)" in relatie_ddl
    assert "sovereign-cloud" in labels_ddl
    # `source_topics` verwijst naar zowel `sources` als `topics`.
    assert {rij[2] for rij in fk_tabel} == {"sources", "topics"}
    assert {rij[2] for rij in fk_labels} == {"sources"}


def test_migratie_is_idempotent(tmp_path) -> None:
    """1.1: opnieuw draaien geeft dezelfde tabellen en rijen (IF NOT EXISTS)."""
    db = _v1_database(tmp_path)
    migrate(db)
    eerste = _snapshot(db)

    # Versie 2 is een noop; ook een eerdere herhaling verandert niets.
    assert migrate(db) == "noop"
    assert _snapshot(db) == eerste


# ==== 1.2 Noop en weigering ==================================================


def test_migratie_op_versie_2_is_noop(tmp_path) -> None:
    """1.2: versie 2 -> noop: versie blijft 2 en geen tabel/index/rij verandert."""
    db = _v1_database(tmp_path)
    migrate(db)
    with connect(db) as connection:
        connection.execute(
            "INSERT INTO sources (name, feed_url, feed_url_key, type, language, is_active) "
            "VALUES ('Voorbeeld', 'https://example.com/feed.xml', "
            "'https://example.com/feed.xml', 'rss', 'nl', 1)"
        )
    vooraf = _snapshot(db)

    assert migrate(db) == "noop"
    assert _versie(db) == "2"
    assert _snapshot(db) == vooraf


@pytest.mark.parametrize("versie", ["3", "99", "onbekend"])
def test_migratie_weigert_nieuwere_of_ongekende_versie(tmp_path, versie: str) -> None:
    """1.2: versie > 2 of onbekend -> weigering, zonder een enkele schrijfactie."""
    db = _v1_database(tmp_path)
    migrate(db)
    with connect(db) as connection:
        connection.execute(
            "UPDATE app_meta SET value = ? WHERE key = 'schema_version'", (versie,)
        )
    vooraf = _snapshot(db)

    with pytest.raises(MigrationError):
        migrate(db)

    assert _versie(db) == versie
    assert _snapshot(db) == vooraf, "weigering mag niets wijzigen"


# ==== 1.3 Rollback bij een fout =============================================


def test_mislukte_migratie_rolt_volledig_terug(tmp_path, monkeypatch) -> None:
    """1.3: fout midden in de migratie -> alles terug, versie blijft 1, geen tabellen."""
    db = _v1_database(tmp_path)
    kapotte = CATALOG_SCHEMA_STATEMENTS + (
        "INSERT INTO bestaat_niet (kolom) VALUES (1)",
    )
    monkeypatch.setattr("app.db_migrate.CATALOG_SCHEMA_STATEMENTS", kapotte)

    with pytest.raises(sqlite3.Error):
        migrate(db)

    assert _versie(db) == "1", "versie mag pas na succes naar 2 gaan"
    assert CATALOG_TABLES & _tabellen(db) == set(), "halve tabellen achtergelaten"


def test_mislukte_migratie_is_opnieuw_uitvoerbaar(tmp_path, monkeypatch) -> None:
    """1.3: na rollback is een herhaling met het juiste schema alsnog geslaagd."""
    db = _v1_database(tmp_path)
    monkeypatch.setattr(
        "app.db_migrate.CATALOG_SCHEMA_STATEMENTS",
        CATALOG_SCHEMA_STATEMENTS + ("INSERT INTO bestaat_niet (kolom) VALUES (1)",),
    )
    with pytest.raises(sqlite3.Error):
        migrate(db)
    monkeypatch.undo()

    assert migrate(db) == "migrated"
    assert _versie(db) == "2"
    assert CATALOG_TABLES <= _tabellen(db)


# ==== 1.4 PRAGMA foreign_keys=ON per verbinding ==============================


def test_elke_verbinding_heeft_foreign_keys_aan(tmp_path) -> None:
    """1.4: `PRAGMA foreign_keys=ON` staat aan op elke verse verbinding."""
    db = _v1_database(tmp_path)
    migrate(db)

    for _ in range(2):
        with connect(db) as connection:
            assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_schrijfactie_naar_onbekend_record_wordt_geweigerd(tmp_path) -> None:
    """1.4: een bronrelatie naar een niet-bestaand record weigert SQLite."""
    db = _v1_database(tmp_path)
    migrate(db)

    with connect(db) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO source_topics (source_id, topic_slug) VALUES (?, ?)",
                (999999, "ai"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO source_cloud_labels (source_id, cloud_label) VALUES (?, ?)",
                (999999, "aws"),
            )


def test_cli_migratie_script(tmp_path, capsys) -> None:
    """1.1/1.2: `python -m app.db_migrate` meldt de uitkomst en is herhaalbaar."""
    db = _v1_database(tmp_path)

    assert migrate_main([db]) == 0
    uitvoer = capsys.readouterr().out
    assert "schema-versie: 2" in uitvoer
    assert "migratie: migrated" in uitvoer

    assert migrate_main([db]) == 0
    assert "migratie: noop" in capsys.readouterr().out


def test_cli_migratie_script_weigert_onbekende_versie(tmp_path, capsys) -> None:
    """1.2: de CLI meldt een weigering met exit code 1 (geen stille succesmelding)."""
    db = _v1_database(tmp_path)
    migrate(db)
    with connect(db) as connection:
        connection.execute(
            "UPDATE app_meta SET value = '7' WHERE key = 'schema_version'"
        )

    assert migrate_main([db]) == 1
    uitvoer = capsys.readouterr()
    assert "FOUT" in uitvoer.err
