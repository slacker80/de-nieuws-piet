"""Data-safe rollback met feitelijke uitvoering (taken 9.1.7 t/m 9.1.10).

De statische controles — volgorde, opt-in-guard en volume-identiteit in tekst
en script — staan in `tests/test_exact_verification.py`. Hier wordt
`scripts/db-rollback.sh` daadwerkelijk uitgevoerd in een wegwerp-context:

* eigen Compose-projectnaam, eigen volume, eigen netwerk en eigen
  backup-directory (via de env-overrides van het script);
 * de hoofdstack wordt alleen vrijgegeven wanneer deze sessie hem startte;
 * de echte volume `nieuws_piet_sqlite_data` wordt op de `CreatedAt`-
   vingerafdruk vóór en na afloop vergeleken en moet exact gelijk zijn;
* de opbouw en afbraak gebeuren met `up -d --build` en `down -v` op de eigen
  projectnaam, plus het verwijderen van alleen die eigen image-tags.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from tests import runtime_env
from tests.test_exact_verification import _bash_functie

# Het script draait altijd vanaf de repo-root (het cd't zelf); deze paden zijn
# alleen voor het lezen van de bron.
SCRIPT = runtime_env.ROOT / "scripts" / "db-rollback.sh"

# Python-script voor de integriteitsverificatie na herstel: PRAGMA
# integrity_check + ten minste één tabel + de data-marker.
INTEGRITY_PY = """
import sqlite3, sys

conn = sqlite3.connect('/app/data/news.db')
integrity = conn.execute('PRAGMA integrity_check').fetchone()
tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()
marker = conn.execute("SELECT value FROM bootstrap_marker WHERE key = 'initialized'").fetchone()
conn.close()

integrity_ok = integrity is not None and integrity[0] == 'ok'
tables_ok = tables is not None and tables[0] > 0
marker_ok = marker is not None and marker[0] == 'nieuws-piet'
print('integrity_check:', integrity[0] if integrity else 'none',
      '| tables:', tables[0] if tables else 0,
      '| marker:', marker[0] if marker else None)
sys.exit(0 if integrity_ok and tables_ok and marker_ok else 1)
"""


def _run_script(name: str, *args: str, env: dict) -> dict:
    """Voert `scripts/db-rollback.sh <name> [args]` uit met de wegwerp-context."""
    proc = runtime_env.run(
        ["bash", str(SCRIPT), name, *args],
        env=env,
        timeout=900,
    )
    return {
        "rc": proc.returncode,
        "output": f"{proc.stdout}\n{proc.stderr}",
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _zet_marker(pad: Path, waarde: str | None) -> None:
    """Zet (`waarde`) of verwijdert (`None`) `bootstrap_marker.initialized`.

    Faalt wanneer de rij niet bestaat, zodat een test nooit per ongeluk een
    andere situatie test dan bedoeld.
    """
    conn = sqlite3.connect(pad)
    if waarde is None:
        cursor = conn.execute(
            "DELETE FROM bootstrap_marker WHERE key = 'initialized'"
        )
    else:
        cursor = conn.execute(
            "UPDATE bootstrap_marker SET value = ? WHERE key = 'initialized'",
            (waarde,),
        )
    gewijzigd = cursor.rowcount
    conn.commit()
    conn.close()
    assert gewijzigd == 1, f"bootstrap_marker.initialized niet gevonden in {pad}"


def _zet_marker_in_volume(env: dict, waarde: str | None, *, stop_backend: bool = True) -> None:
    """Zet/verwijdert de marker in `/app/data/news.db` van de eigen stack.

    `stop_backend=False` laat de draaiende backend ongemoeid: die herstelt de
    marker alleen bij startup (`init_database`), zodat de beschadiging
    zichtbaar blijft voor de verificatie die ná de start draait.
    """
    if stop_backend:
        runtime_env.compose("stop", "backend", env=env, timeout=300)
    if waarde is None:
        actie = "DELETE FROM bootstrap_marker WHERE key = 'initialized'"
    else:
        actie = (
            f"UPDATE bootstrap_marker SET value = '{waarde}' "
            "WHERE key = 'initialized'"
        )
    code = (
        "import sqlite3\n"
        "conn = sqlite3.connect('/app/data/news.db')\n"
        f"cur = conn.execute({actie!r})\n"
        "assert cur.rowcount == 1, 'markerrij ontbreekt'\n"
        "conn.commit()\n"
        "conn.close()\n"
    )
    proc = runtime_env.compose(
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--entrypoint",
        "python",
        "backend",
        "-c",
        code,
        env=env,
        timeout=300,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"


def _wait_health(attempts: int = 60) -> dict:
    """Wacht tot de eigen /health op `status: healthy` antwoordt."""
    import json as _json

    status, body = 0, ""
    for _ in range(attempts):
        status, body = runtime_env.http_get(runtime_env.BACKEND_HEALTH_URL)
        if status == 200:
            try:
                if _json.loads(body).get("status") == "healthy":
                    return {"ready": True, "status": status, "body": body}
            except ValueError:
                pass
        time.sleep(1)
    return {"ready": False, "status": status, "body": body}


@pytest.fixture(scope="module")
def rollback_session():
    """Wegwerp-context waarin preserve én destructive pad feitelijk draaien."""
    runtime_env.require_docker()

    ports_free, reason = runtime_env.release_main_ports()
    if not ports_free:
        pytest.skip(f"rollback-verificatie overgeslagen: {reason}")

    real_before = runtime_env.volume_state(runtime_env.REAL_VOLUME)
    # Compose-projectnamen zijn uitsluitend lowercase alfanumeriek met `-`/`_`;
    # de slug is uniek via pid + random (geen seconde-timestamp).
    project = runtime_env.unique_slug("rollback")
    volume = f"{runtime_env.REAL_VOLUME}_{project}"
    network = f"nieuws_piet_net_{project}"
    workdir = Path(tempfile.mkdtemp(prefix="nieuws-piet-rollback-"))
    backup_dir = workdir / "backups"
    override = workdir / "compose.rollback.yaml"

    override.write_text(
        "# Tijdelijke override voor de rollback-verificatie (niet getrackt):\n"
        "# eigen volume en eigen netwerk, zodat de echte volume\n"
        "# `nieuws_piet_sqlite_data` nooit wordt aangeraakt. Poorten blijven\n"
        "# 3000/8000 zodat het script exact zijn eigen /health-check kan draaien.\n"
        "volumes:\n"
        "  nieuws_piet_sqlite_data:\n"
        f"    name: {volume}\n"
        "networks:\n"
        "  nieuws_piet:\n"
        f"    name: {network}\n",
        encoding="utf-8",
    )

    env = runtime_env.build_env(
        {
            "COMPOSE_PROJECT_NAME": project,
            "COMPOSE_FILE": f"{runtime_env.COMPOSE_FILE}:{override}",
            "NIEUWS_PIET_DB_VOLUME": volume,
            "NIEUWS_PIET_DB_BACKUP_DIR": str(backup_dir),
        }
    )

    evidence: dict = {
        "project": project,
        "volume": volume,
        "network": network,
        "workdir": str(workdir),
        "backup_dir": backup_dir,
        "env": env,
        "real_before": real_before,
        "real_after": None,
        "runs": {},
        "volume_states": {},
        "up_rc": None,
        "up_output": "",
        "ready": {},
        "corrupt_rc": None,
        "refusal_state": {},
        "down_rc": None,
        "down_output": "",
        "containers_after": {},
        "images_after": [],
        "teardown": None,
    }

    def teardown() -> dict:
        """Breekt alléén de eigen wegwerp-context af (idempotent)."""
        if state["done"]:
            return evidence
        state["done"] = True
        down = runtime_env.compose(
            "down", "-v", "--remove-orphans", env=env, timeout=600
        )
        evidence["down_rc"] = down.returncode
        evidence["down_output"] = f"{down.stdout}\n{down.stderr}"
        evidence["containers_after"] = runtime_env.compose_services(env=env)
        runtime_env.run(
            ["docker", "image", "rm", f"{project}-frontend", f"{project}-backend"],
            timeout=300,
        )
        images = runtime_env.run(["docker", "images", "--format", "{{.Repository}}"])
        evidence["images_after"] = [
            line for line in images.stdout.split() if line.startswith(project)
        ]
        evidence["real_after"] = runtime_env.volume_state(runtime_env.REAL_VOLUME)
        return evidence

    state: dict = {"done": False}
    evidence["teardown"] = teardown

    try:
        # Stap 0: eigen stack starten zodat de database in het eigen volume bestaat.
        up = runtime_env.compose("up", "-d", "--build", env=env, timeout=900)
        evidence["up_rc"] = up.returncode
        evidence["up_output"] = f"{up.stdout}\n{up.stderr}"
        assert up.returncode == 0, (
            f"docker compose up -d --build faalde in de wegwerp-context:\n"
            f"{evidence['up_output']}"
        )
        ready = _wait_health()
        assert ready["ready"], f"geen healthy /health na start: {ready}"
        evidence["ready"] = ready
        evidence["volume_states"]["start"] = runtime_env.volume_state(volume)
        assert evidence["volume_states"]["start"], "eigen volume niet aangemaakt"

        # Stap 1: geldige backup van de intacte database (read-only, niet-destructief).
        evidence["runs"]["backup"] = _run_script("backup", env=env)
        assert evidence["runs"]["backup"]["rc"] == 0, evidence["runs"]["backup"]["output"]
        backups = sorted(backup_dir.glob("news.db.*.bak"))
        assert backups, f"geen backup aangemaakt in {backup_dir}"
        evidence["backups"] = [path.name for path in backups]

        # Stap 2: database corrupt maken, zodat het preserve-pad feitelijk moet
        # herstellen (zonder corruptie zou preserve niets te herstellen hebben).
        corrupt = runtime_env.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{volume}:/target",
                "alpine:3.20",
                "sh",
                "-c",
                "set -eu; printf 'corrupt-%s' \"$(date -u +%s)\" > /target/news.db; "
                "ls -la /target",
            ],
            timeout=300,
        )
        evidence["corrupt_rc"] = corrupt.returncode
        assert corrupt.returncode == 0, corrupt.stderr

        # Stap 3: preserve-pad (non-destructief) met feitelijk herstel.
        evidence["runs"]["preserve"] = _run_script("preserve", env=env)
        evidence["volume_states"]["na_preserve"] = runtime_env.volume_state(volume)

        # Stap 4: reset zonder opt-in moet weigeren vóór elke destructieve actie.
        refusal = _run_script("reset", env=env)
        evidence["runs"]["refusal"] = refusal
        evidence["refusal_state"] = {
            "services": {
                name: entry["state"]
                for name, entry in runtime_env.compose_services(env=env).items()
            },
            "volume_state": runtime_env.volume_state(volume),
            "backups": sorted(path.name for path in backup_dir.glob("news.db.*.bak")),
        }

        # Stap 5: destructive pad mét opt-in (backup -> validatie -> down -v ->
        # restore -> verificatie), inclusief de volumewissel.
        evidence["volume_states"]["voor_reset"] = runtime_env.volume_state(volume)
        evidence["runs"]["reset"] = _run_script(
            "reset", "--allow-volume-removal", env=env
        )
        evidence["volume_states"]["na_reset"] = runtime_env.volume_state(volume)
        evidence["backups_na_reset"] = sorted(
            path.name for path in backup_dir.glob("news.db.*.bak")
        )

        # De stack blijft actief tot alle tests hierop draaiden; de afbraak
        # gebeurt in `teardown()` (aangeroepen door 9.1.10 én als veiligheidsnet).
        yield evidence
    finally:
        teardown()
        shutil.rmtree(workdir, ignore_errors=True)
        # Veiligheidsnet: ook wanneer een test hierboven faalt, blijft alleen de
        # eigen context opgeruimd en is de echte volume onaangeroerd.
        assert evidence["down_rc"] == 0, (
            f"eigen context kon niet worden afgebroken:\n{evidence['down_output']}"
        )
        assert evidence["containers_after"] == {}, (
            f"eigen containers zijn blijven staan: {evidence['containers_after']}"
        )
        assert evidence["images_after"] == [], (
            f"eigen images zijn blijven staan: {evidence['images_after']}"
        )
        assert evidence["real_before"] == evidence["real_after"], (
            "de echte volume `nieuws_piet_sqlite_data` is door de rollback-tests gewijzigd"
        )

    return evidence


# ==== 9.1.7 Feitelijk restore op beide paden ==============================


def test_9_1_7_restore_feitelijk_preserve_en_destructief(rollback_session) -> None:
    """9.1.7 Backup wordt feitelijk teruggezet naar `/app/data/news.db` in het named volume (preserve én destructive)."""
    preserve = rollback_session["runs"]["preserve"]
    reset = rollback_session["runs"]["reset"]

    # Preserve-pad: herstel na `docker compose down` (volume behouden).
    assert preserve["rc"] == 0, f"preserve-pad faalde:\n{preserve['output']}"
    assert "==> Feitelijk restore naar /app/data/news.db" in preserve["output"], (
        f"geen feitelijke restore in het preserve-pad:\n{preserve['output']}"
    )
    assert "restore vóór backend-start" in preserve["output"], (
        preserve["output"]
    )
    assert (
        f"OK: preserve-pad voltooid (volume {rollback_session['volume']} behouden)"
        in preserve["output"]
    ), preserve["output"]
    assert rollback_session["volume_states"]["start"] == rollback_session["volume_states"]["na_preserve"], (
        "het preserve-pad heeft het volume vervangen in plaats van behouden"
    )
    assert rollback_session["backups"], "geen backup uit het preserve-pad"

    # Destructief pad: herstel pas ná `docker compose down -v`, in het opnieuw
    # aangemaakte volume.
    assert reset["rc"] == 0, f"destructief pad faalde:\n{reset['output']}"
    down_v = reset["output"].find("==> Opt-in: docker compose down -v")
    herstel = reset["output"].find("==> Feitelijk restore naar /app/data/news.db")
    assert down_v != -1 and herstel != -1, reset["output"]
    assert herstel > down_v, "restore staat vóór `docker compose down -v`"
    assert "OK: destructieve reset voltooid" in reset["output"], reset["output"]
    assert rollback_session["volume_states"]["na_reset"] != rollback_session["volume_states"]["voor_reset"], (
        "het destructieve pad heeft het volume niet opnieuw aangemaakt"
    )
    assert rollback_session["backups_na_reset"], "geen backup na het destructieve pad"


# ==== 9.1.8 `docker compose up -d --build` + integriteit na restore =======


def test_9_1_8_compose_up_en_integriteit_na_restore(rollback_session) -> None:
    """9.1.8 `docker compose up -d --build` na restore + integriteit via `docker compose exec -i backend python`."""
    env = rollback_session["env"]

    up = runtime_env.compose("up", "-d", "--build", env=env, timeout=900)
    assert up.returncode == 0, (
        f"docker compose up -d --build na restore faalde:\n{up.stdout}\n{up.stderr}"
    )

    ready = _wait_health()
    assert ready["ready"], f"stack niet healthy na herstart: {ready}"

    proc = runtime_env.compose(
        "exec", "-i", "backend", "python", env=env, input=INTEGRITY_PY, timeout=300
    )
    assert proc.returncode == 0, (
        f"integriteitsverificatie na restore faalde:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "integrity_check: ok" in proc.stdout, proc.stdout
    assert "marker: nieuws-piet" in proc.stdout, proc.stdout
    assert re.search(r"tables: [1-9]\d*", proc.stdout), proc.stdout


# ==== 9.1.9 `curl` /health na restore =====================================


def test_9_1_9_curl_health_na_restore(rollback_session) -> None:
    """9.1.9 Exact HTTP 200 én JSON `status: healthy` op /health na restore."""
    status, body = runtime_env.http_get(runtime_env.BACKEND_HEALTH_URL)
    assert status == 200, f"/health gaf HTTP {status}: {body}"
    import json as _json

    payload = _json.loads(body)
    assert payload["status"] == "healthy", payload
    assert payload["components"] == {"backend": "healthy", "sqlite": "healthy"}, payload


# ==== Markercontrole in beide restoreverificatiepaden =======================


def test_9_1_7_restore_weigert_ontbrekende_of_verkeerde_marker(rollback_session) -> None:
    """9.1.7: `verify_data` (restore-pad) verwerpt een ontbrekende óf afwijkende marker.

    De backup wordt feitelijk beschadigd (rij verwijderd resp. waarde veranderd),
    daarna `scripts/db-rollback.sh restore` uitgevoerd: de verificatie moet
    falen en de succesmelding mag niet verschijnen.
    """
    env = rollback_session["env"]
    backup_dir = Path(rollback_session["backup_dir"])
    goede = rollback_session["backups"][0]

    for label, waarde in (("ontbrekend", None), ("verkeerd", "fout")):
        naam = f"news.db.marker-{label}.bak"
        doel = backup_dir / naam
        shutil.copy2(backup_dir / goede, doel)
        _zet_marker(doel, waarde)

        resultaat = _run_script("restore", naam, env=env)
        assert resultaat["rc"] != 0, (
            f"restore accepteerde een backup met een {label} marker "
            f"(rc={resultaat['rc']}):\n{resultaat['output']}"
        )
        assert "OK: backup teruggezet" not in resultaat["output"], (
            f"successmelding ondanks een {label} marker:\n{resultaat['output']}"
        )
        assert "| marker:" in resultaat["output"], resultaat["output"]
        verwacht = "geen marker" if waarde is None else waarde
        assert f"| marker: {verwacht}" in resultaat["output"], resultaat["output"]
        assert "| marker: nieuws-piet" not in resultaat["output"], (
            f"de verificatie meldde een geldige marker terwijl die {label} was"
        )

        # Herstel: de goede backup terug, zodat de volume weer geldig is.
        herstel = _run_script("restore", goede, env=env)
        assert herstel["rc"] == 0, herstel["output"]
        assert "| marker: nieuws-piet" in herstel["output"], herstel["output"]

    # `restore` stopt de backend; laat de module in een gezonde staat achter.
    up = runtime_env.compose("up", "-d", "--build", env=env, timeout=900)
    assert up.returncode == 0, f"{up.stdout}\n{up.stderr}"
    ready = _wait_health()
    assert ready["ready"], f"stack niet ready na herstel: {ready}"


def test_9_1_10_preserve_verificatie_weigert_marker_afwijking(rollback_session) -> None:
    """9.1.10: `verify_full` (preserve-/reset-pad) verwerpt een ontbrekende óf afwijkende marker.

    De backend schrijft de marker bij elke startup opnieuw
    (`INSERT OR REPLACE` in `init_database`), dus een beschadiging vóór de start
    zou vanzelf herstellen. Daarom wordt de live database **ná** de start
    beschadigd: integriteit blijft `ok` (dus /health blijft 200 healthy) maar de
    data-marker klopt niet. Vervolgens draait `verify_full` — de exacte functie
    uit `scripts/db-rollback.sh` — en moet die met een niet-nul exit falen.
    """
    env = rollback_session["env"]
    goede = rollback_session["backups"][0]
    bron = SCRIPT.read_text(encoding="utf-8")
    functie = _bash_functie(bron, "verify_full")
    assert functie.strip(), "verify_full ontbreekt in scripts/db-rollback.sh"

    # Voorwaarde: de stack draait en /health is 200 healthy (de verificatie
    # wacht daarop voordat hij de data-marker beoordeelt).
    up = runtime_env.compose("up", "-d", "--build", env=env, timeout=900)
    assert up.returncode == 0, f"{up.stdout}\n{up.stderr}"
    ready = _wait_health()
    assert ready["ready"], f"stack niet ready voor de markerproef: {ready}"

    for label, waarde in (("ontbrekend", None), ("verkeerd", "fout")):
        _zet_marker_in_volume(env, waarde, stop_backend=False)

        resultaat = runtime_env.run(
            ["bash", "-c", f"set -e\nverify_full() {{\n{functie}\n}}\nverify_full"],
            env=env,
            timeout=600,
        )
        output = f"{resultaat.stdout}\n{resultaat.stderr}"
        assert resultaat.returncode != 0, (
            f"verify_full accepteerde een {label} marker (rc={resultaat.returncode}):\n"
            f"{output}"
        )
        assert "integrity_check: ok" in output, output
        verwacht = "geen marker" if waarde is None else waarde
        assert f"| marker: {verwacht}" in output, output
        assert "| marker: nieuws-piet" not in output, output

        # Herstel: de goede backup terug. `restore` stopt de backend, dus daarna
        # opnieuw starten — dat is meteen de startvorming voor de volgende cyclus.
        herstel = _run_script("restore", goede, env=env)
        assert herstel["rc"] == 0, herstel["output"]
        assert "| marker: nieuws-piet" in herstel["output"], herstel["output"]

        up = runtime_env.compose("up", "-d", "--build", env=env, timeout=900)
        assert up.returncode == 0, f"{up.stdout}\n{up.stderr}"
        ready = _wait_health()
        assert ready["ready"], f"stack niet ready na herstel ({label}): {ready}"


# ==== 9.1.10 `down -v` uitsluitend als opt-in ============================


def test_9_1_10_down_v_uitsluitend_opt_in(rollback_session) -> None:
    """9.1.10 `docker compose down -v` alléén als opt-in, na backup + validatie, met restore direct ná `down -v`; de echte volume blijft onaangeroerd."""
    refusal = rollback_session["runs"]["refusal"]
    reset = rollback_session["runs"]["reset"]

    # Zonder opt-in: geweigerd, geen destructieve stap, stack en volume intact.
    assert refusal["rc"] == 2, (
        f"reset zonder opt-in moest exit 2 geven (rc={refusal['rc']}):\n{refusal['output']}"
    )
    assert "GEWEIGERD" in refusal["output"], refusal["output"]
    assert "Opt-in: docker compose down -v" not in refusal["output"], (
        "zonder opt-in is toch `docker compose down -v` gedraaid"
    )
    assert set(rollback_session["refusal_state"]["services"].values()) == {"running"}, (
        f"stack is na de weigering toch geraakt: {rollback_session['refusal_state']}"
    )
    assert (
        rollback_session["refusal_state"]["volume_state"]
        == rollback_session["volume_states"]["voor_reset"]
    ), "volume is na de weigering gewijzigd"
    assert rollback_session["refusal_state"]["backups"] == rollback_session["backups"], (
        "zonder opt-in is toch een backup gemaakt"
    )

    # Met opt-in: backup en validatie vóór `down -v`, restore direct daarna,
    # verificatie als laatste stap.
    output = reset["output"]
    assert reset["rc"] == 0, output
    backup_pos = output.find("==> Niet-destructieve backup")
    validatie_pos = output.find("==> Integriteitsvalidatie van")
    down_v_pos = output.find("==> Opt-in: docker compose down -v")
    restore_pos = output.find("==> Feitelijk restore naar /app/data/news.db")
    verificatie_pos = output.find("==> Verificatie: integriteit + data-marker")
    positie = [backup_pos, validatie_pos, down_v_pos, restore_pos, verificatie_pos]
    assert all(pos != -1 for pos in positie), f"stap ontbreekt in de volgorde: {positie}"
    assert positie == sorted(positie), f"volgorde klopt niet: {positie}"
    assert "PRAGMA integrity_check" in output, output

    # Geen enkele stap schrijft restore vóór `down -v`.
    assert all(
        pos > down_v_pos for pos in (restore_pos, verificatie_pos)
    ), "restore of verificatie staat vóór `docker compose down -v`"

    # De wegwerp-context wordt nu afgebroken (alléén de eigen projectnaam), en
    # de echte volume blijft onaangeroerd.
    rollback_session["teardown"]()
    assert rollback_session["down_rc"] == 0, (
        f"eigen context kon niet worden afgebroken:\n{rollback_session['down_output']}"
    )
    assert rollback_session["containers_after"] == {}, (
        f"eigen containers zijn blijven staan: {rollback_session['containers_after']}"
    )
    assert rollback_session["images_after"] == [], (
        f"eigen images zijn blijven staan: {rollback_session['images_after']}"
    )
    assert rollback_session["real_before"] == rollback_session["real_after"], (
        "de echte volume `nieuws_piet_sqlite_data` is door de rollback-tests gewijzigd"
    )
