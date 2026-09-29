"""FastAPI applicatie-factory met het exacte /health contract (sectie 4).

De applicatie wordt uitsluitend via `create_app()` geconstrueerd (app-factory):
elke test bouwt een verse instance, leest `APP_ENV`/`APP_HEALTH_FAULT` bij
constructie en deelt geen module-globale state met andere tests.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from contextlib import asynccontextmanager

from .config import read_fault_config
from .db import init_database
from .db_migrate import migrate
from .health import HealthService
from .sources_api import router as sources_router

# Standaard databasepad in de backend-container (named volume, taak 2.4).
DEFAULT_DB_PATH = "/app/data/news.db"


def create_app(
    *,
    environ: dict[str, str] | None = None,
    db_path: str | None = None,
    sqlite_probe=None,
    backend_probe=None,
    init_db: bool = True,
) -> FastAPI:
    """Construeert een nieuwe, onafhankelijke applicatie-instance.

    * `APP_ENV` en `APP_HEALTH_FAULT` worden hier bij constructie gelezen.
    * `sqlite_probe`/`backend_probe` zijn test doubles (nooit filesystem-mutaties).
    * `init_db` initialiseert de SQLite database bij applicatiestart (taak 5.1);
      tests zetten dit uit zodat fault-tests nooit de filesystem raken.
    * Elke aanroep levert een nieuwe instance zonder gedeelde mutable state.
    """
    env = os.environ if environ is None else environ
    fault_cfg = read_fault_config(env)
    resolved_db_path = db_path if db_path is not None else env.get("APP_DB_PATH", DEFAULT_DB_PATH)

    health = HealthService(
        fault=fault_cfg.fault,
        db_path=resolved_db_path,
        sqlite_probe=sqlite_probe,
        backend_probe=backend_probe,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        # Taak 5.1: SQLite database initialiseren wanneer de applicatie start.
        # Idempotent; `init_db=False` (tests) slaat dit expliciet over.
        # Daarna de catalogusmigratie v1 -> v2 (delta-spec `source-catalog`):
        # eveneens idempotent, versie 2 is een noop, en nooit de seed (die is
        # een expliciete, handmatige operatie los van de applicatie-start).
        if init_db:
            application.state.db_path = init_database(resolved_db_path)
            migrate(application.state.db_path)
        yield

    app = FastAPI(title="Nieuws Piet backend", version="0.1.0", lifespan=lifespan)
    app.state.health = health
    app.state.health_fault = fault_cfg.fault
    app.state.db_path = resolved_db_path
    app.include_router(sources_router)

    @app.get("/health")
    def health_endpoint() -> JSONResponse:
        status_code, body = health.evaluate()
        return JSONResponse(content=body, status_code=status_code)

    return app


# Runtime-instance voor `uvicorn app.main:app` (container-CMD, taak 2.3).
# Tests gebruiken uitsluitend hun eigen `create_app()`-instanties.
app = create_app()
