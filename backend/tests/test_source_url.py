"""Offline URL-canonicalisatie en -validatie (taken 2.1 t/m 2.3).

Gouden tabel met de voorbeelden uit de delta-spec, de volledige rejectielijst en
de deterministische IDNA-normalisatie. Elke rejectie wordt ook via
`POST /api/sources` gecontroleerd: HTTP 422 én geen opgeslagen record.
"""

from __future__ import annotations

import socket

import pytest

from app.sources_validation import SourceValidationError, canonicalize_url
from tests.conftest import minimale_payload

pytestmark = pytest.mark.usefixtures("socket_guard")

# ==== 2.1 Gouden tabel met normalisatieregels ===============================

GOUDEN_TABEL = [
    # (invoer, verwachte uitvoer, reden/regel)
    (
        " HTTPS://WWW.Example.COM:443  ",
        "https://www.example.com/",
        "trimmen, scheme+host lowercase, standaardpoort weg, leeg pad wordt /",
    ),
    (
        "https://Example.com/News/RSS/",
        "https://example.com/News/RSS/",
        "padhoofdletters en trailing slash blijven behouden",
    ),
    (
        "https://example.com/feed?b=2&a=1",
        "https://example.com/feed?b=2&a=1",
        "queryvolgorde en -waarden blijven behouden",
    ),
    (
        "http://example.com:8080/x",
        "http://example.com:8080/x",
        "niet-standaardpoort blijft behouden",
    ),
    (
        "http://example.com:80/y",
        "http://example.com/y",
        "standaardpoort 80 vervalt bij http",
    ),
    (
        "https://www.example.com",
        "https://www.example.com/",
        "www blijft behouden en leeg pad wordt /",
    ),
    ("https://example.com", "https://example.com/", "leeg pad wordt /"),
    (
        "https://example.com/News",
        "https://example.com/News",
        "padhoofdletters zonder trailing slash blijven behouden",
    ),
    (
        "https://example.com/a%2Fb",
        "https://example.com/a%2Fb",
        "overige percent-encoding blijft behouden",
    ),
    (
        "HTTPS://EXAMPLE.COM/?b=2&a=1",
        "https://example.com/?b=2&a=1",
        "scheme lowercase, query blijft",
    ),
    (
        "http://example.com:8080",
        "http://example.com:8080/",
        "poort behouden, leeg pad wordt /",
    ),
    (
        "http://example.com:1/x",
        "http://example.com:1/x",
        "laagste geldige poort (1) blijft behouden",
    ),
    (
        "http://example.com:65535/x",
        "http://example.com:65535/x",
        "hoogste geldige poort (65535) blijft behouden",
    ),
    (
        "http://[2001:DB8::1]:8080/x",
        "http://[2001:db8::1]:8080/x",
        "IPv6-brackets en poort blijven behouden, host wordt lowercase",
    ),
]


@pytest.mark.parametrize("invoer,verwacht,reden", GOUDEN_TABEL)
def test_gouden_tabel_canonicalisatie(invoer: str, verwacht: str, reden: str) -> None:
    """2.1: elke normalisatieregel levert exact de canonieke uitvoer."""
    assert canonicalize_url(invoer) == verwacht, reden


def test_canonicalisatie_is_idempotent() -> None:
    """2.1: canonieke uitvoer opnieuw canonicaliseren verandert niets."""
    for _invoer, verwacht, _reden in GOUDEN_TABEL:
        assert canonicalize_url(verwacht) == verwacht


def test_trimmen_gebeurt_allen_buitenst() -> None:
    """2.1: buitenste whitespace verdwijnt, interne whitespace wordt geweigerd."""
    assert canonicalize_url("  https://example.com/feed  ") == (
        "https://example.com/feed"
    )
    with pytest.raises(SourceValidationError):
        canonicalize_url("https://example.com/ feed")


# ==== 2.2 Rejectielijst ======================================================

AFKEUR = [
    ("https://example.com/feed#section", "fragment"),
    ("https://user:pass@example.com/feed", "credentials"),
    ("https://user@example.com/feed", "credentials zonder wachtwoord"),
    ("https://example.com/ feed", "interne ongecodeerde whitespace"),
    ("https://example.com/\tfeed", "interne tab"),
    ("https://example.com/\x07feed", "controletekens"),
    ("https://example.com\\feed", "backslashes"),
    ("https://example.com/%zz", "ongeldige percent-escape"),
    ("https://example.com/%2", "afgeknipte percent-escape"),
    ("https://example.com/a/../b", "dot-segmenten"),
    ("https://example.com/a/./b", "statisch dot-segment"),
    ("/feed.xml", "relatieve URL"),
    ("feed.xml", "geen URL"),
    ("ftp://example.com/feed.xml", "niet-http(s)"),
    ("https://example.com:99999/feed", "poort buiten bereik"),
    ("https://example.com:abc/feed", "poort niet numeriek"),
    ("https://example.com:0/feed", "poort 0 buiten bereik"),
    ("https://example.com:/feed", "lege poort"),
    ("http://[::1]:0/x", "IPv6-poort 0 buiten bereik"),
    ("http://[::1]:/x", "IPv6 met lege poort"),
    ("", "leeg"),
    ("   ", "alleen whitespace"),
    ("https:///feed.xml", "geen host"),
    ("//example.com/feed.xml", "geen scheme"),
]


@pytest.mark.parametrize("invoer,reden", AFKEUR)
def test_rejectieregels(invoer: str, reden: str) -> None:
    """2.2: elk rejectiegeval gooit een validatiefout (geen stille acceptatie)."""
    with pytest.raises(SourceValidationError):
        canonicalize_url(invoer)


@pytest.mark.parametrize("invoer,reden", AFKEUR)
def test_rejectie_via_api_geeft_422_zonder_opslaan(
    catalogus_client, invoer: str, reden: str
) -> None:
    """2.2: via de API geeft elk rejectiegeval HTTP 422 en wordt niets opgeslagen."""
    respons = catalogus_client.post(
        "/api/sources", json=minimale_payload(feed_url=invoer)
    )
    assert respons.status_code == 422, f"{reden}: {respons.text}"
    assert catalogus_client.get("/api/sources").json() == []


def test_geen_netwerk_bij_canonicalisatie() -> None:
    """2.3: canonicalisatie opent geen socket en doet geen DNS-resolutie."""

    def _verboden(*_args, **_kwargs):
        raise AssertionError("canonicalisatie mag geen netwerkcontact openen")

    oorspronkelijk_connect = socket.socket.connect
    oorspronkelijk_getaddrinfo = socket.getaddrinfo
    socket.socket.connect = _verboden
    socket.getaddrinfo = _verboden
    try:
        for invoer, verwacht, _reden in GOUDEN_TABEL:
            assert canonicalize_url(invoer) == verwacht
        with pytest.raises(SourceValidationError):
            canonicalize_url("https://example.com/feed#fragment")
    finally:
        socket.socket.connect = oorspronkelijk_connect
        socket.getaddrinfo = oorspronkelijk_getaddrinfo


# ==== 2.3 Deterministische IDNA-normalisatie ================================


@pytest.mark.parametrize(
    "links,rechts",
    [
        ("https://BÜCHER.example/feed", "https://bücher.example/feed"),
        ("https://BÜCHER.EXAMPLE/feed", "https://Bücher.example/feed"),
        ("https://bücher.EXAMPLE/feed", "https://bücher.example/feed"),
        ("https://ΣΟΦΟΣ.example/x", "https://σοφος.example/x"),
    ],
)
def test_idna_hoofdlettervarianten_geven_zelfde_sleutel(
    links: str, rechts: str
) -> None:
    """2.3: hoofdlettervarianten van dezelfde niet-ASCII-host leveren één sleutel."""
    sleutel_links = canonicalize_url(links)
    assert sleutel_links == canonicalize_url(rechts)


def test_idna_is_ascii_punycode_zonder_netwerk() -> None:
    """2.3: de canonieke host is ASCII (punycode) en deterministisch."""
    assert canonicalize_url("https://BÜCHER.example/x") == (
        "https://xn--bcher-kva.example/x"
    )
    assert canonicalize_url("https://xn--bcher-kva.example/x") == (
        "https://xn--bcher-kva.example/x"
    )


def test_idna_sleutel_wordt_aan_record_opgeslagen(catalogus_client) -> None:
    """2.3: de afgeleide `feed_url_key` in de database is de canonieke sleutel."""
    from app.db import connect

    catalogus_client.post(
        "/api/sources", json=minimale_payload(feed_url="https://BÜCHER.example/feed")
    )
    with connect(catalogus_client.app.state.db_path) as connection:
        rij = connection.execute("SELECT feed_url_key FROM sources").fetchone()
    assert rij[0] == "https://xn--bcher-kva.example/feed"
