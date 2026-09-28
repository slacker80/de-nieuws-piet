"""Health-endpoint tests (sectie 4, taken 4.8 t/m 4.13, 4.15 t/m 4.19).

 Vijf exacte named tests (conform spec health-monitoring/health-endpoint):
   test_healthy_system, test_sqlite_failure, test_sqlite_timeout,
   test_backend_failure, test_combined_failure
Elke test bouwt een verse applicatie-instance via de app-factory, reset de
fault-omgeving en voert GEEN filesystem database mutaties uit (alleen doubles).
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.config import HEALTH_FAULT_WHITELIST, read_fault_config
from app.main import create_app
from tests.conftest import (
    assert_health_response,
    build_client,
    healthy_sqlite_probe,
    unhealthy_sqlite_probe,
)

# ==== De vijf exacte named tests =========================================


def test_healthy_system() -> None:
    """Test 1: APP_ENV=test, geen fault -> HTTP 200, exacte success body."""
    client = build_client(app_env="test", fault=None)
    response = client.get("/health")
    assert_health_response(
        response,
        expected_status=200,
        expected_components={"backend": "healthy", "sqlite": "healthy"},
    )


def test_sqlite_failure() -> None:
    """Test 2: APP_ENV=test, APP_HEALTH_FAULT=sqlite -> HTTP 503 SQLite contract."""
    client = build_client(app_env="test", fault="sqlite")
    response = client.get("/health")
    assert_health_response(
        response,
        expected_status=503,
        expected_components={"backend": "healthy", "sqlite": "unhealthy"},
        expected_error="SQLite database not accessible",
    )


def test_sqlite_timeout() -> None:
    """Test 3: APP_HEALTH_FAULT=sqlite_timeout -> 503 binnen probe/client budget."""
    client = build_client(app_env="test", fault="sqlite_timeout")
    service = client.app.state.health

    started = time.perf_counter()
    response = client.get("/health")
    client_elapsed_ms = (time.perf_counter() - started) * 1000.0

    assert_health_response(
        response,
        expected_status=503,
        expected_components={"backend": "healthy", "sqlite": "unhealthy"},
        expected_error="SQLite database not accessible",
    )

    # Server-side probe budget: afgekapt binnen <=500ms.
    assert service.last_sqlite_elapsed_ms is not None
    assert service.last_sqlite_elapsed_ms <= 500.0, (
        f"server probe budget overschreden: {service.last_sqlite_elapsed_ms:.1f}ms"
    )
    # Client-side assertion budget: totale response <=1000ms.
    assert client_elapsed_ms <= 1000.0, (
        f"client assertion budget overschreden: {client_elapsed_ms:.1f}ms"
    )

    service.release()  # hangende test double netjes beëindigen


def test_backend_failure() -> None:
    """Test 4: APP_ENV=test, APP_HEALTH_FAULT=backend -> HTTP 500 backend contract."""
    client = build_client(app_env="test", fault="backend")
    response = client.get("/health")
    assert_health_response(
        response,
        expected_status=500,
        expected_components={"backend": "unhealthy", "sqlite": "healthy"},
        expected_error="Backend internal health check failed",
    )


def test_combined_failure() -> None:
    """Test 5: APP_ENV=test, APP_HEALTH_FAULT=all -> HTTP 503 gecombineerd."""
    client = build_client(app_env="test", fault="all")
    response = client.get("/health")
    assert_health_response(
        response,
        expected_status=503,
        expected_components={"backend": "unhealthy", "sqlite": "unhealthy"},
        expected_error="Backend internal health check failed and SQLite database not accessible",
    )


# ==== Exacte contracten per component (taken 4.9/4.10/4.11) ===============


def test_sqlite_failure_response_contract() -> None:
    """4.9: exact JSON SQLite failure met application/json en HTTP 503."""
    response = build_client(app_env="test", fault="sqlite").get("/health")
    assert response.headers["content-type"] == "application/json"
    assert response.status_code == 503
    assert response.json()["components"] == {"backend": "healthy", "sqlite": "unhealthy"}


def test_backend_failure_response_contract() -> None:
    """4.10: exact JSON backend failure met application/json en HTTP 500."""
    response = build_client(app_env="test", fault="backend").get("/health")
    assert response.headers["content-type"] == "application/json"
    assert response.status_code == 500
    assert response.json()["components"] == {"backend": "unhealthy", "sqlite": "healthy"}


def test_backend_fault_injection_response_contract() -> None:
    """4.11: backend fault-injection antwoordt exact JSON met HTTP 500."""
    client = build_client(app_env="test", fault="backend")
    response = client.get("/health")
    assert response.headers["content-type"].startswith("application/json")
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "Backend internal health check failed"
    assert body["components"]["backend"] == "unhealthy"


def test_success_response_contract() -> None:
    """4.8: exact JSON success met application/json en HTTP 200."""
    response = build_client(app_env="test").get("/health")
    assert response.headers["content-type"].startswith("application/json")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "timestamp": response.json()["timestamp"],
        "components": {"backend": "healthy", "sqlite": "healthy"},
    }


# ==== Test doubles, geen filesystem mutatie (taken 4.13/4.18) ============


def test_sqlite_unavailability_via_test_double(tmp_path) -> None:
    """4.13: SQLite onbeschikbaar via double; databasebestand blijft onaangetast."""
    db_file = tmp_path / "news.db"
    db_file.write_bytes(b"original-bytes")

    def exploding_probe(_db_path: str) -> bool:
        raise AssertionError("fault-pad mag de echte probe niet aanroepen")

    client = build_client(app_env="test", fault="sqlite", sqlite_probe=exploding_probe)
    response = client.get("/health")

    assert response.status_code == 503
    assert db_file.read_bytes() == b"original-bytes", "databasebestand mag niet gewijzigd zijn"


def test_read_only_probe_does_not_create_missing_db(tmp_path) -> None:
    """Echte probe op ontbrekend bestand: ongezond, GEEN creatie (mode=ro)."""
    from app.health import probe_sqlite_readonly

    missing = tmp_path / "absent.db"
    assert probe_sqlite_readonly(str(missing)) is False
    assert not missing.exists(), "read-only probe mag geen databasebestand aanmaken"


# ==== App-factory isolatie en reset cleanup (taken 4.17/4.18) ===========


def test_fault_only_active_with_app_env_test() -> None:
    """4.17: fault is uitsluitend actief met APP_ENV exact `test`."""
    with_fault = build_client(app_env="test", fault="sqlite").get("/health")
    assert with_fault.status_code == 503

    # Zonder APP_ENV: zelfde fault-waarde wordt genegeerd.
    no_app_env = build_client(app_env=None, fault="sqlite").get("/health")
    assert no_app_env.status_code == 200

    # APP_ENV anders dan `test`: fault wordt genegeerd.
    other_env = build_client(app_env="prod", fault="sqlite").get("/health")
    assert other_env.status_code == 200


def test_health_fault_whitelist_exact() -> None:
    """4.17/4.22: whitelist is exact sqlite, sqlite_timeout, backend, all."""
    assert HEALTH_FAULT_WHITELIST == {"sqlite", "sqlite_timeout", "backend", "all"}


def test_unknown_fault_values_are_deterministically_ignored() -> None:
    """4.19: onbekende APP_HEALTH_FAULT-waarden -> telkens exact dezelfde 200."""
    for value in ("random", "sqlite_timeout;drop", "", "SQLITE", "Backend", "all ", "unknown"):
        responses = [
            build_client(app_env="test", fault=value).get("/health") for _ in range(2)
        ]
        for response in responses:
            assert response.status_code == 200, f"onbekende waarde {value!r} gaf {response.status_code}"
            assert response.json()["status"] == "healthy"
            assert response.json()["components"] == {
                "backend": "healthy",
                "sqlite": "healthy",
            }
        # Deterministisch: exact dezelfde body behalve dynamische timestamp.
        first, second = (r.json() for r in responses)
        assert first["status"] == second["status"]
        assert first["components"] == second["components"]


def test_app_env_other_than_test_gives_normal_healthy_response() -> None:
    """4.19: APP_ENV != test -> normale gezonde respons, ook met alle faults."""
    for app_env in ("dev", "prod", "", "Test", "TEST"):
        for fault in HEALTH_FAULT_WHITELIST:
            response = build_client(app_env=app_env, fault=fault).get("/health")
            assert response.status_code == 200, (
                f"APP_ENV={app_env!r} fault={fault!r} gaf {response.status_code}"
            )
            assert response.json()["status"] == "healthy"


def test_app_factory_instances_are_isolated() -> None:
    """4.18: elke test/instance deelt geen fault-state met een andere."""
    faulty = build_client(app_env="test", fault="backend")
    healthy = build_client(app_env="test", fault=None)

    assert faulty.get("/health").status_code == 500
    assert healthy.get("/health").status_code == 200
    # De fault van de ene instance lekt niet naar de andere.
    assert faulty.app.state.health_fault == "backend"
    assert healthy.app.state.health_fault is None


def test_fault_config_is_read_at_construction() -> None:
    """4.18: APP_ENV/APP_HEALTH_FAULT worden bij constructie gelezen."""
    import os

    os.environ["APP_ENV"] = "test"
    os.environ["APP_HEALTH_FAULT"] = "sqlite"
    application = create_app(sqlite_probe=healthy_sqlite_probe, init_db=False)
    assert application.state.health_fault == "sqlite"

    # Wijziging na constructie verandert de bestaande instance niet.
    os.environ["APP_HEALTH_FAULT"] = "backend"
    assert application.state.health_fault == "sqlite"
    # Een NIEUWE instance leest de nieuwe waarde.
    newer = create_app(sqlite_probe=healthy_sqlite_probe, init_db=False)
    assert newer.state.health_fault == "backend"


def test_reset_cleanup_removes_fault_environment() -> None:
    """4.18: cleanup verwijdert APP_ENV en APP_HEALTH_FAULT uit de omgeving."""
    client = build_client(app_env="test", fault="sqlite")
    assert client.get("/health").status_code == 503

    import os

    for key in ("APP_ENV", "APP_HEALTH_FAULT"):
        os.environ.pop(key, None)
        assert key not in os.environ


def test_read_fault_config_falls_back_to_os_environ() -> None:
    """config-lezer gebruikt de actieve omgeving wanneer geen mapping gegeven is."""
    import os

    os.environ["APP_ENV"] = "test"
    os.environ["APP_HEALTH_FAULT"] = "all"
    cfg = read_fault_config()
    assert cfg.fault == "all"


# ==== Budget van de echte read-only probe ===============================


def test_real_sqlite_probe_is_bounded(tmp_path) -> None:
    """4.4/4.12: echte read-only probe rondt af binnen het server-probe budget."""
    import sqlite3

    from app.health import SQLITE_PROBE_BUDGET_MS, run_bounded, probe_sqlite_readonly

    db_file = tmp_path / "news.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE marker (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    conn.execute("INSERT INTO marker VALUES ('a', 'b')")
    conn.commit()
    conn.close()

    started = time.perf_counter()
    outcome = run_bounded(lambda: probe_sqlite_readonly(str(db_file)), SQLITE_PROBE_BUDGET_MS)
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    assert outcome.healthy is True
    assert outcome.timed_out is False
    assert outcome.elapsed_ms <= 500.0
    assert elapsed_ms <= 1000.0


def test_probe_budget_caps_hanging_probe() -> None:
    """4.4: een hangende probe wordt afgekapt binnen het budget (ongezond)."""
    import threading

    from app.health import SQLITE_PROBE_BUDGET_MS, run_bounded

    never = threading.Event()
    started = time.perf_counter()
    outcome = run_bounded(lambda: bool(never.wait()), SQLITE_PROBE_BUDGET_MS)
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    assert outcome.healthy is False
    assert outcome.timed_out is True
    assert elapsed_ms <= 500.0
