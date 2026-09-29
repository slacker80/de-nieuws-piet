"""Veld-, taal- en woordenlijstvalidatie van bronrecords (taken 2.4 en 2.5).

Alle gevallen lopen via `POST /api/sources` tegen een geïsoleerde, gemigreerde
database: 422 betekent dat er niets is opgeslagen.
"""

from __future__ import annotations

import pytest

from app.sources_validation import (
    CLOUD_LABELS,
    LANGUAGES,
    SOURCE_TYPES,
    TOPIC_SLUGS,
    validate_reliability,
)
from tests.conftest import minimale_payload

pytestmark = pytest.mark.usefixtures("socket_guard")


def _post(client, **wijzigingen):
    return client.post("/api/sources", json=minimale_payload(**wijzigingen))


def _opgeslagen(client) -> list[dict]:
    return client.get("/api/sources").json()


# ==== 2.4 type, language en reliability ======================================


@pytest.mark.parametrize(
    "payload,reden",
    [
        ({k: v for k, v in minimale_payload().items() if k != "type"}, "type ontbreekt"),
        ({"type": "json"}, "buiten het enum"),
        ({"type": "RSS"}, "geen casefold: hoofdletters zijn ongeldig"),
        ({"type": 200}, "geen tekstwaarde"),
        ({"type": ""}, "leeg"),
    ],
)
def test_type_validatie(catalogus_client, payload, reden) -> None:
    """2.4: `type` ontbreekt of is ongeldig -> 422 en geen opslaan."""
    body = minimale_payload()
    body.update(payload)
    if "type" not in payload:
        body.pop("type")
    respons = catalogus_client.post("/api/sources", json=body)
    assert respons.status_code == 422, f"{reden}: {respons.text}"
    assert _opgeslagen(catalogus_client) == []


def test_type_exact_uit_enum(catalogus_client) -> None:
    """2.4: `rss` en `atom` zijn geldig, geen automatische typebepaling."""
    for nummer, waarde in enumerate(SOURCE_TYPES):
        # Elk record krijgt een eigen feed-URL zodat geen 409-dubbele ontstaat.
        respons = _post(
            catalogus_client,
            type=waarde,
            feed_url=f"https://example.com/type-{nummer}.xml",
        )
        assert respons.status_code == 201, respons.text
    assert {item["type"] for item in _opgeslagen(catalogus_client)} == set(SOURCE_TYPES)


def test_language_ontbreekt_geeft_422(catalogus_client) -> None:
    """2.4: `language` is verplicht -> 422 en geen record."""
    body = minimale_payload()
    body.pop("language")
    assert catalogus_client.post("/api/sources", json=body).status_code == 422
    assert _opgeslagen(catalogus_client) == []


def test_wordt_naar_lowercase_genormaliseerd(catalogus_client) -> None:
    """2.4: `NL` wordt opgeslagen als `nl`."""
    respons = _post(catalogus_client, language="NL")
    assert respons.status_code == 201
    assert respons.json()["language"] == "nl"


@pytest.mark.parametrize("code", ["zz", "nl-NL", "eng", "nederlands", "und-DU"])
def test_language_buiten_lijst_geeft_422(catalogus_client, code: str) -> None:
    """2.4: elke waarde buiten de expliciete codelijst -> 422."""
    assert _post(catalogus_client, language=code).status_code == 422
    assert _opgeslagen(catalogus_client) == []


@pytest.mark.parametrize("code", ["und", "mul", "UND", "MUL"])
def test_und_en_mul_zijn_geldig(catalogus_client, code: str) -> None:
    """2.4: `und` en `mul` zijn expliciet opgenomen, ook als hoofdletters."""
    respons = _post(catalogus_client, language=code)
    assert respons.status_code == 201
    assert respons.json()["language"] == code.lower()


def test_language_codelijst_is_iso639_1_met_und_en_mul() -> None:
    """2.4: 184 ISO 639-1-codes plus `und` en `mul`, uniek en lowercase."""
    iso = [code for code in LANGUAGES if code not in ("und", "mul")]
    assert len(iso) == 184, f"verwacht 184 ISO 639-1-codes, gevonden {len(iso)}"
    assert len(set(LANGUAGES)) == len(LANGUAGES)
    assert set(LANGUAGES) >= {"und", "mul", "nl", "en", "de", "uk", "ar"}
    assert all(code == code.lower() for code in LANGUAGES)
    assert all(len(code) == 2 for code in iso)


@pytest.mark.parametrize(
    "waarde",
    [True, False, "4", 4.5, 0, 6, -1, [], {}],
)
def test_reliability_ongeldig(catalogus_client, waarde) -> None:
    """2.4: boolean, string, decimale notatie en bereikfouten -> 422."""
    assert _post(catalogus_client, reliability=waarde).status_code == 422
    assert _opgeslagen(catalogus_client) == []


@pytest.mark.parametrize("waarde", [1, 3, 5])
def test_reliability_geldige_integers(catalogus_client, waarde: int) -> None:
    """2.4: integers 1..5 worden bewaard als integer (geen bool)."""
    respons = _post(catalogus_client, reliability=waarde)
    assert respons.status_code == 201
    assert respons.json()["reliability"] == waarde


def test_reliability_expliciet_null(catalogus_client) -> None:
    """2.4: `null` wordt als null opgeslagen."""
    respons = _post(catalogus_client, reliability=None)
    assert respons.status_code == 201
    assert respons.json()["reliability"] is None


def test_reliability_default_is_null(catalogus_client) -> None:
    """2.4: zonder `reliability` blijft de waarde null."""
    assert _post(catalogus_client).json()["reliability"] is None


def test_reliability_weigert_bool_ook_al_is_int_ouders(catalogus_client) -> None:
    """2.4: een boolean mag nooit als integer 1..5 doorsijpelen."""
    with pytest.raises(Exception):
        validate_reliability(True)
    assert _post(catalogus_client, reliability=True).status_code == 422


def test_is_active_default_false(catalogus_client) -> None:
    """2.4: standaard is een nieuwe bron inactief."""
    assert _post(catalogus_client).json()["is_active"] is False


def test_is_active_explicit_true(catalogus_client) -> None:
    """2.4: `is_active` is een boolean; true wordt bewaard."""
    respons = _post(catalogus_client, is_active=True)
    assert respons.status_code == 201
    assert respons.json()["is_active"] is True


@pytest.mark.parametrize("waarde", ["true", 1, "ja", None])
def test_is_active_niet_boolean_geeft_422(catalogus_client, waarde) -> None:
    """2.4: niet-boolean waarden voor `is_active` -> 422."""
    assert _post(catalogus_client, is_active=waarde).status_code == 422


def test_name_moet_niet_leeg_zijn(catalogus_client) -> None:
    """2.4: `name` is verplicht en na trimmen niet leeg."""
    assert _post(catalogus_client, name="   ").status_code == 422
    assert _post(catalogus_client, name=42).status_code == 422
    body = minimale_payload()
    body.pop("name")
    assert catalogus_client.post("/api/sources", json=body).status_code == 422


def test_name_wordt_getrimd(catalogus_client) -> None:
    """2.4: opgeslagen naam is getrimd, inhoud ongewijzigd."""
    assert _post(catalogus_client, name="  Nieuwe Feed  ").json()["name"] == "Nieuwe Feed"


# ==== 2.5 Woordenlijsten =====================================================


@pytest.mark.parametrize("slug", ["onbekend", "AI", "kubernetes-en-cloud", "", "5g"])
def test_onbekend_onderwerp_geeft_422(catalogus_client, slug: str) -> None:
    """2.5: een onderwerp buiten de woordenlijst -> 422."""
    assert _post(catalogus_client, topics=[slug]).status_code == 422
    assert _opgeslagen(catalogus_client) == []


def test_dubbel_onderwerp_geeft_422(catalogus_client) -> None:
    """2.5: dezelfde slug twee keer in één request -> 422."""
    assert _post(catalogus_client, topics=["ai", "linux", "ai"]).status_code == 422
    assert _opgeslagen(catalogus_client) == []


def test_geldig_onderwerp_wordt_gerelateerd(catalogus_client) -> None:
    """2.5: bekende slugs worden exact bewaard, in woordenlijstvolgorde."""
    respons = _post(catalogus_client, topics=["linux", "ai"])
    assert respons.status_code == 201
    assert respons.json()["topics"] == ["ai", "linux"]


@pytest.mark.parametrize("label", ["google-cloud", "AWS", "", "azure-cloud"])
def test_onbekend_cloudlabel_geeft_422(catalogus_client, label: str) -> None:
    """2.5: een cloudlabel buiten de exacte set -> 422."""
    assert _post(catalogus_client, cloud_labels=[label]).status_code == 422
    assert _opgeslagen(catalogus_client) == []


def test_dubbel_cloudlabel_geeft_422(catalogus_client) -> None:
    """2.5: hetzelfde cloudlabel twee keer -> 422."""
    assert _post(catalogus_client, cloud_labels=["aws", "aws"]).status_code == 422
    assert _opgeslagen(catalogus_client) == []


def test_meerdere_cloudlabels_worden_geaccepteerd(catalogus_client) -> None:
    """2.5: meerdere cloudlabels per bron mogen."""
    respons = _post(catalogus_client, cloud_labels=["azure", "multi-cloud"])
    assert respons.status_code == 201
    assert respons.json()["cloud_labels"] == ["azure", "multi-cloud"]


def test_geen_automatische_afleiding(catalogus_client) -> None:
    """2.5: naam en URL's noemen een provider, maar er is geen label afgeleid."""
    respons = _post(
        catalogus_client,
        name="AWS officiële feed",
        feed_url="https://example.com/aws-azure-feed.xml",
    )
    assert respons.status_code == 201
    assert respons.json()["cloud_labels"] == []
    assert respons.json()["topics"] == []


def test_woordlijsten_zijn_definitief() -> None:
    """2.5: de vaste woordenlijsten komen exact overeen met de delta-spec."""
    assert set(CLOUD_LABELS) == {
        "azure",
        "aws",
        "t-cloud",
        "otc",
        "multi-cloud",
        "sovereign-cloud",
    }
    assert set(SOURCE_TYPES) == {"rss", "atom"}
    assert len(TOPIC_SLUGS) == len(set(TOPIC_SLUGS))
    assert {"ai", "kubernetes", "linux", "t-cloud-public", "open-telekom-cloud",
            "digital-sovereignty", "azure", "aws", "ukraine", "middle-east",
            "geopolitics", "ethereum"} <= set(TOPIC_SLUGS)


def test_onbekend_veld_geeft_422(catalogus_client) -> None:
    """2.5: de payload is strict; onbekende velden worden geweigerd."""
    body = minimale_payload(bogus="x")
    assert catalogus_client.post("/api/sources", json=body).status_code == 422
    assert _opgeslagen(catalogus_client) == []
