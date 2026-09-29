"""Repositorylaag voor de broncatalogus op lokale SQLite (source-catalog).

Ontwerpregels:
* Het databasepad komt uitsluitend uit `app.state.db_path` (via de router), dus
  twee applicatie-instanties delen nooit data; de seed en de migratie krijgen
  het pad als expliciete parameter.
* Writes (`POST`, `PATCH`, seed) draaien in één `BEGIN IMMEDIATE`-transactie
  over bronrecord én relaties; de `UNIQUE`-index op `feed_url_key` is de
  autoriteit bij duplicaten (app-check vooraf, database als sluitpost).
* Foutmapping is deterministisch en lekt niets: onbekend id -> `SourceNotFound`,
  duplicate feed-identiteit -> `SourceConflict`, ongeldige invoer ->
  `SourceValidationError`, database onbereikbaar -> `DatabaseUnavailable`.
  Er wordt nooit herprobeerd: het aantal databasepogingen per aanroep is vast.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

from .db import connect
from .sources_validation import (
    CLOUD_LABELS,
    LANGUAGES,
    SOURCE_TYPES,
    TOPIC_SLUGS,
    SourceInput,
    SourceValidationError,
)

_DATABASE_DETAIL = "database onbereikbaar"


class SourceNotFound(LookupError):
    """Onbekend id -> HTTP 404."""


class SourceConflict(RuntimeError):
    """Bestaande feed-identiteit -> HTTP 409."""


class DatabaseUnavailable(RuntimeError):
    """Database onbereikbaar -> HTTP 503 met vaste melding."""

    def __init__(self) -> None:
        super().__init__(_DATABASE_DETAIL)


def _map_sqlite_error(exc: sqlite3.Error) -> Exception:
    if isinstance(exc, sqlite3.IntegrityError):
        if "ux_sources_feed_url_key" in str(exc):
            return SourceConflict("feed-URL bestaat al")
        return SourceValidationError("opslag voldoet niet aan de databasecontroles")
    return DatabaseUnavailable()


@contextmanager
def _write(db_path: str) -> Iterator[sqlite3.Connection]:
    """Eén `BEGIN IMMEDIATE`-transactie; alle fouten rollback'en volledig.

    Ook het openen van de verbinding zelf valt onder de vaste foutmapping: een
    onbereikbare database levert `DatabaseUnavailable` (HTTP 503) op, nooit een
    onbehandelde `sqlite3`-fout. Het aantal databasepogingen per aanroep blijft
    daarmee vast: er wordt nooit herprobeerd.
    """
    try:
        with connect(db_path) as connection:
            connection.isolation_level = None
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.Error as exc:
                raise _map_sqlite_error(exc) from None
            try:
                yield connection
            except sqlite3.Error as exc:
                _rollback(connection)
                raise _map_sqlite_error(exc) from None
            except BaseException:
                _rollback(connection)
                raise
            else:
                connection.execute("COMMIT")
    except sqlite3.Error as exc:
        # Het openen van de verbinding of de COMMIT mislukte.
        raise _map_sqlite_error(exc) from None


def _rollback(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("ROLLBACK")
    except sqlite3.Error:
        pass  # de oorspronkelijke fout is leidend


_SELECT = (
    "SELECT id, name, feed_url, website_url, type, language, reliability, is_active "
    "FROM sources"
)


def _relaties(
    connection: sqlite3.Connection, source_ids: Sequence[int]
) -> dict[int, tuple[tuple[str, ...], tuple[str, ...]]]:
    """Onderwerpen en cloudlabels per bron, gesteld in woordenlijstvolgorde."""
    thema: dict[int, set[str]] = {sid: set() for sid in source_ids}
    labels: dict[int, set[str]] = {sid: set() for sid in source_ids}
    if source_ids:
        grens = ",".join("?" for _ in source_ids)
        for sid, slug in connection.execute(
            f"SELECT source_id, topic_slug FROM source_topics WHERE source_id IN ({grens})",
            tuple(source_ids),
        ):
            thema[sid].add(slug)
        for sid, label in connection.execute(
            f"SELECT source_id, cloud_label FROM source_cloud_labels WHERE source_id IN ({grens})",
            tuple(source_ids),
        ):
            labels[sid].add(label)
    return {
        sid: (
            tuple(slug for slug in TOPIC_SLUGS if slug in thema[sid]),
            tuple(label for label in CLOUD_LABELS if label in labels[sid]),
        )
        for sid in source_ids
    }


def _record(
    row: sqlite3.Row | tuple, thema: tuple[str, ...], labels: tuple[str, ...]
) -> dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "feed_url": row[2],
        "website_url": row[3],
        "type": row[4],
        "language": row[5],
        "reliability": row[6],
        "is_active": bool(row[7]),
        "topics": list(thema),
        "cloud_labels": list(labels),
    }


def catalogus_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Genormaliseerde velden zoals de repository ze terugleest (geen `id`)."""
    return {
        "name": payload["name"],
        "feed_url": payload["feed_url"],
        "website_url": payload.get("website_url"),
        "type": payload["type"],
        "language": payload["language"],
        "reliability": payload.get("reliability"),
        "is_active": bool(payload.get("is_active", False)),
        "topics": list(payload.get("topics", [])),
        "cloud_labels": list(payload.get("cloud_labels", [])),
    }


# ==== Leespaden ==============================================================


def list_sources(
    db_path: str,
    *,
    is_active: bool | None = None,
    topic: str | None = None,
    cloud_label: str | None = None,
) -> list[dict[str, Any]]:
    """Volledige catalogus in één respons, oplopend op id, filters als AND."""
    clauses: list[str] = []
    parameters: list[Any] = []
    if is_active is not None:
        clauses.append("is_active = ?")
        parameters.append(1 if is_active else 0)
    if topic is not None:
        clauses.append(
            "id IN (SELECT source_id FROM source_topics WHERE topic_slug = ?)"
        )
        parameters.append(topic)
    if cloud_label is not None:
        clauses.append(
            "id IN (SELECT source_id FROM source_cloud_labels WHERE cloud_label = ?)"
        )
        parameters.append(cloud_label)

    sql = _SELECT
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id ASC"

    try:
        with connect(db_path) as connection:
            rows = connection.execute(sql, parameters).fetchall()
            relaties = _relaties(connection, [row[0] for row in rows])
    except sqlite3.Error as exc:
        raise _map_sqlite_error(exc) from None

    return [
        _record(row, *relaties[row[0]])
        for row in rows
    ]


def get_source(db_path: str, source_id: int) -> dict[str, Any]:
    try:
        with connect(db_path) as connection:
            row = connection.execute(
                _SELECT + " WHERE id = ?", (source_id,)
            ).fetchone()
            if row is None:
                raise SourceNotFound(f"bron met id {source_id} bestaat niet")
            relaties = _relaties(connection, [source_id])
    except sqlite3.Error as exc:
        raise _map_sqlite_error(exc) from None
    return _record(row, *relaties[source_id])


def source_state(db_path: str, source_id: int) -> dict[str, Any]:
    """Bestaande velden als invoer voor PATCH-validatie (zonder `id`)."""
    return catalogus_state(get_source(db_path, source_id))


# ==== Schrijfpaden ===========================================================


def _insert(
    connection: sqlite3.Connection, record: SourceInput
) -> int:
    cursor = connection.execute(
        "INSERT INTO sources (name, feed_url, feed_url_key, website_url, type, "
        "language, reliability, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            record.name,
            record.feed_url,
            record.feed_url_key,
            record.website_url,
            record.type,
            record.language,
            record.reliability,
            1 if record.is_active else 0,
        ),
    )
    source_id = int(cursor.lastrowid)
    _replace_relaties(connection, source_id, record)
    return source_id


def _replace_relaties(
    connection: sqlite3.Connection, source_id: int, record: SourceInput
) -> None:
    """Vervangt de volledige set onderwerpen én cloudlabels (PATCH-semantiek)."""
    connection.execute("DELETE FROM source_topics WHERE source_id = ?", (source_id,))
    connection.execute(
        "DELETE FROM source_cloud_labels WHERE source_id = ?", (source_id,)
    )
    for slug in record.topics:
        connection.execute(
            "INSERT INTO source_topics (source_id, topic_slug) VALUES (?, ?)",
            (source_id, slug),
        )
    for label in record.cloud_labels:
        connection.execute(
            "INSERT INTO source_cloud_labels (source_id, cloud_label) VALUES (?, ?)",
            (source_id, label),
        )


def _bestaat(
    connection: sqlite3.Connection, feed_url_key: str, source_id: int | None = None
) -> bool:
    if source_id is None:
        rij = connection.execute(
            "SELECT 1 FROM sources WHERE feed_url_key = ?", (feed_url_key,)
        ).fetchone()
    else:
        rij = connection.execute(
            "SELECT 1 FROM sources WHERE feed_url_key = ? AND id <> ?",
            (feed_url_key, source_id),
        ).fetchone()
    return rij is not None


def create_source(db_path: str, record: SourceInput) -> dict[str, Any]:
    """HTTP 201-pad: unieke feed-identiteit over actieve én inactieve bronnen."""
    try:
        with _write(db_path) as connection:
            if _bestaat(connection, record.feed_url_key):
                raise SourceConflict("feed-URL bestaat al")
            source_id = _insert(connection, record)
    except sqlite3.IntegrityError as exc:
        raise _map_sqlite_error(exc) from None
    return _record(
        (source_id, record.name, record.feed_url, record.website_url, record.type,
         record.language, record.reliability, 1 if record.is_active else 0),
        record.topics,
        record.cloud_labels,
    )


def insert_if_absent(db_path: str, record: SourceInput) -> bool:
    """Insert-only seedpad: voegt alleen toe, wijzigt of verwijdert nooit iets."""
    try:
        with _write(db_path) as connection:
            if _bestaat(connection, record.feed_url_key):
                return False
            _insert(connection, record)
    except sqlite3.IntegrityError as exc:
        raise _map_sqlite_error(exc) from None
    return True


def update_source(
    db_path: str, source_id: int, record: SourceInput
) -> dict[str, Any]:
    """PATCH-pad: bronrecord én relaties in één transactie met eindvalidatie."""
    try:
        with _write(db_path) as connection:
            bestaand = connection.execute(
                "SELECT 1 FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
            if bestaand is None:
                raise SourceNotFound(f"bron met id {source_id} bestaat niet")
            if _bestaat(connection, record.feed_url_key, source_id):
                raise SourceConflict("feed-URL bestaat al")
            connection.execute(
                "UPDATE sources SET name = ?, feed_url = ?, feed_url_key = ?, "
                "website_url = ?, type = ?, language = ?, reliability = ?, "
                "is_active = ? WHERE id = ?",
                (
                    record.name,
                    record.feed_url,
                    record.feed_url_key,
                    record.website_url,
                    record.type,
                    record.language,
                    record.reliability,
                    1 if record.is_active else 0,
                    source_id,
                ),
            )
            _replace_relaties(connection, source_id, record)
    except sqlite3.IntegrityError as exc:
        raise _map_sqlite_error(exc) from None
    return _record(
        (source_id, record.name, record.feed_url, record.website_url, record.type,
         record.language, record.reliability, 1 if record.is_active else 0),
        record.topics,
        record.cloud_labels,
    )


# ==== Opties =================================================================


def source_options(db_path: str) -> dict[str, list[str]]:
    """Onderwerpen (uit de `topics`-tabel), typen, taalbeleid en cloudlabels."""
    slugs: list[str] = []
    try:
        with connect(db_path) as connection:
            rijen = connection.execute(
                "SELECT slug FROM topics ORDER BY slug"
            ).fetchall()
        slugs = [rij[0] for rij in rijen]
    except sqlite3.Error as exc:
        raise _map_sqlite_error(exc) from None

    if not slugs:
        # Nooit liegen over de geldige waarden: zonder gevulde tabel toont de
        # route de code-woordenlijst die de validatie ook echt hanteert.
        slugs = list(TOPIC_SLUGS)
    return {
        "topics": slugs,
        "types": list(SOURCE_TYPES),
        "languages": list(LANGUAGES),
        "cloud_labels": list(CLOUD_LABELS),
    }


__all__ = [
    "DatabaseUnavailable",
    "SourceConflict",
    "SourceNotFound",
    "catalogus_state",
    "create_source",
    "get_source",
    "insert_if_absent",
    "list_sources",
    "source_options",
    "source_state",
    "update_source",
]
