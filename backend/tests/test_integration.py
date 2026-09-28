"""Integratietests (sectie 8, taken 8.1 t/m 8.8).

Alle tests draaien de volledige applicatie (frontend + backend) via de echte
Docker Compose-opstelling:

* de exacte startopdracht `docker compose up -d --build` wordt uitgevoerd en de
  returncode wordt gecontroleerd (geen stille, niet-gecontroleerde start);
* readiness (frontend HTTP 200 + marker, backend HTTP 200 + `status: healthy`)
  wordt gemeten vóór elke vervolgstap;
* 8.1 start vanuit een schone checkout — uitsluitend getrackte bestanden, dus
  zonder `node_modules`, `.next` of andere lokale artefacten — in een eigen
  project-, volume- en netwerkcontext, en ruimt alleen die context op;
* 8.4/8.5 meten in de lokale chromium-browser bij 360x800 in plaats van alleen
  te kijken naar HTML-tekenreeksen;
* de stack wordt per sessie één keer gestart en alléén opgeruimd wanneer deze
  sessie ze startte (zie `tests/runtime_env.py`).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from tests import runtime_env

_clean_checkout: dict | None = None


# ==== 8.1 Test complete applicatie startup met `docker compose up -d --build` (clean-checkout) ============


def _tracked_files_copy(target: Path) -> int:
    """Kopieert uitsluitend getrackte bestanden (schone checkout) naar `target`."""
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(runtime_env.ROOT),
        capture_output=True,
        check=True,
    )
    archive = subprocess.run(
        ["tar", "--null", "-T", "-", "-cf", "-"],
        cwd=str(runtime_env.ROOT),
        input=listing.stdout,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["tar", "-xf", "-"],
        cwd=str(target),
        input=archive.stdout,
        capture_output=True,
        check=True,
    )
    return len([name for name in listing.stdout.split(b"\0") if name])


def _clean_checkout_start() -> dict:
    """Start de applicatie vanuit een schone checkout in een eigen context.

    Eigen projectnaam, eigen volume, eigen netwerk en eigen poorten; de echte
    volume `nieuws_piet_sqlite_data` wordt vóór en na afloop op de `CreatedAt`-
    vingerafdruk gecontroleerd.
    """
    global _clean_checkout
    if _clean_checkout is not None:
        return _clean_checkout

    runtime_env.require_docker()
    real_volume_before = runtime_env.volume_state(runtime_env.REAL_VOLUME)

    # Compose-projectnamen zijn uitsluitend lowercase alfanumeriek met `-`/`_`;
    # de slug is uniek via pid + random (geen seconde-timestamp).
    project = runtime_env.unique_slug("cleantest")
    volume = f"{runtime_env.REAL_VOLUME}_{project}"
    network = f"nieuws_piet_net_{project}"
    target = Path(tempfile.mkdtemp(prefix="nieuws-piet-clean-"))
    override = target / "compose.clean-checkout.yaml"
    compose_files = ["-f", "compose.yaml", "-f", override.name]
    project_args = ["-p", project, *compose_files]
    evidence: dict = {
        "project": project,
        "volume": volume,
        "network": network,
        "target": str(target),
        "real_volume_before": real_volume_before,
        "files": 0,
        "up_rc": None,
        "up_output": "",
        "ready": False,
        "attempts": 0,
        "services": {},
        "down_rc": None,
        "containers_after": {},
        "images_after": [],
        "real_volume_after": None,
    }

    try:
        evidence["files"] = _tracked_files_copy(target)

        frontend_port = runtime_env.free_port(13000)
        backend_port = runtime_env.free_port(18000)
        override.write_text(
            "# Tijdelijke override voor de clean-checkout test (niet getrackt):\n"
            "# eigen poorten, eigen volume en eigen netwerk, zodat de echte stack\n"
            "# en de echte volume `nieuws_piet_sqlite_data` niet worden geraakt.\n"
            "services:\n"
            "  frontend:\n"
            "    ports: !override\n"
            f'      - "127.0.0.1:{frontend_port}:3000"\n'
            "  backend:\n"
            "    ports: !override\n"
            f'      - "127.0.0.1:{backend_port}:8000"\n'
            "volumes:\n"
            "  nieuws_piet_sqlite_data:\n"
            f"    name: {volume}\n"
            "networks:\n"
            "  nieuws_piet:\n"
            f"    name: {network}\n",
            encoding="utf-8",
        )

        # Exacte startopdracht, uitgevoerd in de schone checkout.
        up = runtime_env.compose(
            *project_args, "up", "-d", "--build", cwd=target, timeout=900
        )
        evidence["up_rc"] = up.returncode
        evidence["up_output"] = f"{up.stdout}\n{up.stderr}"

        if up.returncode == 0:
            for attempt in range(1, 61):
                evidence["attempts"] = attempt
                f_status, f_body = runtime_env.http_get(
                    f"http://127.0.0.1:{frontend_port}/"
                )
                b_status, b_body = runtime_env.http_get(
                    f"http://127.0.0.1:{backend_port}/health"
                )
                healthy = False
                if b_status == 200:
                    try:
                        healthy = json.loads(b_body).get("status") == "healthy"
                    except ValueError:
                        healthy = False
                if f_status == 200 and "Nieuws Piet" in f_body and healthy:
                    evidence["ready"] = True
                    break
                time.sleep(1)

            services = runtime_env.compose_services(
                env=runtime_env.build_env(
                    {
                        "COMPOSE_PROJECT_NAME": project,
                        "COMPOSE_FILE": f"{target / 'compose.yaml'}:{override}",
                    }
                )
            )
            evidence["services"] = {
                name: entry["state"] for name, entry in services.items()
            }
    finally:
        # Opruimen: alleen de eigen context (down -v op de eigen projectnaam) en
        # de eigen image-tags. Nooit `--rmi local`: dat raakt ook andermans
        # dangling images. De echte stack wordt niet aangeraakt.
        compose_files = ["-f", "compose.yaml", "-f", "compose.clean-checkout.yaml"]
        project_args = ["-p", project, *compose_files]
        down = runtime_env.compose(
            *project_args, "down", "-v", "--remove-orphans", cwd=target, timeout=600
        )
        evidence["down_rc"] = down.returncode
        evidence["down_output"] = f"{down.stdout}\n{down.stderr}"

        runtime_env.run(
            ["docker", "image", "rm", f"{project}-frontend", f"{project}-backend"],
            timeout=300,
        )

        ps_after = runtime_env.compose_services(
            env=runtime_env.build_env(
                {
                    "COMPOSE_PROJECT_NAME": project,
                    "COMPOSE_FILE": f"{target / 'compose.yaml'}:{override}",
                }
            )
        )
        evidence["containers_after"] = ps_after
        images = runtime_env.run(["docker", "images", "--format", "{{.Repository}}"])
        evidence["images_after"] = [
            line
            for line in images.stdout.split()
            if line.startswith(project)
        ]
        evidence["real_volume_after"] = runtime_env.volume_state(runtime_env.REAL_VOLUME)
        shutil.rmtree(target, ignore_errors=True)

    _clean_checkout = evidence
    return evidence


def test_complete_app_startup() -> None:
    """8.1: Test complete applicatie startup met `docker compose up -d --build` (clean-checkout)."""
    evidence = _clean_checkout_start()

    assert evidence["files"] > 0, "geen getrackte bestanden gekopieerd"
    assert evidence["up_rc"] == 0, (
        f"docker compose up -d --build faalde in de clean checkout "
        f"(rc={evidence['up_rc']}):\n{evidence['up_output']}"
    )
    assert evidence["ready"], (
        f"stack niet ready na {evidence['attempts']} pogingen "
        f"(services: {evidence['services']})"
    )
    assert evidence["services"].get("backend") == "running", evidence["services"]
    assert evidence["services"].get("frontend") == "running", evidence["services"]

    # Volledige opruiming van de eigen context, zonder de echte stack te raken.
    assert evidence["down_rc"] == 0, (
        f"cleanup `down -v` op de eigen context faalde:\n{evidence['down_output']}"
    )
    assert evidence["containers_after"] == {}, (
        f"clean-checkout containers zijn blijven staan: {evidence['containers_after']}"
    )
    assert evidence["images_after"] == [], (
        f"clean-checkout images zijn blijven staan: {evidence['images_after']}"
    )
    assert evidence["real_volume_before"] == evidence["real_volume_after"], (
        "de echte volume `nieuws_piet_sqlite_data` is door de clean-checkout test gewijzigd"
    )


# ==== 8.2 Verifieer dat frontend en backend toegankelijk zijn ============


def test_frontend_backend_accessibility() -> None:
    """8.2: Verifieer dat frontend en backend toegankelijk zijn."""
    stack = runtime_env.ensure_stack_up()
    assert stack["ok"], f"stack niet ready: {stack}"

    frontend_status, frontend_body = runtime_env.http_get(runtime_env.FRONTEND_URL)
    assert frontend_status == 200, f"frontend gaf HTTP {frontend_status}"
    assert "Nieuws Piet" in frontend_body, "marker-tekst ontbreekt in de frontend"

    backend_status, backend_body = runtime_env.http_get(runtime_env.BACKEND_HEALTH_URL)
    assert backend_status == 200, f"backend gaf HTTP {backend_status}"
    payload = json.loads(backend_body)
    assert payload["status"] == "healthy", payload
    assert payload["components"] == {"backend": "healthy", "sqlite": "healthy"}, payload

    # Beide antwoorden komen van dezelfde `docker compose up -d --build`.
    services = runtime_env.compose_services()
    assert sorted(services) == ["backend", "frontend"]
    assert all(entry["state"] == "running" for entry in services.values()), services


# ==== 8.3 Test health endpoint integratie met Docker Compose ============


def test_health_endpoint_integration() -> None:
    """8.3: Test health endpoint integratie met Docker Compose."""
    runtime_env.ensure_stack_up()

    # De Compose-healthcheck draait in de backend-container op hetzelfde contract.
    services = runtime_env.compose_services()
    assert services["backend"]["health"] == "healthy", services["backend"]

    # Externe HTTP-check op exact hetzelfde contract.
    status, body = runtime_env.http_get(runtime_env.BACKEND_HEALTH_URL)
    payload = json.loads(body)
    assert status == 200, f"/health gaf HTTP {status}"
    assert payload["status"] == "healthy"
    assert payload["components"] == {"backend": "healthy", "sqlite": "healthy"}
    assert payload["timestamp"].endswith("Z"), payload["timestamp"]
    assert list(payload) == ["status", "timestamp", "components"], list(payload)

    # De frontend bereikt de backend binnen dezelfde Compose-stack.
    frontend_status, frontend_body = runtime_env.http_get(runtime_env.FRONTEND_URL)
    assert frontend_status == 200 and "Nieuws Piet" in frontend_body


# ==== 8.4 Verifieer mobiele responsiviteit van Next.js applicatie bij 360px ============


def test_mobile_responsiveness() -> None:
    """8.4: Verifieer mobiele responsiviteit van Next.js applicatie bij 360px."""
    probe = runtime_env.mobile_probe()

    # Gemeten in de lokale chromium-browser, niet uit de HTML afgeleid.
    assert probe["viewport"] == {"width": 360, "height": 800}, probe["viewport"]
    assert probe["noHorizontalScroll"], (
        f"horizontale overflow: scrollWidth={probe['scrollWidth']} > "
        f"clientWidth={probe['clientWidth']}"
    )
    assert probe["overflowing"] == [], (
        f"elementen breken buiten de 360px-viewport: {probe['overflowing']}"
    )
    assert probe["markerVisible"], "marker 'Nieuws Piet' niet zichtbaar bij 360px"
    assert probe["navVisible"], "nav-landmark niet zichtbaar bij 360px"
    assert probe["mainVisible"], "main-landmark niet zichtbaar bij 360px"
    assert probe["emptyVisible"], "lege staat niet zichtbaar bij 360px"


# ==== 8.5 Test applicatie functionaliteit met lege staat ============


def test_app_functionality_empty_state() -> None:
    """8.5: Test applicatie functionaliteit met lege staat."""
    probe = runtime_env.mobile_probe()

    assert probe["title"] == "Nieuws Piet", probe["title"]
    assert probe["h1"].strip() == "Nieuws Piet", probe["h1"]
    assert probe["emptyVisible"], "tekst 'Nog geen nieuws beschikbaar' niet zichtbaar"
    assert probe["hasManifest"], "PWA-manifest ontbreekt in de lege staat"
    assert probe["consoleErrors"] == [], (
        f"console-fouten tijdens het laden: {probe['consoleErrors']}"
    )
    assert probe["blocked"] == [], (
        f"de pagina vraagt niet-localhost verkeer aan: {probe['blocked']}"
    )

    # Backend blijft gezond terwijl de frontend de lege staat toont.
    status, body = runtime_env.http_get(runtime_env.BACKEND_HEALTH_URL)
    assert status == 200 and json.loads(body)["status"] == "healthy"


# ==== 8.6 Documenteer succesvolle integratietest resultaten ============


def test_integration_test_results_documentation() -> None:
    """8.6: Documenteer succesvolle integratietest resultaten."""
    summary_path = runtime_env.ROOT / "IMPLEMENTATION_SUMMARY.md"
    assert summary_path.exists(), "IMPLEMENTATION_SUMMARY.md ontbreekt"
    summary = summary_path.read_text(encoding="utf-8")

    # Concrete, gemeten resultaten in plaats van een generieke "geslaagd".
    assert "docker compose up -d --build" in summary, "startopdracht niet gedocumenteerd"
    assert re.search(r"Readiness geslaagd na \d+ pogingen", summary), (
        "geen gemeten readiness-resultaat in de samenvatting"
    )
    assert "HTTP 200" in summary, "geen HTTP-200-resultaat gedocumenteerd"
    assert "status: healthy" in summary, "geen health-resultaat gedocumenteerd"
    assert "360x800" in summary, "geen mobiel viewport-resultaat gedocumenteerd"
    assert "npm run test:e2e" in summary, "geen e2e-opdracht gedocumenteerd"
    assert re.search(r"\b1 passed\b", summary), (
        "geen concreet Playwright-resultaat in de samenvatting"
    )

    # Alle integratietaken 8.1-8.8 komen expliciet voor.
    for taak in ["8.1", "8.2", "8.3", "8.4", "8.5", "8.6", "8.7", "8.8"]:
        assert re.search(rf"\b{re.escape(taak)}\b", summary), (
            f"taak {taak} is niet gedocumenteerd in IMPLEMENTATION_SUMMARY.md"
        )


# ==== 8.7 Implementeer reproduceerbare mobiele acceptatie bij 360x800 met Playwright ============


def test_mobile_acceptance_playwright() -> None:
    """8.7: Reproduceerbare mobiele acceptatie: configuratie en testspecificatie."""
    config = (runtime_env.FRONTEND_DIR / "playwright.config.js").read_text(encoding="utf-8")
    assert re.search(r"width:\s*360,\s*height:\s*800", config), "viewport is geen 360x800"
    assert "browserName: 'chromium'" in config, "geen lokale chromium-browser"
    assert "baseURL: 'http://localhost:3000'" in config, "geen lokale frontend-URL"

    spec = (runtime_env.FRONTEND_DIR / "tests" / "mobile.spec.js").read_text(encoding="utf-8")
    # Exacte expected assertions uit de taakopdracht.
    assert "page.setViewportSize({ width: 360, height: 800 })" in spec, (
        "viewport wordt niet vóór navigatie ingesteld"
    )
    assert spec.index("page.setViewportSize") < spec.index("page.goto"), (
        "viewport staat niet vóór de navigatie"
    )
    assert "Nog geen nieuws beschikbaar" in spec, "lege-staatassertie ontbreekt"
    assert re.search(r"scrollWidth\s*\)\s*\.toBeLessThanOrEqual", spec) or (
        "expect(scrollWidth).toBeLessThanOrEqual(clientWidth)" in spec
    ), "geen scrollWidth <= clientWidth-assertie"
    assert re.search(r"locator\('nav'\)", spec), "geen nav-landmarkassertie"
    assert re.search(r"locator\('main'\)", spec), "geen main-landmarkassertie"


def test_mobile_acceptance_playwright_integration() -> None:
    """8.7: Feitelijke Playwright-run bij 360x800 (`npm run test:e2e`)."""
    e2e = runtime_env.mobile_e2e()
    assert e2e["rc"] == 0, (
        f"npm run test:e2e faalde (rc={e2e['rc']}, {e2e['seconds']}s):\n{e2e['output']}"
    )
    assert re.search(r"\b1 passed\b", e2e["output"]), (
        f"geen geslaagde mobiele acceptatietest in de uitvoer:\n{e2e['output']}"
    )
    assert "mobile responsive acceptance at 360x800" in e2e["output"], (
        "de 360x800-test is niet uitgevoerd"
    )
    assert e2e["stack"]["ok"], f"stack niet ready vóór de e2e-run: {e2e['stack']}"


# ==== 8.8 Voer de frontend/backend readiness loop uit en laat die slagen vóór `npm run test:e2e` ============


def test_readiness_loop_before_e2e() -> None:
    """8.8: Frontend/backend readiness loop slaagt vóór `npm run test:e2e`."""
    loop = runtime_env.readiness_loop()
    assert loop.returncode == 0, (
        f"readiness loop faalde (rc={loop.returncode}):\n{loop.stdout}\n{loop.stderr}"
    )
    assert re.search(r"Readiness geslaagd na \d+ pogingen", loop.stdout), (
        f"geen succesmelding in de readiness loop:\n{loop.stdout}"
    )

    # De e2e-wrapper voert start -> readiness -> Playwright uit, en die volgorde
    # is bovendien in de feitelijke run gemeten (tijdstippen in runtime_env).
    e2e = runtime_env.mobile_e2e()
    assert e2e["readiness_rc"] == 0, e2e["readiness_output"]
    assert e2e["readiness_before_e2e"], (
        "de readiness loop is niet vóór `npm run test:e2e` afgerond"
    )

    wrapper = (runtime_env.ROOT / "scripts" / "run-mobile-e2e.sh").read_text(encoding="utf-8")
    assert wrapper.index("docker compose up -d --build") < wrapper.index(
        "readiness-loop.sh"
    ) < wrapper.index("npx playwright test"), (
        "run-mobile-e2e.sh voert start, readiness en e2e niet in die volgorde uit"
    )


# ==== Opruimgarantie bij een gefaalde start ================================


def test_startup_faal_ruimt_eigen_context_op() -> None:
    """Een fout ná een geslaagd `up` laat geen containers, poorten, netwerk of volume achter.

    De afbouw wordt direct ná `docker compose up -d --build` geregistreerd (nog
    vóór readiness/health), zodat ook een falende readiness de eigen context
    volledig opruimt. De hoofdstack en de echte volume blijven onaangeroerd.
    """
    runtime_env.require_docker()
    hoofd_before = runtime_env.compose_services()
    real_before = runtime_env.volume_state(runtime_env.REAL_VOLUME)

    ctx = runtime_env.isolated_context("startfail")
    project = ctx["project"]

    # Cleanups vóór `ensure_stack_up` registreren: `cleanup_all` werkt in
    # omgekeerde volgorde, dus de stack-cleanup (door `ensure_stack_up`
    # zelf geregistreerd) draait als eerste en deze twee daarna.
    def _verwijder_images() -> bool:
        runtime_env.run(
            ["docker", "image", "rm", f"{project}-frontend", f"{project}-backend"],
            timeout=300,
        )
        return True

    def _verwijder_werkmap() -> bool:
        shutil.rmtree(ctx["target"], ignore_errors=True)
        return True

    runtime_env.register_cleanup(f"werkmap {project}", _verwijder_werkmap)
    runtime_env.register_cleanup(f"images {project}", _verwijder_images)

    waargenomen: dict = {}

    def _faal_ready() -> dict:
        # De afbouw móet al geregistreerd zijn in de readiness-fase.
        waargenomen["cleanup_geregistreerd"] = runtime_env.cleanup_registered(
            ctx["cleanup_name"]
        )
        return {"ok": False, "attempts": 1, "frontend_status": 0, "backend_status": 0}

    with pytest.raises(AssertionError, match="niet ready"):
        runtime_env.ensure_stack_up(
            ctx["env"],
            ready_probe=_faal_ready,
            remove_volume=True,
            expect_network_gone=True,
        )

    assert waargenomen.get("cleanup_geregistreerd") is True, (
        "de afbouw werd niet direct ná het geslaagde `up` geregistreerd"
    )

    # Feitelijke restcontrole in de eigen context.
    assert runtime_env.compose_services(ctx["env"]) == {}, "containers bleven staan"
    assert runtime_env.volume_state(ctx["volume"]) is None, "eigen volume bleef bestaan"
    assert not runtime_env.network_exists(ctx["network"]), "eigen netwerk bleef bestaan"
    bezet = sorted(
        poort
        for poort, vrij in runtime_env.wait_ports_free(list(ctx["ports"])).items()
        if not vrij
    )
    assert bezet == [], f"poorten bleven bezet: {bezet}"

    # Eigen images weg (alleen die van dit project).
    runtime_env.run(
        ["docker", "image", "rm", f"{project}-frontend", f"{project}-backend"],
        timeout=300,
    )
    images = runtime_env.run(["docker", "images", "--format", "{{.Repository}}"])
    assert [naam for naam in images.stdout.split() if naam.startswith(project)] == [], (
        "eigen images bleven staan"
    )

    # De hoofdstack en de echte volume zijn niet geraakt. De kernvergelijking
    # laat de tijdsaanduiding van `docker compose ps` ("Up 58 seconds")
    # buiten beschouwing: die verandert ook zonder tussenkomst van deze test.
    assert runtime_env.volume_state(runtime_env.REAL_VOLUME) == real_before, (
        "de echte volume is door de gefaalde start gewijzigd"
    )
    kern_na = {
        naam: (entry["name"], entry["state"], entry["health"])
        for naam, entry in runtime_env.compose_services().items()
    }
    kern_voor = {
        naam: (entry["name"], entry["state"], entry["health"])
        for naam, entry in hoofd_before.items()
    }
    assert kern_na == kern_voor, (
        f"de hoofdstack is geraakt: {kern_voor} -> {kern_na}"
    )


# ==== Samenvattende integratietest suite ==========================


def test_integration_test_suite() -> None:
    """Samenvattende test suite voor alle integratietests."""
    # Elke integratietest wordt feitelijk uitgevoerd; de stack, de clean-checkout
    # en de e2e-run zijn per sessie gememoïseerd, dus er draait niets dubbel.
    test_complete_app_startup()
    test_frontend_backend_accessibility()
    test_health_endpoint_integration()
    test_mobile_responsiveness()
    test_app_functionality_empty_state()
    test_mobile_acceptance_playwright()
    test_mobile_acceptance_playwright_integration()
    test_readiness_loop_before_e2e()
    test_startup_faal_ruimt_eigen_context_op()
