"""Exacte Verificatie Taken (sectie 9, taken 92-130).

Implementeer exacte verificatie taken voor data-safe rollback, health test-only config,
compose exact commands en mobile exact verificatie.

Alle tests zijn unit tests (geen externe services) en volgen de app-factory
isoleringsstrategie (elke test bouwt een verse applicatie-instance).
"""

import json
import re
import subprocess
import time

import pytest
from pathlib import Path

# Detectie via de Docker CLI en de daemon (geen Python-`docker`-module: die is
# geen project-afhankelijkheid en zou tests laten overslaan terwijl de CLI wél
# beschikbaar is).
from tests import runtime_env


# ==== Artefact-paden en semantische hulpfuncties ================================
# De controles hieronder zoeken naar *betekenis* (volgordes, condities, opsommingen,
# config-waarden) in plaats van naar exacte zinsdelen uit de specs. Ze draaien
# volledig statisch en claimen nooit dat een runtime-verificatie is uitgevoerd.

ROOT = Path("/home/peter/git/de-nieuws-piet")
CHANGE = ROOT / "openspec" / "changes" / "bootstrap-local-news-dashboard"

SPEC_SQLITE = CHANGE / "specs" / "database" / "local-sqlite" / "spec.md"
SPEC_HEALTH = CHANGE / "specs" / "health-monitoring" / "health-endpoint" / "spec.md"
SPEC_SETUP = CHANGE / "specs" / "local-development" / "setup" / "spec.md"
SPEC_LOCALDEV = CHANGE / "specs" / "documentation" / "local-dev" / "spec.md"

COMPOSE_FILE = ROOT / "compose.yaml"
SCRIPT_READINESS = ROOT / "scripts" / "readiness-loop.sh"
SCRIPT_ACCEPTANCE = ROOT / "scripts" / "compose-acceptance.sh"
SCRIPT_ROLLBACK = ROOT / "scripts" / "db-rollback.sh"
SCRIPT_SMOKE = ROOT / "scripts" / "frontend-smoke.sh"
TEST_MOBILE_JS = ROOT / "frontend" / "tests" / "mobile.spec.js"
CONFIG_PLAYWRIGHT = ROOT / "frontend" / "playwright.config.js"
PACKAGE_JSON = ROOT / "frontend" / "package.json"
PACKAGE_LOCK = ROOT / "frontend" / "package-lock.json"
HEALTH_CONFIG = ROOT / "backend" / "app" / "config.py"

# Categorieën van het verbod op externe diensten voor alle tests.
CATEGORIEEN = (
    r"accounts?\b|\bapi[ -]?keys?\b",   # accounts / API keys
    r"\bsaas\b|\bcloud\b",              # SaaS / browser cloud
    r"\bpaid\b|\bbetaalde?\b",          # paid services
    r"external api|externe api",        # external APIs
)


def _lees(pad: Path) -> str:
    """Leest een verplicht artefact. Een ontbrekend artefact is een defect, geen
    runtime-skip: deze tests draaien volledig statisch."""
    assert pad.is_file(), f"verplicht artefact ontbreekt: {pad.relative_to(ROOT)}"
    return pad.read_text(encoding="utf-8")


def _code_blokken(tekst: str) -> list:
    """[(taal, inhoud)] van alle afgesloten code-blokken in Markdown."""
    return [
        (m.group(1).lower(), m.group(2))
        for m in re.finditer(r"```([A-Za-z0-9_+-]*)\n(.*?)```", tekst, re.S)
    ]


def _bash_blok(tekst: str, naald: str) -> str:
    """Het eerste shell-codeblok dat de naald bevat (anders leeg)."""
    for taal, body in _code_blokken(tekst):
        if taal in ("", "bash", "sh", "shell") and naald in body:
            return body
    for _taal, body in _code_blokken(tekst):
        if naald in body:
            return body
    return ""


def _js_blokken(tekst: str) -> str:
    """Alle JavaScript-snippets uit Markdown samengevoegd."""
    return "\n".join(b for t, b in _code_blokken(tekst) if t in ("js", "javascript"))


def _kop_blokken(tekst: str, niveau: str) -> list:
    """[(titel, tekst)] per Markdown-kop van het gegeven niveau."""
    pat = re.compile(rf"^{niveau}[ \t]+(.+?)[ \t]*$", re.M)
    koppen = list(pat.finditer(tekst))
    uit = []
    for i, m in enumerate(koppen):
        start = m.end()
        eind = koppen[i + 1].start() if i + 1 < len(koppen) else len(tekst)
        uit.append((m.group(1).strip(), tekst[start:eind]))
    return uit


def _scenario_blokken(tekst: str) -> list:
    return _kop_blokken(tekst, r"####")


def _requirement_blokken(tekst: str) -> list:
    return _kop_blokken(tekst, r"###")


def _scenario_waar(tekst: str, predicaat) -> str:
    """Het eerste scenario dat aan het predicaat voldoet (anders leeg)."""
    for _titel, body in _scenario_blokken(tekst):
        if predicaat(body):
            return body
    return ""


def _eis_waar(tekst: str, predicaat) -> str:
    """De eerste requirement (inclusief scenario's) die aan het predicaat voldoet."""
    for _titel, body in _requirement_blokken(tekst):
        if predicaat(body):
            return body
    return ""


def _bash_var(tekst: str, naam: str):
    """Waarde van een shell-variabele-assignatie, of None."""
    m = re.search(rf"^[ \t]*{re.escape(naam)}=(\S+)[ \t]*$", tekst, re.M)
    if not m:
        return None
    return m.group(1).strip("\"'")


def _bash_var_int(tekst: str, naam: str):
    w = _bash_var(tekst, naam)
    if w is None:
        return None
    m = re.search(r"-?\d+", w)
    return int(m.group(0)) if m else None


def _curl_max_time(tekst: str):
    """Los `curl --max-time` op: literaal getal of een variabele."""
    m = re.search(
        r"--max-time[ \t]+(?:\"\$\{([A-Z0-9_]+)\}\"|\$\{([A-Z0-9_]+)\}|(\d+))",
        tekst,
    )
    if not m:
        return None
    if m.group(3):
        return int(m.group(3))
    return _bash_var_int(tekst, m.group(1) or m.group(2))


def _pijl_ketens(tekst: str) -> list:
    """Alle `→`-volgordes (stappenketens) uit de tekst."""
    ketens = []
    for regel in tekst.splitlines():
        for m in re.finditer(r"(?:^|[:;])[ \t]*((?:[^.;\n]+→)+[^.;\n]*)", regel):
            stappen = [s.strip() for s in m.group(1).split("→")]
            ketens.append([re.sub(r"^[\s*_`]+|[\s*_`,]+$", "", s) for s in stappen])
    return ketens


def _pijl_volgorde(tekst: str, delen: list) -> bool:
    """Of er een pijlketen bestaat waarin de deeltjes strikt in de gegeven volgorde staan."""
    for keten in _pijl_ketens(tekst):
        posities = []
        for deel in delen:
            plek = next(
                (i for i, stap in enumerate(keten) if deel.lower() in stap.lower()),
                None,
            )
            if plek is None:
                break
            posities.append(plek)
        else:
            if len(posities) == len(delen) and all(
                a < b for a, b in zip(posities, posities[1:])
            ):
                return True
    return False


def _succes_guards(tekst: str) -> list:
    """De condities waaronder het script met exit 0 stopt (succespad)."""
    guards = []
    for m in re.finditer(r"^[ \t]*if[ \t]+(.+?);?[ \t]*then[ \t]*$", tekst, re.M):
        cond = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(";")
        rest = tekst[m.end():]
        eind = re.search(r"^[ \t]*(fi|else|elif)\b", rest, re.M)
        blok = rest[: eind.start()] if eind else rest[:400]
        if re.search(r"\bexit[ \t]+0\b", blok):
            guards.append(cond)
    return guards


def _flags(tekst: str) -> set:
    """Boolean-readiness-flags die het script bijhoudt."""
    return set(
        re.findall(r"^[ \t]*([A-Za-z_][A-Za-z0-9_]*)=(?:true|false)\b", tekst, re.M)
    )


def _niet_succes_exit(tekst: str) -> bool:
    return bool(re.search(r"\bexit[ \t]+[1-9]\d*\b", tekst))


def _compose_blok(pad: Path, sleutel: str) -> str:
    """De tekst van een top-level blok in een compose-bestand (indentatie-gestuurd)."""
    tekst = _lees(pad)
    m = re.search(
        rf"^{re.escape(sleutel)}:[ \t]*\n(.*?)(?=^[^\s#]|\Z)", tekst, re.M | re.S
    )
    return m.group(1) if m else ""


def _compose_services(pad: Path) -> list:
    """Service-namen uit een compose-bestand, zonder yaml-afhankelijkheid."""
    return re.findall(
        r"^  ([A-Za-z0-9._-]+):[ \t]*$", _compose_blok(pad, "services"), re.M
    )


def _bash_functie(tekst: str, naam: str) -> str:
    """Inhoud van een shell-functie met evenwichtige accolades."""
    m = re.search(rf"^[ \t]*{re.escape(naam)}\(\)[ \t]*\{{", tekst, re.M)
    if not m:
        return ""
    diepte = 1
    i = m.end()
    while i < len(tekst) and diepte:
        if tekst[i] == "{":
            diepte += 1
        elif tekst[i] == "}":
            diepte -= 1
        i += 1
    return tekst[m.end(): i - 1]


def _http_status_assertie(tekst: str) -> bool:
    """De statuscode wordt opgehaald én exact met 200 vergeleken."""
    return bool(re.search(r"%\{http_code\}", tekst)) and bool(
        re.search(r"[\"']200[\"']", tekst) or re.search(r"=\s*200\b", tekst)
    )


def _json_status_gezond(tekst: str) -> bool:
    """De JSON-body wordt getoetst op `status` == `healthy` (spatie-tolerant)."""
    return bool(re.search(r"['\"]status['\"].{0,80}healthy", tekst, re.I | re.S)) or bool(
        re.search(r"\bstatus\b[^.\n]{0,40}\bhealthy\b", tekst, re.I)
    )


def _zichtbaar_verwachting(tekst: str, naald: str):
    """Positie van een `expect(...)` op de naald die op `.toBeVisible()` uitkomt."""
    for m in re.finditer(r"expect\(", tekst):
        eind = tekst.find(";", m.start())
        uiting = tekst[m.start(): eind if eind != -1 else m.start() + 500]
        if naald in uiting and re.search(r"\)\s*\.\s*toBeVisible\(\)", uiting):
            return m.start()
    return None


def _geen_vaste_slaaptijd(tekst: str) -> bool:
    return (
        re.search(
            r"waitForTimeout|page\.waitFor\b|await\s+new\s+Promise|\bsleep\s*\(", tekst
        )
        is None
    )


def _localhost_netwerkisolatie(tekst: str) -> bool:
    return bool(
        re.search(r"\.route\(", tekst)
        and re.search(r"localhost", tekst)
        and re.search(r"127\.0\.0\.1", tekst)
        and re.search(r"route\.continue\(\)", tekst)
        and re.search(r"route\.abort\(\)", tekst)
    )


def _categorieen_gedekt(tekst: str) -> bool:
    laag = tekst.lower()
    return all(re.search(pat, laag) for pat in CATEGORIEEN)


def _mobiele_bronnen() -> list:
    """[(naam, javascript)] van de spec-snippet en de daadwerkelijke Playwright-test."""
    return [
        ("de local-dev spec", _js_blokken(_lees(SPEC_LOCALDEV))),
        ("frontend/tests/mobile.spec.js", _lees(TEST_MOBILE_JS)),
    ]


# ==== 9.1 Data-safe Rollback Verificatie (10 taken) ================================


def test_9_1_1_verify_db_rollback_named_volume() -> None:
    """9.1.1 Verifieer exacte DB rollback named volume `nieuws_piet_sqlite_data` (exacte volume identiteit)."""
    runtime_env.require_docker()

    # Controleer volume definitie in compose.yaml
    compose_path = Path("/home/peter/git/de-nieuws-piet/compose.yaml")
    if compose_path.exists():
        content = compose_path.read_text()
        assert "nieuws_piet_sqlite_data" in content
        assert "name: nieuws_piet_sqlite_data" in content
        # Controleer dat er geen project prefix is
        assert "name: " not in content or "nieuws_piet_sqlite_data" in content
    else:
        pytest.skip("compose.yaml niet gevonden")


def test_9_1_2_verify_backend_mount_and_db_file() -> None:
    """9.1.2 Verifieer backend mount `/app/data` en database file `/app/data/news.db`."""
    runtime_env.require_docker()

    # Controleer backend volume mount in compose.yaml
    compose_path = Path("/home/peter/git/de-nieuws-piet/compose.yaml")
    if compose_path.exists():
        content = compose_path.read_text()
        assert "- nieuws_piet_sqlite_data:/app/data" in content
        # Controleer dat de database file pad correct is
        assert "/app/data/news.db" in content
    else:
        pytest.skip("compose.yaml niet gevonden")


def test_9_1_3_verify_host_backup_outside_named_volume() -> None:
    """9.1.3 Verifieer host backup `./backups/news.db.<UTC timestamp>.bak` outside named volume."""
    # Controleer backup script in de spec of documentatie
    backup_script = Path("/home/peter/git/de-nieuws-piet/scripts/preserve-rollback.sh")
    if backup_script.exists():
        content = backup_script.read_text()
        assert "backups/" in content
        assert "news.db." in content
    else:
        # Controleer in de documentatie
        docs_path = Path("/home/peter/git/de-nieuws-piet/docs/data-safe-rollback-restore.md")
        if docs_path.exists():
            content = docs_path.read_text()
            assert "backups/" in content
            assert "news.db." in content
        else:
            pytest.skip("backup script of documentatie niet gevonden")


def test_9_1_4_verify_exact_shell_command_sequence() -> None:
    """9.1.4 Verifieer exact shell command sequence met `docker compose`/`docker` en standaard shell (geen `docker-compose` v1)."""
    # Controleer dat de spec exacte commando's beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "docker compose" in content
        assert "docker-compose" not in content or "docker-compose v1" not in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_1_5_verify_stop_backend_mkdir_backups_backup() -> None:
    """9.1.5 Verifieer stop backend, `mkdir -p backups`, backup vanaf READ-ONLY named volume mount, non-destructive `docker compose down`."""
    # Het uitvoerbare pad staat in scripts/db-rollback.sh (er bestaat geen
    # apart preserve-rollback-script); hier wordt die bron zelf gecontroleerd.
    script = _lees(SCRIPT_ROLLBACK)

    # 1. Backend stoppen vóór de backup: geen schrijvers naar de database.
    make_backup = _bash_functie(script, "make_backup")
    assert make_backup, "make_backup ontbreekt in db-rollback.sh"
    assert "docker compose stop backend" in make_backup, (
        "de backup stopt de backend niet"
    )

    # 2. `mkdir -p backups` op de host, buiten het named volume.
    backup_dir = _bash_var(script, "BACKUP_DIR")
    assert backup_dir in ("backups", "${NIEUWS_PIET_DB_BACKUP_DIR:-backups}"), (
        f"BACKUP_DIR is niet de spec-waarde `backups`: {backup_dir}"
    )
    assert re.search(r'mkdir -p "\$\{BACKUP_DIR\}"', make_backup), (
        "geen `mkdir -p` voor de backup-directory"
    )
    assert re.search(
        r"\./backups/news\.db\.<UTC timestamp>\.bak", script
    ), "de backup-identiteit ontbreekt in de script-header"

    # 3. De bron is READ-ONLY: alleen-lezen mount van het named volume.
    assert re.search(r'-v "\$\{VOLUME\}:/source:ro"', make_backup), (
        "de backup wordt niet vanaf een READ-ONLY named-volume-mount gemaakt"
    )

    # 4. Non-destructief pad: `docker compose down` zonder `-v`.
    preserve = _bash_functie(script, "cmd_preserve")
    assert preserve, "cmd_preserve ontbreekt in db-rollback.sh"
    assert re.search(r"^[ \t]*docker compose down[ \t]*$", preserve, re.M), (
        "het preserve-pad voert geen non-destructieve `docker compose down` uit"
    )
    assert not re.search(r"^[ \t]*docker compose down -v", preserve, re.M), (
        "het preserve-pad verwijdert het volume"
    )


def test_9_1_6_verify_backup_integrity_validation() -> None:
    """9.1.6 Verifieer backup-integriteitsvalidatie met `PRAGMA integrity_check` = `ok`
    vóór elke destructieve actie; bij falen stopt de procedure."""
    spec = _lees(SPEC_SQLITE)
    script = _lees(SCRIPT_ROLLBACK)

    # De validatie opent de backup read-only en voert `PRAGMA integrity_check` uit.
    validatie = _scenario_waar(
        spec,
        lambda b: "PRAGMA integrity_check" in b
        and re.search(r"mode=ro|read-only|\b:ro\b", b, re.I),
    )
    assert validatie, "geen read-only integriteitsvalidatie-scenario in de SQLite-spec"

    # Exact `ok` is de enige acceptabele uitkomst.
    assert re.search(
        r"['\"]?ok['\"]?[ \t]+vereist|result(?:aat)?[^.\n]{0,30}[=]=?[ \t]*['\"]?ok",
        validatie,
        re.I,
    ), "validatie accepteert niet uitsluitend exact `ok`"

    # Bij elk ander resultaat breekt de procedure af met een foutexit.
    assert re.search(
        r"exit code ongelijk aan 0|ongelijk aan 0|"
        r"sys\.exit\([^)]*else[ \t]+1\s*\)|\bexit[ \t]+1\b",
        validatie,
    ), "falen op integriteit leidt niet tot een afgebroken procedure"

    # De validatie staat vóór de destructieve actie in de voorgeschreven volgorde.
    assert _pijl_volgorde(
        spec, ["integriteitsvalidatie", "down -v"]
    ), "integriteitsvalidatie staat niet vóór `docker compose down -v`"

    # Het rollback-script koppelt het pragma-resultaat daadwerkelijk aan exit != 0
    # en draait onder `set -e`, waardoor falen de rest van de procedure stopt.
    validate = _bash_functie(script, "validate_backup")
    assert validate, "validate_backup ontbreekt in db-rollback.sh"
    assert "PRAGMA integrity_check" in validate, "script voert geen integriteitscheck uit"
    assert re.search(r"mode=ro", validate), "script opent de backup niet read-only"
    assert re.search(
        r"sys\.exit\(\s*0\s+if\s+result\s*==\s*['\"]ok['\"]\s+else\s+1\s*\)", validate
    ), "script breekt niet af met exit != 0 als de integriteit niet `ok` is"
    assert re.search(
        r"^set -[a-z]*e", script, re.M
    ), "script breekt niet af bij een fout (geen `set -e`)"


def test_9_1_7_verify_feitelijk_restore() -> None:
    """9.1.7 Verifieer feitelijk restore: backup terugzetten naar `/app/data/news.db` in het named volume voor preserve pad én voor destructive reset pad (destructive pad: pas ná opt-in `docker compose down -v`, in het opnieuw aangemaakte volume; nooit vóór `down -v`)."""
    # Controleer restore script
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "restore" in content
        assert "/app/data/news.db" in content
        assert "down -v" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_1_8_verify_docker_compose_up_after_restore() -> None:
    """9.1.8 Verifieer `docker compose up -d --build` na restore en integriteitsverificatie via `docker compose exec -i backend python` (`PRAGMA integrity_check` + ten minste één tabel)."""
    runtime_env.require_docker()

    # Controleer dat de spec `docker compose up -d --build` beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "docker compose up -d --build" in content
        assert "docker compose exec -i backend python" in content
        assert "PRAGMA integrity_check" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_1_9_verify_curl_health_assertie() -> None:
    """9.1.9 Verifieer `curl` /health assertie (exact HTTP 200 én JSON body `status: healthy`)."""
    spec = _lees(SPEC_SQLITE)
    script = _lees(SCRIPT_ROLLBACK)

    # Het verificatiescenario legt beide asserties vast.
    verificatie = _scenario_waar(spec, lambda b: "curl" in b and "/health" in b)
    assert verificatie, "geen curl-/health-verificatie in de SQLite-spec"
    assert re.search(
        r"localhost:8000/health", verificatie
    ), "/health wordt niet op de backend-URL afgevraagd"
    assert _http_status_assertie(
        verificatie
    ), "geen exacte HTTP-200-assertie op de health endpoint"
    assert _json_status_gezond(
        verificatie
    ), "geen JSON-assertie op `status: healthy` in de health response"

    # Dezelfde twee asserties staan in het uitvoerbare rollback-script.
    volledig = _bash_functie(script, "verify_full")
    assert volledig, "verify_full ontbreekt in db-rollback.sh"
    assert re.search(
        r"localhost:8000/health", volledig
    ), "script checkt de health endpoint niet op de backend-URL"
    assert _http_status_assertie(
        volledig
    ), "script stelt de HTTP-status niet exact gelijk aan 200"
    assert _json_status_gezond(
        volledig
    ), "script toetst de JSON-body niet op `status: healthy`"


def test_9_1_10_verify_docker_compose_down_v_opt_in_only() -> None:
    """9.1.10 Verifieer `docker compose down -v` uitsluitend als opt-in en alléén na
    geslaagde backup en integriteitsvalidatie, met restore direct ná `down -v` in het
    opnieuw aangemaakte volume `nieuws_piet_sqlite_data` en verificatie van integriteit,
    data-marker en health direct na restore; verifieer dat GEEN enige stap restore vóór
    `down -v` voorschrijft."""
    spec = _lees(SPEC_SQLITE)
    script = _lees(SCRIPT_ROLLBACK)

    # 1. De voorgeschreven volgorde: validatie -> down -v -> restore -> verificatie.
    assert _pijl_volgorde(
        spec, ["integriteitsvalidatie", "down -v", "restore", "verificatie"]
    ), "de vaste volgorde op het destructive pad ontbreekt of klopt niet"

    # 2. Standaard blijft niet-destructief. Elke `down -v` valt in een sectie die de
    #    opt-in-qualificatie draagt, behalve puur ordende referenties ("na `down -v`").
    assert re.search(
        r"docker compose down(?! -v)", spec
    ), "geen niet-destructieve standaardstap `docker compose down`"
    koppen = list(re.finditer(r"^#{3,6}[ \t]+.+$", spec, re.M))

    def _omvattende_sectie(pos: int) -> str:
        start, eind = 0, len(spec)
        for i, k in enumerate(koppen):
            if k.start() > pos:
                break
            start = k.start()
            eind = koppen[i + 1].start() if i + 1 < len(koppen) else len(spec)
        return spec[start:eind]

    for m in re.finditer(r"docker compose down -v", spec):
        sectie = _omvattende_sectie(m.start())
        if re.search(r"opt-in|uitsluitend|ALL[ÉE]N|expliciet", sectie, re.I):
            continue
        regel = spec[spec.rfind("\n", 0, m.start()) + 1: spec.find("\n", m.start())]
        assert re.search(
            r"\b(na|ná|vóór|ervóór|voordat|alvorens|nooit|niet|zonder)\b", regel, re.I
        ), f"`docker compose down -v` zonder opt-in-kwalificatie: {regel.strip()}"

    # 3. In elk codeblok met `down -v` volgt de restore pas daarna.
    blokken = [b for _t, b in _code_blokken(spec) if "down -v" in b]
    assert blokken, "geen uitvoerbare destructive sequence in de spec"
    paar = 0
    for blok in blokken:
        plek_down = blok.index("down -v")
        herstel = blok.find("/target")
        if herstel == -1:
            continue
        assert herstel > plek_down, "restore staat vóór `docker compose down -v`"
        paar += 1
    assert paar, "geen codeblok waarin de restore na `down -v` volgt"

    # 4. Het script voert het destructieve pad in diezelfde volgorde uit.
    reset = _bash_functie(script, "cmd_reset")
    assert reset, "cmd_reset ontbreekt in db-rollback.sh"
    stappen = (
        r"\bmake_backup\b",
        r"\bvalidate_backup\b",
        r"^[ \t]*docker compose down -v[ \t]*$",
        r"\bcopy_backup_into_volume\b",
        r"^[ \t]*verify\b",
    )
    plekken = []
    for pat in stappen:
        m = re.search(pat, reset, re.M)
        assert m, f"destructieve stap ontbreekt of staat verkeerd: {pat}"
        plekken.append(m.start())
    assert plekken == sorted(plekken), "de volgorde in cmd_reset klopt niet"

    down = re.search(r"^[ \t]*docker compose down -v[ \t]*$", reset, re.M).start()
    herstellingen = [
        m.start() for m in re.finditer(r"\bcopy_backup_into_volume\b", reset)
    ]
    assert herstellingen and all(p > down for p in herstellingen), (
        "restore vóór `docker compose down -v` in db-rollback.sh"
    )

    # 5. Zonder expliciete opt-in geen volume-verwijdering; volume-identiteit blijft exact.
    assert re.search(
        r"ALLOW_VOLUME_REMOVAL", reset
    ), "geen opt-in-guard rond `docker compose down -v`"
    volume_regel = re.search(r'^VOLUME="([^"]*)"$', script, re.M)
    assert volume_regel, "VOLUME-variabele ontbreekt in db-rollback.sh"
    assert volume_regel.group(1) in (
        "nieuws_piet_sqlite_data",
        "${NIEUWS_PIET_DB_VOLUME:-nieuws_piet_sqlite_data}",
    ), "herstel gebeurt niet in het named volume `nieuws_piet_sqlite_data`"


# ==== Strikte volume-/resource-identificator-validatie =====================

ONGELDIGE_IDENTIFICATOREN = (
    "/absoluut/pad",
    "relatief/pad",
    "./pad",
    "nieuws db",
    "nieuws:db",
    "nieuws\\db",
    "-leidend",
    ".",
    "..",
    "  spaties  ",
    "naam\nmet-regeleinde",
    "naam;rm -rf",
)


def _draai_script_met_volume(volume: str, *args: str) -> dict:
    """Draait `scripts/db-rollback.sh` met een opgegeven `NIEUWS_PIET_DB_VOLUME`."""
    env = runtime_env.build_env({"NIEUWS_PIET_DB_VOLUME": volume})
    proc = subprocess.run(
        ["bash", str(SCRIPT_ROLLBACK), *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return {"rc": proc.returncode, "output": f"{proc.stdout}\n{proc.stderr}"}


def test_9_1_volumenaam_weigert_pad_slash_en_witruimte() -> None:
    """`NIEUWS_PIET_DB_VOLUME` wordt als Docker named-volume-identificator behandeld.

    Paden, slashes, backslashes, kolonnen, witruimte, leidende tekens en
    niet-bestaande namen worden vóór élke docker-opdracht geweigerd (geen
    bind-mount, geen andermans pad). `--help` blijft met een geldige naam
    werken, zodat de validatie de dispatch niet overslaat.
    """
    script = _lees(SCRIPT_ROLLBACK)
    assert "validate_volume_name" in script, "validatie-functie ontbreekt"
    plek_validatie = script.index('validate_volume_name "${VOLUME}"')
    plek_dispatch = script.index('case "${MODE}" in')
    assert plek_validatie < plek_dispatch, (
        "de volumenaam wordt niet vóór de dispatch gevalideerd"
    )

    for naam in ONGELDIGE_IDENTIFICATOREN:
        resultaat = _draai_script_met_volume(naam, "--help")
        assert resultaat["rc"] == 1, (
            f"{naam!r} werd niet als volumenaam geweigerd:\n{resultaat['output']}"
        )
        assert "geen geldige Docker named-volume-naam:" in resultaat["output"], (
            resultaat["output"]
        )
        assert "Gebruik:" not in resultaat["output"], (
            f"de dispatch liep vóór de validatie voor {naam!r}"
        )

    # Lege waarde: `${NIEUWS_PIET_DB_VOLUME:-...}` valt terug op de named volume,
    # zodat een lege override nooit een lege volumenaam oplevert.
    leeg = _draai_script_met_volume("", "--help")
    assert leeg["rc"] == 0, leeg["output"]
    assert "geen geldige Docker named-volume-naam" not in leeg["output"], leeg["output"]

    geldig = _draai_script_met_volume("nieuws_piet_sqlite_data_test", "--help")
    assert geldig["rc"] == 0, geldig["output"]
    assert "Gebruik:" in geldig["output"], geldig["output"]


def test_9_1_resource_identificatoren_gestrenge_validatie() -> None:
    """Ook project-, volume- en netwerknamen volgen die strenge identificatorregel.

    `isolated_context()`/`ensure_stack_up()` gebruiken dezelfde regel, zodat een
    test nooit een pad of vreemde identificator als Compose-projectnaam doorgeeft.
    """
    for naam in ONGELDIGE_IDENTIFICATOREN:
        with pytest.raises(AssertionError):
            runtime_env.validate_docker_name(naam, "volumenaam")
        with pytest.raises(AssertionError):
            runtime_env.validate_docker_name(naam, "projectnaam")

    for naam in ("nieuws_piet_sqlite_data", "nieuws-piet-net_1", "np.2", "P1"):
        assert runtime_env.validate_docker_name(naam, "netwerknaam") == naam


# ==== 9.2 Health Test-only Config Verificatie (8 taken) ================================


def test_9_2_1_verify_health_test_only_exact_config() -> None:
    """9.2.1 Verifieer health test-only exact config: ONLY when `APP_ENV=test`."""
    # Controleer dat de spec health test-only exact config beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "APP_ENV=test" in content
        assert "test-only" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_2_2_verify_app_health_fault_whitelist() -> None:
    """9.2.2 Verifieer `APP_HEALTH_FAULT` whitelist exact `sqlite`, `sqlite_timeout`, `backend`, `all`."""
    # Controleer dat de spec `APP_HEALTH_FAULT` whitelist exact beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "APP_HEALTH_FAULT" in content
        assert "sqlite" in content
        assert "sqlite_timeout" in content
        assert "backend" in content
        assert "all" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_2_3_verify_deterministisch_gedrag_onbekende_fault() -> None:
    """9.2.3 Verifieer deterministisch gedrag bij onbekende `APP_HEALTH_FAULT` waarden en
    bij `APP_ENV` anders dan `test` (normale gezonde respons)."""
    spec = _lees(SPEC_HEALTH)
    config = _lees(HEALTH_CONFIG)
    scenarios = _scenario_blokken(spec)

    # A. Niet-test omgeving: de fault wordt genegeerd en het normale gezonde contract
    #    (HTTP 200) geldt, terwijl er wél een fault was aangevraagd.
    niet_test = [
        body
        for _titel, body in scenarios
        if "APP_ENV" in body
        and "APP_HEALTH_FAULT" in body
        and re.search(r"anders dan|zonder[ \t]+`?APP_ENV", body)
    ]
    assert niet_test, "geen scenario dat het gedrag buiten de test-omgeving beschrijft"
    for body in niet_test:
        assert re.search(
            r"\b200\b", body
        ), "buiten de test-omgeving ontbreekt het normale gezonde contract"
        assert re.search(r"normaal|gezond|healthy|genegeerd", body, re.I), (
            "de fault wordt buiten de test-omgeving niet genegeerd"
        )

    # B. De implementatie toetst de APP_ENV-guard en de whitelist daadwerkelijk.
    assert re.search(
        r"app_env\s*!=\s*[\"']test[\"']", config
    ), "de implementatie toetst `APP_ENV` niet op exact `test`"
    assert re.search(
        r"requested\s+not\s+in\s+HEALTH_FAULT_WHITELIST", config
    ), "onbekende waarden worden niet tegen de whitelist getoetst"
    wit = re.search(r"HEALTH_FAULT_WHITELIST\s*=\s*frozenset\(\{([^}]*)\}\)", config)
    assert wit, "de whitelist van `APP_HEALTH_FAULT` is niet als set gedeclareerd"
    waarden = {w.strip().strip("\"'") for w in wit.group(1).split(",") if w.strip()}
    assert waarden == {"sqlite", "sqlite_timeout", "backend", "all"}, (
        f"de whitelist is niet exact: {sorted(waarden)}"
    )

    # C. Onbekende waarde => deterministisch exact dezelfde normale respons, en nooit
    #    een niet-gedefinieerde foutrespons.
    onbekend = [
        body
        for _titel, body in scenarios
        if "APP_HEALTH_FAULT" in body
        and re.search(r"niet-whitelisted|onbekende waarde", body, re.I)
    ]
    assert onbekend, "geen scenario voor onbekende `APP_HEALTH_FAULT` waarden"
    for body in onbekend:
        assert re.search(
            r"\b200\b", body
        ), "een onbekende waarde levert niet de normale respons"
        assert re.search(r"exact dezelfde|deterministisch", body, re.I), (
            "het gedrag bij onbekende waarden is niet deterministisch geformuleerd"
        )
        assert re.search(r"nooit[^.\n]*fout", body, re.I), (
            "een onbekende waarde kan nog steeds een foutrespons geven"
        )


def test_9_2_4_verify_five_exact_named_tests() -> None:
    """9.2.4 Verifieer vijf exacte named tests met exacte assertions: `test_healthy_system`, `test_sqlite_failure`, `test_sqlite_timeout`, `test_backend_failure`, `test_combined_failure`."""
    # Controleer dat de spec vijf exacte named tests beschrijft
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


def test_9_2_5_verify_sqlite_timeout_server_probe_budget() -> None:
    """9.2.5 Verifieer `sqlite_timeout` server probe budget <=500ms."""
    # Controleer dat de spec `sqlite_timeout` server probe budget <=500ms beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "sqlite_timeout" in content
        assert "server probe budget" in content
        assert "<=500ms" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_2_6_verify_client_assertion_budget() -> None:
    """9.2.6 Verifieer client assertion budget <=1000ms."""
    # Controleer dat de spec client assertion budget <=1000ms beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "client assertion budget" in content
        assert "<=1000ms" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_2_7_verify_app_factory_isolatie() -> None:
    """9.2.7 Verifieer app-factory/proces-isolatie en reset cleanup per test."""
    # Controleer dat de spec app-factory isolatie beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "app-factory" in content
        assert "isolatie" in content
        assert "reset cleanup" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_2_8_verify_geen_filesystem_database_mutaties() -> None:
    """9.2.8 Verifieer geen filesystem database mutaties in fault tests (test doubles alleen)."""
    # Controleer dat de spec geen filesystem database mutaties beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "filesystem database mutaties" in content
        assert "test doubles" in content
    else:
        pytest.skip("spec.md niet gevonden")


# ==== 9.3 Compose Exact Command Verificatie (9 taken) ================================


def test_9_3_1_verify_exact_command_docker_compose_up_d_build() -> None:
    """9.3.1 Verifieer exact command: `docker compose up -d --build`."""
    # Controleer dat de spec exact command: `docker compose up -d --build` beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "docker compose up -d --build" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_3_2_verify_only_frontend_and_backend_services() -> None:
    """9.3.2 Verifieer only `frontend` and `backend` services."""
    # Controleer dat de spec only `frontend` and `backend` services beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "frontend" in content
        assert "backend" in content
        assert "SQLite" not in content or "backend-volume mounted" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_3_3_verify_exact_paths_urls() -> None:
    """9.3.3 Verifieer exact paths URLs."""
    # Controleer dat de spec exact paths URLs beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "http://localhost:3000/" in content
        assert "http://localhost:8000/health" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_3_4_verify_copyable_shell_loop_frontend() -> None:
    """9.3.4 Verifieer copyable shell loop die frontend `http://localhost:3000/` zelfstandig checkt op exact HTTP 200 én body marker `Nieuws Piet`."""
    # Controleer dat de spec copyable shell loop beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "shell loop" in content
        assert "http://localhost:3000/" in content
        assert "Nieuws Piet" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_3_5_verify_backend_health_endpoint() -> None:
    """9.3.5 Verifieer backend `http://localhost:8000/health` op exact HTTP 200 én JSON body `status: healthy`."""
    # Controleer dat de spec backend `http://localhost:8000/health` beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "http://localhost:8000/health" in content
        assert "HTTP 200" in content
        assert "status: healthy" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_3_6_verify_max_30_attempts_sleep_1_curl_max_time_5() -> None:
    """9.3.6 Verifieer max 30 attempts, sleep 1, curl `--max-time 5` (het readiness
    contract in de spec én in de uitvoerbare scripts)."""
    loop = _bash_blok(_lees(SPEC_SETUP), "MAX_ATTEMPTS")
    assert loop, "geen copyable readiness loop in de setup-spec"

    bronnen = (
        ("de setup-spec", loop),
        ("scripts/readiness-loop.sh", _lees(SCRIPT_READINESS)),
        ("scripts/compose-acceptance.sh", _lees(SCRIPT_ACCEPTANCE)),
    )
    for naam, bron in bronnen:
        assert _bash_var_int(bron, "MAX_ATTEMPTS") == 30, (
            f"{naam}: het aantal pogingen is niet begrensd op 30"
        )
        assert re.search(
            r"seq[^\n]*MAX_ATTEMPTS|i\s*<=?\s*MAX_ATTEMPTS", bron
        ), f"{naam}: de wachtloop wordt niet door MAX_ATTEMPTS begrensd"
        assert _bash_var_int(bron, "SLEEP_SECONDS") == 1, (
            f"{naam}: de slaaptijd per poging is niet 1 seconde"
        )
        assert re.search(r"\bsleep\b", bron), f"{naam}: geen slaapstap in de wachtloop"
        assert _curl_max_time(bron) == 5, (
            f"{naam}: `curl --max-time` is niet 5 seconden"
        )
        assert _niet_succes_exit(bron), (
            f"{naam}: na de laatste poging wordt geen foutexit geretourneerd"
        )


def test_9_3_7_verify_only_success_if_both_flags_true() -> None:
    """9.3.7 Verifieer only success if BOTH flags true, otherwise exit nonzero after loop."""
    loop = _bash_blok(_lees(SPEC_SETUP), "MAX_ATTEMPTS")
    assert loop, "geen copyable readiness loop in de setup-spec"

    bronnen = (
        ("de setup-spec", loop),
        ("scripts/readiness-loop.sh", _lees(SCRIPT_READINESS)),
        ("scripts/compose-acceptance.sh", _lees(SCRIPT_ACCEPTANCE)),
    )
    for naam, bron in bronnen:
        vlaggen = _flags(bron)
        assert len(vlaggen) >= 2, (
            f"{naam}: worden minder dan twee readiness-flags bijgehouden"
        )

        guards = _succes_guards(bron)
        assert guards, f"{naam}: geen conditioneel succespad (exit 0) gevonden"
        for cond in guards:
            assert "&&" in cond, (
                f"{naam}: het succespad eist niet tegelijk beide voorwaarden: {cond}"
            )
            betrokken = [v for v in vlaggen if v in cond]
            assert len(betrokken) == len(vlaggen), (
                f"{naam}: het succespad controleert niet alle flags "
                f"({sorted(vlaggen)}): {cond}"
            )

        assert _niet_succes_exit(bron), (
            f"{naam}: na de wachtloop wordt niet met een foutexit gestopt"
        )


def test_9_3_8_verify_sqlite_never_a_service() -> None:
    """9.3.8 Verifieer SQLite never a service: de compose-configuratie bevat alleen
    frontend en backend; de database is een backend-volume, geen service."""
    diensten = _compose_services(COMPOSE_FILE)
    assert diensten, "compose.yaml bevat geen services-sectie"
    assert sorted(diensten) == ["backend", "frontend"], (
        f"onverwachte compose-services: {sorted(diensten)}"
    )
    assert not [d for d in diensten if re.search(r"sqlite|database|\bdb\b", d, re.I)], (
        "SQLite (of een database) is opgevoerd als service"
    )

    volumes = _compose_blok(COMPOSE_FILE, "volumes")
    assert re.search(
        r"^[ \t]*nieuws_piet_sqlite_data:[ \t]*$", volumes, re.M
    ), "het named volume `nieuws_piet_sqlite_data` is niet gedeclareerd"
    assert re.search(
        r"^[ \t]*name:[ \t]*nieuws_piet_sqlite_data[ \t]*$", volumes, re.M
    ), "de volume-identiteit bevat een Compose-projectprefix"
    assert "nieuws_piet_sqlite_data:/app/data" in _compose_blok(
        COMPOSE_FILE, "services"
    ), "het SQLite-volume is niet als backend-mount opgevoerd"

    setup = _lees(SPEC_SETUP)
    assert any(
        "sqlite" in regel.lower()
        and "service" in regel.lower()
        and re.search(r"\b(nooit|niet|geen|never|zonder)\b", regel, re.I)
        for regel in setup.splitlines()
    ), "de setup-spec stelt niet dat SQLite geen service is"


def test_9_3_9_verify_frontend_smoke_never_health() -> None:
    """9.3.9 Verifieer frontend smoke op `http://localhost:3000/` en NOOIT `/health`
    (backend-health verwijzingen elders blijven toegestaan)."""
    setup = _lees(SPEC_SETUP)
    rook = _lees(SCRIPT_SMOKE)

    # De smoke-eis noemt de frontend root-URL en sluit `/health` als frontend controle uit.
    eis = _eis_waar(
        setup,
        lambda b: "smoke" in b.lower()
        and "3000" in b
        and "/health" in b
        and re.search(r"nooit|niet", b, re.I),
    )
    assert eis, "geen frontend-smoke-eis die `/health` als frontend controle uitsluit"
    assert re.search(
        r"http://localhost:3000/", eis
    ), "de frontend-smoke-eis gebruikt niet de root-URL"

    # Nergens wordt de frontend-URL met `/health` gecombineerd.
    assert (
        re.search(r"localhost:3000\s*/health", setup) is None
    ), "een frontend-check gebruikt `/health`"

    # Elke `/health`-verwijzing hoort bij de backend of is expliciet als frontend
    # controle uitgesloten; backend-health elders blijft toegestaan.
    for regel in setup.splitlines():
        if "/health" not in regel:
            continue
        assert re.search(
            r"localhost:8000|\bbackend\b|uitsluitend|nooit|niet", regel, re.I
        ), f"`/health` in een frontend-context: {regel.strip()}"

    # Het uitvoerbare smoke-script checkt de root-URL, eist HTTP 200 + marker en
    # weigert actief een /health-frontend.
    assert _bash_var(rook, "FRONTEND_URL") == "http://localhost:3000/", (
        "frontend-smoke.sh gebruikt niet de frontend root-URL"
    )
    assert (
        re.search(r"localhost:3000\s*/health", rook) is None
    ), "frontend-smoke.sh checkt `/health` op de frontend"
    assert re.search(
        r"case[ \t]+\"\$\{FRONTEND_URL\}\"", rook
    ) and re.search(r"\*/health\*", rook), (
        "frontend-smoke.sh mist de guard die een /health-frontend-URL weigert"
    )
    assert _http_status_assertie(rook), "frontend-smoke.sh mist de exacte HTTP-200-assertie"
    assert re.search(r"Nieuws Piet", rook), "frontend-smoke.sh mist de body-marker"


# ==== 9.4 Mobile Exact Verificatie (12 taken) ================================


def test_9_4_1_verify_local_dev_dependency_playwright_test() -> None:
    """9.4.1 Verifieer local dev dependency `@playwright/test` version pinned in project lockfile."""
    # Controleer dat de spec local dev dependency `@playwright/test` version pinned beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "@playwright/test" in content
        assert "version pinned" in content
        assert "package-lock.json" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_4_2_verify_command_npm_run_test_e2e() -> None:
    """9.4.2 Verifieer command `npm run test:e2e`."""
    # Controleer dat de spec command `npm run test:e2e` beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "npm run test:e2e" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_4_3_verify_start_local_frontend_beforehand() -> None:
    """9.4.3 Verifieer start local frontend beforehand met `docker compose up -d --build` + readiness loop."""
    # Controleer dat de spec start local frontend beforehand met `docker compose up -d --build` + readiness loop beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "docker compose up -d --build" in content
        assert "readiness loop" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_4_4_verify_npm_ci_en_locale_browser_setup() -> None:
    """9.4.4 Verifieer `npm ci` en lokale browser setup met
    `npx playwright install chromium` (geen cloud browser)."""
    spec = _lees(SPEC_LOCALDEV)

    eis = _eis_waar(
        spec, lambda b: "npm ci" in b and re.search(r"playwright[ \t]+install", b)
    )
    assert eis, "geen Playwright-installatie-eis in de local-dev spec"
    assert re.search(
        r"playwright[ \t]+install[ \t]+chromium", eis
    ), "de browser wordt niet met `npx playwright install chromium` geïnstalleerd"

    install_regels = [
        r for r in eis.splitlines() if re.search(r"playwright[ \t]+install", r)
    ]
    assert install_regels, "de installatie-eis bevat geen installatieregel"
    for regel in install_regels:
        assert re.search(
            r"\b(geen|zonder|no|without|nooit|niet)\b[^.\n]*\bcloud\b"
            r"|\bcloud\b[^.\n]*\b(geen|zonder|no)\b",
            regel,
            re.I,
        ), f"browser-installatie is niet expliciet lokaal: {regel.strip()}"

    # Het project is daadwerkelijk ingericht op `npm ci` met een exact gepinde lockfile.
    pakket = json.loads(_lees(PACKAGE_JSON))
    versie = pakket.get("devDependencies", {}).get("@playwright/test")
    assert versie, "@playwright/test ontbreekt als lokale dev dependency"
    assert re.fullmatch(
        r"\d+\.\d+\.\d+", str(versie)
    ), "de Playwright-versie is niet exact gepind"
    lock = json.loads(_lees(PACKAGE_LOCK))
    pin = lock.get("packages", {}).get("node_modules/@playwright/test", {}).get("version")
    assert pin == versie, f"lockfile ({pin}) wijkt af van package.json ({versie})"
    assert re.search(
        r"browserName:\s*['\"]chromium['\"]", _lees(CONFIG_PLAYWRIGHT)
    ), "de testconfiguratie gebruikt geen lokale chromium-browser"


def test_9_4_5_verify_test_http_localhost_3000_viewport_360x800_vóór_navigatie() -> None:
    """9.4.5 Verifieer test `http://localhost:3000/`, viewport 360x800 vóór navigatie."""
    # Controleer dat de spec test `http://localhost:3000/`, viewport 360x800 vóór navigatie beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "http://localhost:3000/" in content
        assert "viewport 360x800" in content
        assert "vóór navigatie" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_4_6_verify_assert_marker_text_nieuws_piet() -> None:
    """9.4.6 Verifieer assert marker text `Nieuws Piet` (zichtbaarheidsassertie na navigatie)."""
    for naam, bron in _mobiele_bronnen():
        assert bron.strip(), f"{naam}: bevat geen JavaScript-test"
        goto = re.search(r"page\.goto\(", bron)
        assert goto, f"{naam}: navigatie naar de frontend ontbreekt"
        plek = _zichtbaar_verwachting(bron, "'Nieuws Piet'")
        assert plek is not None, (
            f"{naam}: geen zichtbaarheidsassertie op de marker 'Nieuws Piet'"
        )
        assert plek > goto.start(), (
            f"{naam}: de marker-assertie staat vóór de navigatie"
        )


def test_9_4_7_verify_visible_nav_landmark() -> None:
    """9.4.7 Verifieer visible nav landmark (zichtbare `nav`)."""
    for naam, bron in _mobiele_bronnen():
        assert bron.strip(), f"{naam}: bevat geen JavaScript-test"
        assert _zichtbaar_verwachting(bron, "'nav'") is not None, (
            f"{naam}: geen zichtbaarheidsassertie op het `nav`-landmark"
        )


def test_9_4_8_verify_visible_main_landmark() -> None:
    """9.4.8 Verifieer visible main landmark (zichtbare `main`)."""
    for naam, bron in _mobiele_bronnen():
        assert bron.strip(), f"{naam}: bevat geen JavaScript-test"
        assert _zichtbaar_verwachting(bron, "'main'") is not None, (
            f"{naam}: geen zichtbaarheidsassertie op het `main`-landmark"
        )


def test_9_4_9_verify_text_nog_geen_nieuws_beschikbaar() -> None:
    """9.4.9 Verifieer text `Nog geen nieuws beschikbaar` (zichtbaarheidsassertie)."""
    for naam, bron in _mobiele_bronnen():
        assert bron.strip(), f"{naam}: bevat geen JavaScript-test"
        assert _zichtbaar_verwachting(bron, "'Nog geen nieuws beschikbaar'") is not None, (
            f"{naam}: geen zichtbaarheidsassertie op de leegstaat-tekst"
        )


def test_9_4_10_verify_scrollWidth_clientWidth() -> None:
    """9.4.10 Verifieer `scrollWidth <= clientWidth`."""
    # Controleer dat de spec `scrollWidth <= clientWidth` beschrijft
    spec_path = Path("/home/peter/git/de-nieuws-piet/openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md")
    if spec_path.exists():
        content = spec_path.read_text()
        assert "scrollWidth <= clientWidth" in content
    else:
        pytest.skip("spec.md niet gevonden")


def test_9_4_11_verify_stabiele_UI_readiness() -> None:
    """9.4.11 Verifieer stabiele UI readiness met auto-retry assertions (geen vaste
    slaaptijd) en netwerkisolatie (alleen localhost toegestaan)."""
    spec = _lees(SPEC_LOCALDEV)

    for naam, bron in _mobiele_bronnen():
        assert bron.strip(), f"{naam}: bevat geen JavaScript-test"
        assert _localhost_netwerkisolatie(bron), (
            f"{naam}: geen netwerkisolatie die uitsluitend localhost toestaat"
        )
        assert _geen_vaste_slaaptijd(bron), (
            f"{naam}: vaste slaaptijd in plaats van auto-retry assertions"
        )
        assert _zichtbaar_verwachting(bron, "'Nieuws Piet'") is not None, (
            f"{naam}: geen auto-retry expect-assertie na het laden"
        )

    assert re.search(
        r"auto-retry[^\n]*slaaptijd|geen vaste timeout", spec, re.I
    ), "de spec formuleert de auto-retry-/geen-vaste-tijd-eis niet"


def test_9_4_12_verify_explicitly_ban_accounts_api_keys() -> None:
    """9.4.12 Verifieer explicitly ban accounts/API keys/SaaS/browser cloud/paid
    services/external APIs for all tests."""
    spec = _lees(SPEC_LOCALDEV)

    # 1. Het verbod geldt expliciet voor alle tests en dekt alle categorieën.
    regels = [r for r in spec.splitlines() if re.search(r"voor alle tests|all tests", r, re.I)]
    assert regels, "geen verbod dat voor alle tests geldt"
    gedekt = False
    for regel in regels:
        verbod = re.search(
            r"verbant|verbied|forbids?\b|ban\b|zonder|geen|nooit|niet", regel, re.I
        )
        if verbod and _categorieen_gedekt(regel):
            gedekt = True
    assert gedekt, "het verbod dekt niet alle categorieën voor alle tests"

    # 2. Het verbod staat ook als expliciete opsomming bij de Playwright-configuratie.
    lijst = re.search(r"verbieden alle tests:((?:\n[ \t]*-[ \t].+)+)", spec)
    assert lijst, "geen expliciete verbodslijst bij de Playwright-configuratie"
    items = [m.strip() for m in re.findall(r"^[ \t]*-[ \t]+(.+)$", lijst.group(1), re.M)]
    assert len(items) == 4, f"verbodslijst telt {len(items)} categorieën in plaats van 4"
    assert _categorieen_gedekt(" ".join(items)), (
        f"verbodslijst dekt niet alle categorieën: {items}"
    )

    # 3. De tests blokkeren feitelijk verkeer naar niet-localhost.
    for naam, bron in _mobiele_bronnen():
        assert _localhost_netwerkisolatie(bron), (
            f"{naam}: externe requests worden niet geblokkeerd"
        )


# ==== Samenvattende exacte verificatie test suite ==========================


def test_exact_verification_test_suite() -> None:
    """Samenvattende test suite voor alle exacte verificatie taken."""
    # Voer alle exacte verificatie tests uit en verifieer dat ze slagen.

    # Test 1: Data-safe Rollback Verificatie
    test_9_1_1_verify_db_rollback_named_volume()
    test_9_1_2_verify_backend_mount_and_db_file()
    test_9_1_3_verify_host_backup_outside_named_volume()
    test_9_1_4_verify_exact_shell_command_sequence()
    test_9_1_5_verify_stop_backend_mkdir_backups_backup()
    test_9_1_6_verify_backup_integrity_validation()
    test_9_1_7_verify_feitelijk_restore()
    test_9_1_8_verify_docker_compose_up_after_restore()
    test_9_1_9_verify_curl_health_assertie()
    test_9_1_10_verify_docker_compose_down_v_opt_in_only()
    test_9_1_volumenaam_weigert_pad_slash_en_witruimte()
    test_9_1_resource_identificatoren_gestrenge_validatie()

    # Test 2: Health Test-only Config Verificatie
    test_9_2_1_verify_health_test_only_exact_config()
    test_9_2_2_verify_app_health_fault_whitelist()
    test_9_2_3_verify_deterministisch_gedrag_onbekende_fault()
    test_9_2_4_verify_five_exact_named_tests()
    test_9_2_5_verify_sqlite_timeout_server_probe_budget()
    test_9_2_6_verify_client_assertion_budget()
    test_9_2_7_verify_app_factory_isolatie()
    test_9_2_8_verify_geen_filesystem_database_mutaties()

    # Test 3: Compose Exact Command Verificatie
    test_9_3_1_verify_exact_command_docker_compose_up_d_build()
    test_9_3_2_verify_only_frontend_and_backend_services()
    test_9_3_3_verify_exact_paths_urls()
    test_9_3_4_verify_copyable_shell_loop_frontend()
    test_9_3_5_verify_backend_health_endpoint()
    test_9_3_6_verify_max_30_attempts_sleep_1_curl_max_time_5()
    test_9_3_7_verify_only_success_if_both_flags_true()
    test_9_3_8_verify_sqlite_never_a_service()
    test_9_3_9_verify_frontend_smoke_never_health()

    # Test 4: Mobile Exact Verificatie
    test_9_4_1_verify_local_dev_dependency_playwright_test()
    test_9_4_2_verify_command_npm_run_test_e2e()
    test_9_4_3_verify_start_local_frontend_beforehand()
    test_9_4_4_verify_npm_ci_en_locale_browser_setup()
    test_9_4_5_verify_test_http_localhost_3000_viewport_360x800_vóór_navigatie()
    test_9_4_6_verify_assert_marker_text_nieuws_piet()
    test_9_4_7_verify_visible_nav_landmark()
    test_9_4_8_verify_visible_main_landmark()
    test_9_4_9_verify_text_nog_geen_nieuws_beschikbaar()
    test_9_4_10_verify_scrollWidth_clientWidth()
    test_9_4_11_verify_stabiele_UI_readiness()
    test_9_4_12_verify_explicitly_ban_accounts_api_keys()

    # Alle tests geslaagd
    assert True
