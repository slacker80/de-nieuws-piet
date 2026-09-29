"""Shared fixtures voor de health-tests (sectie 4, taken 4.16/4.18).

* app-factory per test: elke test bouwt zijn eigen `create_app()`-instance.
* reset cleanup: `APP_ENV`/`APP_HEALTH_FAULT` worden na afloop verwijderd.
* geen filesystem database mutaties: probes zijn test doubles of read-only.
"""

from __future__ import annotations

import os
import socket

import pytest
from fastapi.testclient import TestClient

from app.config import read_fault_config
from app.db import init_database
from app.db_migrate import migrate
from app.main import create_app
from tests import runtime_env

# Omgevingssleutels die de health-config bepalen; altijd opgeruimd na de test.
_FAULT_ENV_KEYS = ("APP_ENV", "APP_HEALTH_FAULT", "APP_DB_PATH")


def pytest_sessionfinish(session, exitstatus):
    """Bouwt alles af wat deze testsessie startte (stack, `next start`, logs).

    Alleen eigen resources: runtime_env registreert uitsluitend wat de sessie
    zelf heeft gestart en laat bestaande services met rust.
    """
    runtime_env.cleanup_all()


def pytest_runtest_logreport(report):
    """Registreert elke overgeslagen test in `runtime_env.skipped_tests`.

    De verplichte lokale suite draait als laatste een guard op die lijst, zodat
    een sessie met overgeslagen tests nooit als "volledig gedraaid" kan
    doorgaan (geen misleidende voltooiing).
    """
    if report.outcome != "skipped":
        return
    reden = report.longrepr
    if isinstance(reden, tuple) and len(reden) == 3:
        reden = reden[2]
    runtime_env.skipped_tests.append(f"{report.nodeid}: {reden}")


@pytest.fixture(autouse=True)
def reset_fault_environment():
    """Garandeert een schone omgeving vóór en na elke test (reset cleanup)."""
    saved = {key: os.environ.get(key) for key in _FAULT_ENV_KEYS}
    for key in _FAULT_ENV_KEYS:
        os.environ.pop(key, None)
    yield
    for key in _FAULT_ENV_KEYS:
        os.environ.pop(key, None)
        if saved[key] is not None:
            os.environ[key] = saved[key]


@pytest.fixture
def fault_env(monkeypatch):
    """Zet fault-variabelen en verwijdert ze automatisch bij afloop."""

    def _set(app_env: str | None = None, fault: str | None = None, db_path: str | None = None):
        for key, value in (
            ("APP_ENV", app_env),
            ("APP_HEALTH_FAULT", fault),
            ("APP_DB_PATH", db_path),
        ):
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)

    yield _set
    for key in _FAULT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def healthy_sqlite_probe(_db_path: str) -> bool:
    """Read-only test double: SQLite bereikbaar, GEEN filesystem-mutatie."""
    return True


def unhealthy_sqlite_probe(_db_path: str) -> bool:
    """Read-only test double: SQLite onbereikbaar, GEEN filesystem-mutatie."""
    return False


def build_client(
    *,
    app_env: str | None = "test",
    fault: str | None = None,
    sqlite_probe=None,
    backend_probe=None,
    db_path: str = "/nonexistent/never-created.db",
    init_db: bool = False,
) -> TestClient:
    """Bouwt een verse app-instance via de app-factory met test-environment.

    `init_db=False` (standaard): tests initialiseren GEEN database, zodat
    fault-tests nooit filesystem database mutaties uitvoeren (taak 4.18).
    """
    environ: dict[str, str] = {}
    if app_env is not None:
        environ["APP_ENV"] = app_env
    if fault is not None:
        environ["APP_HEALTH_FAULT"] = fault

    if sqlite_probe is None:
        # Default double: geen echte database nodig, geen filesystem-mutatie.
        sqlite_probe = healthy_sqlite_probe

    application = create_app(
        environ=environ,
        db_path=db_path,
        sqlite_probe=sqlite_probe,
        backend_probe=backend_probe,
        init_db=init_db,
    )
    return TestClient(application)


@pytest.fixture
def socket_guard(monkeypatch):
    """Blokkeert élke verbinding of DNS-resolutie naar een externe host.

    De catalogussuite is volledig offline (delta-spec `source-catalog`,
    taak 7.2): lokale sockets (AF_UNIX) en loopback blijven toegestaan omdat
    sommige testhulpmiddelen die gebruiken; extern contact is een directe
    mislukking van de test.
    """
    echte_connect = socket.socket.connect
    echte_connect_ex = socket.socket.connect_ex
    echte_getaddrinfo = socket.getaddrinfo
    echte_create_connection = socket.create_connection

    def _lokale_adressen(adres) -> bool:
        if isinstance(adres, (str, bytes)):
            return True  # AF_UNIX-pad: lokale socket, geen netwerkcontact
        host = adres[0] if isinstance(adres, (tuple, list)) else adres
        return host in ("127.0.0.1", "::1", "localhost", "", None)

    def connect(self, address, *args, **kwargs):
        assert _lokale_adressen(address), (
            f"socket-guard: verboden verbinding naar extern adres {address!r}"
        )
        return echte_connect(self, address, *args, **kwargs)

    def connect_ex(self, address, *args, **kwargs):
        assert _lokale_adressen(address), (
            f"socket-guard: verboden verbinding naar extern adres {address!r}"
        )
        return echte_connect_ex(self, address, *args, **kwargs)

    def getaddrinfo(host, *args, **kwargs):
        assert host in ("127.0.0.1", "::1", "localhost", "", None), (
            f"socket-guard: verbode DNS-resolutie van {host!r}"
        )
        return echte_getaddrinfo(host, *args, **kwargs)

    def create_connection(address, *args, **kwargs):
        assert _lokale_adressen(address), (
            f"socket-guard: verboden verbinding naar extern adres {address!r}"
        )
        return echte_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    yield


@pytest.fixture
def catalogus_db(tmp_path) -> str:
    """Tijdelijke database op schema-versie 2 met de woordenlijst gevuld."""
    db_file = tmp_path / "news.db"
    init_database(str(db_file))
    assert migrate(str(db_file)) == "migrated"
    return str(db_file)


@pytest.fixture
def catalogus_client(catalogus_db) -> TestClient:
    """Beheer-CLI tegen een verse, geïsoleerde catalogusdatabase."""
    return build_client(db_path=catalogus_db, init_db=False)


def minimale_payload(**wijzigingen) -> dict:
    """Geldig minimale POST-payload voor de catalogustests."""
    payload = {
        "name": "Voorbeeld Feed",
        "feed_url": "https://example.com/feed.xml",
        "type": "rss",
        "language": "nl",
    }
    payload.update(wijzigingen)
    return payload


def assert_timestamp_rfc3339_utc(value: str) -> None:
    """Controleert RFC3339 UTC: eindigt op Z en is parseerbaar als UTC."""
    from datetime import datetime, timezone

    assert isinstance(value, str)
    assert value.endswith("Z"), f"timestamp moet UTC (Z) zijn: {value}"
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(None)


def assert_health_response(
    response,
    *,
    expected_status: int,
    expected_components: dict[str, str],
    expected_error: str | None = None,
) -> dict:
    """Volledige response-assertie: status, headers, JSON body, timestamp."""
    assert response.status_code == expected_status
    assert response.headers["content-type"].startswith("application/json")

    body = response.json()
    expected_keys = ["status", "timestamp", "components"] + ([] if expected_error is None else ["error"])
    assert list(body.keys()) == expected_keys, f"onverwachte body-volgorde: {list(body.keys())}"

    if expected_status == 200:
        assert body["status"] == "healthy"
        assert expected_error is None
    else:
        assert body["status"] == "unhealthy"
        assert body["error"] == expected_error

    assert isinstance(body["components"], dict)
    assert body["components"] == expected_components
    assert set(body["components"].keys()) == {"backend", "sqlite"}
    assert_timestamp_rfc3339_utc(body["timestamp"])
    return body
