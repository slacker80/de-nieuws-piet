"""Bestaande backup/restore met gevulde v2-catalogusdata (taak 7.3).

Er wordt géén nieuwe backupfunctie toegevoegd: het bestaande proces
`scripts/db-rollback.sh` draait in een geïsoleerde wegwerp-context (eigen
project, eigen volume, eigen netwerk, eigen poorten, eigen backup-directory)
rond een gevulde catalogus. Verificatie: backup -> `PRAGMA integrity_check` =
`ok` -> volume weggooien -> restore -> exact dezelfde catalogusrijen en
relaties, plus opnieuw `ok`.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest

from tests import runtime_env

SCRIPT = runtime_env.ROOT / "scripts" / "db-rollback.sh"

# Uitlezing van `/app/data/news.db` vanuit een verse container (alleen lezen).
CATALOGUS_PY = """
import json, sqlite3

conn = sqlite3.connect('/app/data/news.db')
data = {
    'integrity': conn.execute('PRAGMA integrity_check').fetchone()[0],
    'version': conn.execute(
        "SELECT value FROM app_meta WHERE key='schema_version'"
    ).fetchone()[0],
    'sources': conn.execute(
        "SELECT id, name, feed_url, feed_url_key, website_url, type, language, "
        "reliability, is_active FROM sources ORDER BY id"
    ).fetchall(),
    'topics': conn.execute(
        "SELECT source_id, topic_slug FROM source_topics "
        "ORDER BY source_id, topic_slug"
    ).fetchall(),
    'labels': conn.execute(
        "SELECT source_id, cloud_label FROM source_cloud_labels "
        "ORDER BY source_id, cloud_label"
    ).fetchall(),
}
conn.close()
print('CATALOGUS_JSON:' + json.dumps(data))
"""


def _run_script(name: str, *args: str, env: dict) -> dict:
    proc = runtime_env.run(["bash", str(SCRIPT), name, *args], env=env, timeout=900)
    return {
        "rc": proc.returncode,
        "output": f"{proc.stdout}\n{proc.stderr}",
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _python(env: dict, code: str, *, service_run: bool) -> dict:
    """Voert Python uit in de backend-container (exec bij draaiend, run anders)."""
    if service_run:
        proc = runtime_env.compose(
            "exec", "-T", "backend", "python", "-c", code, env=env, timeout=300
        )
    else:
        proc = runtime_env.compose(
            "run", "--rm", "--no-deps", "-T", "--entrypoint", "python",
            "backend", "-c", code, env=env, timeout=300,
        )
    return {
        "rc": proc.returncode,
        "output": f"{proc.stdout}\n{proc.stderr}",
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _lees_catalogus(env: dict, *, draait: bool) -> dict:
    """Leest rijen, relaties, schema-versie en integriteit uit de database."""
    resultaat = _python(env, CATALOGUS_PY, service_run=draait)
    assert resultaat["rc"] == 0, resultaat["output"]
    regel = next(
        (lijn for lijn in resultaat["stdout"].splitlines()
         if lijn.startswith("CATALOGUS_JSON:")),
        None,
    )
    assert regel, f"geen meetresultaat: {resultaat['output']}"
    return json.loads(regel.split("CATALOGUS_JSON:", 1)[1])


def _wacht_gezond(env: dict, url: str, pogingen: int = 60) -> dict:
    status, body = 0, ""
    for _ in range(pogingen):
        status, body = runtime_env.http_get(url)
        if status == 200:
            try:
                if json.loads(body).get("status") == "healthy":
                    return {"ready": True, "status": status, "body": body}
            except ValueError:
                pass
        time.sleep(1)
    return {"ready": False, "status": status, "body": body}


@pytest.fixture(scope="module")
def catalogus_backup_session():
    """Gevulde v2-catalogus in een wegwerp-context rond het bestaande proces."""
    ctx = runtime_env.isolated_context("catbak")
    env = ctx["env"]
    backup_dir = Path(ctx["target"]) / "backups"
    env = runtime_env.build_env(
        {
            **{k: v for k, v in env.items() if k in ("PATH", "HOME")},
            "COMPOSE_PROJECT_NAME": ctx["project"],
            "COMPOSE_FILE": f"{runtime_env.COMPOSE_FILE}:{ctx['override']}",
            "NIEUWS_PIET_DB_VOLUME": ctx["volume"],
            "NIEUWS_PIET_DB_BACKUP_DIR": str(backup_dir),
        }
    )
    health_url = f"http://127.0.0.1:{ctx['ports'][1]}/health"
    real_before = runtime_env.volume_state(runtime_env.REAL_VOLUME)

    evidence: dict = {
        "ctx": ctx,
        "env": env,
        "backup_dir": backup_dir,
        "health_url": health_url,
        "runs": {},
        "backups": [],
        "voor": None,
        "na": None,
        "seed_output": "",
        "down_rc": None,
        "down_output": "",
        "real_before": real_before,
        "real_after": None,
        "teardown": None,
    }
    state = {"done": False}

    def teardown() -> dict:
        if state["done"]:
            return evidence
        state["done"] = True
        down = runtime_env.compose(
            "down", "-v", "--remove-orphans", env=env, timeout=600
        )
        evidence["down_rc"] = down.returncode
        evidence["down_output"] = f"{down.stdout}\n{down.stderr}"
        runtime_env.run(
            ["docker", "image", "rm", f"{ctx['project']}-backend"], timeout=300
        )
        shutil.rmtree(ctx["target"], ignore_errors=True)
        evidence["real_after"] = runtime_env.volume_state(runtime_env.REAL_VOLUME)
        return evidence

    evidence["teardown"] = teardown

    try:
        # Alleen de backend: de catalogus is backend-data, het frontend is niet
        # nodig voor backup/restore.
        up = runtime_env.compose("up", "-d", "--build", "backend", env=env, timeout=900)
        assert up.returncode == 0, f"compose up faalde:\n{up.stdout}\n{up.stderr}"
        ready = _wacht_gezond(env, health_url)
        assert ready["ready"], f"backend niet healthy: {ready}"

        # De migratie heeft bij startup gedraaid; de seed vult de starterset.
        seed = _python(env, "import sys; sys.argv=['source_seed']; "
                        "from app.source_seed import main; raise SystemExit(main())",
                       service_run=True)
        evidence["seed_output"] = seed["output"]
        assert seed["rc"] == 0, seed["output"]
        assert "toegevoegd: 15" in seed["output"], seed["output"]

        evidence["voor"] = _lees_catalogus(env, draait=True)
        assert evidence["voor"]["integrity"] == "ok"
        assert evidence["voor"]["version"] == "2"
        assert len(evidence["voor"]["sources"]) == 15
        assert evidence["voor"]["topics"], "de starterset moet relaties hebben"

        # Bestaand proces: backup + integriteitsvalidatie (PRAGMA integrity_check).
        evidence["runs"]["backup"] = _run_script("backup", env=env)
        assert evidence["runs"]["backup"]["rc"] == 0, evidence["runs"]["backup"]["output"]
        backups = sorted(backup_dir.glob("news.db.*.bak"))
        assert backups, f"geen backup in {backup_dir}"
        evidence["backups"] = [pad.name for pad in backups]

        evidence["runs"]["validate"] = _run_script("validate", env=env)
        assert evidence["runs"]["validate"]["rc"] == 0, evidence["runs"]["validate"]["output"]
        assert "integrity_check: ok" in evidence["runs"]["validate"]["stdout"]

        # Data weggooien: volume volledig verwijderen, daarna restore.
        weg = runtime_env.compose("down", "-v", env=env, timeout=600)
        assert weg.returncode == 0, f"down -v faalde:\n{weg.stdout}\n{weg.stderr}"
        assert runtime_env.volume_state(ctx["volume"]) is None, "volume bestaat nog"

        evidence["runs"]["restore"] = _run_script("restore", env=env)
        assert evidence["runs"]["restore"]["rc"] == 0, evidence["runs"]["restore"]["output"]
        assert "integrity_check: ok" in evidence["runs"]["restore"]["stdout"], (
            evidence["runs"]["restore"]["output"]
        )
        assert "OK: backup teruggezet" in evidence["runs"]["restore"]["output"]

        evidence["na"] = _lees_catalogus(env, draait=False)

        yield evidence
    finally:
        teardown()
        assert evidence["down_rc"] == 0, evidence["down_output"]
        assert evidence["real_before"] == evidence["real_after"], (
            "de echte volume is door de catalogus-backuptest gewijzigd"
        )


def test_backup_van_gevulde_v2_catalogus(catalogus_backup_session) -> None:
    """7.3: backup van een gevulde v2-database met integriteit `ok`."""
    session = catalogus_backup_session
    assert session["runs"]["backup"]["rc"] == 0
    assert session["backups"], "geen backupbestand aangemaakt"
    assert "==> Niet-destructieve backup" in session["runs"]["backup"]["output"]
    assert "OK: backup gemaakt en gevalideerd" in session["runs"]["backup"]["output"]
    # De backup zelf is read-only gevalideerd met PRAGMA integrity_check.
    assert "PRAGMA integrity_check" in session["runs"]["validate"]["output"]
    assert "integrity_check: ok" in session["runs"]["validate"]["stdout"]


def test_restore_bewaart_catalogusrijen_en_relaties(catalogus_backup_session) -> None:
    """7.3: na restore zijn de catalogusrijen én relaties exact gelijk."""
    session = catalogus_backup_session
    voor, na = session["voor"], session["na"]

    assert na["sources"] == voor["sources"], "catalogusrijen zijn gewijzigd"
    assert na["topics"] == voor["topics"], "onderwerprelaties zijn gewijzigd"
    assert na["labels"] == voor["labels"], "cloudlabel-relaties zijn gewijzigd"
    assert len(na["sources"]) == 15
    assert len(na["topics"]) == len(voor["topics"])
    assert len(na["labels"]) == len(voor["labels"])


def test_restore_levert_integriteit_ok_en_versie_2(catalogus_backup_session) -> None:
    """7.3: na restore geeft `PRAGMA integrity_check` exact `ok`, versie blijft 2."""
    session = catalogus_backup_session
    assert session["na"]["integrity"] == "ok"
    assert session["na"]["version"] == "2"
    assert "integrity_check: ok" in session["runs"]["restore"]["stdout"]


def test_restore_proces_is_het_bestaande_script(catalogus_backup_session) -> None:
    """7.3: er is geen nieuwe backupfunctie; alles loopt via `db-rollback.sh`."""
    session = catalogus_backup_session
    assert SCRIPT.is_file()
    output = session["runs"]["restore"]["output"]
    assert "==> Integriteitsvalidatie van" in output
    assert "==> Feitelijk restore naar /app/data/news.db" in output
    assert "PRAGMA integrity_check" in output
    # Alle stappen liepen via hetzelfde script; de afbraak (eigen context,
    # echte volume onaangeroerd) gebeurt in de fixture-na-afloop hieronder.
