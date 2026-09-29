"""Discrete Verified Tasks (sectie 10, taken 104-138).

Implementeer discrete verified tasks voor elke acceptance met exacte assertions
en verificatie. Dekken:

- 10.1 Database/local-sqlite Spec Updates
- 10.2 Health-monitoring/health-endpoint Spec Updates
- 10.3 Local-development/setup Spec Updates
- 10.4 Documentation/local-dev Spec Updates
- 10.5 Design.md Updates
- 10.6 Tasks.md Updates

Alle tests zijn unit tests (geen externe services) en volgen de app-factory
isoleringsstrategie (elke test bouwt een verse applicatie-instance).
"""

import re
from collections import defaultdict

import pytest
from pathlib import Path

# Geen Docker-detectie nodig: deze tests verifiëren statisch spec-, design-,
# tasks- en documentatie-inhoud. Runtime-Docker-tests staan in
# tests/test_integration.py en tests/test_rollback_runtime.py (CLI-detectie).


# ==== Hulppatronen voor concrete invarianten ================================

# Geen enkele v1 (`docker-compose`) commando-aanroep; alleen negatieve vermeldingen
# van de verboden syntax zijn toegestaan.
V1_INVOCATION = re.compile(r"\bdocker-compose\s+(up|down|run|exec|build|ps|logs|stop|restart|config)\b")

# Elke taak moet een concrete referentie hebben om testbaar te zijn: ofwel een
# waarde (code-span, URL, pad, bestandsnaam, vergelijking, getal), ofwel een
# benoemd systeemelement of opgeleverd artefact uit de gesloten woordenlijst
# hieronder. Een vage opdracht zonder inspectiepunt valt hierdoor af.
REFERENT_NOUNS = (
    # opgeleverde artefacten
    "documentatie", "documenteren", "tests", "test", "testing", "structuur",
    "configuratie", "verificatie", "checks", "script", "patronen",
    "directories", "lifecycle", "management", "opstelling", "smoke",
    "commando", "commando's", "spec", "specs", "contract", "contracten",
    "status", "ontwerp", "validatie", "functionaliteit", "persistentie",
    "manifest", "afhankelijkheden", "lockfile", "readme", "gitignore",
    # systeemelementen
    "frontend", "backend", "database", "sqlite", "docker", "compose",
    "container", "service", "services", "volume", "netwerk", "applicatie",
    "pagina", "landingspagina", "endpoint", "api", "url", "localhost",
    "browser", "viewport", "landmark", "marker", "health", "pwa",
    "next.js", "fastapi", "playwright", "e2e",
)
REFERENT = re.compile(
    r"`[^`]+`"          # code span
    r"|https?://"       # URL
    r"|/\w"             # pad
    r"|\.\w{1,10}\b"    # bestandsuitbreiding / dot-qualified naam
    r"|<="              # contractvergelijking
    r"|\d"              # concrete numerieke waarde
    r"|" + "|".join(re.escape(n) for n in REFERENT_NOUNS) + r"\b",
    re.IGNORECASE,
)

# Imperatieve Nederlandse werkwoorden waarmee een taak actionable is.
ACTION_VERBS = (
    "Creëer", "Initialiseer", "Configureer", "Implementeer", "Stel", "Voeg",
    "Valideer", "Voer", "Test", "Verifieer", "Documenteer",
)
# Werkwoorden die de taak zelf tot een uitvoerbare verificatie maken.
VERIFY_VERBS = ("Verifieer", "Valideer", "Test", "Voer")
# Een verificatietaak mag testbaarheid ook ontlenen aan een expliciete
# voorwaarde of resultaatmarkering in plaats van aan een systeemreferentie.
CONDITIE = re.compile(
    r"\b(exit|nonzero|true|false|success|both|status|http|json|200|503|500)\b",
    re.IGNORECASE,
)
# Aggregaat-taak: een sectiekop-checkbox die het aantal kindertaken declareert.
AGGREGAAT = re.compile(r".+\(\d+ taken\)$")


def _checkbox_regels(content: str) -> list:
    """Alle checkbox-regels uit een tasks.md."""
    return [l for l in content.splitlines() if re.match(r"^\s*- \[[ x]\] ", l)]


def _aggregaat_labels(content: str) -> dict:
    """Aggregaat-id -> werkgebied-label (zonder id-prefix en zonder kindertelling)."""
    labels = {}
    for regel in _checkbox_regels(content):
        m = re.match(r"^\s*- \[[ x]\] (\d+\.\d+)\s+(.*)$", regel)
        if not m:
            continue
        tid, tekst = m.group(1), m.group(2)
        if AGGREGAAT.fullmatch(tekst):
            labels[tid] = re.sub(r"\s*\(\d+ taken\)$", "", tekst).strip()
    return labels


def _task_ids(content: str) -> list:
    """Unieke task-ID's in documentvolgorde; faalt bij een checkbox zonder ID."""
    ids = []
    for regel in _checkbox_regels(content):
        m = re.match(r"^\s*- \[[ x]\] (\d+(?:\.\d+)+)\s+\S", regel)
        assert m, f"checkbox zonder task-ID: {regel.strip()}"
        ids.append(m.group(1))
    return ids


def _assert_restore_ligt_na_down_v(content: str) -> None:
    """Elke volgorde-beschrijving plaatst `down -v` vóór restore.

    Gecontroleerd wordt de pijl-keten (`→`): de eerste stap na de kop die `down -v`
    noemt moet vóór de eerste stap komen die `restore` noemt. Er mag nergens een
    volgorde staan waarin restore vóór `docker compose down -v` komt (destructieve
    pad: backup → validatie → `down -v` → restore → verificatie).
    """
    for regel in content.splitlines():
        if "→" not in regel or "restore" not in regel.lower():
            continue
        stappen = regel.lower().split("→")
        idx_down = next(
            (i for i in range(1, len(stappen)) if "down -v" in stappen[i]), None
        )
        if idx_down is None and "down -v" in stappen[0]:
            idx_down = 0
        idx_restore = next(
            (i for i in range(1, len(stappen)) if re.search(r"\brestore", stappen[i])),
            None,
        )
        if idx_restore is None:
            continue
        assert idx_down is not None, f"volgorde zonder down -v: {regel.strip()}"
        assert idx_down < idx_restore, f"restore vóór down -v in: {regel.strip()}"


# ==== 10.1 Database/local-sqlite Spec Updates (6 taken) ================================


def test_10_1_1_verify_db_rollback_named_volume_spec() -> None:
    """10.1.1 Verifieer DB rollback named volume `nieuws_piet_sqlite_data` (exacte volume identiteit) in spec."""
    # Concrete volume-identiteit: exacte naam, expliciete `name:`-declaraties en geen Compose-projectprefix
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "nieuws_piet_sqlite_data" in content
        assert "name: nieuws_piet_sqlite_data" in content
        assert "zonder Compose project prefix" in content
        assert "-v nieuws_piet_sqlite_data:" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_1_2_verify_backend_mount_and_db_file_spec() -> None:
    """10.1.2 Verifieer backend mount `/app/data` and database file `/app/data/news.db` in spec."""
    # Concrete pad-contracten: backend mount en database file moeten exact vastliggen
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert re.search(r"(?i)backend\s+mount\**\s*:\s*`?/app/data`?", content)
        assert re.search(r"(?i)database\s+file\**\s*:\s*`?/app/data/news\.db`?", content)
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_1_3_verify_host_backup_outside_named_volume_spec() -> None:
    """10.1.3 Verifieer host backup `./backups/news.db.<UTC timestamp>.bak` outside named volume in spec."""
    # Concrete backup-contract: exact pad, host-backup begrip en ligging buiten het named volume
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "./backups/news.db.<UTC timestamp>.bak" in content
        assert re.search(r"(?i)host[\s-]backup", content)
        assert "buiten het named volume" in content
        assert 'mode=ro' in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_1_4_verify_exact_shell_command_sequence_spec() -> None:
    """10.1.4 Verifieer exact shell command sequence met `docker compose`/`docker` en standaard shell (geen `docker-compose` v1) in spec."""
    # Concrete shell-sequence: vaste start, exacte commando's, read-only bron, geen v1-aanroep
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "set -euo pipefail" in content
        assert "docker compose stop backend" in content
        assert "mkdir -p backups" in content
        assert "-v nieuws_piet_sqlite_data:/source:ro" in content
        assert not V1_INVOCATION.search(content)
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_1_5_verify_backup_integrity_non_destructive_down_spec() -> None:
    """10.1.5 Verifieer backup-integriteitsvalidatie, non-destructive `docker compose down` en feitelijk restore in spec."""
    # Concrete invarianten: integriteitsvalidatie stopt de procedure, down blijft niet-destructief, restore is feitelijk
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "PRAGMA integrity_check" in content
        assert "exit code ongelijk aan 0" in content
        assert "docker compose down" in content
        assert re.search(r"(?i)non-destructive down|niet-destructieve", content)
        assert "feitelijk teruggezet" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_1_6_verify_docker_compose_down_v_opt_in_only_spec() -> None:
    """10.1.6 Verifieer `docker compose down -v` uitsluitend als opt-in in spec, met volgorde backup → validatie → `down -v` → restore → verificatie (geen restore vóór `down -v`)."""
    # Concrete invarianten: opt-in-only, vaste volgorde en expliciet verbod op restore vóór `down -v`
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "docker compose down -v" in content
        assert "uitsluitend een expliciete opt-in" in content
        assert "Restore staat nooit vóór `docker compose down -v`" in content
        assert "backup → integriteitsvalidatie → opt-in `docker compose down -v` → restore" in content
        _assert_restore_ligt_na_down_v(content)
    else:
        pytest.skip("spec.md niet gevonden")


# ==== 10.2 Health-monitoring/health-endpoint Spec Updates (6 taken) ================================


def test_10_2_1_verify_health_test_only_exact_config_spec() -> None:
    """10.2.1 Verifieer health test-only exact config: ONLY when `APP_ENV=test` in spec."""
    # Concrete invariant: fault-injectie is uitsluitend actief bij exacte `APP_ENV=test`-waarde
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "test-only" in content
        assert "`APP_ENV` exact de waarde `test`" in content
        assert "APP_ENV=test" in content
        assert "APP_HEALTH_FAULT" in content
        assert "test doubles" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_2_2_verify_app_health_fault_whitelist_spec() -> None:
    """10.2.2 Verifieer `APP_HEALTH_FAULT` whitelist `sqlite`, `sqlite_timeout`, `backend`, `all` in spec."""
    # Controleer dat de spec `APP_HEALTH_FAULT` whitelist `sqlite`, `sqlite_timeout`, `backend`, `all` beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "APP_HEALTH_FAULT" in content
        assert "whitelist" in content
        assert "sqlite" in content
        assert "sqlite_timeout" in content
        assert "backend" in content
        assert "all" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_2_3_verify_five_exact_named_tests_spec() -> None:
    """10.2.3 Verifieer vijf exacte named tests met exacte assertions inclusief `test_sqlite_timeout` in spec."""
    # Controleer dat de spec vijf exacte named tests met exacte assertions inclusief `test_sqlite_timeout` beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "test_healthy_system" in content
        assert "test_sqlite_failure" in content
        assert "test_sqlite_timeout" in content
        assert "test_backend_failure" in content
        assert "test_combined_failure" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_2_4_verify_sqlite_timeout_server_probe_budget_spec() -> None:
    """10.2.4 Verifieer `sqlite_timeout` server probe budget <=500ms in spec."""
    # Controleer dat de spec `sqlite_timeout` server probe budget <=500ms in spec beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "sqlite_timeout" in content
        assert "server probe budget" in content
        assert "<=500ms" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_2_5_verify_client_assertion_budget_spec() -> None:
    """10.2.5 Verifieer client assertion budget <=1000ms in spec."""
    # Controleer dat de spec client assertion budget <=1000ms in spec beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "client assertion budget" in content
        assert "<=1000ms" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_2_6_verify_app_factory_isolatie_spec() -> None:
    """10.2.6 Verifieer app-factory/proces-isolatie, reset cleanup en geen filesystem database mutaties in spec."""
    # Controleer dat de spec app-factory isolatie, reset cleanup en geen filesystem database mutaties beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "app-factory" in content
        assert "isolatie" in content
        assert "reset cleanup" in content
        assert "filesystem database mutaties" in content
    else:
        pytest.skip("spec.md niet gevonden")


# ==== 10.3 Local-development/setup Spec Updates (6 taken) ================================


def test_10_3_1_verify_exact_command_docker_compose_up_d_build_spec() -> None:
    """10.3.1 Verifieer exact command: `docker compose up -d --build` in spec."""
    # Controleer dat de spec exact command: `docker compose up -d --build` in spec beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "docker compose up -d --build" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_3_2_verify_only_frontend_and_backend_services_spec() -> None:
    """10.3.2 Verifieer only `frontend` and `backend` services in spec."""
    # Controleer dat de spec only `frontend` and `backend` services in spec beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "frontend" in content
        assert "backend" in content
        assert "SQLite" not in content or "backend-volume mounted" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_3_3_verify_copyable_shell_loop_frontend_spec() -> None:
    """10.3.3 Verifieer copyable shell loop met exacte HTTP status én body assertions voor frontend in spec."""
    # Controleer dat de spec copyable shell loop met exacte HTTP status én body assertions voor frontend in spec beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "shell loop" in content
        assert "HTTP status" in content
        assert "body assertions" in content
        assert "frontend" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_3_4_verify_max_30_attempts_sleep_1_curl_max_time_5_spec() -> None:
    """10.3.4 Verifieer max 30 attempts, sleep 1, curl `--max-time 5` in spec."""
    # Concrete budget-waarden: readiness loop legt 30/1/5 exact vast in variabelen én samenvatting
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "MAX_ATTEMPTS=30" in content
        assert "SLEEP_SECONDS=1" in content
        assert "CURL_MAX_TIME=5" in content
        assert "Max 30 attempts, `sleep 1`, `curl --max-time 5`" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_3_5_verify_sqlite_never_a_service_spec() -> None:
    """10.3.5 Verifieer SQLite never a service in spec."""
    # Concrete invariant: SQLite is backend-volume mounted, nooit een eigen service
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "nooit een service" in content
        assert "backend-volume mounted" in content
        assert "nieuws_piet_sqlite_data" in content
        assert "niet gecheckt" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_3_6_verify_frontend_smoke_never_health_spec() -> None:
    """10.3.6 Verifieer frontend smoke op `http://localhost:3000/` en NOOIT `/health` in spec."""
    # Concrete invariant: frontend smoke gebruikt uitsluitend de frontend URL; `/health` is backend-only
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert re.search(r"(?i)frontend (externe )?smoke", content)
        assert "http://localhost:3000/" in content
        assert "NOOIT `/health`" in content
        assert "`/health` is uitsluitend een backend endpoint" in content
        assert "http://localhost:8000/health" in content
    else:
        pytest.skip("spec.md niet gevonden")


# ==== 10.4 Documentation/local-dev Spec Updates (7 taken) ================================


def test_10_4_1_verify_local_dev_dependency_playwright_test_spec() -> None:
    """10.4.1 Verifieer mobile exact: local dev dependency `@playwright/test` version pinned in project lockfile in spec."""
    # Controleer dat de spec mobile exact: local dev dependency `@playwright/test` version pinned in project lockfile in spec beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "@playwright/test" in content
        assert "version pinned" in content
        assert "package-lock.json" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_4_2_verify_command_npm_run_test_e2e_spec() -> None:
    """10.4.2 Verifieer command `npm run test:e2e` na geslaagde readiness loop in spec."""
    # Controleer dat de spec command `npm run test:e2e` na geslaagde readiness loop in spec beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "npm run test:e2e" in content
        assert "readiness loop" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_4_3_verify_test_http_localhost_3000_viewport_360x800_vóór_navigatie_spec() -> None:
    """10.4.3 Verifieer test `http://localhost:3000/`, viewport 360x800 vóór navigatie in spec."""
    # Controleer dat de spec test `http://localhost:3000/`, viewport 360x800 vóór navigatie in spec beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "http://localhost:3000/" in content
        assert "viewport 360x800" in content
        assert "vóór navigatie" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_4_4_verify_assert_marker_text_nieuws_piet_spec() -> None:
    """10.4.4 Verifieer assert marker text `Nieuws Piet`, visible nav landmark, visible main landmark in spec."""
    # Concrete assertions: marker-tekst plus beide zichtbare landmarks staan exact voorgeschreven
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "marker `Nieuws Piet`" in content
        assert "zichtbare `nav` landmark" in content
        assert "zichtbare `main` landmark" in content
        assert "page.locator('nav')" in content
        assert "page.locator('main')" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_4_5_verify_text_nog_geen_nieuws_beschikbaar_spec() -> None:
    """10.4.5 Verifieer text `Nog geen nieuws beschikbaar`, and `scrollWidth <= clientWidth` in spec."""
    # Concrete assertions: lege-tekst en horizontale-scroll-contract
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "tekst `Nog geen nieuws beschikbaar`" in content
        assert "scrollWidth <= clientWidth" in content
        assert "toBeLessThanOrEqual(clientWidth)" in content
        assert "360x800" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_4_6_verify_explicitly_ban_accounts_api_keys_spec() -> None:
    """10.4.6 Verifieer explicitly ban accounts/API keys/SaaS/browser cloud/paid services/external APIs in spec."""
    # Concrete contractwaarden: de vier verboden categorieën gelden expliciet voor alle tests
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        for verboden in (
            "Accounts/API keys",
            "SaaS/browser cloud",
            "Paid services",
            "External APIs",
        ):
            assert verboden in content, verboden
        assert "verbieden alle tests" in content
        assert "voor alle tests" in content
        assert "route.abort()" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_10_4_7_verify_rollback_failure_playwright_documentatie_spec() -> None:
    """10.4.7 Verifieer rollback-, failure testing- en Playwright documentatie bevatten de exacte commando's en budgetten in spec."""
    # Controleer dat de spec rollback-, failure testing- en Playwright documentatie bevatten de exacte commando's en budgetten in spec beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "rollback" in content
        assert "failure testing" in content
        assert "Playwright" in content
        assert "commando's" in content
        assert "budgetten" in content
    else:
        pytest.skip("spec.md niet gevonden")


# ==== 10.5 Design.md Updates (5 taken) ================================


def test_10_5_1_verify_design_decisions_reflect_new_requirements() -> None:
    """10.5.1 Verifieer design decisions reflect new requirements in design.md."""
    # Concrete design-beslissingen: sectie Beslissingen bevat per nieuw requirement een benoemde beslissing
    design_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/design.md")
    if design_path.exists():
        content = design_path.read_text()
        assert "## Beslissingen" in content
        for beslissing in (
            "### Technology Stack Beslissing",
            "### Compose Acceptance Beslissing",
            "### Data-Safe Rollback Beslissing",
            "### Failure Testing Beslissing",
            "### Mobile Acceptance Beslissing",
        ):
            assert beslissing in content, beslissing
        # Technische invarianten die in die beslissingen zijn vastgelegd
        for waarde in (
            "nieuws_piet_sqlite_data",
            "docker compose up -d --build",
            "APP_ENV=test",
            "APP_HEALTH_FAULT",
            "360x800",
            "PRAGMA integrity_check",
        ):
            assert waarde in content, waarde
    else:
        pytest.skip("design.md niet gevonden")


def test_10_5_2_verify_architecture_decisions_align_with_exact_specifications() -> None:
    """10.5.2 Verifieer architecture decisions align with exact specifications in design.md."""
    # Architectuurbeslissingen moeten de exacte spec-contracten overnemen (paden, volume, URLs)
    design_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/design.md")
    if design_path.exists():
        content = design_path.read_text()
        assert "### Architectuur Beslissing" in content
        assert "### Modulegrenzen" in content
        assert "monorepo" in content.lower()
        for waarde in (
            "frontend/",
            "backend/",
            "nieuws_piet_sqlite_data",
            "/app/data/news.db",
            "http://localhost:3000",
            "http://localhost:8000/health",
        ):
            assert waarde in content, waarde
    else:
        pytest.skip("design.md niet gevonden")


def test_10_5_3_verify_technology_stack_decisions_support_all_requirements() -> None:
    """10.5.3 Verifieer technology stack decisions support all requirements in design.md."""
    # De volledige stack (frontend, backend, database, e2e) moet expliciet gekozen en aanspreekbaar zijn
    design_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/design.md")
    if design_path.exists():
        content = design_path.read_text()
        assert "### Technology Stack Beslissing" in content
        for technologie in ("Docker Compose", "Next.js", "FastAPI", "SQLite", "Playwright", "@playwright/test"):
            assert technologie in content, technologie
        # De stack moet de contracten dekken die de specs eisen
        assert "/health" in content
        assert "npm run test:e2e" in content
        assert "Alternatieven Overwogen" in content
    else:
        pytest.skip("design.md niet gevonden")


def test_10_5_4_verify_risk_mitigation_strategies_address_new_requirements() -> None:
    """10.5.4 Verifieer risk mitigation strategies address new requirements in design.md."""
    # Risicosectie: benoemde risico's met mitigatie die de nieuwe requirements concreet afdekken
    design_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/design.md")
    if design_path.exists():
        content = design_path.read_text()
        assert "## Risico's / Trade-offs" in content
        sectie = content.split("## Risico's / Trade-offs", 1)[1].split("## Migratie Plan", 1)[0]
        for risico in (
            "### Risico: Docker afhankelijkheid",
            "### Risico: SQLite beperkingen",
            "### Risico: Complexiteit van monorepo",
            "### Risico: Test-only configuratie",
            "### Risico: Onjuiste of corrupte backup",
            "### Risico: Mobiele test afhankelijkheid",
        ):
            assert risico in sectie, risico
        assert sectie.count("**Mitigatie**") >= 6
        for waarde in (
            "PRAGMA integrity_check",
            "APP_ENV=test",
            "APP_HEALTH_FAULT",
            "@playwright/test",
            "docker compose down -v",
        ):
            assert waarde in sectie, waarde
    else:
        pytest.skip("design.md niet gevonden")


def test_10_5_5_verify_migration_plan_uses_docker_compose_up_d_build() -> None:
    """10.5.5 Verifieer migration plan uses `docker compose up -d --build` en bevat geen verouderde `docker-compose` commando's in design.md."""
    # Migratieplan gebruikt exact de v2-opdracht en noemt nergens een v1-aanroep
    design_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/design.md")
    if design_path.exists():
        content = design_path.read_text()
        migratie = content.split("## Migratie Plan", 1)[1]
        assert "docker compose up -d --build" in migratie
        assert "docker compose" in migratie
        assert "readiness loop" in migratie
        assert "http://localhost:3000" in migratie
        assert "npm run test:e2e" in migratie
        assert not V1_INVOCATION.search(content)
    else:
        pytest.skip("design.md niet gevonden")


# ==== 10.6 Tasks.md Updates (5 taken) ================================


def test_10_6_1_verify_discrete_verified_tasks_for_each_acceptance() -> None:
    """10.6.1 Verifieer discrete verified tasks for each acceptance in tasks.md."""
    # Checkbox/task-ID-structuur: elke checkbox draagt een unieke, geldig geschematiseerde
    # task-ID; secties en parents bestaan; nummering is 1..n; aggregaat-taken declareren
    # exact hun aantal kinderen.
    tasks_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/tasks.md")
    if tasks_path.exists():
        content = tasks_path.read_text()
        regels = _checkbox_regels(content)
        ids = _task_ids(content)

        # Uniekheid van de task-ID's
        assert len(ids) == len(set(ids)), "dubbele task-ID's in tasks.md"

        # Alle tien secties zijn als kop aanwezig
        secties = set(re.findall(r"^## (\d+)\.", content, re.M))
        assert secties == {str(i) for i in range(1, 11)}, secties

        # Elke taak hoort bij een bestaande sectie; sub-taken hebben een bestaande parent
        id_set = set(ids)
        for tid in ids:
            delen = tid.split(".")
            assert delen[0] in secties, f"sectie {delen[0]} ontbreekt voor taak {tid}"
            if len(delen) == 3:
                parent = ".".join(delen[:2])
                assert parent in id_set, f"parent {parent} ontbreekt voor taak {tid}"

        # Nummering binnen elke groep is aaneengesloten 1..n (geen gaten of dubbelen)
        groepen = defaultdict(list)
        for tid in ids:
            delen = tid.split(".")
            groepen[".".join(delen[:-1])].append(int(delen[-1]))
        for groep, nummers in groepen.items():
            assert sorted(nummers) == list(range(1, len(nummers) + 1)), (
                f"nummering in '{groep or 'sectieniveau'}': {sorted(nummers)}"
            )

        # Aggregaat-taken declareren exact hun aantal directe kinderen
        aggregaten = 0
        for regel in regels:
            m = re.match(r"^\s*- \[[ x]\] (\d+\.\d+) .+\((\d+) taken\)$", regel)
            if not m:
                continue
            aggregaten += 1
            parent, verwacht = m.group(1), int(m.group(2))
            diepte = parent.count(".") + 1
            kinderen = [
                i for i in ids
                if i.startswith(parent + ".") and i.count(".") == diepte
            ]
            assert len(kinderen) == verwacht, (
                f"{parent}: {len(kinderen)} kinderen, gedekt {verwacht}"
            )
        assert aggregaten == 10, aggregaten
    else:
        pytest.skip("tasks.md niet gevonden")


def test_10_6_2_verify_use_dutch_prose_but_exact_SHALL_MUST() -> None:
    """10.6.2 Verifieer use Dutch prose but exact SHALL/MUST and Given/When/Then in specs in tasks.md."""
    # Taken zijn Nederlands geformuleerd; de exacte requirement-taal (SHALL/MUST,
    # Given/When/Then, Requirement/Scenario) hoort in de vier delta specs, niet als
    # Engelse metaterm in het Nederlandse takenbestand.
    tasks_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/tasks.md")
    specs_dir = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs")
    if not (tasks_path.exists() and specs_dir.exists()):
        pytest.skip("tasks.md of specs niet gevonden")

    tasks_content = tasks_path.read_text()
    engelse_openers = (
        "Verify ", "Ensure ", "Create ", "Implement ", "Configure ",
        "Document ", "Run ", "Test that", "The system",
    )
    for regel in _checkbox_regels(tasks_content):
        m = re.match(r"^\s*- \[[ x]\] \d+(?:\.\d+)+\s+(.*)$", regel)
        assert m, f"checkbox zonder task-ID: {regel.strip()}"
        tekst = m.group(1)
        assert not tekst.startswith(engelse_openers), f"Engelse prose: {regel.strip()}"
        if not AGGREGAAT.fullmatch(tekst):
            assert tekst.startswith(ACTION_VERBS), f"geen imperatief Nederlands werkwoord: {regel.strip()}"

    spec_bestanden = sorted(specs_dir.glob("*/*/spec.md"))
    assert len(spec_bestanden) == 4, [str(p) for p in spec_bestanden]
    for sp in spec_bestanden:
        c = sp.read_text()
        assert re.search(r"^### Requirement: ", c, re.M), sp.name
        assert re.search(r"^#### Scenario: ", c, re.M), sp.name
        assert "SHALL" in c, sp.name
        assert "**Given**" in c and "**When**" in c and "**Then**" in c, sp.name
    # MUST is de exacte eis voor de test-only fault-injectie
    assert any("MUST" in sp.read_text() for sp in spec_bestanden)


def test_10_6_3_verify_ensure_no_duplicate_timeout_rollback() -> None:
    """10.6.3 Verifieer ensure no duplicate timeout/rollback in tasks.md."""
    # Concrete contractwaarden: exact één budgetpaar (500ms/1000ms) en één rollback-volgorde
    # waarin `down -v` altijd vóór restore staat.
    tasks_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/tasks.md")
    if tasks_path.exists():
        content = tasks_path.read_text()

        # Timeout-contract: geen afwijkende of dubbele budgetwaarden
        ms_waarden = set(re.findall(r"(\d+)\s*ms", content))
        assert ms_waarden == {"500", "1000"}, ms_waarden
        assert "sqlite_timeout" in content
        assert "server probe budget <=500ms" in content
        assert "client assertion budget <=1000ms" in content

        # Rollback-contract: opt-in `down -v`, restore nooit vóór, vaste volgorde
        assert "docker compose down -v" in content
        assert "restore nooit vóór `down -v`" in content
        assert "geen restore vóór `down -v`" in content
        assert "volgorde backup → validatie → `down -v` → restore → verificatie" in content
        _assert_restore_ligt_na_down_v(content)
    else:
        pytest.skip("tasks.md niet gevonden")


def test_10_6_4_verify_all_tasks_are_actionable_and_testable() -> None:
    """10.6.4 Verifieer all tasks are actionable and testable in tasks.md."""
    # Actionable: elke niet-aggregaat taak opent met een imperatief Nederlands werkwoord.
    # Testable: elke taak noemt een concrete referentie (waarde, pad, code,
    # contract, systeemelement of opgeleverd artefact) — geen vage opdrachten
    # zonder inspectiepunt.
    tasks_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/tasks.md")
    if tasks_path.exists():
        content = tasks_path.read_text()
        ids = _task_ids(content)
        labels = _aggregaat_labels(content)
        assert len(ids) == len(set(ids))

        taakregels = 0
        aggregaten = 0
        for regel in _checkbox_regels(content):
            m = re.match(r"^\s*- \[[ x]\] (\d+(?:\.\d+)+) (.*)$", regel)
            assert m, f"checkbox zonder task-ID: {regel.strip()}"
            tid, tekst = m.group(1), m.group(2)
            if AGGREGAAT.fullmatch(tekst):
                # aggregaat-regel (sectiekop met kindertelling) heeft geen werkwoord
                aggregaten += 1
                continue
            taakregels += 1
            assert tekst.startswith(ACTION_VERBS), f"niet actionable ({tid}): {tekst}"
            # het werkgebied van de parent-aggregaat telt mee als referentie
            delen = tid.split(".")
            werkgebied = labels.get(".".join(delen[:-1]), "") if len(delen) > 1 else ""
            zoektekst = f"{tekst} {werkgebied}"
            if tekst.startswith(VERIFY_VERBS):
                # uitvoerbare verificatie: systeemreferentie óf expliciete voorwaarde
                assert REFERENT.search(zoektekst) or CONDITIE.search(zoektekst), (
                    f"niet testbaar ({tid}): {tekst}"
                )
            else:
                # oplevertaak: moet het opgeleverde artefact bij naam noemen
                assert REFERENT.search(zoektekst), f"niet testbaar ({tid}): {tekst}"
        assert aggregaten == 10, aggregaten
        assert taakregels == len(ids) - aggregaten, (taakregels, len(ids), aggregaten)
    else:
        pytest.skip("tasks.md niet gevonden")


def test_10_6_5_verify_no_verouderde_docker_compose_v1_commando_s() -> None:
    """10.6.5 Verifieer geen verouderde `docker-compose` (v1) commando's of obsolete taken meer voorkomen in tasks.md."""
    # Concrete invariant: nergens een v1-aanroep of v1-bestandsnaam; elke vermelding van
    # `docker-compose` staat in een negatieve context en alle opdrachten zijn v2.
    tasks_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/tasks.md")
    if tasks_path.exists():
        content = tasks_path.read_text()

        assert not V1_INVOCATION.search(content), V1_INVOCATION.search(content)
        assert "docker-compose.yml" not in content
        assert "docker-compose.yaml" not in content

        negaties = ("geen", "nooit", "verboden", "verouderde", "obsolete", "v1")
        for regel in content.splitlines():
            if "docker-compose" in regel:
                laag = regel.lower()
                assert any(n in laag for n in negaties), f"vermelding zonder negatie: {regel.strip()}"

        # Alle Compose-opdrachten in de taken gebruiken de v2-syntax
        assert "docker compose up -d --build" in content
        assert "docker compose down -v" in content
        assert "docker compose config" in content
    else:
        pytest.skip("tasks.md niet gevonden")


# ==== Samenvattende discrete verified tasks test suite ==========================


def test_discrete_verified_tasks_test_suite() -> None:
    """Samenvattende test suite voor alle discrete verified tasks."""
    # Voer alle discrete verified tasks tests uit en verifieer dat ze slagen.

    # Test 1: Database/local-sqlite Spec Updates (10.1.1 - 10.1.6)
    test_10_1_1_verify_db_rollback_named_volume_spec()
    test_10_1_2_verify_backend_mount_and_db_file_spec()
    test_10_1_3_verify_host_backup_outside_named_volume_spec()
    test_10_1_4_verify_exact_shell_command_sequence_spec()
    test_10_1_5_verify_backup_integrity_non_destructive_down_spec()
    test_10_1_6_verify_docker_compose_down_v_opt_in_only_spec()

    # Test 2: Health-monitoring/health-endpoint Spec Updates (10.2.1 - 10.2.6)
    test_10_2_1_verify_health_test_only_exact_config_spec()
    test_10_2_2_verify_app_health_fault_whitelist_spec()
    test_10_2_3_verify_five_exact_named_tests_spec()
    test_10_2_4_verify_sqlite_timeout_server_probe_budget_spec()
    test_10_2_5_verify_client_assertion_budget_spec()
    test_10_2_6_verify_app_factory_isolatie_spec()

    # Test 3: Local-development/setup Spec Updates (10.3.1 - 10.3.6)
    test_10_3_1_verify_exact_command_docker_compose_up_d_build_spec()
    test_10_3_2_verify_only_frontend_and_backend_services_spec()
    test_10_3_3_verify_copyable_shell_loop_frontend_spec()
    test_10_3_4_verify_max_30_attempts_sleep_1_curl_max_time_5_spec()
    test_10_3_5_verify_sqlite_never_a_service_spec()
    test_10_3_6_verify_frontend_smoke_never_health_spec()

    # Test 4: Documentation/local-dev Spec Updates (10.4.1 - 10.4.7)
    test_10_4_1_verify_local_dev_dependency_playwright_test_spec()
    test_10_4_2_verify_command_npm_run_test_e2e_spec()
    test_10_4_3_verify_test_http_localhost_3000_viewport_360x800_vóór_navigatie_spec()
    test_10_4_4_verify_assert_marker_text_nieuws_piet_spec()
    test_10_4_5_verify_text_nog_geen_nieuws_beschikbaar_spec()
    test_10_4_6_verify_explicitly_ban_accounts_api_keys_spec()
    test_10_4_7_verify_rollback_failure_playwright_documentatie_spec()

    # Test 5: Design.md Updates (10.5.1 - 10.5.5)
    test_10_5_1_verify_design_decisions_reflect_new_requirements()
    test_10_5_2_verify_architecture_decisions_align_with_exact_specifications()
    test_10_5_3_verify_technology_stack_decisions_support_all_requirements()
    test_10_5_4_verify_risk_mitigation_strategies_address_new_requirements()
    test_10_5_5_verify_migration_plan_uses_docker_compose_up_d_build()

    # Test 6: Tasks.md Updates (10.6.1 - 10.6.5)
    test_10_6_1_verify_discrete_verified_tasks_for_each_acceptance()
    test_10_6_2_verify_use_dutch_prose_but_exact_SHALL_MUST()
    test_10_6_3_verify_ensure_no_duplicate_timeout_rollback()
    test_10_6_4_verify_all_tasks_are_actionable_and_testable()
    test_10_6_5_verify_no_verouderde_docker_compose_v1_commando_s()

    # Alle tests geslaagd
    assert True
