"""FastAPI-routes voor het bronbeheer (capability `source-catalog`).

Exact vijf routes, geen meer en geen minder:

* `GET    /api/sources`          volledige catalogus, opties `is_active`,
                                 `topic` en `cloud_label` (AND), standaard
                                 inclusief inactieve bronnen, gesorteerd op id
* `GET    /api/sources/{id}`     detail, 404 bij onbekend id
* `POST   /api/sources`          201 bij succes, 409 bij duplicate identiteit
* `PATCH  /api/sources/{id}`     200 bij succes, 404 bij onbekend id (geen upsert)
* `GET    /api/source-options`   onderwerpen, typen, taalbeleid en cloudlabels

Geen `DELETE`, geen opties-CRUD en geen upsert-/mergegedrag. Foutbodies zijn
vast en lekken nooit SQL, stacktraces of paden: 404/409/422/503 met vaste
Nederlandse meldingen.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from . import sources_repository as repository
from .sources_validation import (
    CLOUD_LABELS,
    TOPIC_SLUGS,
    SourceValidationError,
    validate_patch,
    validate_source,
    with_defaults,
)

DETAIL_404 = "bron bestaat niet"
DETAIL_409 = "feed-URL bestaat al"
DETAIL_422 = "ongeldige invoer"
DETAIL_503 = "database onbereikbaar"

router = APIRouter()


def _db_path(request: Request) -> str:
    """Databasepad uitsluitend uit `app.state.db_path` (app-factory-isolatie)."""
    return request.app.state.db_path


@contextmanager
def _foutafhandeling() -> Iterator[None]:
    """Zet repository- en validatiefouten om in de vaste foutsemantiek."""
    try:
        yield
    except SourceValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from None
    except repository.SourceNotFound:
        raise HTTPException(status_code=404, detail=DETAIL_404) from None
    except repository.SourceConflict:
        raise HTTPException(status_code=409, detail=DETAIL_409) from None
    except repository.DatabaseUnavailable:
        raise HTTPException(status_code=503, detail=DETAIL_503) from None


def _met_defaults(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SourceValidationError(DETAIL_422)
    return with_defaults(payload)


@router.get("/api/sources")
def list_sources(
    db_path: str = Depends(_db_path),
    is_active: bool | None = Query(default=None),
    topic: str | None = Query(default=None),
    cloud_label: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Volledige catalogus in één respons; filters worden als AND gecombineerd."""
    with _foutafhandeling():
        if topic is not None and topic not in TOPIC_SLUGS:
            raise HTTPException(status_code=422, detail="topic staat niet in de woordenlijst")
        if cloud_label is not None and cloud_label not in CLOUD_LABELS:
            raise HTTPException(
                status_code=422, detail="cloud_label staat niet in de woordenlijst"
            )
        return repository.list_sources(
            db_path, is_active=is_active, topic=topic, cloud_label=cloud_label
        )


@router.get("/api/source-options")
def source_options(db_path: str = Depends(_db_path)) -> dict[str, list[str]]:
    """Precies één opties-route: onderwerpen, typen, taalbeleid en cloudlabels."""
    with _foutafhandeling():
        return repository.source_options(db_path)


@router.get("/api/sources/{source_id}")
def get_source(source_id: int, db_path: str = Depends(_db_path)) -> dict[str, Any]:
    """Detail van één bron; onbekend id is 404."""
    with _foutafhandeling():
        return repository.get_source(db_path, source_id)


@router.post("/api/sources", status_code=201)
def create_source(
    payload: dict[str, Any] = Body(...),
    db_path: str = Depends(_db_path),
) -> dict[str, Any]:
    """Nieuw publicatiekanaal; standaard inactief, 201 bij succes."""
    with _foutafhandeling():
        record = validate_source(_met_defaults(payload))
        return repository.create_source(db_path, record)


@router.patch("/api/sources/{source_id}")
def update_source(
    source_id: int,
    payload: dict[str, Any] = Body(...),
    db_path: str = Depends(_db_path),
) -> dict[str, Any]:
    """Wijzigt een bestaand record; een onbekend id wordt nooit aangemaakt."""
    with _foutafhandeling():
        bestaand = repository.source_state(db_path, source_id)
        record = validate_patch(payload, bestaand)
        return repository.update_source(db_path, source_id, record)
