"""Documentatie-afstemming (taken 1.5, 2.6, 4.4, 6.4 en 7.4).

Controleert dat `docs/source-catalog.md` exact datgene beschrijft wat de code en
de tests daadwerkelijk doen: migratiestappen, URL-/taal-/woordenlijstvoorbeelden,
de vijf routes, de handmatige seed en de bestaande backup/restore.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.db_migrate import CATALOG_SCHEMA_STATEMENTS, SCHEMA_VERSION
from tests import runtime_env

pytestmark = pytest.mark.usefixtures("socket_guard")

DOC = runtime_env.ROOT / "docs" / "source-catalog.md"
BACKEND = runtime_env.ROOT / "backend"


def _doc() -> str:
    assert DOC.is_file(), f"ontbreekt: {DOC}"
    return DOC.read_text(encoding="utf-8")


def _testbron(*namen: str) -> str:
    return "\n".join(
        (BACKEND / "tests" / f"{naam}.py").read_text(encoding="utf-8") for naam in namen
    )


# ==== 1.5 Migratiestappen =====================================================


def _gedocumenteerde_stappen(tekst: str) -> list[str]:
    """Objectnamen uit de bestelde migratietabel (rijen `| n | omschrijving |`)."""
    stappen: list[str] = []
    for regel in tekst.splitlines():
        match = re.match(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*$", regel)
        if match:
            stappen.append(match.group(2))
    return stappen


def test_migratiestappen_staan_in_documentatie() -> None:
    """1.5: de versiegestuurde stappen zijn lokaal gedocumenteerd."""
    tekst = _doc()
    assert "python -m app.db_migrate" in tekst
    stappen = _gedocumenteerde_stappen(tekst)
    assert len(stappen) >= 7, f"verwacht minstens 7 gedocumenteerde stappen: {stappen}"


def test_migratiestappen_komen_overeen_met_de_migratie() -> None:
    """1.5: de gedocumenteerde volgorde is de volgorde van de echte migratie."""
    tekst = _doc()
    documentatie = " ".join(_gedocumenteerde_stappen(tekst))
    tabellen = re.findall(
        r"CREATE TABLE IF NOT EXISTS\s+(\w+)", " ".join(CATALOG_SCHEMA_STATEMENTS), re.I
    )
    assert tabellen, "geen tabellen in de migratie"
    for naam in tabellen:
        if naam == "app_meta":
            continue  # bestaat al uit v1; wordt in de documentatie als stap 7 genoemd
        assert naam in documentatie, f"tabel {naam} ontbreekt in de documentatie"
    # Volgorde: de documentatie noemt `topics` vóór `sources`, net als de migratie.
    assert documentatie.index("topics") < documentatie.index("sources")
    assert "ux_sources_feed_url_key" in tekst
    assert "PRAGMA foreign_key_check" in tekst
    assert str(SCHEMA_VERSION) in tekst


def test_migratiegedrag_is_gedocumenteerd() -> None:
    """1.5: noop, weigering en rollback zijn beschreven zoals de tests ze toetsen."""
    tekst = _doc()
    for onderdeel in ("noop", "weigering", "rollback", "PRAGMA foreign_keys"):
        assert onderdeel in tekst, f"{onderdeel} niet gedocumenteerd"
    bron = _testbron("test_source_migration")
    for onderdeel in ("migrated", "noop", "foreign_key_check", "rollback"):
        assert onderdeel in bron


def test_bootstrap_versiemarkerregel_is_gedocumenteerd_en_getest() -> None:
    """1.5: de markerregel van `init_database` staat in de doc én in de tests."""
    tekst = _doc()
    for onderdeel in (
        "init_database",
        "schema_version",
        "versiemarker",
        "geen enkele byte",
        "mode=ro",
        "bootstrap_marker",
        "MigrationError",
        "BEGIN IMMEDIATE",
        "TOCTOU",
        "sidecar",
    ):
        assert onderdeel in tekst, f"{onderdeel} niet gedocumenteerd"
    bron = _testbron("test_db_lifespan")
    for onderdeel in ("init_database", "MigrationError", "_hash", "TestClient", "_snapshot"):
        assert onderdeel in bron, f"{onderdeel} niet getest"
    race = _testbron("test_db_concurrency")
    for onderdeel in ("BEGIN IMMEDIATE", "MigrationError", "threading"):
        assert onderdeel in race, f"{onderdeel} niet in de concurrentietests"


# ==== 2.6 URL-regels, taalbeleid en woordenlijsten ===========================


@pytest.mark.parametrize(
    "voorbeeld",
    [
        " HTTPS://WWW.Example.COM:443  ",
        "https://www.example.com/",
        "https://Example.com/News/RSS/",
        "https://example.com/News/RSS/",
        "https://example.com/feed?b=2&a=1",
        "http://example.com:8080/x",
        "https://example.com/a%2Fb",
        "https://example.com/feed#section",
        "https://user:pass@example.com/feed",
        "https://example.com/ feed",
        "https://example.com/%zz",
        "https://example.com/a/../b",
        "/feed.xml",
        "https://example.com:99999/feed",
        "https://xn--bcher-kva.example/feed",
    ],
)
def test_url_voorbeeld_staat_in_documentatie_en_in_tests(voorbeeld: str) -> None:
    """2.6: elk gedocumenteerd URL-voorbeeld is een assertie in de tests 2.1/2.2/2.3."""
    assert voorbeeld in _doc(), f"voorbeeld ontbreekt in de documentatie: {voorbeeld}"
    assert voorbeeld in _testbron("test_source_url"), (
        f"voorbeeld komt niet voor in tests/test_source_url.py: {voorbeeld}"
    )


@pytest.mark.parametrize(
    "code", ["und", "mul", "nl", "en", "de", "uk", "ar", "zz"]
)
def test_taalbeleid_staat_in_documentatie_en_in_tests(code: str) -> None:
    """2.6: taalbeleid (`und`/`mul` en de afkeurcode `zz`) is in beide vastgelegd."""
    assert f"`{code}`" in _doc() or f'"{code}"' in _doc(), code
    bron = _testbron("test_source_validation")
    assert f'"{code}"' in bron, f"taalcode {code} niet getest"


def test_woordenlijsten_komen_exact_overeen() -> None:
    """2.6: onderwerpen, cloudlabels en typen in de doc zijn exact de code-lijsten."""
    from app.sources_validation import CLOUD_LABELS, SOURCE_TYPES, TOPIC_SLUGS

    tekst = _doc()
    for slug in TOPIC_SLUGS:
        assert f"`{slug}`" in tekst, f"onderwerp {slug} niet gedocumenteerd"
    for label in CLOUD_LABELS:
        assert f"`{label}`" in tekst, f"cloudlabel {label} niet gedocumenteerd"
    for type_ in SOURCE_TYPES:
        assert f"`{type_}`" in tekst, f"type {type_} niet gedocumenteerd"
    assert "184 ISO 639-1" in tekst
    bron = _testbron("test_source_validation", "test_source_api")
    for label in CLOUD_LABELS:
        assert f'"{label}"' in bron
    # De tests toetsen de woordenlijst tegen de code-lijst zelf (geen kopie),
    # plus expliciete onbekende/dubbele items.
    assert "TOPIC_SLUGS" in bron and "CLOUD_LABELS" in bron
    for slug in ("ai", "linux", "kubernetes", "ukraine"):
        assert f'"{slug}"' in bron, f"onderwerp {slug} niet expliciet getest"


def test_reliability_en_statusvoorbeelden_zijn_getest() -> None:
    """2.6: de gedocumenteerde validatiegevallen staan als assertie in de tests."""
    tekst = _doc()
    assert "`null` of een echte integer 1..5" in tekst
    bron = _testbron("test_source_validation")
    for waarde in ("4.5", '"4"', "0", "6", "True", "False"):
        assert waarde in bron, f"reliability-voorbeeld {waarde} niet getest"


# ==== 4.4 API-contract ========================================================


def _gedocumenteerde_routes(tekst: str) -> set[str]:
    return set(re.findall(r"`(GET|POST|PATCH|DELETE|PUT)`\s*\|\s*`(/api/[^`]+)`", tekst))


def test_documentatie_noemt_exact_de_vijf_routes() -> None:
    """4.4: de documentatie noemt exact de vijf routes uit de delta-spec."""
    routes = _gedocumenteerde_routes(_doc())
    assert routes == {
        ("GET", "/api/sources"),
        ("GET", "/api/sources/{id}"),
        ("POST", "/api/sources"),
        ("PATCH", "/api/sources/{id}"),
        ("GET", "/api/source-options"),
    }, routes


def test_documentatie_suggereert_geen_andere_routes() -> None:
    """4.4: geen DELETE/PUT-route, geen opties-CRUD en geen pagination."""
    tekst = _doc()
    for pad in re.findall(r"`(/api/[^`]+)`", tekst):
        assert pad in (
            "/api/sources",
            "/api/sources/{id}",
            "/api/source-options",
        ), f"onverwacht pad in de documentatie: {pad}"
    assert "geen `DELETE`" in tekst
    assert "geen pagination" in tekst.lower() or "geen pagination." in tekst


def test_documentatie_beschrijft_filters_en_statuscodes() -> None:
    """4.4: filters, responsvelden en de vier foutstatussen staan erin."""
    tekst = _doc()
    for onderdeel in (
        "is_active", "topic", "cloud_label", "AND",
        "404", "409", "422", "503",
        "bron bestaat niet", "feed-URL bestaat al", "database onbereikbaar",
        "feed_url_key", "is_active", "topics", "cloud_labels",
    ):
        assert onderdeel in tekst, f"{onderdeel} ontbreekt in het API-contract"
    assert "oplopend" in tekst


# ==== 6.4 Seed-documentatie ====================================================


def test_seed_documentatie_beschrijft_handmatige_start() -> None:
    """6.4: de documentatie beschrijft hoe de seed handmatig wordt gestart."""
    tekst = _doc()
    assert "python -m app.source_seed" in tekst
    assert "nooit bij applicatie-start" in tekst or "**nooit** bij applicatie-start" in tekst
    assert "APP_DB_PATH" in tekst
    assert "Exit codes" in tekst or "exit codes" in tekst.lower()


def test_seed_documentatie_beschrijft_beoordelingscriteria() -> None:
    """6.4: de beoordelingscriteria voor een starter zijn vastgelegd."""
    tekst = _doc()
    for criterium in ("officiële", "handmatig", "aggregators", "reviewed"):
        assert criterium in tekst, f"criterium {criterium!r} ontbreekt"


def test_seed_documentatie_beschrijft_no_overwrite() -> None:
    """6.4: herhaling wijzigt nooit bestaande records."""
    tekst = _doc()
    assert "nooit gewijzigd of overschreven" in tekst
    assert "insert-only" in tekst
    bron = _testbron("test_source_seed")
    assert "test_seed_no_overwrite_bewaart_gebruikerswijziging" in bron
    assert "test_herhaling_is_idempotent" in bron


# ==== 7.4 Backup/restore-documentatie =========================================


def test_backup_documentatie_beschrijft_de_bestaande_procedure() -> None:
    """7.4: de bestaande procedure uit `data-safe-rollback-restore.md` wordt gevolgd."""
    tekst = _doc()
    assert "data-safe-rollback-restore.md" in tekst
    for subcommando in ("backup", "validate", "restore", "preserve", "reset"):
        assert f"scripts/db-rollback.sh {subcommando}" in tekst, subcommando
    assert "PRAGMA integrity_check" in tekst


def test_backup_documentatie_noemt_catalogus_als_bewaarde_data() -> None:
    """7.4: de catalogus is expliciet als bewaarde data bij restore benoemd."""
    tekst = _doc()
    for tabel in ("sources", "source_topics", "source_cloud_labels", "topics"):
        assert f"`{tabel}`" in tekst, f"tabel {tabel} niet als bewaarde data genoemd"
    assert "schema-versie 2" in tekst
    assert "tests/test_source_backup_restore.py" in tekst


def test_geen_nieuwe_backupfunctie_in_documentatie() -> None:
    """7.4: er wordt geen nieuwe backupfunctie beschreven, alleen het bestaande script."""
    tekst = _doc()
    assert "geen aparte catalogus-backupfunctie" in tekst
    assert (runtime_env.ROOT / "scripts" / "db-rollback.sh").is_file()
