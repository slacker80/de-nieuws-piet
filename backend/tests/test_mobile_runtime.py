"""Mobiele exacte verificatie met runtime-evidence (taken 9.4.1 t/m 9.4.12).

De statische controles — lockfile-pin, testspecificatie, spec-teksten en de
verbodslijst — staan in `tests/test_exact_verification.py`. Deze module voegt de
feitelijke uitvoering toe:

* geïnstalleerde versus gepinde `@playwright/test`-versie;
* lokale chromium-browser (browserregistry, geen cloud browser);
* `npm run test:e2e` met de readiness loop vóór de run;
* metingen in de browser zelf bij 360x800, inclusief een bewuste aanvraag naar
  een externe URL die aantoonbaar wordt geblokkeerd.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests import runtime_env

FRONTEND = runtime_env.FRONTEND_DIR


def _package_json() -> dict:
    return json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))


def _package_lock() -> dict:
    return json.loads((FRONTEND / "package-lock.json").read_text(encoding="utf-8"))


def _playwright_pin() -> str:
    pin = _package_json().get("devDependencies", {}).get("@playwright/test")
    assert pin, "geen @playwright/test als lokale dev dependency"
    return str(pin)


def _e2e() -> dict:
    return runtime_env.mobile_e2e()


def _probe() -> dict:
    return runtime_env.mobile_probe()


# ==== 9.4.1 t/m 9.4.4: afhankelijkheden, opdracht, readiness en browser ====


def test_9_4_1_runtime_playwright_pin_in_lockfile() -> None:
    """9.4.1 `@playwright/test` is exact gepind in de lockfile én geïnstalleerd."""
    pin = _playwright_pin()
    assert re.fullmatch(r"\d+\.\d+\.\d+", pin), f"versie niet exact gepind: {pin}"

    locked = _package_lock()["packages"]["node_modules/@playwright/test"]
    assert locked["version"] == pin, (
        f"lockfile ({locked['version']}) wijkt af van package.json ({pin})"
    )
    assert locked.get("integrity", "").startswith("sha512-"), (
        "lockfile bevat geen integriteits-hash voor @playwright/test"
    )

    installed = runtime_env.installed_playwright_version()
    assert installed == pin, (
        f"geïnstalleerde versie ({installed}) wijkt af van de pin ({pin})"
    )


def test_9_4_2_runtime_npm_run_test_e2e() -> None:
    """9.4.2 `npm run test:e2e` bestaat en slaagt feitelijk."""
    script = _package_json()["scripts"].get("test:e2e")
    assert script == "../scripts/run-mobile-e2e.sh", f"onverwachte test:e2e-opdracht: {script}"

    e2e = _e2e()
    assert e2e["rc"] == 0, (
        f"npm run test:e2e faalde (rc={e2e['rc']}, {e2e['seconds']}s):\n{e2e['output']}"
    )
    assert re.search(r"\b1 passed\b", e2e["output"]), e2e["output"]
    assert "mobile responsive acceptance at 360x800" in e2e["output"]


def test_9_4_3_runtime_readiness_before_e2e() -> None:
    """9.4.3 Stack start met `docker compose up -d --build` + readiness vóór de e2e-run."""
    e2e = _e2e()

    # Feitelijk uitgevoerde readiness, afgerond vóór `npm run test:e2e`.
    assert e2e["readiness_rc"] == 0, e2e["readiness_output"]
    assert re.search(r"Readiness geslaagd na \d+ pogingen", e2e["readiness_output"]), (
        e2e["readiness_output"]
    )
    assert e2e["readiness_before_e2e"], "readiness is niet vóór de e2e-run afgerond"

    # De stack waar de run op uitkwam is de exacte startopdracht + readiness.
    assert e2e["stack"]["ok"], e2e["stack"]
    assert e2e["stack"]["frontend_marker"] and e2e["stack"]["backend_healthy"]

    # Startopdracht en volgorde staan ook in het uitvoerbare wrapper-script.
    wrapper = (runtime_env.ROOT / "scripts" / "run-mobile-e2e.sh").read_text(encoding="utf-8")
    assert "docker compose up -d --build" in wrapper
    assert wrapper.index("docker compose up -d --build") < wrapper.index(
        "readiness-loop.sh"
    ) < wrapper.index("npx playwright test")


def test_9_4_4_runtime_npm_ci_en_lokale_browser() -> None:
    """9.4.4 Feitelijk `npm ci` in een verse, geïsoleerde kopie + lokale chromium-setup.

    De bestaande `frontend/node_modules` wordt niet vertrouwd: alleen de
    manifesten worden gekopieerd, `npm ci` bouwt de boom van nul op en
    `npx playwright install chromium` + het executable-pad komen uit die verse
    installatie. De werkmap wordt altijd opgeruimd (ook bij falen).
    """
    runtime_env.require_node()

    evidence = runtime_env.npm_ci_isolated()

    # Isolatie: uitsluitend de manifesten, dus geen overgenomen node_modules.
    assert evidence["copied"][:2] == ["package.json", "package-lock.json"], evidence["copied"]
    assert evidence["fresh_install"], "de kopie bevatte al een node_modules"
    assert evidence["rc"] == 0, (
        f"npm ci faalde (rc={evidence['rc']}, {evidence['seconds']}s):\n{evidence['output']}"
    )
    assert evidence["node_modules_present"], "npm ci heeft @playwright/test niet geïnstalleerd"
    assert evidence["packages"] > 0, evidence

    # Gepinde dependency, lockfile én de daadwerkelijke installatie zijn identiek.
    pin, locked, installed = evidence["pin"], evidence["locked"], evidence["installed"]
    assert pin and re.fullmatch(r"\d+\.\d+\.\d+", pin), f"niet exact gepind: {pin}"
    assert locked == pin, f"lockfile {locked} wijkt af van package.json {pin}"
    assert installed == pin, f"geïnstalleerd {installed} wijkt af van de pin {pin}"

    # Feitelijke lokale browser-setup vanuit deze verse installatie (geen cloud).
    assert evidence["browser_rc"] == 0, evidence["browser_output"]
    executable = evidence["executable"] or ""
    assert evidence["executable_exists"], f"chromium-executable ontbreekt: {executable}"
    assert executable.startswith(evidence["home"]), executable
    assert str(Path(evidence["home"]) / ".cache" / "ms-playwright") in executable, executable
    assert Path(evidence["target"]).exists() is False, "npm-werkmap is niet opgeruimd"


# ==== 9.4.5 t/m 9.4.10: metingen in de browser bij 360x800 =================


def test_9_4_5_runtime_viewport_360x800_op_localhost() -> None:
    """9.4.5 Meting op `http://localhost:3000/` met viewport 360x800."""
    probe = _probe()
    assert probe["url"].startswith("http://localhost:3000"), probe["url"]
    assert probe["viewport"] == {"width": 360, "height": 800}, probe["viewport"]

    # Dezelfde URL/viewport staan in de Playwright-configuratie.
    config = (FRONTEND / "playwright.config.js").read_text(encoding="utf-8")
    assert "baseURL: 'http://localhost:3000'" in config
    assert re.search(r"width:\s*360,\s*height:\s*800", config)


def test_9_4_6_runtime_marker_text_zichtbaar() -> None:
    """9.4.6 Marker-tekst `Nieuws Piet` is in de browser zichtbaar."""
    probe = _probe()
    assert probe["markerVisible"], f"marker niet zichtbaar: {probe}"
    assert probe["h1"].strip() == "Nieuws Piet", probe["h1"]


def test_9_4_7_runtime_nav_landmark_zichtbaar() -> None:
    """9.4.7 `nav`-landmark is zichtbaar."""
    assert _probe()["navVisible"], "nav-landmark niet zichtbaar"


def test_9_4_8_runtime_main_landmark_zichtbaar() -> None:
    """9.4.8 `main`-landmark is zichtbaar."""
    assert _probe()["mainVisible"], "main-landmark niet zichtbaar"


def test_9_4_9_runtime_leegstaat_tekst_zichtbaar() -> None:
    """9.4.9 Tekst `Nog geen nieuws beschikbaar` is zichtbaar."""
    assert _probe()["emptyVisible"], "lege-staattekst niet zichtbaar"


def test_9_4_10_runtime_scrollwidth_clientwidth() -> None:
    """9.4.10 `scrollWidth <= clientWidth` (geen horizontale scrolling)."""
    probe = _probe()
    assert probe["scrollWidth"] <= probe["clientWidth"], (
        f"scrollWidth {probe['scrollWidth']} > clientWidth {probe['clientWidth']}"
    )
    assert probe["noHorizontalScroll"], probe
    assert probe["overflowing"] == [], probe["overflowing"]


# ==== 9.4.11 t/m 9.4.12: readiness zonder slaaptijd en lokaal-only tests ==


def test_9_4_11_runtime_auto_retry_en_netwerkisolatie() -> None:
    """9.4.11 Auto-retry readiness zonder vaste slaaptijd, netwerkisolatie actief."""
    probe = _probe()

    # De meting wacht met auto-retry op de zichtbare marker (geen `waitForTimeout`)
    # en komt uit met een zichtbare UI — dezelfde strategie als de suite.
    assert probe["markerVisible"], probe

    # Netwerkisolatie blokkeert feitelijk verkeer naar niet-localhost: een
    # bewuste aanvraag naar `https://example.invalid/` komt er niet doorheen.
    assert probe["externalFetch"] == "blocked", (
        f"externe aanvraag werd niet geblokkeerd: {probe['externalFetch']}"
    )
    assert probe["blocked"] == [], (
        f"de pagina zelf vroeg niet-localhost verkeer aan: {probe['blocked']}"
    )

    # De suite slaagt met auto-retry assertions (geen vaste slaaptijd).
    e2e = _e2e()
    assert e2e["rc"] == 0 and re.search(r"\b1 passed\b", e2e["output"])


def test_9_4_12_runtime_geen_accounts_keys_saas_of_externe_apis() -> None:
    """9.4.12 Accounts/API-keys/SaaS/cloud browser/betaalde diensten/externe API's zijn verbannen."""
    probe = _probe()

    # Geen enkele niet-localhost aanvraag bereikt de browser, en een bewuste
    # externe aanvraag wordt afgewezen (geen externe API's, geen SaaS).
    assert probe["blocked"] == [], probe["blocked"]
    assert probe["externalFetch"] == "blocked", probe["externalFetch"]
    assert probe["consoleErrors"] == [], probe["consoleErrors"]

    # De geserveerde pagina bevat geen absolute externe URLs.
    status, body = runtime_env.http_get(runtime_env.FRONTEND_URL)
    assert status == 200
    assert runtime_env.external_urls(body) == [], runtime_env.external_urls(body)

    # Geen cloud browser: de chromium-browser komt uit de lokale registry.
    browser = runtime_env.local_chromium()
    assert browser["exists"] and browser["path"].startswith(browser["home"]), browser

    # Nog geen accounts/keys in de testbronnen: uitsluitend localhost-URL's.
    for bron in [FRONTEND / "tests" / "mobile.spec.js", FRONTEND / "playwright.config.js"]:
        tekst = bron.read_text(encoding="utf-8")
        extern = runtime_env.external_urls(tekst)
        assert extern == [], f"{bron.name} bevat externe URLs: {extern}"
        assert re.search(
            r"api[_-]?key|secret|password|bearer|oauth|token\s*[:=]", tekst, re.I
        ) is None, f"{bron.name} bevat credentials-verwijzingen"


# ==== Samenvattende suite voor de mobiele runtime =========================


def test_mobile_runtime_suite() -> None:
    """Samenvattende test: alle 9.4-taken met feitelijke runtime-evidence."""
    test_9_4_1_runtime_playwright_pin_in_lockfile()
    test_9_4_2_runtime_npm_run_test_e2e()
    test_9_4_3_runtime_readiness_before_e2e()
    test_9_4_4_runtime_npm_ci_en_lokale_browser()
    test_9_4_5_runtime_viewport_360x800_op_localhost()
    test_9_4_6_runtime_marker_text_zichtbaar()
    test_9_4_7_runtime_nav_landmark_zichtbaar()
    test_9_4_8_runtime_main_landmark_zichtbaar()
    test_9_4_9_runtime_leegstaat_tekst_zichtbaar()
    test_9_4_10_runtime_scrollwidth_clientwidth()
    test_9_4_11_runtime_auto_retry_en_netwerkisolatie()
    test_9_4_12_runtime_geen_accounts_keys_saas_of_externe_apis()
