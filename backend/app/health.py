"""Health-check implementatie met exacte JSON/HTTP contracten.

Contracten (sectie 4, taken 4.2/4.3/4.4/4.7):
* gezond                     -> HTTP 200, status "healthy"
* SQLite ongezond            -> HTTP 503, error "SQLite database not accessible"
* backend ongezond           -> HTTP 500, error "Backend internal health check failed"
* beide ongezond             -> HTTP 503, gecombineerde foutmelding

Alle probes lopen binnen een hard budget (server probe <=500ms) zodat een
oplopende storage-probe het health-contract nooit kan laten vastlopen.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .config import SQLITE_PROBE_BUDGET_MS

# Componenten: exact backend + SQLite (geen andere componenten in het contract).
COMPONENT_BACKEND = "backend"
COMPONENT_SQLITE = "sqlite"

ERROR_SQLITE = "SQLite database not accessible"
ERROR_BACKEND = "Backend internal health check failed"
ERROR_COMBINED = "Backend internal health check failed and SQLite database not accessible"

# De "hangende" test double is per HealthService-instance (geen gedeelde
# module-globale state): een cleanup van de ene test beïnvloedt de volgende niet.


@dataclass(frozen=True)
class ProbeOutcome:
    """Resultaat van een bounded probe."""

    healthy: bool
    timed_out: bool
    elapsed_ms: float


def run_bounded(fn: Callable[[], bool], budget_ms: int = SQLITE_PROBE_BUDGET_MS) -> ProbeOutcome:
    """Voert `fn` uit in een worker-thread en wacht maximaal `budget_ms`.

    Wanneer de probe niet binnen het budget terugkeert wordt hij afgekapt en
    als ongezond gerapporteerd (server probe budget <=500ms).
    """
    import time

    result: dict[str, bool] = {}
    started = time.perf_counter()

    def worker() -> None:
        try:
            result["value"] = bool(fn())
        except Exception:  # noqa: BLE001 - elke probe-fout is "ongezond"
            result["value"] = False

    thread = threading.Thread(target=worker, daemon=True, name="health-probe")
    thread.start()
    thread.join(timeout=budget_ms / 1000.0)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if thread.is_alive():
        return ProbeOutcome(healthy=False, timed_out=True, elapsed_ms=elapsed_ms)
    return ProbeOutcome(healthy=result.get("value", False), timed_out=False, elapsed_ms=elapsed_ms)


def probe_sqlite_readonly(db_path: str) -> bool:
    """Read-only SQLite-probe: opent uitsluitend bestaand bestand, mutatie nooit.

    `mode=ro` voorkomt creatie van databasebestanden; een ontbrekend of
    onleesbaar bestand levert `False` (ongezond) zonder filesystem-mutatie.
    """
    uri = f"file:{db_path}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=1.0)
    except sqlite3.Error:
        # Ontbrekend of onleesbaar bestand: ongezond, GEEN filesystem-mutatie.
        return False
    try:
        row = connection.execute("SELECT 1").fetchone()
        return row is not None and row[0] == 1
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def probe_backend_self_check() -> bool:
    """Interne backend self-check zonder externe afhankelijkheden.

    Controleert uitsluitend in-process invariants; er wordt geen netwerk,
    account of externe dienst geraakt.
    """
    import sys

    if sys.version_info < (3, 10):
        return False
    # Basisinvariant: tijd en SQLite-module zijn beschikbaar voor de backend.
    return datetime.now(timezone.utc).tzinfo is not None and sqlite3.sqlite_version_info[0] >= 3


class HealthService:
    """Bepaalt de health-status en bouwt de exacte response-body."""

    def __init__(
        self,
        *,
        fault: str | None,
        db_path: str,
        sqlite_probe: Callable[[str], bool] | None = None,
        backend_probe: Callable[[], bool] | None = None,
        budget_ms: int = SQLITE_PROBE_BUDGET_MS,
    ) -> None:
        # `fault` is al gefilterd door HealthFaultConfig (bij constructie).
        self._fault = fault
        self._db_path = db_path
        self._sqlite_probe = sqlite_probe or probe_sqlite_readonly
        self._backend_probe = backend_probe or probe_backend_self_check
        self._budget_ms = budget_ms
        # Per-instance hang-event voor de `sqlite_timeout` test double.
        self._hang_event = threading.Event()
        # laatste probe-metingen (diagnose; geen onderdeel van de HTTP-body)
        self.last_sqlite_elapsed_ms: float | None = None
        self.last_backend_elapsed_ms: float | None = None

    def release(self) -> None:
        """Beëindigt een eventueel nog hangende test double (test-cleanup)."""
        self._hang_event.set()

    def _hang_probe(self) -> bool:
        """Test double voor `sqlite_timeout`: blokkeert tot release, blijft ongezond."""
        self._hang_event.wait()
        return False

    # ---- componenten -------------------------------------------------

    def _sqlite_healthy(self) -> bool:
        # Fault-pad: uitsluitend test doubles, nooit de echte database.
        if self._fault in {"sqlite", "sqlite_timeout", "all"}:
            if self._fault == "sqlite_timeout":
                # Test double die hangt: bounded executor kapt af binnen budget.
                outcome = run_bounded(self._hang_probe, self._budget_ms)
            else:
                outcome = ProbeOutcome(healthy=False, timed_out=False, elapsed_ms=0.0)
            self.last_sqlite_elapsed_ms = outcome.elapsed_ms
            return outcome.healthy

        outcome = run_bounded(lambda: self._sqlite_probe(self._db_path), self._budget_ms)
        self.last_sqlite_elapsed_ms = outcome.elapsed_ms
        return outcome.healthy

    def _backend_healthy(self) -> bool:
        if self._fault in {"backend", "all"}:
            self.last_backend_elapsed_ms = 0.0
            return False
        outcome = run_bounded(self._backend_probe, self._budget_ms)
        self.last_backend_elapsed_ms = outcome.elapsed_ms
        return outcome.healthy

    # ---- response ----------------------------------------------------

    def evaluate(self) -> tuple[int, dict]:
        """Geeft (http_status, exacte JSON-body) voor de huidige configuratie."""
        backend_ok = self._backend_healthy()
        sqlite_ok = self._sqlite_healthy()

        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        components = {
            COMPONENT_BACKEND: "healthy" if backend_ok else "unhealthy",
            COMPONENT_SQLITE: "healthy" if sqlite_ok else "unhealthy",
        }

        if backend_ok and sqlite_ok:
            body = {
                "status": "healthy",
                "timestamp": timestamp,
                "components": components,
            }
            return 200, body

        if sqlite_ok and not backend_ok:
            body = {
                "status": "unhealthy",
                "timestamp": timestamp,
                "components": components,
                "error": ERROR_BACKEND,
            }
            return 500, body

        if backend_ok and not sqlite_ok:
            body = {
                "status": "unhealthy",
                "timestamp": timestamp,
                "components": components,
                "error": ERROR_SQLITE,
            }
            return 503, body

        body = {
            "status": "unhealthy",
            "timestamp": timestamp,
            "components": components,
            "error": ERROR_COMBINED,
        }
        return 503, body
