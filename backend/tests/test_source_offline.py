"""Offline-garantie over de volledige catalogussuite (taak 7.2).

Elke catalogustest die zonder Docker draait, staat onder een socket-guard die
alle verbindingen en DNS-resoluties naar externe hosts blokkeert (AF_UNIX en
loopback blijven toegestaan voor lokale testhulpmiddelen). Hier wordt dat
tweemaal bewezen:

1. een dekkingscontrole: elke offline catalogusmodule draait daadwerkelijk
   onder die guard;
2. een strenge sweep: de complete offline keten (migratie -> seed -> API)
   draait met een guard die élke niet-lokale verbinding tot een directe
   mislukking maakt.
"""

from __future__ import annotations

import socket

import pytest

from app.db import init_database
from app.db_migrate import migrate
from app.source_seed import seed
from tests.conftest import build_client, minimale_payload

pytestmark = pytest.mark.usefixtures("socket_guard")

# Modules die volledig offline zijn en dus onder de socket-guard staan.
OFFLINE_MODULES = (
    "test_source_migration",
    "test_db_lifespan",
    "test_db_concurrency",
    "test_source_url",
    "test_source_validation",
    "test_source_api",
    "test_source_seed",
    "test_source_health_regression",
    "test_source_offline",
)

# Runtime-modules die de Docker-daemon (AF_UNIX-socket) en loopback gebruiken.
# Bewust níet socket-guarded: ze openen geen verbinding naar een externe host.
RUNTIME_MODULES = ("test_source_backup_restore",)


def _module(name: str):
    return __import__(f"tests.{name}", fromlist=[name])


def _fixtures_uit_module(module) -> set[str]:
    """`usefixtures`-namen van het module-level `pytestmark` (Mark óf lijst)."""
    markering = getattr(module, "pytestmark", [])
    if not isinstance(markering, (list, tuple)):
        markering = [markering]
    namen: set[str] = set()
    for item in markering:
        mark = getattr(item, "mark", item)  # MarkDecorator of Mark
        if getattr(mark, "name", None) == "usefixtures":
            namen.update(mark.args)
    return namen


@pytest.mark.parametrize("naam", OFFLINE_MODULES)
def test_offline_module_draait_onder_socket_guard(naam: str) -> None:
    """7.2: elke offline catalogusmodule markeert alle testen met socket-guard."""
    assert "socket_guard" in _fixtures_uit_module(_module(naam)), (
        f"{naam} mist `pytestmark = pytest.mark.usefixtures(\"socket_guard\")`"
    )


@pytest.mark.parametrize("naam", RUNTIME_MODULES)
def test_runtime_module_is_bewust_uitgezonderd(naam: str) -> None:
    """7.2: de Docker-runtime staat bewust buiten de offline-set, met reden."""
    module = _module(naam)
    documentatie = (module.__doc__ or "")
    assert "db-rollback.sh" in documentatie, (
        f"{naam} hoort bij het bestaande backupproces en gebruikt de "
        "Docker-daemon via een lokale AF_UNIX-socket"
    )
    assert not _fixtures_uit_module(module), (
        f"{naam} mag geen offline socket-guard claimen terwijl het Docker gebruikt"
    )


def _streng_blokkeren(monkeypatch) -> None:
    """Blokkeert élke verbinding of resolutie die niet lokaal is."""
    oorspronkelijk = (
        socket.socket.connect,
        socket.socket.connect_ex,
        socket.getaddrinfo,
        socket.create_connection,
    )

    def _verboden(*_args, **_kwargs):
        raise AssertionError("offline sweep: netwerkcontact is verboden")

    monkeypatch.setattr(socket.socket, "connect", _verboden)
    monkeypatch.setattr(socket.socket, "connect_ex", _verboden)
    monkeypatch.setattr(socket, "getaddrinfo", _verboden)
    monkeypatch.setattr(socket, "create_connection", _verboden)
    return oorspronkelijk


def test_volledige_offline_keten_zonder_netwerk(tmp_path, monkeypatch) -> None:
    """7.2: migratie, seed én beheer-API draaien zonder één socket."""
    _streng_blokkeren(monkeypatch)

    pad = str(tmp_path / "offline.db")
    init_database(pad)
    assert migrate(pad) == "migrated"
    assert seed(pad)["added"], "de seed moet offline vullen"

    with build_client(db_path=pad, init_db=False) as client:
        lijst = client.get("/api/sources")
        assert lijst.status_code == 200
        assert len(lijst.json()) == 15

        aangemaakt = client.post(
            "/api/sources", json=minimale_payload(
                name="Offline toevoeging",
                feed_url="https://example.com/offline.xml",
                topics=["linux"],
            )
        )
        assert aangemaakt.status_code == 201
        assert client.get(f"/api/sources/{aangemaakt.json()['id']}").status_code == 200
        assert client.get("/api/source-options").status_code == 200
        assert client.patch(
            f"/api/sources/{aangemaakt.json()['id']}", json={"name": "Hernoemd"}
        ).status_code == 200
        # Rejecties en foutpaden eveneens offline.
        assert client.post(
            "/api/sources", json=minimale_payload(feed_url="https://example.com/x#f")
        ).status_code == 422
        assert client.get("/api/sources/9999").status_code == 404


def test_canonicalisatie_gebruikt_geen_resolver(monkeypatch) -> None:
    """7.2: ook de URL-laag opent nooit een socket, ook niet indirect."""
    from app.sources_validation import canonicalize_url

    _streng_blokkeren(monkeypatch)
    for invoer in (
        " HTTPS://WWW.Example.COM:443  ",
        "https://BÜCHER.example/feed",
        "http://example.com:8080/x?b=2&a=1",
    ):
        assert canonicalize_url(invoer)
    with pytest.raises(Exception):
        canonicalize_url("https://example.com/feed#fragment")
