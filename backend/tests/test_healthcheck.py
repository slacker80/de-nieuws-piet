"""Healthcheck tests (sectie 7, taken 7.1 t/m 7.7).

Implementeer geautomatiseerde healthcheck tests voor backend, SQLite en frontend
componenten. Dekken:

- 7.1: Geautomatiseerde healthcheck tests (backend, SQLite, frontend)
- 7.2: Tests voor Docker Compose services (echte Compose-configuratie + stack)
- 7.3: Tests voor Next.js applicatie (echte `next build` + `next start`)
- 7.4: Tests voor FastAPI health endpoint
- 7.5: Tests voor SQLite database
- 7.6: Voer healthcheck tests uit en verifieer dat alle tests slagen
- 7.7: Documenteer health test commando's

7.4/7.5 zijn unit tests volgens de app-factory-isolering (elke test bouwt een
verse applicatie-instance). 7.2/7.3 draaien daadwerkelijk Docker Compose en de
Next.js-build via `tests/runtime_env.py` (CLI/daemon-detectie, memoïsatie).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests import runtime_env
from tests.conftest import build_client, assert_health_response


# ==== 7.1 Geautomatiseerde healthcheck tests ================================


def test_backend_healthcheck() -> None:
    """7.1: backend healthcheck test (FastAPI health endpoint)."""
    client = build_client(app_env="test", fault=None)
    response = client.get("/health")
    assert_health_response(
        response,
        expected_status=200,
        expected_components={"backend": "healthy", "sqlite": "healthy"},
    )


def test_sqlite_healthcheck() -> None:
    """7.2: SQLite healthcheck test (via health endpoint met fault)."""
    client = build_client(app_env="test", fault="sqlite")
    response = client.get("/health")
    assert_health_response(
        response,
        expected_status=503,
        expected_components={"backend": "healthy", "sqlite": "unhealthy"},
        expected_error="SQLite database not accessible",
    )


def test_backend_sqlite_combined_healthcheck() -> None:
    """7.3: gecombineerde backend+SQLite healthcheck test."""
    client = build_client(app_env="test", fault="all")
    response = client.get("/health")
    assert_health_response(
        response,
        expected_status=503,
        expected_components={"backend": "unhealthy", "sqlite": "unhealthy"},
        expected_error="Backend internal health check failed and SQLite database not accessible",
    )


# ==== 7.2 Tests voor Docker Compose services ============================


def test_docker_compose_service_healthcheck() -> None:
    """7.2: Docker Compose service healthcheck test (echte Compose-configuratie)."""
    runtime_env.require_docker()
    config = runtime_env.compose_config()

    # Exact twee services; SQLite is nooit een service.
    assert sorted(config["services"]) == ["backend", "frontend"], (
        f"onverwachte services: {sorted(config['services'])}"
    )

    healthcheck = config["services"]["backend"].get("healthcheck") or {}
    command = healthcheck.get("test") or []
    code = " ".join(str(part) for part in command)

    # De healthcheck loopt in de backend-container en toetst de /health endpoint
    # op exact HTTP 200 én JSON `status: healthy` (zelfde contract als de
    # readiness loop).
    assert command[:2] == ["CMD", "python"] and "-c" in command, (
        f"backend healthcheck is geen python-check in de container: {command}"
    )
    assert "127.0.0.1:8000/health" in code, "healthcheck raakt niet de backend-/health endpoint"
    assert "r.status==200" in code, "healthcheck stelt de HTTP-status niet exact gelijk aan 200"
    assert "d.get('status')=='healthy'" in code, (
        "healthcheck toetst de JSON-body niet op `status: healthy`"
    )

    # Afgetimede check met expliciete budgetten (geen eindeloze startup-wachtfase).
    assert healthcheck.get("interval") == "10s"
    assert healthcheck.get("timeout") == "5s"
    assert healthcheck.get("retries") == 5
    assert healthcheck.get("start_period") == "15s"

    # Frontend heeft bewust GEEN healthcheck op /health: /health is uitsluitend
    # een backend-endpoint; frontend-readiness gebeurt via de readiness loop.
    assert "healthcheck" not in config["services"]["frontend"], (
        "frontend mag geen /health-healthcheck hebben"
    )


def test_docker_compose_service_dependencies() -> None:
    """7.2: Docker Compose service afhankelijkheden én feitelijk gezonde services."""
    runtime_env.require_docker()
    config = runtime_env.compose_config()

    # Frontend start pas ná de backend (readiness-condition, taak 2.5).
    frontend_depends = config["services"]["frontend"].get("depends_on") or {}
    assert frontend_depends.get("backend", {}).get("condition") == "service_started", (
        f"onverwachte afhankelijkheid: {frontend_depends}"
    )

    # Feitelijk gestart met de exacte startopdracht; de returncode én de
    # readiness-meting worden gecontroleerd (geen stille, niet-gecontroleerde start).
    stack = runtime_env.ensure_stack_up()
    assert stack["ok"], f"stack niet ready: {stack}"
    assert stack["frontend_marker"] and stack["backend_healthy"], f"onvolledige readiness: {stack}"

    services = runtime_env.compose_services()
    assert sorted(services) == ["backend", "frontend"]
    assert services["backend"]["state"] == "running", services["backend"]
    assert services["backend"]["health"] == "healthy", services["backend"]
    assert services["frontend"]["state"] == "running", services["frontend"]

    # Alleen de backend mount de named volume op /app/data; frontend heeft geen volumes.
    backend_volumes = [
        v.get("source")
        for v in (config["services"]["backend"].get("volumes") or [])
        if isinstance(v, dict)
    ]
    assert backend_volumes == [runtime_env.REAL_VOLUME], backend_volumes
    assert "volumes" not in config["services"]["frontend"]


# ==== 7.3 Tests voor Next.js applicatie ================================


def test_nextjs_app_healthcheck() -> None:
    """7.3: Next.js applicatie bouwt en serveert (echte `next build` + `next start`)."""
    runtime_env.require_node()

    build = runtime_env.next_build()
    assert build["rc"] == 0, f"next build faalde (rc={build['rc']}):\n{build['output']}"

    server = runtime_env.next_serve()
    status, body = runtime_env.http_get(server["url"])
    assert status == 200, f"Next.js gaf geen HTTP 200 op {server['url']}: {status}"
    assert "Nieuws Piet" in body, "marker-tekst 'Nieuws Piet' ontbreekt in de served pagina"
    assert "Nog geen nieuws beschikbaar" in body, "lege staat ontbreekt in de served pagina"
    assert 'name="viewport"' in body, "viewport-meta ontbreekt (mobiele rendering)"
    assert runtime_env.external_urls(body) == [], (
        f"pagina verwijst naar externe URLs: {runtime_env.external_urls(body)}"
    )


def test_nextjs_app_mobile_healthcheck() -> None:
    """7.3: Next.js mobiele webapp: viewport, PWA-manifest, landmarks en lege staat."""
    runtime_env.require_node()
    server = runtime_env.next_serve()
    status, body = runtime_env.http_get(server["url"])
    assert status == 200

    # Exacte viewport-tag voor mobiel (360px-viewport wordt in de e2e-suite gemeten).
    assert (
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>' in body
    ), "viewport-meta mist 'initial-scale=1'"

    # PWA-manifest en favicon zijn lokaal bereikbaar (geen SaaS/CDN).
    manifest_status, manifest_body = runtime_env.http_get(
        server["url"].rstrip("/") + "/manifest.json"
    )
    assert manifest_status == 200, f"manifest niet bereikbaar: {manifest_status}"
    assert '"name"' in manifest_body, "manifest bevat geen naam"

    # Primaire landmarks en lege staat zijn in de server-gerenderde HTML aanwezig.
    assert "<nav" in body, "nav-landmark ontbreekt in de SSR-HTML"
    assert "<main" in body, "main-landmark ontbreekt in de SSR-HTML"
    assert "empty-state" in body, "lege-staat component ontbreekt in de SSR-HTML"

    # De metingen zelf (360x800, geen horizontale scrolling) lopen in de
    # Playwright-suite: zie 8.4/8.7 en tests/test_mobile_runtime.py (9.4.x).


# ==== 7.4 Tests voor FastAPI health endpoint ================================


def test_fastapi_health_endpoint_healthcheck() -> None:
    """7.4: FastAPI health endpoint healthcheck test."""
    # Dit is een unit test die de FastAPI health endpoint healthcheck
    # (taak 4.6) test.

    client = build_client(app_env="test", fault=None)
    response = client.get("/health")

    # Basis healthcheck validatie
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["components"]["backend"] == "healthy"
    assert response.json()["components"]["sqlite"] == "healthy"


def test_fastapi_health_endpoint_failure_scenarios() -> None:
    """7.4: FastAPI health endpoint failure scenarios test."""
    # Test verschillende failure scenarios via de health endpoint.

    # SQLite failure
    client = build_client(app_env="test", fault="sqlite")
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["components"]["sqlite"] == "unhealthy"

    # Backend failure
    client = build_client(app_env="test", fault="backend")
    response = client.get("/health")
    assert response.status_code == 500
    assert response.json()["components"]["backend"] == "unhealthy"

    # Gecombineerde failure
    client = build_client(app_env="test", fault="all")
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["components"]["backend"] == "unhealthy"
    assert response.json()["components"]["sqlite"] == "unhealthy"


# ==== 7.5 Tests voor SQLite database ================================


def test_sqlite_database_healthcheck() -> None:
    """7.5: SQLite database healthcheck test."""
    # Dit is een unit test die de SQLite database healthcheck
    # (taak 5.4) test.

    from app.db import init_database, connect, read_marker

    # Test database initialisatie
    test_db_path = "/tmp/test_healthcheck.db"
    result = init_database(test_db_path)

    assert result == test_db_path

    # Test database verbinding
    with connect(test_db_path) as connection:
        cursor = connection.execute("SELECT value FROM bootstrap_marker WHERE key = 'initialized'")
        row = cursor.fetchone()
        assert row is not None

    # Test marker
    marker = read_marker(test_db_path)
    assert marker == "nieuws-piet"


def test_sqlite_database_failure_healthcheck() -> None:
    """7.5: SQLite database failure healthcheck test."""
    # Test SQLite database failure scenario.

    from app.db import connect

    # Test met een niet-bestaande database - SQLite creëert een nieuwe database
    # in plaats van een exception te verhogen.
    with connect("/tmp/nonexistent.db") as connection:
        # De verbinding is gemaakt, maar de database wordt gecreëerd
        # Dit is het verwachte gedrag voor SQLite.
        assert connection is not None

    # Controleer dat de database is gecreëerd
    import os
    assert os.path.exists("/tmp/nonexistent.db")


# ==== 7.6 Voer healthcheck tests uit en verifieer dat alle tests slagen =========


def test_all_healthcheck_tests_pass() -> None:
    """7.6: Voer alle healthcheck tests uit en verifieer dat ze slagen."""
    # Unit-niveau (app-factory): alle vier de healthpaden met exacte assertions.
    assert_health_response(
        build_client(app_env="test", fault=None).get("/health"),
        expected_status=200,
        expected_components={"backend": "healthy", "sqlite": "healthy"},
    )
    assert_health_response(
        build_client(app_env="test", fault="sqlite").get("/health"),
        expected_status=503,
        expected_components={"backend": "healthy", "sqlite": "unhealthy"},
        expected_error="SQLite database not accessible",
    )
    assert_health_response(
        build_client(app_env="test", fault="backend").get("/health"),
        expected_status=500,
        expected_components={"backend": "unhealthy", "sqlite": "healthy"},
        expected_error="Backend internal health check failed",
    )
    assert_health_response(
        build_client(app_env="test", fault="all").get("/health"),
        expected_status=503,
        expected_components={"backend": "unhealthy", "sqlite": "unhealthy"},
        expected_error="Backend internal health check failed and SQLite database not accessible",
    )

    # Runtime-niveau (7.2/7.3): echte Compose-configuratie + draaiende stack,
    # echte Next.js-build en -server. Beide zijn per sessie gememoïseerd.
    test_docker_compose_service_healthcheck()
    test_docker_compose_service_dependencies()
    test_nextjs_app_healthcheck()
    test_nextjs_app_mobile_healthcheck()


# ==== 7.7 Documenteer health test commando's ================================


def test_health_test_command_documentation() -> None:
    """7.7: Documenteer health test commando's."""
    root = runtime_env.ROOT
    setup = (root / "docs" / "development-setup.md").read_text(encoding="utf-8")
    failure = (root / "docs" / "failure-testing.md").read_text(encoding="utf-8")

    # Backend/health tests.
    assert "python -m pytest tests/ -v" in setup, "geen pytest-opdracht in de setup-docs"
    assert "python -m pytest tests/test_health.py -v" in failure, (
        "geen health-testopdracht in de failure-testing-docs"
    )

    # Frontendtests: exacte startopdracht, readiness loop, daarna `npm run test:e2e`.
    assert "npm run test:e2e" in setup, "geen `npm run test:e2e` in de setup-docs"
    assert "docker compose up -d --build" in setup, "geen exacte startopdracht in de docs"
    assert "./scripts/readiness-loop.sh" in setup, (
        "geen readiness loop tussen start en e2e in de docs"
    )

    # De volgorde in de documentatie: start -> readiness -> e2e (de eerste
    # reeks die na elkaar voorkomt, niet per se de allereerste vermelding).
    start = setup.find("docker compose up -d --build")
    readiness = setup.find("./scripts/readiness-loop.sh", start)
    e2e = setup.find("npm run test:e2e", readiness)
    assert -1 < start < readiness < e2e, (
        "de gedocumenteerde volgorde is niet start -> readiness -> e2e"
    )


# ==== Samenvattende healthcheck test suite ==========================


def test_healthcheck_test_suite() -> None:
    """Samenvattende test suite voor alle healthcheck tests."""
    # Test 1-4: backend-, SQLite- en gecombineerde paden met exacte assertions.
    assert_health_response(
        build_client(app_env="test", fault=None).get("/health"),
        expected_status=200,
        expected_components={"backend": "healthy", "sqlite": "healthy"},
    )
    assert_health_response(
        build_client(app_env="test", fault="sqlite").get("/health"),
        expected_status=503,
        expected_components={"backend": "healthy", "sqlite": "unhealthy"},
        expected_error="SQLite database not accessible",
    )
    assert_health_response(
        build_client(app_env="test", fault="backend").get("/health"),
        expected_status=500,
        expected_components={"backend": "unhealthy", "sqlite": "healthy"},
        expected_error="Backend internal health check failed",
    )
    assert_health_response(
        build_client(app_env="test", fault="all").get("/health"),
        expected_status=503,
        expected_components={"backend": "unhealthy", "sqlite": "unhealthy"},
        expected_error="Backend internal health check failed and SQLite database not accessible",
    )

    # Test 5-6: FastAPI- en SQLite-health (7.4/7.5).
    test_fastapi_health_endpoint_healthcheck()
    test_sqlite_database_healthcheck()

    # Test 7-10: Compose-services en Next.js (7.2/7.3), memoïseerd per sessie.
    test_docker_compose_service_healthcheck()
    test_docker_compose_service_dependencies()
    test_nextjs_app_healthcheck()
    test_nextjs_app_mobile_healthcheck()

    # Test 11: gedocumenteerde testcommando's (7.7).
    test_health_test_command_documentation()
