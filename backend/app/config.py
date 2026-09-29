"""Test-only fault-injection configuratie voor het /health contract.

Regels (sectie 4, taken 4.17/4.19):
* `APP_HEALTH_FAULT` is EXCLUSIEF actief wanneer `APP_ENV` exact `test` is.
* Whitelist is exact: sqlite, sqlite_timeout, backend, all.
* Elke andere waarde (inclusief hoofdlettervarianten, leeg, achtervoegsels)
  wordt deterministisch genegeerd -> normaal gezond contract.
* De waarden worden bij constructie van de health-instance gelezen (app-factory),
  niet als module-globale state: zo lekt een fault nooit tussen instanties.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

# Exacte whitelist; geen enkele andere waarde wordt erkend.
HEALTH_FAULT_WHITELIST = frozenset({"sqlite", "sqlite_timeout", "backend", "all"})

# Server-side probe budget voor de SQLite-probe (ms). Ruim onder de 500ms van
# de spec zodat afkap + overhead altijd binnen het >=500ms budget blijft.
SQLITE_PROBE_BUDGET_MS = 400


@dataclass(frozen=True)
class HealthFaultConfig:
    """Bevroren snapshot van de fault-config op het moment van constructie."""

    app_env: str
    requested: str

    @property
    def fault(self) -> str | None:
        """De actieve fault, of `None` wanneer er geen fault mag gelden."""
        if self.app_env != "test":
            return None
        if self.requested not in HEALTH_FAULT_WHITELIST:
            return None
        return self.requested


def read_fault_config(environ: Mapping[str, str] | None = None) -> HealthFaultConfig:
    """Leest `APP_ENV`/`APP_HEALTH_FAULT` uit de gegeven (of actieve) omgeving."""
    import os

    env = os.environ if environ is None else environ
    return HealthFaultConfig(
        app_env=env.get("APP_ENV", ""),
        requested=env.get("APP_HEALTH_FAULT", ""),
    )
