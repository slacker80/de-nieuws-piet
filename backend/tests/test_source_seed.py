"""Handmatig beoordeelde, offline seed (taken 6.1 t/m 6.3)."""

from __future__ import annotations

import json
import sqlite3

import pytest

from app.db import init_database
from app.db_migrate import migrate
from app.source_seed import DEFAULT_SEED_FILE, SeedError, load_seed, main, seed
from app.sources_validation import (
    CLOUD_LABELS,
    SOURCE_TYPES,
    TOPIC_SLUGS,
    SourceValidationError,
    canonicalize_url,
    validate_source,
    with_defaults,
)
from tests.conftest import build_client

pytestmark = pytest.mark.usefixtures("socket_guard")


def _seedbron() -> dict:
    return json.loads(DEFAULT_SEED_FILE.read_text(encoding="utf-8"))


def _rijen(db_path: str) -> list[tuple]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            "SELECT id, name, feed_url, feed_url_key, website_url, type, language, "
            "reliability, is_active FROM sources ORDER BY id"
        ).fetchall()


def _relaties(db_path: str) -> tuple[list[tuple], list[tuple]]:
    with sqlite3.connect(db_path) as connection:
        topics = connection.execute(
            "SELECT source_id, topic_slug FROM source_topics ORDER BY source_id, topic_slug"
        ).fetchall()
        labels = connection.execute(
            "SELECT source_id, cloud_label FROM source_cloud_labels "
            "ORDER BY source_id, cloud_label"
        ).fetchall()
    return topics, labels


# ==== 6.1 Beoordeelde starterset ==============================================


def test_seedbestand_bestaat_in_repo() -> None:
    """6.1: de starterset staat als lokaal bestand in de repo (geen netwerk)."""
    assert DEFAULT_SEED_FILE.is_file()
    assert DEFAULT_SEED_FILE.parent.name == "app"
    bron = _seedbron()
    assert bron["capability"] == "source-catalog"
    assert isinstance(bron["sources"], list) and bron["sources"]


@pytest.mark.parametrize("index", range(len(json.loads(DEFAULT_SEED_FILE.read_text())["sources"])))
def test_elke_seed_entry_doorstaat_url_validatie(index: int) -> None:
    """6.1: elke feed-URL doorstaat de canonicalisatie en de rejectieregels."""
    entry = _seedbron()["sources"][index]
    sleutel = canonicalize_url(entry["feed_url"])
    assert sleutel.startswith("https://") or sleutel.startswith("http://")
    assert "#" not in entry["feed_url"]
    if entry.get("website_url"):
        assert canonicalize_url(entry["website_url"])


@pytest.mark.parametrize("index", range(len(json.loads(DEFAULT_SEED_FILE.read_text())["sources"])))
def test_elke_seed_entry_is_volledig_geldig(index: int) -> None:
    """6.1: elke entry voldoet aan de volledige veld-, taal- en woordenlijstvalidatie."""
    entry = _seedbron()["sources"][index]
    record = validate_source(with_defaults({k: v for k, v in entry.items()
                                            if k != "reviewed"}))
    assert record.name and record.feed_url_key
    assert record.type in SOURCE_TYPES
    assert set(record.topics) <= set(TOPIC_SLUGS)
    assert set(record.cloud_labels) <= set(CLOUD_LABELS)


def test_geen_onbevestigde_urls() -> None:
    """6.1: elke entry draagt een beoordelingsdatum en de set is uniek."""
    bron = _seedbron()
    sleutels = [canonicalize_url(entry["feed_url"]) for entry in bron["sources"]]
    assert len(set(sleutels)) == len(sleutels), "dubbele feed-URL in de seed"
    for entry in bron["sources"]:
        assert entry.get("reviewed"), f"{entry['name']} mist beoordeling"
        assert entry["reviewed"] == bron["reviewed_on"]
        assert entry["feed_url"].startswith("https://"), entry["feed_url"]


def test_beoordelingscriteria_zijn_vastgelegd() -> None:
    """6.1: de beoordelingscriteria staan in het seedbestand zelf."""
    criteria = _seedbron()["review_criteria"]
    assert "officiële" in criteria and "handmatig" in criteria
    assert "aggregators" in criteria


# ==== 6.2 Insert-only seedoperatie ===========================================


def _lege_database(tmp_path) -> str:
    pad = str(tmp_path / "seed.db")
    init_database(pad)
    assert migrate(pad) == "migrated"
    return pad


def test_eerste_run_vult_de_starters(tmp_path) -> None:
    """6.2: één seed-run op een lege v2-database vult alle starters."""
    pad = _lege_database(tmp_path)
    resultaat = seed(pad)
    assert len(resultaat["added"]) == len(_seedbron()["sources"])
    assert resultaat["existing"] == []
    assert len(_rijen(pad)) == len(_seedbron()["sources"])
    # Na handmatige beoordeling mogen de starters expliciet actief zijn.
    assert all(rij[8] == 1 for rij in _rijen(pad))


def test_herhaling_is_idempotent(tmp_path) -> None:
    """6.2: een tweede run voegt niets toe en verandert niets."""
    pad = _lege_database(tmp_path)
    seed(pad)
    voor = (_rijen(pad), _relaties(pad))
    tweede = seed(pad)
    assert tweede["added"] == []
    assert len(tweede["existing"]) == len(_seedbron()["sources"])
    assert (_rijen(pad), _relaties(pad)) == voor


def test_seed_no_overwrite_bewaart_gebruikerswijziging(tmp_path) -> None:
    """6.2: een handmatig gewijzigd starter-record blijft ongewijzigd."""
    pad = _lege_database(tmp_path)
    seed(pad)
    with sqlite3.connect(pad) as connection:
        connection.execute(
            "UPDATE sources SET name = 'Handmatig gewijzigd', is_active = 0, "
            "reliability = 1 WHERE id = (SELECT id FROM sources LIMIT 1)"
        )
        gewijzigd = connection.execute(
            "SELECT name, is_active, reliability FROM sources ORDER BY id LIMIT 1"
        ).fetchone()
    seed(pad)
    with sqlite3.connect(pad) as connection:
        na = connection.execute(
            "SELECT name, is_active, reliability FROM sources ORDER BY id LIMIT 1"
        ).fetchone()
    assert na == gewijzigd


def test_ontbrekende_starter_wordt_aangevuld(tmp_path) -> None:
    """6.2: één ontbrekende starter wordt toegevoegd, de rest blijft zoals het is."""
    pad = _lege_database(tmp_path)
    seed(pad)
    with sqlite3.connect(pad) as connection:
        slachtoffer = connection.execute(
            "SELECT id FROM sources ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        verwijderde = connection.execute(
            "SELECT name FROM sources WHERE id = ?", (slachtoffer,)
        ).fetchone()[0]
        connection.execute("DELETE FROM sources WHERE id = ?", (slachtoffer,))
        voor_ids = connection.execute(
            "SELECT id FROM sources ORDER BY id"
        ).fetchall()
    tweede = seed(pad)
    assert verwijderde in tweede["added"]
    with sqlite3.connect(pad) as connection:
        namen = {rij[0] for rij in connection.execute("SELECT name FROM sources")}
    assert verwijderde in namen
    assert len(namen) == len(_seedbron()["sources"])
    with sqlite3.connect(pad) as connection:
        overgebleven = connection.execute(
            "SELECT id FROM sources ORDER BY id"
        ).fetchall()
    assert overgebleven[: len(voor_ids)] == voor_ids


def test_onbekende_seed_velden_worden_geweigerd(tmp_path) -> None:
    """6.2: een onbekende veldnaam in het seedbestand blokkeert de hele seed."""
    pad = _lege_database(tmp_path)
    slecht = tmp_path / "slecht.json"
    slecht.write_text(
        json.dumps({"sources": [dict(_seedbron()["sources"][0], bogus="x")]}),
        encoding="utf-8",
    )
    with pytest.raises(SeedError):
        load_seed(slecht)
    with pytest.raises(SeedError):
        seed(pad, seed_file=slecht)
    assert _rijen(pad) == []


def test_ongeldige_entry_laat_geen_halve_seed_achter(tmp_path) -> None:
    """6.2: alle entries worden eerst gevalideerd; één fout voorkomt elke insert."""
    pad = _lege_database(tmp_path)
    geldig = dict(_seedbron()["sources"][0])
    ongeldig = dict(_seedbron()["sources"][1], language="zz")
    with pytest.raises(SourceValidationError):
        seed(pad, entries=[geldig, ongeldig])
    assert _rijen(pad) == []


def test_seed_wordt_niet_uitgevoerd_bij_appstart(tmp_path) -> None:
    """6.2: applicatie-start initialiseert en migreert, maar voert de seed niet uit."""
    pad = str(tmp_path / "appstart.db")
    with build_client(db_path=pad, init_db=True) as client:
        assert client.get("/api/sources").status_code == 200
        assert client.get("/api/sources").json() == []
    with sqlite3.connect(pad) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0


def test_seed_wordt_niet_uitgevoerd_bij_migratie(tmp_path) -> None:
    """6.2: de migratie levert een lege catalogus; de seed is een aparte stap."""
    pad = str(tmp_path / "migratie.db")
    init_database(pad)
    assert migrate(pad) == "migrated"
    with sqlite3.connect(pad) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0


def test_seed_weigert_database_op_versie_1(tmp_path, capsys) -> None:
    """6.2: de CLI weigert een niet-gemigreerde database zonder te schrijven."""
    pad = str(tmp_path / "versie1.db")
    init_database(pad)
    assert main([pad]) == 1
    fout = capsys.readouterr().err
    assert "schema-versie 2" in fout
    with sqlite3.connect(pad) as connection:
        tabellen = {
            rij[0]
            for rij in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "sources" not in tabellen, "de weigerde seed mag niets hebben aangemaakt"


def test_seed_cli_geeft_0_en_is_herhaalbaar(tmp_path, capsys) -> None:
    """6.2: de CLI meldt het resultaat en is bij herhaling idempotent."""
    pad = _lege_database(tmp_path)
    assert main([pad]) == 0
    uitvoer = capsys.readouterr().out
    assert f"toegevoegd: {len(_seedbron()['sources'])}" in uitvoer
    assert "OK: seed uitgevoerd (insert-only, offline)" in uitvoer
    assert main([pad]) == 0
    tweede = capsys.readouterr().out
    assert "toegevoegd: 0" in tweede


def test_seedbestand_met_structuurfout_wordt_geweigerd(tmp_path) -> None:
    """6.2: een onleesbaar of onvolledig seedbestand wordt expliciet geweigerd."""
    leeg = tmp_path / "leeg.json"
    leeg.write_text("{}", encoding="utf-8")
    with pytest.raises(SeedError):
        load_seed(leeg)
    ontbreekt = tmp_path / "bestaat-niet.json"
    with pytest.raises(SeedError):
        load_seed(ontbreekt)
    ongeldig = tmp_path / "ongeldig.json"
    ongeldig.write_text(
        json.dumps({"sources": [{"name": "Zonder beoordeling"}]}), encoding="utf-8"
    )
    with pytest.raises(SeedError):
        load_seed(ongeldig)


# ==== 6.3 Volledig offline ====================================================


def test_seed_opent_geen_sockets(tmp_path) -> None:
    """6.3: de hele seed-operatie verloopt offline (socket-guard rond seed)."""
    pad = _lege_database(tmp_path)
    resultaat = seed(pad)
    assert len(resultaat["added"]) > 0
    # Herhaling eveneens: geen enkel netwerkcontact, alle sleutels lokaal afgeleid.
    assert seed(pad)["added"] == []
    for entry in _seedbron()["sources"]:
        assert canonicalize_url(entry["feed_url"])


def test_seed_gebruikt_uitsluitend_lokale_bestanden(tmp_path) -> None:
    """6.3: de seed leest alleen het in de repo opgenomen JSON-bestand."""
    pad = _lege_database(tmp_path)
    seed(pad)
    with sqlite3.connect(pad) as connection:
        for (sleutel,) in connection.execute("SELECT feed_url_key FROM sources"):
            assert sleutel.startswith("http")
            assert " " not in sleutel
