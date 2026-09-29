"""Beheer-API van de broncatalogus (taken 3.1 t/m 3.5, 4.1 t/m 4.3, 5.1/5.2).

Alle testen draaien tegen een eigen, geïsoleerde v2-database via de app-factory;
fouten worden bovendien gecontroleerd op lekken (SQL, stacktrace, pad).
"""

from __future__ import annotations

import concurrent.futures
import json

import pytest

from app.db import init_database
from app.db_migrate import migrate
from tests.conftest import build_client, minimale_payload

pytestmark = pytest.mark.usefixtures("socket_guard")

# ==== 3.1 Databasepad-isolatie ===============================================


def test_app_instances_delen_geen_bronrecords(tmp_path) -> None:
    """3.1: twee `create_app`-instanties met verschillende `db_path` delen niets."""
    pad_a, pad_b = str(tmp_path / "a.db"), str(tmp_path / "b.db")
    for pad in (pad_a, pad_b):
        init_database(pad)
        assert migrate(pad) == "migrated"

    client_a = build_client(db_path=pad_a)
    client_b = build_client(db_path=pad_b)

    assert client_a.post("/api/sources", json=minimale_payload()).status_code == 201
    assert [item["id"] for item in client_a.get("/api/sources").json()] == [1]
    assert client_b.get("/api/sources").json() == []
    assert client_b.get("/api/sources/1").status_code == 404


def _catalogus_vullen(client, **overstekend) -> list[int]:
    """Levert een kleine catalogus terug met gemengde status en labels."""
    payloads = [
        minimale_payload(
            name="Actief AI",
            feed_url="https://example.com/ai.xml",
            is_active=True,
            topics=["ai"],
            cloud_labels=["azure"],
        ),
        minimale_payload(
            name="Inactief Linux",
            feed_url="https://example.com/linux.xml",
            is_active=False,
            topics=["linux"],
            cloud_labels=["aws"],
        ),
        minimale_payload(
            name="Actief AI + AWS",
            feed_url="https://example.com/ai-aws.xml",
            is_active=True,
            topics=["ai"],
            cloud_labels=["aws"],
            **overstekend,
        ),
    ]
    ids: list[int] = []
    for payload in payloads:
        respons = client.post("/api/sources", json=payload)
        assert respons.status_code == 201, respons.text
        ids.append(respons.json()["id"])
    return ids


# ==== 4.1 Lijst, sortering en filters ========================================


def test_lege_catalogus_geeft_200_met_lege_lijst(catalogus_client) -> None:
    """4.1: een lege catalogus is 200 met `[]`, geen fout."""
    respons = catalogus_client.get("/api/sources")
    assert respons.status_code == 200
    assert respons.json() == []


def test_standaard_inclusief_inactief_en_oplopend_op_id(catalogus_client) -> None:
    """4.1: standaard inclusief inactieve bronnen, gesorteerd op oplopend id."""
    ids = _catalogus_vullen(catalogus_client)
    lijst = catalogus_client.get("/api/sources").json()
    assert [item["id"] for item in lijst] == ids
    assert sorted(item["id"] for item in lijst) == ids
    assert {item["is_active"] for item in lijst} == {True, False}


def test_filter_is_active(catalogus_client) -> None:
    """4.1: `is_active=true` levert uitsluitend actieve bronnen."""
    _catalogus_vullen(catalogus_client)
    actief = catalogus_client.get("/api/sources", params={"is_active": "true"}).json()
    assert actief != []
    assert all(item["is_active"] for item in actief)
    inactief = catalogus_client.get("/api/sources", params={"is_active": "false"}).json()
    assert inactief and not any(item["is_active"] for item in inactief)


def test_filters_worden_als_and_gecombineerd(catalogus_client) -> None:
    """4.1: alleen bronnen die aan alle drie de filters voldoen worden geretourneerd."""
    _catalogus_vullen(catalogus_client)
    respons = catalogus_client.get(
        "/api/sources",
        params={"is_active": "true", "topic": "ai", "cloud_label": "azure"},
    )
    assert respons.status_code == 200
    assert [item["name"] for item in respons.json()] == ["Actief AI"]


def test_filter_zonder_matches_geeft_lege_lijst(catalogus_client) -> None:
    """4.1: een geldige combinatie zonder resultaat levert `[]`, geen fout."""
    _catalogus_vullen(catalogus_client)
    respons = catalogus_client.get(
        "/api/sources", params={"topic": "ethereum", "cloud_label": "otc"}
    )
    assert respons.status_code == 200
    assert respons.json() == []


@pytest.mark.parametrize(
    "params",
    [
        {"topic": "onbekend"},
        {"topic": "AI"},
        {"cloud_label": "google-cloud"},
        {"is_active": "ja"},
    ],
)
def test_ongeldige_filterwaarde_geeft_422(catalogus_client, params) -> None:
    """4.1: een filterwaarde buiten de woordenlijst -> 422."""
    _catalogus_vullen(catalogus_client)
    assert catalogus_client.get("/api/sources", params=params).status_code == 422


# ==== 4.2 Detail en PATCH zonder upsert ======================================


def test_detail_van_bestaand_record(catalogus_client) -> None:
    """4.2: detail geeft 200 met onderwerpen én cloudlabels."""
    ids = _catalogus_vullen(catalogus_client)
    respons = catalogus_client.get(f"/api/sources/{ids[0]}")
    assert respons.status_code == 200
    body = respons.json()
    assert body["id"] == ids[0]
    assert body["topics"] == ["ai"]
    assert body["cloud_labels"] == ["azure"]


def test_detail_onbekend_id_404(catalogus_client) -> None:
    """4.2: onbekend id -> 404 met de vaste melding."""
    respons = catalogus_client.get("/api/sources/9999")
    assert respons.status_code == 404
    assert respons.json() == {"detail": "bron bestaat niet"}


def test_patch_op_onbekend_id_maakt_geen_record_aan(catalogus_client) -> None:
    """4.2: PATCH op een onbekend id -> 404 en geen upsert."""
    respons = catalogus_client.patch("/api/sources/42", json={"name": "Nieuw"})
    assert respons.status_code == 404
    assert catalogus_client.get("/api/sources").json() == []
    assert catalogus_client.get("/api/sources/42").status_code == 404


# ==== 4.3 POST-statussen ======================================================


def test_post_geeft_201_met_opgeslagen_record(catalogus_client) -> None:
    """4.3: geldige POST -> 201 met de opgeslagen waarden."""
    respons = catalogus_client.post(
        "/api/sources",
        json=minimale_payload(topics=["linux"], reliability=4, website_url=None),
    )
    assert respons.status_code == 201
    body = respons.json()
    assert body["id"] == 1
    assert body["name"] == "Voorbeeld Feed"
    assert body["feed_url"] == "https://example.com/feed.xml"
    assert body["website_url"] is None
    assert body["reliability"] == 4
    assert body["is_active"] is False
    assert body["topics"] == ["linux"]
    assert body["cloud_labels"] == []


def test_post_duplicate_geeft_409_zonder_wijziging(catalogus_client) -> None:
    """4.3: dezelfde feed-URL (ook met ander schrijfpatroon) -> 409."""
    eerste = catalogus_client.post("/api/sources", json=minimale_payload())
    assert eerste.status_code == 201
    for variant in (
        "https://example.com/feed.xml",
        " HTTPS://Example.com/feed.xml ",
        "https://example.com:443/feed.xml",
    ):
        respons = catalogus_client.post(
            "/api/sources", json=minimale_payload(feed_url=variant, name="Ander")
        )
        assert respons.status_code == 409, variant
        assert respons.json() == {"detail": "feed-URL bestaat al"}
    assert len(catalogus_client.get("/api/sources").json()) == 1
    assert catalogus_client.get("/api/sources/1").json()["name"] == "Voorbeeld Feed"


def test_post_ongeldig_geeft_422_zonder_opslaan(catalogus_client) -> None:
    """4.3: ongeldige invoer -> 422 en geen record."""
    for payload in (
        minimale_payload(type="json"),
        minimale_payload(language="zz"),
        minimale_payload(reliability=True),
        minimale_payload(feed_url="/relatief.xml"),
        {k: v for k, v in minimale_payload().items() if k != "name"},
    ):
        assert catalogus_client.post("/api/sources", json=payload).status_code == 422
    assert catalogus_client.get("/api/sources").json() == []


# ==== 3.2 Unieke feed-identiteit, gedeelde website, concurrency ==============


def test_duplicate_tegenover_inactieve_bron_geeft_409(catalogus_client) -> None:
    """3.2: de UNIQUE-index geldt over actieve én inactieve bronnen."""
    aangelegd = catalogus_client.post(
        "/api/sources", json=minimale_payload(is_active=False)
    )
    assert aangelegd.status_code == 201
    assert catalogus_client.post(
        "/api/sources", json=minimale_payload(name="Tweede")
    ).status_code == 409


def test_gedeelde_website_url_levert_bei_201(catalogus_client) -> None:
    """3.2: `website_url` is niet uniek; twee kanalen mogen dezelfde site delen."""
    website = "https://voorbeeld.example/"
    eerste = catalogus_client.post(
        "/api/sources",
        json=minimale_payload(feed_url="https://example.com/1.xml",
                              website_url=website),
    )
    tweede = catalogus_client.post(
        "/api/sources",
        json=minimale_payload(feed_url="https://example.com/2.xml",
                              website_url=website),
    )
    assert eerste.status_code == 201
    assert tweede.status_code == 201
    assert {item["website_url"] for item in catalogus_client.get("/api/sources").json()} == {
        "https://voorbeeld.example/"
    }


def test_gelijktijdige_insert_met_zelfde_sleutel(catalogus_db) -> None:
    """3.2: precies één van twee gelijktijdige inserts slaagt, geen duplicaat."""
    payload = minimale_payload(name="Race")
    clients = [build_client(db_path=catalogus_db) for _ in range(2)]

    def _verzoek(client):
        return client.post("/api/sources", json=payload).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        statussen = sorted(pool.map(_verzoek, clients))

    assert statussen == [201, 409], statussen
    controle = build_client(db_path=catalogus_db)
    rijen = controle.get("/api/sources").json()
    assert len(rijen) == 1, "UNIQUE-index heeft geen duplicaat toegelaten"
    assert controle.get("/api/sources").status_code == 200  # geen corruptie


# ==== 3.3 PATCH-atomiciteit ===================================================


def _bron_met_relaties(client) -> dict:
    respons = client.post(
        "/api/sources",
        json=minimale_payload(
            topics=["ai", "linux"], cloud_labels=["azure"], reliability=3
        ),
    )
    assert respons.status_code == 201, respons.text
    return respons.json()


def test_patch_atomiciteit_ongeldige_eindtoestand(catalogus_client) -> None:
    """3.3: ongeldige eindtoestand -> 422 en record én relaties onveranderd."""
    voor = _bron_met_relaties(catalogus_client)
    respons = catalogus_client.patch(
        f"/api/sources/{voor['id']}",
        json={"name": "Gewijzigd", "topics": ["onbekend"], "cloud_labels": ["otc"]},
    )
    assert respons.status_code == 422
    na = catalogus_client.get(f"/api/sources/{voor['id']}").json()
    assert na == voor


def test_patch_conflict_laat_alles_onveranderd(catalogus_client) -> None:
    """3.3: feed-URL van een ander record -> 409 en niets gewijzigd."""
    eerste = _bron_met_relaties(catalogus_client)
    tweede = catalogus_client.post(
        "/api/sources", json=minimale_payload(feed_url="https://example.com/tweede.xml")
    )
    assert tweede.status_code == 201

    voor_eerste = catalogus_client.get(f"/api/sources/{eerste['id']}").json()
    voor_tweede = catalogus_client.get(f"/api/sources/{tweede.json()['id']}").json()
    respons = catalogus_client.patch(
        f"/api/sources/{tweede.json()['id']}",
        json={"feed_url": eerste["feed_url"]},
    )
    assert respons.status_code == 409
    assert respons.json() == {"detail": "feed-URL bestaat al"}
    assert catalogus_client.get(f"/api/sources/{tweede.json()['id']}").json() == voor_tweede
    assert catalogus_client.get(f"/api/sources/{eerste['id']}").json() == voor_eerste


def test_patch_weggelaten_velden_blijven_onveranderd(catalogus_client) -> None:
    """3.3: alleen `name` wijzigen laat taal en betrouwbaarheid met rust."""
    bron = _bron_met_relaties(catalogus_client)
    respons = catalogus_client.patch(f"/api/sources/{bron['id']}", json={"name": "Nieuw"})
    assert respons.status_code == 200
    body = respons.json()
    assert body["name"] == "Nieuw"
    assert body["language"] == bron["language"]
    assert body["reliability"] == bron["reliability"]
    assert body["topics"] == bron["topics"]
    assert body["cloud_labels"] == bron["cloud_labels"]


@pytest.mark.parametrize("veld", ["name", "language", "type", "topics", "is_active"])
def test_patch_null_alleen_voor_nullable_velden(catalogus_client, veld: str) -> None:
    """3.3: `null` is alleen toegestaan voor `website_url` en `reliability`."""
    bron = _bron_met_relaties(catalogus_client)
    respons = catalogus_client.patch(f"/api/sources/{bron['id']}", json={veld: None})
    if veld in ("website_url", "reliability"):
        assert respons.status_code == 200
    else:
        assert respons.status_code == 422
        assert catalogus_client.get(f"/api/sources/{bron['id']}").json() == bron


def test_patch_null_wist_nullable_veld(catalogus_client) -> None:
    """3.3: `null` wist `website_url` en `reliability`."""
    bron = catalogus_client.post(
        "/api/sources",
        json=minimale_payload(website_url="https://voorbeeld.example/",
                              reliability=5),
    ).json()
    respons = catalogus_client.patch(
        f"/api/sources/{bron['id']}", json={"reliability": None, "website_url": None}
    )
    assert respons.status_code == 200
    assert respons.json()["reliability"] is None
    assert respons.json()["website_url"] is None


def test_lege_patch_geeft_422(catalogus_client) -> None:
    """3.3: een PATCH zonder velden -> 422 en geen wijziging."""
    bron = _bron_met_relaties(catalogus_client)
    assert catalogus_client.patch(f"/api/sources/{bron['id']}", json={}).status_code == 422
    assert catalogus_client.get(f"/api/sources/{bron['id']}").json() == bron


# ==== 3.4 Vervangende lijstsemantiek =========================================


def test_patch_vervangt_volledige_onderwerpen_set(catalogus_client) -> None:
    """3.4: een aanwezige lijst vervangt de volledige set."""
    bron = _bron_met_relaties(catalogus_client)
    assert bron["topics"] == ["ai", "linux"]
    respons = catalogus_client.patch(f"/api/sources/{bron['id']}", json={"topics": ["ukraine"]})
    assert respons.status_code == 200
    assert respons.json()["topics"] == ["ukraine"]


def test_patch_lege_onderwerpen_set_wist_relaties(catalogus_client) -> None:
    """3.4: `[]` wist alle onderwerpen."""
    bron = _bron_met_relaties(catalogus_client)
    respons = catalogus_client.patch(f"/api/sources/{bron['id']}", json={"topics": []})
    assert respons.status_code == 200
    assert respons.json()["topics"] == []


def test_patch_vervangt_en_wist_cloudlabels(catalogus_client) -> None:
    """3.4: cloudlabels vervangen, `[]` wist alle labels."""
    bron = _bron_met_relaties(catalogus_client)
    assert bron["cloud_labels"] == ["azure"]
    vervangen = catalogus_client.patch(
        f"/api/sources/{bron['id']}", json={"cloud_labels": ["otc", "aws"]}
    )
    assert vervangen.status_code == 200
    assert set(vervangen.json()["cloud_labels"]) == {"aws", "otc"}
    gewist = catalogus_client.patch(
        f"/api/sources/{bron['id']}", json={"cloud_labels": []}
    )
    assert gewist.json()["cloud_labels"] == []


# ==== 3.5 Foutmapping en geen lekken =========================================


def _onbereikbare_client(tmp_path):
    return build_client(db_path=str(tmp_path / "ontbreekt" / "news.db"))


@pytest.mark.parametrize(
    "methode,pad,payload",
    [
        ("get", "/api/sources", None),
        ("get", "/api/sources/1", None),
        ("get", "/api/source-options", None),
        ("post", "/api/sources", minimale_payload()),
        ("patch", "/api/sources/1", {"name": "X"}),
    ],
)
def test_onbereikbare_database_geeft_503_met_vaste_melding(
    tmp_path, methode, pad, payload
) -> None:
    """3.5: onbereikbare database -> 503 met de vaste, begrensde melding."""
    client = _onbereikbare_client(tmp_path)
    if payload is None:
        respons = getattr(client, methode)(pad)
    else:
        respons = getattr(client, methode)(pad, json=payload)
    assert respons.status_code == 503, respons.text
    assert respons.json() == {"detail": "database onbereikbaar"}


@pytest.fixture
def foutresponsen(catalogus_client) -> list[str]:
    """Verzamelt alle catalogus-foutresponsen als tekst voor lekcontrole."""
    _bron_met_relaties(catalogus_client)
    tweede = catalogus_client.post(
        "/api/sources",
        json=minimale_payload(name="Tweede", feed_url="https://example.com/tweede.xml"),
    )
    assert tweede.status_code == 201, tweede.text
    onbereikbaar = build_client(db_path="/nonexistent/never-created.db")
    responses = [
        catalogus_client.get("/api/sources/404"),
        catalogus_client.post("/api/sources", json=minimale_payload()),
        catalogus_client.post("/api/sources", json=minimale_payload(type="json")),
        catalogus_client.get("/api/sources", params={"topic": "bogus"}),
        catalogus_client.patch("/api/sources/1", json={}),
        catalogus_client.patch("/api/sources/1", json={"feed_url": "https://example.com/tweede.xml"}),
        onbereikbaar.get("/api/sources"),
        onbereikbaar.post("/api/sources", json=minimale_payload()),
        build_client(db_path="/nonexistent/never-created.db").get("/api/sources/1"),
    ]
    for respons in responses:
        assert respons.status_code >= 400, respons.text
    return [respons.text for respons in responses]


def test_foutresponsen_lekken_geen_interne_details(foutresponsen) -> None:
    """3.5: geen SQL, geen stacktrace en geen lokaal pad in foutresponsen."""
    verboden = (
        "select ", "insert ", "update ", "delete from", "pragma",
        "traceback", "sqlite3", ".py", "/home/", "/app/data", "file "
    )
    for tekst in foutresponsen:
        laag = tekst.lower()
        for sleutelwoord in verboden:
            assert sleutelwoord not in laag, f"{sleutelwoord!r} lekt in {tekst!r}"


def test_foutresponsen_zijn_begrensd_en_json(catalogus_client, foutresponsen) -> None:
    """3.5: elke foutbody is één korte JSON-regel met een vaste melding."""
    for tekst in foutresponsen:
        assert len(tekst) < 200, tekst
        assert "\n" not in tekst, tekst
        assert isinstance(json.loads(tekst), dict), tekst


# ==== 5.1 Opties-endpoint =====================================================


def test_opties_bevatten_vier_onderdelen(catalogus_client) -> None:
    """5.1: precies de sleutels onderwerpen, typen, taalbeleid en cloudlabels."""
    respons = catalogus_client.get("/api/source-options")
    assert respons.status_code == 200
    body = respons.json()
    assert list(body.keys()) == ["topics", "types", "languages", "cloud_labels"]
    assert body["types"] == ["rss", "atom"]
    assert "und" in body["languages"] and "mul" in body["languages"]
    assert len(body["languages"]) == 186


def test_opties_cloudlabels_exact(catalogus_client) -> None:
    """5.1: de cloudlabels zijn exact de zes toegestane waarden."""
    body = catalogus_client.get("/api/source-options").json()
    assert body["cloud_labels"] == [
        "azure",
        "aws",
        "t-cloud",
        "otc",
        "multi-cloud",
        "sovereign-cloud",
    ]


def test_opties_onderwerpen_zijn_de_woordenlijst(catalogus_client) -> None:
    """5.1: de onderwerpen staan oplopend en komen uit de woordenlijst."""
    from app.sources_validation import TOPIC_SLUGS

    body = catalogus_client.get("/api/source-options").json()
    assert set(body["topics"]) == set(TOPIC_SLUGS)
    assert body["topics"] == sorted(body["topics"])


# ==== 5.2 Geen aanvullende of wijzigingsroutes =================================


def _api_routes(app) -> set[tuple[str, str]]:
    """(methode, pad) van alles wat de app daadwerkelijk declareert (OpenAPI)."""
    paden = app.openapi().get("paths", {})
    return {
        (methode.upper(), pad)
        for pad, methoden in paden.items()
        if pad.startswith("/api")
        for methode in methoden
    }


def test_exact_vijf_catalogusroutes(catalogus_client) -> None:
    """4.4/5.2: uitsluitend de vijf routes uit de delta-spec staan gedeclareerd."""
    assert _api_routes(catalogus_client.app) == {
        ("GET", "/api/sources"),
        ("GET", "/api/sources/{source_id}"),
        ("POST", "/api/sources"),
        ("PATCH", "/api/sources/{source_id}"),
        ("GET", "/api/source-options"),
    }


@pytest.mark.parametrize(
    "methode,pad",
    [
        ("get", "/api/options"),
        ("post", "/api/source-options/extra"),
        ("get", "/api/sources/1/activate"),
        ("put", "/api/sources/1/archive"),
        ("delete", "/api/source-options/topics/ai"),
        ("get", "/api/sources/1/export"),
    ],
)
def test_niet_gedeclareerde_route_geeft_404(catalogus_client, methode, pad) -> None:
    """5.2: elke niet-gedeclareerde route geeft 404 (geen verborgen routes)."""
    assert getattr(catalogus_client, methode)(pad).status_code == 404


@pytest.mark.parametrize(
    "methode,pad",
    [
        ("post", "/api/source-options"),
        ("patch", "/api/source-options"),
        ("put", "/api/source-options"),
        ("delete", "/api/source-options"),
        ("delete", "/api/sources"),
        ("delete", "/api/sources/1"),
        ("put", "/api/sources"),
    ],
)
def test_geen_opties_wijzigingsroutes_en_geen_delete(
    catalogus_client, methode, pad
) -> None:
    """5.2: alleen de gedeclareerde methoden bestaan; wijzigen/verwijderen niet."""
    respons = getattr(catalogus_client, methode)(pad)
    assert respons.status_code == 405, respons.text
    toegestaan = set(respons.headers.get("allow", "").split(", "))
    assert "GET" in toegestaan
    assert "DELETE" not in toegestaan


def test_opties_ongewijzigd_na_catalogusschrijfactie(catalogus_client) -> None:
    """5.2: een catalogusschrijfactie verandert de opties niet."""
    voor = catalogus_client.get("/api/source-options").json()
    assert catalogus_client.post(
        "/api/sources", json=minimale_payload(topics=["ai"], cloud_labels=["aws"])
    ).status_code == 201
    assert catalogus_client.get("/api/source-options").json() == voor


# ==== Extra: PATCH-updates blijven beperkt tot de vijf routes =================


def test_patch_geeft_200_voor_geldige_wijziging(catalogus_client) -> None:
    """4.2: PATCH op een bestaand record -> 200 met het bijgewerkte record."""
    bron = _bron_met_relaties(catalogus_client)
    respons = catalogus_client.patch(f"/api/sources/{bron['id']}", json={"name": "Nieuwe naam"})
    assert respons.status_code == 200
    assert respons.json()["name"] == "Nieuwe naam"
    assert catalogus_client.get(f"/api/sources/{bron['id']}").json() == respons.json()
