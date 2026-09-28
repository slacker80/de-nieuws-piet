"""SQLite database tests (sectie 5, taken 5.1 t/m 5.4).

Dekken: minimale configuratie, initialisatiescript, connectie lifecycle zonder
pooling, database-operaties en persistentie. Alle tests werken op een tijdelijk
pad (tmp_path) en raken nooit de echte database in het named volume.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.db import (
    DEFAULT_DB_PATH,
    SCHEMA_STATEMENTS,
    VOLUME_NAME,
    connect,
    get_db_path,
    init_database,
    integrity_ok,
    read_marker,
)
from app.db_init import main as db_init_main
from app.main import DEFAULT_DB_PATH as MAIN_DEFAULT_DB_PATH


# ==== 5.1 Minimale configuratie en connectie lifecycle ====================


def test_default_paths_match_compose_identity() -> None:
    """5.1: databasepad en volume-identiteit komen overeen met de spec."""
    assert DEFAULT_DB_PATH == "/app/data/news.db"
    assert MAIN_DEFAULT_DB_PATH == "/app/data/news.db"
    assert VOLUME_NAME == "nieuws_piet_sqlite_data"


def test_get_db_path_honours_env_override(monkeypatch) -> None:
    """5.1: `APP_DB_PATH` overschrijft de standaard."""
    monkeypatch.setenv("APP_DB_PATH", "/tmp/custom/news.db")
    assert get_db_path() == "/tmp/custom/news.db"


def test_init_database_creates_minimal_schema(tmp_path) -> None:
    """5.1: initialisatie maakt de minimale configuratie (tabellen + marker)."""
    db_file = tmp_path / "news.db"
    result = init_database(str(db_file))

    assert result == str(db_file)
    assert db_file.exists()

    with connect(str(db_file)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "app_meta" in tables
    assert "bootstrap_marker" in tables


def test_init_database_is_idempotent(tmp_path) -> None:
    """5.1: herhaald initialiseren (bij elke start) geeft geen fouten/duplicaten."""
    db_file = tmp_path / "news.db"
    init_database(str(db_file))
    first_tables = _table_names(db_file)
    init_database(str(db_file))
    second_tables = _table_names(db_file)

    assert first_tables == second_tables
    assert read_marker(str(db_file)) == "nieuws-piet"

    with connect(str(db_file)) as connection:
        count = connection.execute("SELECT count(*) FROM bootstrap_marker").fetchone()[0]
    assert count == 1, "marker mag niet dupliceren bij herinitialisatie"


def _table_names(db_file) -> set[str]:
    with connect(str(db_file)) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }


# ==== 5.2 Initialisatiescript =============================================


def test_db_init_script_creates_database(tmp_path, capsys) -> None:
    """5.2: `python -m app.db_init` initialiseert en meldt integrity_check."""
    db_file = tmp_path / "news.db"
    exit_code = db_init_main([str(db_file)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert str(db_file) in captured.out
    assert "integrity_check: ok" in captured.out
    assert "OK: database geïnitialiseerd" in captured.out
    assert db_file.exists()


def test_db_init_script_is_idempotent(tmp_path, capsys) -> None:
    """5.2: het script is veilig herhaalbaar uit te voeren."""
    db_file = tmp_path / "news.db"
    assert db_init_main([str(db_file)]) == 0
    capsys.readouterr()
    assert db_init_main([str(db_file)]) == 0


def test_db_init_script_fails_on_invalid_path(tmp_path, capsys) -> None:
    """5.2: onmogelijk pad -> exit code != 0 (geen stille succesmelding)."""
    blocker = tmp_path / "blocker"
    blocker.write_text("ik ben een bestand, geen map")
    bad_path = blocker / "nested" / "news.db"

    exit_code = db_init_main([str(bad_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "FOUT" in captured.err


# ==== 5.3 Connectie management zonder pooling ============================


def test_connect_opens_and_closes_fresh_connection(tmp_path) -> None:
    """5.3: elke operatie opent een verse connectie en sluit die af."""
    db_file = tmp_path / "news.db"
    init_database(str(db_file))

    with connect(str(db_file)) as connection:
        assert isinstance(connection, sqlite3.Connection)
    # Na de contextmanager is de connectie daadwerkelijk gesloten.
    assert connection.execute, "connectie-object bestaat nog (geen close)"
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_connect_does_not_pool_connections(tmp_path) -> None:
    """5.3: opeenvolgende aanroepen delen GEEN connectie (geen pooling)."""
    db_file = tmp_path / "news.db"
    init_database(str(db_file))

    with connect(str(db_file)) as first:
        first_id = id(first)
    with connect(str(db_file)) as second:
        second_id = id(second)

    # Verschillende objecten: geen gedeelde/poolling-verbinding.
    assert first_id != second_id


def test_connect_rolls_back_on_error(tmp_path) -> None:
    """5.3: een fout tijdens de operatie rollback't de transactie."""
    db_file = tmp_path / "news.db"
    init_database(str(db_file))

    with pytest.raises(ValueError):
        with connect(str(db_file)) as connection:
            connection.execute(
                "INSERT INTO app_meta (key, value) VALUES ('rollback_test', 'x')"
            )
            raise ValueError("opzettelijke fout")

    with connect(str(db_file)) as connection:
        row = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'rollback_test'"
        ).fetchone()
    assert row is None, "ongecommitte transactie mag niet zichtbaar zijn"


def test_connect_commits_on_success(tmp_path) -> None:
    """5.3: succesvolle operaties worden gecommit en blijven behouden."""
    db_file = tmp_path / "news.db"
    init_database(str(db_file))

    with connect(str(db_file)) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('committed', 'yes')"
        )

    with connect(str(db_file)) as connection:
        row = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'committed'"
        ).fetchone()
    assert row is not None and row[0] == "yes"


# ==== 5.4 Database operaties en persistentie ==============================


def test_database_operations_and_persistence(tmp_path) -> None:
    """5.4: CRUD-operaties slagen en zijn terug te lezen via nieuwe connecties."""
    db_file = tmp_path / "news.db"
    init_database(str(db_file))

    with connect(str(db_file)) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('source', 'rss')"
        )
        connection.execute("DELETE FROM app_meta WHERE key = 'schema_version'")

    # Nieuwe verbinding (geen pooling) leest de gewijzigde staat terug.
    with connect(str(db_file)) as connection:
        source = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'source'"
        ).fetchone()
        version = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'schema_version'"
        ).fetchone()

    assert source is not None and source[0] == "rss"
    assert version is None


def test_persistence_across_reconnect(tmp_path) -> None:
    """5.4: data overleeft het sluiten en heropenen van de connectie (persistentie)."""
    db_file = tmp_path / "news.db"
    init_database(str(db_file))

    with connect(str(db_file)) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO bootstrap_marker (key, value) VALUES (?, ?)",
            ("persistence_check", "behouden"),
        )

    # Volledig nieuwe connectie + integriteitscontrole.
    assert read_marker(str(db_file)) == "nieuws-piet"
    assert integrity_ok(str(db_file)) is True

    with connect(str(db_file)) as connection:
        row = connection.execute(
            "SELECT value FROM bootstrap_marker WHERE key = 'persistence_check'"
        ).fetchone()
    assert row is not None and row[0] == "behouden"


def test_readonly_probe_never_creates_database(tmp_path) -> None:
    """5.3/5.4: read-only paden (health-probe) creëren geen bestand."""
    from app.health import probe_sqlite_readonly

    missing = tmp_path / "never-created.db"
    assert probe_sqlite_readonly(str(missing)) is False
    assert not missing.exists()


def test_schema_statements_are_create_if_not_exists() -> None:
    """5.1: schema-uitdrukkingen zijn idempotent (`IF NOT EXISTS`)."""
    assert SCHEMA_STATEMENTS
    for statement in SCHEMA_STATEMENTS:
        assert "IF NOT EXISTS" in statement
