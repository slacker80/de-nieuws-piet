"""/health-regressie naast een gevulde catalogus (taak 7.1).

Het bestaande health-contract blijft exact ongewijzigd: dezelfde statuscode,
dezelfde Content-Type, dezelfde JSON-body en geen enkele catalogusuitbreiding.
"""

from __future__ import annotations

import pytest

from app.db import init_database
from app.db_migrate import migrate
from app.source_seed import seed
from tests.conftest import assert_health_response, build_client

pytestmark = pytest.mark.usefixtures("socket_guard")

VERWACHTE_COMPONENTEN = {"backend": "healthy", "sqlite": "healthy"}


def _gevulde_catalogus(tmp_path):
    """Database op schema-versie 2 met de volledige starterset gevuld."""
    pad = str(tmp_path / "health.db")
    init_database(pad)
    assert migrate(pad) == "migrated"
    resultaat = seed(pad)
    assert resultaat["added"], "de starterset moet de catalogus vullen"
    return pad


def test_health_contract_op_gevulde_catalogus(tmp_path) -> None:
    """7.1: statuscode, Content-Type en JSON-body blijven exact hetzelfde."""
    pad = _gevulde_catalogus(tmp_path)
    with build_client(db_path=pad, init_db=False) as client:
        # Bewijs dat de catalogus daadwerkelijk gevuld is.
        bronnen = client.get("/api/sources")
        assert bronnen.status_code == 200
        assert len(bronnen.json()) > 0

        respons = client.get("/health")
        assert_health_response(
            respons,
            expected_status=200,
            expected_components=VERWACHTE_COMPONENTEN,
        )


def test_health_body_heeft_exact_de_bestaande_sleutels(tmp_path) -> None:
    """7.1: uitsluitend `status`, `timestamp` en `components`, in die volgorde."""
    pad = _gevulde_catalogus(tmp_path)
    with build_client(db_path=pad, init_db=False) as client:
        body = client.get("/health").json()
    assert list(body.keys()) == ["status", "timestamp", "components"]
    assert body["status"] == "healthy"
    assert body["components"] == VERWACHTE_COMPONENTEN


def test_health_bevat_geen_catalogusvelden(tmp_path) -> None:
    """7.1: geen catalogusvelden, geen broncomponenten en geen extra componenten."""
    pad = _gevulde_catalogus(tmp_path)
    with build_client(db_path=pad, init_db=False) as client:
        body = client.get("/health").json()

    tekst = str(body).lower()
    for verboden in (
        "source", "catalog", "bron", "feed", "seed", "topics", "migrat", "schema"
    ):
        assert verboden not in tekst, f"catalogusveld {verboden!r} lekt in /health"
    assert set(body["components"]) == {"backend", "sqlite"}


def test_health_content_type_is_exact_application_json(tmp_path) -> None:
    """7.1: Content-Type blijft `application/json` (geen catalogus-uitbreiding)."""
    pad = _gevulde_catalogus(tmp_path)
    with build_client(db_path=pad, init_db=False) as client:
        respons = client.get("/health")
    assert respons.headers["content-type"] == "application/json"


def test_health_blijft_onveranderd_bij_sqlite_fault(tmp_path) -> None:
    """7.1: ook een fault-respons houdt exact dezelfde vorm, zonder catalogus."""
    pad = _gevulde_catalogus(tmp_path)
    client = build_client(db_path=pad, fault="sqlite", init_db=False)
    respons = client.get("/health")
    assert_health_response(
        respons,
        expected_status=503,
        expected_components={"backend": "healthy", "sqlite": "unhealthy"},
        expected_error="SQLite database not accessible",
    )
    assert list(respons.json().keys()) == ["status", "timestamp", "components", "error"]


def test_catalogusroutes_veranderen_healthcontract_niet(tmp_path) -> None:
    """7.1: catalogusroutes zijn toegevoegd zonder de health-route te raken."""
    pad = _gevulde_catalogus(tmp_path)
    with build_client(db_path=pad, init_db=False) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/api/sources", json={
            "name": "Nieuw", "feed_url": "https://example.com/nieuw.xml",
            "type": "rss", "language": "nl",
        }).status_code == 201
        assert_health_response(
            client.get("/health"),
            expected_status=200,
            expected_components=VERWACHTE_COMPONENTEN,
        )
