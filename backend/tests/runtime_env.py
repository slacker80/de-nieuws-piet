"""Runtime-hulp voor tests die écht Docker Compose, Next.js en Playwright draaien.

Waarom deze module bestaat:

* Detectie via de Docker **CLI + daemon**, niet via de Python-`docker`-module.
  Die module is geen project-afhankelijkheid en zou tests laten overslaan op
  machines waar de CLI en de daemon wél gewoon beschikbaar zijn.
* Memoïsatie per pytest-sessie. Samenvattende tests (bv.
  `test_integration_test_suite`) roepen andere tests rechtstreeks aan; zonder
  memoïsatie zou `docker compose up -d --build`, `next build` of de mobiele
  e2e-suite meermaals draaien en zou elke test de stack ook weer affakkelen.
* Alleen eigen resources. De staat van de hoofdstack wordt vóór de eerste
  test vastgelegd; een stack die al actief was wordt nooit gestopt, `down -v`
  wordt door deze module nooit gebruikt en alle started resources krijgen een
  sessie-afbouw via `register_cleanup`/`cleanup_all` (conftest.sessionfinish).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "frontend"
COMPOSE_FILE = ROOT / "compose.yaml"
READINESS_LOOP = ROOT / "scripts" / "readiness-loop.sh"

MAIN_PROJECT = "de-nieuws-piet"
REAL_VOLUME = "nieuws_piet_sqlite_data"

FRONTEND_URL = "http://127.0.0.1:3000/"
BACKEND_HEALTH_URL = "http://127.0.0.1:8000/health"
NEXT_PORT = 3100
NEXT_URL = f"http://127.0.0.1:{NEXT_PORT}/"

# Docker-identificator: alleen alfanumeriek, `_`, `.` en `-`, beginnend met een
# alfanumeriek teken. Paden, slashes, backslashes, kolonnen en witruimte horen
# er nooit bij (dat zouden bind mounts of andermans resources zijn).
DOCKER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

_docker: bool | None = None
_node: bool | None = None
_initial_services: dict[str, dict] | None = None
_stack: dict | None = None
_build: dict | None = None
_serve: dict | None = None
_e2e: dict | None = None
_npm_ci: dict | None = None
_cleanups: list[tuple[str, object]] = []
# Overgeslagen tests (pytest.report); de lokale suite controleert dit aan het eind.
skipped_tests: list[str] = []


def validate_docker_name(name: str, what: str = "resource-naam") -> str:
    """Geeft `name` terug wanneer het een geldige Docker-identificator is.

    Anders een AssertionError (geen stille acceptatie): paden, slashes,
    backslashes, kolonnen en witruimte worden geweigerd.
    """
    if not isinstance(name, str) or not DOCKER_NAME_RE.match(name):
        raise AssertionError(
            f"ongeldige {what}: {name!r} — verwacht een Docker-identificator "
            "(alfanumeriek, `_`, `.`, `-`; geen paden, slashes, backslashes, "
            "kolonnen of witruimte)"
        )
    return name


def unique_slug(prefix: str) -> str:
    """Unieke, compose-geldige slug: prefix + pid + random (geen seconde-timestamp)."""
    validate_docker_name(prefix, "projectprefix")
    return f"{prefix}{os.getpid()}{secrets.token_hex(4)}"



# ==== Omgeving & uitvoering ================================================


def docker_available() -> bool:
    """True wanneer de Docker CLI én de daemon bereikbaar zijn (geen module-import)."""
    global _docker
    if _docker is None:
        if shutil.which("docker") is None:
            _docker = False
        else:
            try:
                probe = subprocess.run(
                    ["docker", "info", "--format", "{{.ServerVersion}}"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
            except (OSError, subprocess.TimeoutExpired):
                probe = None
            _docker = probe is not None and probe.returncode == 0
    return _docker


def require_docker(reason: str = "Docker niet beschikbaar") -> None:
    """Slaat de test over wanneer de Docker CLI/daemon ontbreekt."""
    if not docker_available():
        pytest.skip(reason)


def node_available() -> bool:
    global _node
    if _node is None:
        _node = shutil.which("npm") is not None and shutil.which("node") is not None
    return _node


def require_node(reason: str = "npm/node niet beschikbaar") -> None:
    if not node_available():
        pytest.skip(reason)


def build_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Sessie-omgeving plus expliciete extra's (nooit globaal in `os.environ`)."""
    env = dict(os.environ)
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    env.pop("CI", None)  # Playwright gedraagt zich ook buiten CI identiek
    if extra:
        env.update(extra)
    return env


def run(
    cmd: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int = 600,
    input: str | None = None,
) -> subprocess.CompletedProcess:
    """Voert een commando uit en vangt uitvoer + returncode af (geen check)."""
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env if env is not None else build_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input,
    )


def compose(
    *args: str,
    env: dict[str, str] | None = None,
    timeout: int = 600,
    cwd: Path = ROOT,
    input: str | None = None,
) -> subprocess.CompletedProcess:
    """`docker compose <args>` (projectdirectory = `cwd`, standaard de repo)."""
    return run(
        ["docker", "compose", *args],
        cwd=cwd,
        env=env,
        timeout=timeout,
        input=input,
    )


def compose_config(env: dict[str, str] | None = None) -> dict:
    """Opgeloste Compose-configuratie (echte Compose-parser, geen mock)."""
    proc = compose("config", "--format", "json", env=env, timeout=180)
    assert proc.returncode == 0, (
        f"docker compose config faalde (rc={proc.returncode}): {proc.stderr}"
    )
    return json.loads(proc.stdout)


def compose_services(env: dict[str, str] | None = None) -> dict[str, dict]:
    """Alle containers van het project (ook gestopte), per service."""
    proc = compose("ps", "--all", "--format", "json", env=env, timeout=180)
    assert proc.returncode == 0, (
        f"docker compose ps faalde (rc={proc.returncode}): {proc.stderr}"
    )
    services: dict[str, dict] = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        services[entry.get("Service", "")] = {
            "name": entry.get("Name", ""),
            "state": entry.get("State", ""),
            "health": entry.get("Health", ""),
            "status": entry.get("Status", ""),
        }
    return services


def initial_services() -> dict[str, dict]:
    """Projectstaat bij de allereerste test die Docker raakt (vóór alles wat start)."""
    global _initial_services
    if _initial_services is None:
        _initial_services = (
            compose_services() if docker_available() else {}
        )
    return _initial_services


def volume_state(name: str) -> str | None:
    """Vingerafdruk van een volume (bestaat + `CreatedAt`), of None.

    Deze Docker-versie publiceert geen volume-ID in `docker volume inspect`,
    dus `CreatedAt` is de stabiele identiteit: een volume dat verwijderd en
    opnieuw aangemaakt wordt (destructief pad) krijgt een nieuwe waarde, een
    volume dat behouden blijft (preserve pad) niet.
    """
    if not docker_available():
        return None
    proc = run(
        ["docker", "volume", "inspect", name, "--format", "{{.CreatedAt}}"],
        timeout=60,
    )
    created = proc.stdout.strip()
    if proc.returncode != 0 or not created:
        return None
    return created


def port_free(port: int) -> bool:
    """True wanneer er géén proces op 127.0.0.1:`port` luistert (dus vrij is).

    `SO_REUSEADDR` zorgt ervoor dat een rustende TIME_WAIT-verbinding op die
    poort (geen luisteraar) niet als "bezet" wordt gemeld; een actieve
    luisteraar bindt nooit met die optie, dus die blijft wél onderscheiden.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def wait_ports_free(
    ports: list[int], *, attempts: int = 10, delay: float = 1.0
) -> dict[int, bool]:
    """Wacht tot de opgegeven poorten vrij zijn (geef de eindstatus terug).

    Na `docker compose down` kan de poortdoorname (docker-proxy) nog enkele
    seconden blijven hangen; zonder deze wachtfase zou een correcte afbraak als
    een probleem worden gemeld.
    """
    status = {port: port_free(port) for port in ports}
    for _ in range(max(attempts, 1) - 1):
        if all(status.values()):
            break
        time.sleep(delay)
        for port, free in list(status.items()):
            if not free:
                status[port] = port_free(port)
    return status


def published_ports(env: dict[str, str] | None = None) -> list[int]:
    """Gepubliceerde host-poorten uit de opgeloste Compose-configuratie."""
    cfg = compose_config(env)
    ports: set[int] = set()
    for service in cfg.get("services", {}).values():
        for entry in service.get("ports") or []:
            published = entry.get("published") if isinstance(entry, dict) else str(entry).split(":")[0]
            try:
                ports.add(int(published))
            except (TypeError, ValueError):
                continue
    return sorted(ports)


def network_names(env: dict[str, str] | None = None) -> list[str]:
    """Oploste netwerknamen uit de Compose-configuratie."""
    cfg = compose_config(env)
    return [
        entry.get("name")
        for entry in cfg.get("networks", {}).values()
        if isinstance(entry, dict) and entry.get("name")
    ]


def network_exists(name: str) -> bool:
    return run(["docker", "network", "inspect", name], timeout=60).returncode == 0


def free_port(preferred: int) -> int:
    """Geeft `preferred` wanneer die vrij is, anders een willekeurig vrije poort."""
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return int(probe.getsockname()[1])
    raise AssertionError(f"geen vrije poort rond {preferred}")


def http_get(url: str, timeout: float = 5) -> tuple[int, str]:
    """HTTP-GET; geeft (0, "") bij verbindingsfout, anders (status, body)."""
    request = urllib.request.Request(url, headers={"User-Agent": "nieuws-piet-tests"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:  # pragma: no cover - zeldzame tak
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return int(exc.code), body
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return 0, ""


def register_cleanup(name: str, fn) -> None:
    """Registreert een afbouwactie voor resources die deze sessie startte."""
    _cleanups.append((name, fn))


def cleanup_registered(name: str) -> bool:
    """True wanneer de afbouwactie met deze naam al geregistreerd staat."""
    return any(registered == name for registered, _fn in _cleanups)


def cleanup_all() -> None:
    """Voert alle afbouwacties in omgekeerde volgorde uit (conftest.sessionfinish).

    Een cleanup die een fout meldt (exception, `False` of `{"ok": False}`) wordt
    expliciet gerapporteerd, zodat achtergebleven resources nooit onopgemerkt
    blijven.
    """
    while _cleanups:
        name, fn = _cleanups.pop()
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - afbouw mag de exit niet verpesten
            print(f"[runtime_env] cleanup {name} faalde: {exc}")
            continue
        if result is False or (isinstance(result, dict) and not result.get("ok", True)):
            print(f"[runtime_env] cleanup {name} meldt een probleem: {result}")


# ==== Compose-stack op de vaste acceptatiepoorten ==========================


def wait_ready(*, attempts: int = 60, sleep_seconds: float = 1.0) -> dict:
    """Wacht tot frontend én backend exact voldoen; geeft de meting terug."""
    evidence: dict = {
        "attempts": 0,
        "frontend_status": 0,
        "frontend_marker": False,
        "backend_status": 0,
        "backend_healthy": False,
        "ok": False,
    }
    for attempt in range(1, attempts + 1):
        frontend_status, frontend_body = http_get(FRONTEND_URL)
        backend_status, backend_body = http_get(BACKEND_HEALTH_URL)

        marker = "Nieuws Piet" in frontend_body
        healthy = False
        if backend_status == 200:
            try:
                healthy = json.loads(backend_body).get("status") == "healthy"
            except ValueError:
                healthy = False

        evidence.update(
            attempts=attempt,
            frontend_status=frontend_status,
            frontend_marker=marker,
            backend_status=backend_status,
            backend_healthy=healthy,
            backend_body=backend_body[:400],
        )
        if frontend_status == 200 and marker and backend_status == 200 and healthy:
            evidence["ok"] = True
            return evidence
        if attempt < attempts:
            time.sleep(sleep_seconds)
    return evidence


def wait_compose_health(
    service: str = "backend", *, attempts: int = 60, sleep_seconds: float = 1.0
) -> str:
    """Wacht tot de Docker-healthcheck van `service` `healthy` is.

    De HTTP-readiness kan al slaan terwijl de container-healthcheck nog in de
    `start_period` zit; deze meting is de echte Compose-healthstatus.
    """
    status = ""
    for _ in range(attempts):
        entry = compose_services().get(service)
        if entry is None:
            return ""
        status = entry.get("health", "")
        if status == "healthy":
            return status
        time.sleep(sleep_seconds)
    return status


def volume_names(env: dict[str, str] | None = None) -> list[str]:
    """Oploste volumenamen uit de Compose-configuratie."""
    cfg = compose_config(env)
    return [
        entry.get("name")
        for entry in cfg.get("volumes", {}).values()
        if isinstance(entry, dict) and entry.get("name")
    ]


def stop_stack(
    env: dict[str, str] | None = None,
    *,
    remove_volume: bool = False,
    expect_network_gone: bool = False,
) -> dict:
    """Breekt een eigen stack af én verifieert dat er niets achterblijft.

    Na `down` wordt gecontroleerd op: geen containers meer van dit project,
    alle gepubliceerde poorten vrij, volumestatus (`down` houdt het volume,
    `down -v` verwijdert het) en — wanneer deze context het netwerk zelf
    aanmaakte — het ontbreken daarvan. Het resultaat bevat `ok` plus de
    gevonden `problems`, zodat een falende opruiming nooit onopgemerkt blijft.
    """
    require_docker()
    try:
        ports = published_ports(env)
        volumes = volume_names(env)
        networks = network_names(env)
    except AssertionError:  # config niet (meer) leesbaar: nog steeds opruimen
        ports, volumes, networks = [], [], []

    args = ["down"] + (["-v"] if remove_volume else []) + ["--remove-orphans"]
    down = compose(*args, env=env, timeout=600)
    containers = compose_services(env)
    # Poorten krijgen na `down` enige tijd; wachten voorkomt een valse melding.
    port_status = wait_ports_free(ports)
    volume_status = {name: volume_state(name) for name in volumes}
    network_status = {name: network_exists(name) for name in networks}

    problems: list[str] = []
    if down.returncode != 0:
        problems.append(f"`docker compose {' '.join(args)}` gaf rc={down.returncode}")
    if containers:
        problems.append(f"containers blijven staan: {sorted(containers)}")
    busy = sorted(port for port, free in port_status.items() if not free)
    if busy:
        problems.append(f"poorten blijven bezet: {busy}")
    for name, state in volume_status.items():
        if remove_volume and state is not None:
            problems.append(f"volume {name} bestaat nog na `down -v`")
        if not remove_volume and state is None:
            problems.append(f"volume {name} is verwijderd terwijl dat niet mocht")
    if expect_network_gone:
        for name, exists in network_status.items():
            if exists:
                problems.append(f"netwerk {name} bestaat nog")

    return {
        "ok": not problems,
        "problems": problems,
        "project": MAIN_PROJECT if env is None else env.get("COMPOSE_PROJECT_NAME", ""),
        "rc": down.returncode,
        "args": args,
        "containers": containers,
        "ports": port_status,
        "volumes": volume_status,
        "networks": network_status,
    }


def isolated_context(prefix: str) -> dict:
    """Eigen projectnaam, volume, netwerk, poorten en werkmap voor een test.

    Alleen dit project wordt geraakt; de hoofdstack en de echte volume
    `nieuws_piet_sqlite_data` blijven buiten beeld. Bij een fout tijdens het
    opzetten wordt de werkmap direct verwijderd.
    """
    require_docker()
    project = unique_slug(prefix.lower())
    volume = validate_docker_name(f"{REAL_VOLUME}_{project}", "volumenaam")
    network = validate_docker_name(f"nieuws_piet_net_{project}", "netwerknaam")
    target = Path(tempfile.mkdtemp(prefix=f"nieuws-piet-{prefix.lower()}-"))
    try:
        override = target / "compose.isolated.yaml"
        frontend_port = free_port(13000)
        backend_port = free_port(18000)
        override.write_text(
            "# Tijdelijke override voor een geïsoleerde testcontext (niet getrackt):\n"
            "# eigen poorten, eigen volume en eigen netwerk, zodat de hoofdstack\n"
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
        env = build_env(
            {
                "COMPOSE_PROJECT_NAME": project,
                "COMPOSE_FILE": f"{COMPOSE_FILE}:{override}",
            }
        )
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return {
        "project": project,
        "volume": volume,
        "network": network,
        "target": target,
        "override": override,
        "env": env,
        "ports": (frontend_port, backend_port),
        "cleanup_name": f"stack afbreken ({project})",
    }


def ensure_stack_up(
    env: dict[str, str] | None = None,
    *,
    ready_probe=None,
    health_probe=None,
    remove_volume: bool = False,
    expect_network_gone: bool = False,
) -> dict:
    """`docker compose up -d --build` + readiness, maximaal één keer per sessie.

    De afbouw wordt **onmiddellijk na een succesvol `up` geregistreerd** (nog
    vóór readiness en health), zodat elke fout daarna — inclusief een falende
    readiness — de context toch opruimt. Gooit een AssertionError met de
    feitelijke Compose-uitvoer; vóór het opgooien wordt de eigen context
    afgebroken en gecontroleerd.
    """
    global _stack
    require_docker()
    main = env is None
    if main and _stack is not None and _stack.get("ready"):
        return _stack

    project = (
        MAIN_PROJECT
        if main
        else validate_docker_name(env.get("COMPOSE_PROJECT_NAME", ""), "projectnaam")
    )
    started = (not initial_services()) if main else True
    cleanup_name = f"stack afbreken ({project})"

    def _stop() -> dict:
        return stop_stack(
            env, remove_volume=remove_volume, expect_network_gone=expect_network_gone
        )

    up = compose("up", "-d", "--build", env=env, timeout=900)
    if up.returncode != 0:
        detail = f"--- stdout ---\n{up.stdout}\n--- stderr ---\n{up.stderr}"
        if started:
            # Ook een mislukte start mag geen restanten achterlaten.
            detail += f"\n--- opruiming ---\n{_stop()}"
        raise AssertionError(
            f"docker compose up -d --build faalde (rc={up.returncode})\n{detail}"
        )

    if started:
        # MÉTEN na het geslaagde `up`, vóór readiness/health.
        register_cleanup(cleanup_name, _stop)

    try:
        ready = ready_probe() if ready_probe is not None else wait_ready()
        assert ready.get("ok"), (
            f"stack niet ready na {ready.get('attempts')} pogingen: {ready}"
        )
        docker_health = (
            health_probe("backend") if health_probe is not None else wait_compose_health("backend")
        )
        assert docker_health == "healthy", (
            f"Compose-healthcheck van de backend is niet healthy (status: {docker_health})"
        )
    except BaseException:
        if started:
            result = _stop()
            if not result["ok"]:
                print(f"[runtime_env] opruiming na gefaalde start: {result['problems']}")
        if main:
            _stack = None
        raise

    result = {
        "started": started,
        "ready": True,
        "docker_health": docker_health,
        "project": project,
        "cleanup": cleanup_name if started else None,
        "containers": compose_services(env),
        **ready,
    }
    if main:
        _stack = result
    return result


def stop_main_stack() -> bool:
    """Stopt de hoofdstack alléén wanneer deze sessie ze startte.

    Controleert het resultaat: geen containers meer, vrije poorten en de echte
    volume `nieuws_piet_sqlite_data` moet bewaard blijven (nooit `down -v`).
    `True` betekent "niets te doen of netjes opgeruimd" — alleen een feitelijk
    gefaalde opruiming geeft `False`.
    """
    global _stack
    if os.environ.get("NIEUWS_PIET_KEEP_STACK") == "1":
        return True  # bewust niet stoppen
    if _stack is None or not _stack.get("started"):
        return True  # niets (meer) om af te breken
    result = stop_stack(None, remove_volume=False)
    _stack = None
    if not result["ok"]:
        print(f"[runtime_env] hoofdstack-stop meldt: {result['problems']}")
    return bool(result["ok"])


def release_main_ports() -> tuple[bool, str]:
    """Maakt 127.0.0.1:3000/8000 vrij voor een wegwerp-context.

    (False, reden) wanneer de stack al vóór deze sessie actief was: die wordt
    nooit gestopt, zodat tests nooit de bestaande diensten van de gebruiker
    onderbreken.
    """
    require_docker()
    if initial_services():
        return False, "hoofdstack was al actief vóór deze testsessie en wordt niet gestopt"
    stop_main_stack()
    running = [
        name
        for name, entry in compose_services().items()
        if entry.get("state") == "running"
    ]
    if running:
        return False, f"hoofdstack nog actief: {sorted(running)}"
    return True, "poorten 3000/8000 vrij"


def readiness_loop() -> subprocess.CompletedProcess:
    """Draait het echte frontend/backend readiness-loop-script."""
    require_docker()
    return run(["bash", str(READINESS_LOOP)], timeout=300)


# ==== Next.js ==============================================================


def next_build() -> dict:
    """Één `npm run build` per sessie met de feitelijke returncode."""
    global _build
    require_node()
    if _build is None:
        started = time.monotonic()
        proc = run(["npm", "run", "build"], cwd=FRONTEND_DIR, timeout=600)
        _build = {
            "rc": proc.returncode,
            "output": f"{proc.stdout}\n{proc.stderr}",
            "seconds": round(time.monotonic() - started, 1),
        }
    return _build


def next_serve() -> dict:
    """Serveert de gebouwde Next.js-app lokaal op poort 3100 (één keer per sessie)."""
    global _serve
    require_node()
    if _serve is not None and _serve.get("alive"):
        return _serve

    build = next_build()
    assert build["rc"] == 0, f"next build faalde (rc={build['rc']}):\n{build['output']}"

    log_path = Path(
        f"/tmp/nieuws-piet-next-start-{os.getpid()}-{secrets.token_hex(3)}.log"
    )
    log_handle = log_path.open("w")
    proc = subprocess.Popen(
        ["npm", "run", "start", "--", "-p", str(NEXT_PORT)],
        cwd=str(FRONTEND_DIR),
        env=build_env(),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )

    def _stop() -> None:
        serve = _serve
        if not serve:
            return
        serve["alive"] = False
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        log_handle.close()
        log_path.unlink(missing_ok=True)

    register_cleanup("next start stoppen", _stop)

    status = 0
    output = ""
    for _ in range(60):
        if proc.poll() is not None:
            break
        status, _body = http_get(NEXT_URL)
        if status == 200:
            _serve = {"alive": True, "url": NEXT_URL, "log": str(log_path), "status": status}
            return _serve
        time.sleep(1)

    log_handle.flush()
    output = log_path.read_text(errors="replace") if log_path.exists() else ""
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
    log_handle.close()
    _serve = {"alive": False, "url": NEXT_URL, "log": str(log_path), "status": status}
    raise AssertionError(
        f"next start gaf geen HTTP 200 op {NEXT_URL} (laatste status {status})\n"
        f"--- next start uitvoer ---\n{output}"
    )


def next_stop() -> None:
    serve = _serve
    if serve:
        serve["alive"] = False


# ==== Mobiele Playwright-e2e ===============================================


def mobile_e2e() -> dict:
    """`npm run test:e2e` (met de readiness loop vóór de run), één keer per sessie."""
    global _e2e
    require_node()
    if _e2e is not None:
        return _e2e

    stack = ensure_stack_up()
    readiness_started = time.monotonic()
    loop = readiness_loop()
    readiness_finished = time.monotonic()
    started = time.monotonic()
    proc = run(
        ["npm", "run", "test:e2e"],
        cwd=FRONTEND_DIR,
        env=build_env({"PW_HEADLESS": "1"}),
        timeout=900,
    )
    _e2e = {
        "rc": proc.returncode,
        "output": f"{proc.stdout}\n{proc.stderr}",
        "seconds": round(time.monotonic() - started, 1),
        "readiness_rc": loop.returncode,
        "readiness_output": f"{loop.stdout}\n{loop.stderr}",
        # Readiness MOET vóór de e2e-run afgerond zijn: de tijdstippen maken
        # die volgorde aantoonbaar in plaats van alleen aannemelijk.
        "readiness_before_e2e": (
            loop.returncode == 0 and readiness_finished <= started
        ),
        "readiness_seconds": round(readiness_finished - readiness_started, 1),
        "stack": stack,
    }
    return _e2e


def local_chromium() -> dict:
    """Lokale chromium-browser via de Playwright-browserregistry (geen cloud browser)."""
    require_node()
    probe = run(
        [
            "node",
            "-e",
            "const {chromium}=require('playwright-core');"
            "const fs=require('fs');"
            "const p=chromium.executablePath();"
            "process.stdout.write(JSON.stringify({path:p,exists:fs.existsSync(p)}))",
        ],
        cwd=FRONTEND_DIR,
        timeout=120,
    )
    assert probe.returncode == 0, f"chromium-pad kon niet worden bepaald: {probe.stderr}"
    data = json.loads(probe.stdout)
    dry = run(
        ["npx", "playwright", "install", "--dry-run", "chromium"],
        cwd=FRONTEND_DIR,
        timeout=300,
    )
    data["dry_run_rc"] = dry.returncode
    data["dry_run_output"] = f"{dry.stdout}\n{dry.stderr}"
    data["home"] = str(Path.home())
    return data


def installed_playwright_version() -> str | None:
    """Versie van de daadwerkelijk geïnstalleerde `@playwright/test`-package."""
    pkg = FRONTEND_DIR / "node_modules" / "@playwright" / "test" / "package.json"
    if not pkg.exists():
        return None
    return json.loads(pkg.read_text()).get("version")


def npm_ci_isolated() -> dict:
    """Feitelijk `npm ci` in een verse, geïsoleerde kopie van `frontend/`.

    De bestaande `frontend/node_modules` wordt bewust NIET gebruikt: alleen
    `package.json` en `package-lock.json` worden gekopieerd, `npm ci` bouwt de
    boom van nul op en de lokale Chromium-setup (`npx playwright install
    chromium` + het executable-pad) wordt vanuit die verse installatie
    gecontroleerd. De werkmap wordt altijd verwijderd, ook wanneer een stap
    faalt. Alleen lokale packages (bootstrap-toegestaan); geen cloud browser.
    """
    global _npm_ci
    require_node()
    if _npm_ci is not None:
        return _npm_ci

    target = Path(tempfile.mkdtemp(prefix=f"nieuws-piet-npmci-{os.getpid()}-"))
    evidence: dict = {
        "target": str(target),
        "copied": [],
        "rc": None,
        "output": "",
        "seconds": 0.0,
        "pin": None,
        "locked": None,
        "installed": None,
        "fresh_install": False,
        "node_modules_present": False,
        "packages": 0,
        "browser_rc": None,
        "browser_output": "",
        "executable": None,
        "executable_exists": False,
        "home": str(Path.home()),
    }
    try:
        for name in ("package.json", "package-lock.json"):
            shutil.copy2(FRONTEND_DIR / name, target / name)
            evidence["copied"].append(name)
        npmrc = FRONTEND_DIR / ".npmrc"
        if npmrc.exists():
            shutil.copy2(npmrc, target / npmrc.name)
            evidence["copied"].append(".npmrc")

        manifest = json.loads((target / "package.json").read_text(encoding="utf-8"))
        lockfile = json.loads((target / "package-lock.json").read_text(encoding="utf-8"))
        evidence["pin"] = manifest.get("devDependencies", {}).get("@playwright/test")
        evidence["locked"] = lockfile.get("packages", {}).get(
            "node_modules/@playwright/test", {}
        ).get("version")

        # Geen overgenomen node_modules: `npm ci` bepaalt de hele boom.
        evidence["fresh_install"] = not (target / "node_modules").exists()
        started = time.monotonic()
        ci = run(["npm", "ci", "--no-audit", "--no-fund"], cwd=target, timeout=900)
        evidence["rc"] = ci.returncode
        evidence["output"] = f"{ci.stdout}\n{ci.stderr}"
        evidence["seconds"] = round(time.monotonic() - started, 1)

        installed_pkg = target / "node_modules" / "@playwright" / "test" / "package.json"
        evidence["node_modules_present"] = installed_pkg.exists()
        if installed_pkg.exists():
            evidence["installed"] = json.loads(installed_pkg.read_text()).get("version")
        modules = target / "node_modules"
        evidence["packages"] = len(list(modules.iterdir())) if modules.is_dir() else 0

        # Feitelijke lokale browser-setup vanuit deze verse installatie.
        browser = run(["npx", "playwright", "install", "chromium"], cwd=target, timeout=900)
        evidence["browser_rc"] = browser.returncode
        evidence["browser_output"] = f"{browser.stdout}\n{browser.stderr}"

        probe = run(
            [
                "node",
                "-e",
                "const {chromium}=require('playwright-core');"
                "const fs=require('fs');"
                "const p=chromium.executablePath();"
                "process.stdout.write(JSON.stringify({path:p,exists:fs.existsSync(p)}))",
            ],
            cwd=target,
            timeout=120,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            data = json.loads(probe.stdout)
            evidence["executable"] = data.get("path")
            evidence["executable_exists"] = bool(data.get("exists"))

        _npm_ci = evidence
        return evidence
    finally:
        # Gegarandeerde opruiming, ook bij een falende stap.
        shutil.rmtree(target, ignore_errors=True)


def external_urls(text: str) -> list[str]:
    """Absolute URLs die niet naar localhost/127.0.0.1 wijzen."""
    urls = re.findall(r"https?://[^\s\"'<>\\)]+", text)
    return [
        url
        for url in urls
        if not re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?(/|$)", url)
    ]


# ==== Feitelijke mobiele meting in de lokale chromium-browser =============

# Meting in de browser zelf (360x800, lokale chromium, netwerkisolatie):
# viewport vóór navigatie, landmarks/teksten, scrollbreedte en console-fouten.
# Auto-retry via `waitFor` (geen vaste slaaptijd), net als de Playwright-suite.
_PROBE_JS = r"""
// Modulepad via de omgeving: het script staat in /tmp, dus Node zou
// `require('@playwright/test')` niet in frontend/node_modules vinden.
const { chromium } = require(process.env.PROBE_PW_MODULE);

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 360, height: 800 } });
    const blocked = [];
    const consoleErrors = [];

    // Netwerkisolatie: alleen localhost/127.0.0.1 mag verkeer zien. Op de
    // context, zodat elke pagina in deze meting eraan gehoorzaamt.
    await context.route('**/*', (route) => {
      const url = route.request().url();
      let host = '';
      try { host = new URL(url).hostname; } catch (error) { host = ''; }
      if (host === 'localhost' || host === '127.0.0.1') return route.continue();
      // `example.invalid` is de bewuste controleaanvraag en wordt apart gemeld.
      if (host !== 'example.invalid') blocked.push(url);
      return route.abort();
    });

    const page = await context.newPage();
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', (error) => consoleErrors.push(String(error)));

    // Viewport staat al vóór de navigatie op 360x800.
    await page.goto('http://localhost:3000/', { waitUntil: 'load' });

    // Auto-retry readiness: marker moet zichtbaar worden (geen `waitForTimeout`).
    await page.getByText('Nieuws Piet').first().waitFor({ state: 'visible', timeout: 10000 });

    const markerVisible = await page.getByText('Nieuws Piet').first().isVisible();
    const navVisible = await page.locator('nav').first().isVisible();
    const mainVisible = await page.locator('main').first().isVisible();
    const emptyVisible = await page
      .getByText('Nog geen nieuws beschikbaar')
      .first()
      .isVisible();

    const metrics = await page.evaluate(() => {
      const root = document.documentElement;
      const overflowing = [];
      for (const el of document.querySelectorAll('body *')) {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.right > root.clientWidth + 1) {
          const cls = el.className ? String(el.className).trim().split(/\s+/)[0] : '';
          overflowing.push(el.tagName.toLowerCase() + (cls ? '.' + cls : ''));
        }
      }
      return {
        scrollWidth: root.scrollWidth,
        clientWidth: root.clientWidth,
        title: document.title,
        overflowing,
        hasManifest: !!document.querySelector('link[rel="manifest"]'),
        h1: (document.querySelector('h1') || {}).textContent || '',
      };
    });

    // Bewuste controle: een verzoek naar niet-localhost moet geblokkeerd worden.
    // Op een aparte pagina, zodat de console van de gemeten pagina schoon blijft.
    const guard = await context.newPage();
    const externalFetch = await guard.evaluate(() =>
      fetch('https://example.invalid/nieuws')
        .then(() => 'reached')
        .catch(() => 'blocked')
    );
    await guard.close();

    process.stdout.write('PROBE_JSON:' + JSON.stringify({
      url: page.url(),
      viewport: page.viewportSize(),
      markerVisible,
      navVisible,
      mainVisible,
      emptyVisible,
      scrollWidth: metrics.scrollWidth,
      clientWidth: metrics.clientWidth,
      noHorizontalScroll: metrics.scrollWidth <= metrics.clientWidth,
      overflowing: metrics.overflowing,
      title: metrics.title,
      hasManifest: metrics.hasManifest,
      h1: metrics.h1,
      externalFetch,
      blocked,
      consoleErrors,
    }));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""

_probe: dict | None = None


def mobile_probe() -> dict:
    """Meet de pagina in lokale chromium bij 360x800 (één keer per sessie)."""
    global _probe
    require_node()
    if _probe is not None:
        return _probe

    ensure_stack_up()

    with tempfile.NamedTemporaryFile(
        "w", suffix=".js", prefix="nieuws-piet-probe-", delete=False
    ) as handle:
        handle.write(_PROBE_JS)
        script_path = Path(handle.name)
    try:
        proc = run(
            ["node", str(script_path)],
            cwd=FRONTEND_DIR,
            env=build_env(
                {"PROBE_PW_MODULE": str(FRONTEND_DIR / "node_modules" / "@playwright" / "test")}
            ),
            timeout=300,
        )
    finally:
        script_path.unlink(missing_ok=True)

    assert proc.returncode == 0, (
        f"mobiele meting faalde (rc={proc.returncode})\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    match = re.search(r"PROBE_JSON:(\{.*\})", proc.stdout, re.S)
    assert match, f"geen meetresultaat in de uitvoer:\n{proc.stdout}\n{proc.stderr}"
    _probe = json.loads(match.group(1))
    return _probe
