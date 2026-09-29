"""Offline validatie en canonicalisatie voor de broncatalogus (source-catalog).

Ontwerpregels (delta-spec `source-catalog`):
* Uitsluitend offline: `urllib.parse` uit de standaardbibliotheek, geen sockets,
  geen DNS, geen redirects en geen enkele nieuwe afhankelijkheid.
* Eén zuivere canonicalisatiefunctie (`canonicalize_url`) is het enige pad dat
  `feed_url`/`website_url` afleidt; de gouden testtabel dekt elke regel.
* Woordenlijsten zijn expliciet opgesomd: onderwerpen, cloudlabels, typen en
  taalcodes worden nooit afgeleid, nooit gefold en nooit extern opgehaald.
* Validatiefouten dragen een vaste, Nederlandse melding zonder SQL, stacktrace
  of pad; de router zet ze om in HTTP 422.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

# ==== Woordenlijsten ==========================================================

# Gecontroleerde typen: exact, lowercase, geen automatische typebepaling.
SOURCE_TYPES: tuple[str, ...] = ("rss", "atom")

# Cloudlabels: exact deze set, in deze volgorde (volgt de delta-spec).
CLOUD_LABELS: tuple[str, ...] = (
    "azure",
    "aws",
    "t-cloud",
    "otc",
    "multi-cloud",
    "sovereign-cloud",
)

# Onderwerpen: stabiele slugs (nooit hernoemd) met een Nederlandse naam.
# De woordenlijst volgt de onderwerpen uit README.md, aangevuld met de
# provider- en regio-dimensies die de catalogus expliciet moet kunnen labelen.
TOPICS: tuple[tuple[str, str], ...] = (
    ("ai", "AI"),
    ("ai-tools", "AI-tools"),
    ("aws", "AWS"),
    ("azure", "Azure"),
    ("digital-sovereignty", "Digitale soevereiniteit"),
    ("ethereum", "Ethereum"),
    ("geopolitics", "Geopolitiek"),
    ("kubernetes", "Kubernetes en cloud native"),
    ("linux", "Linux en open source"),
    ("middle-east", "Iran en Midden-Oosten"),
    ("open-telekom-cloud", "Open Telekom Cloud"),
    ("t-cloud-public", "T Cloud Public"),
    ("ukraine", "Oekraïne"),
)
TOPIC_SLUGS: tuple[str, ...] = tuple(slug for slug, _name in TOPICS)

# Expliciet opgesomde ISO 639-1-lijst (184 codes), aangevuld met `und` en `mul`.
# De lijst staat er volledig in tekst: geen package-afhankelijkheid, geen
# afleiding en geen netwerkcontrole bij het valideren.
_ISO_639_1 = """
aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co
cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl
gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv ka kg
ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml
mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt
qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te
tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh
zu
""".split()
LANGUAGES: tuple[str, ...] = (*_ISO_639_1, "und", "mul")

# Veldnamen die een bronrecord mogen bevatten (strict: onbekend -> 422).
SOURCE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "feed_url",
        "website_url",
        "type",
        "language",
        "reliability",
        "is_active",
        "topics",
        "cloud_labels",
    }
)
# PATCH: alleen `website_url` en `reliability` mogen `null` zijn.
NULLABLE_FIELDS: frozenset[str] = frozenset({"website_url", "reliability"})

# Velden die een POST-payload (en een seed-entry) mogen missen, met default.
SOURCE_DEFAULTS: dict[str, Any] = {
    "website_url": None,
    "reliability": None,
    "is_active": False,
    "topics": [],
    "cloud_labels": [],
}


def with_defaults(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Vult ontbrekende optionele velden aan vóór de volledige eindvalidatie."""
    data = dict(payload)
    for key, value in SOURCE_DEFAULTS.items():
        data.setdefault(key, value)
    return data

_URL_BAD_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
_URL_HOST_ALLOWED = re.compile(r"^[A-Za-z0-9._:\-\[\]]+$")


class SourceValidationError(ValueError):
    """Ongeldige invoer; de router toont `detail` als HTTP 422."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


# ==== URL-canonicalisatie =====================================================


def _idna_host(host: str) -> str:
    """Deterministische, offline IDNA-normalisatie van het hostdeel.

    Elk label wordt afzonderlijk via de ingebouwde IDNA-codec (nameprep +
    ToASCII) omgezet en daarna lowercase gemaakt. Zelfde invoer -> exact
    dezelfde sleutel, zonder enig netwerkgebruik.
    """
    labels: list[str] = []
    for label in host.split("."):
        if label and not label.isascii():
            try:
                label = label.encode("idna").decode("ascii")
            except UnicodeError:
                raise SourceValidationError(
                    "host kan niet IDNA-genormaliseerd worden"
                ) from None
        labels.append(label.lower())
    return ".".join(labels)


def _poort_aanwezig(netloc: str) -> bool:
    """Geeft aan of de authority poortsyntax bevat (`host:poort` / `[v6]:poort`).

    `urlsplit(...).port` is `None` bij zowel een ontbrekende als een *lege*
    poort (`https://example.com:/feed`), dus de aanwezigheid van de kolon moet
    los van de waarde bekeken worden.
    """
    if netloc.startswith("["):
        sluit = netloc.find("]")
        return sluit != -1 and netloc[sluit + 1 :].startswith(":")
    # Gebruikersinformatie (`@`) is voor dit punt al geweigerd, dus een kolon in
    # een ongebracket authority kan alleen de poortscheiding zijn.
    return ":" in netloc


def canonicalize_url(value: str) -> str:
    """Valideert en canonicaliseert een absolute http(s)-URL offline.

    Regels: trimmen; scheme en host lowercase; IDNA-host; standaardpoort weg;
    leeg pad -> `/`; `www`, scheme, padhoofdletters, niet-lege trailing slash,
    queryvolgorde/-waarden en overige percent-encoding blijven behouden.
    Geweigerd: fragment, credentials, controletekens, interne whitespace,
    backslashes, ongeldige percent-escapes, dot-segmenten, relatieve of
    niet-http(s)-URL's en een ongeldige poort (niet numeriek, leeg of buiten
    1..65535).
    """
    if not isinstance(value, str):
        raise SourceValidationError("URL moet een tekstwaarde zijn")

    trimmed = value.strip()
    if not trimmed:
        raise SourceValidationError("URL mag niet leeg zijn")

    for char in trimmed:
        if char.isspace() or ord(char) < 0x21 or ord(char) == 0x7F:
            raise SourceValidationError("URL bevat whitespace of controletekens")
        if char == "\\":
            raise SourceValidationError("URL bevat een backslash")

    if "#" in trimmed:
        raise SourceValidationError("URL mag geen fragment bevatten")

    try:
        parts = urlsplit(trimmed)
    except ValueError:
        raise SourceValidationError("URL is niet parseerbaar") from None

    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.netloc:
        raise SourceValidationError("URL moet een absolute http- of https-URL zijn")

    if "@" in parts.netloc:
        raise SourceValidationError("URL mag geen credentials bevatten")

    try:
        port = parts.port
    except ValueError:
        raise SourceValidationError("URL heeft een ongeldige poort") from None

    # Poort moet numeriek en binnen 1..65535 zijn. `parts.port` levert al een
    # ValueError voor niet-numerieke of te hoge waarden, maar accepteert `:0`
    # en ziet een lege poort (`:`) als "geen poort": beide hier expliciet
    # weigeren, ook binnen IPv6-brackets (`http://[::1]:0/x`, `[::1]:/x`).
    if _poort_aanwezig(parts.netloc):
        if port is None or not 1 <= port <= 65535:
            raise SourceValidationError("URL heeft een ongeldige poort")

    host = parts.hostname
    if not host:
        raise SourceValidationError("URL mist een host")
    host = _idna_host(host)
    if not _URL_HOST_ALLOWED.match(host):
        raise SourceValidationError("URL heeft een ongeldige host")

    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        authority = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    else:
        authority = f"[{host}]" if ":" in host else host

    path = parts.path or "/"
    for segment in path.split("/"):
        if segment in (".", ".."):
            raise SourceValidationError("URL mag geen dot-segmenten in het pad bevatten")

    controleren = path + (f"?{parts.query}" if parts.query else "")
    if _URL_BAD_PERCENT.search(controleren):
        raise SourceValidationError("URL bevat een ongeldige percent-escape")

    return urlunsplit((scheme, authority, path, parts.query, ""))


# ==== Veldvalidatie ===========================================================


def validate_name(value: Any) -> str:
    if not isinstance(value, str):
        raise SourceValidationError("name moet een tekstwaarde zijn")
    name = value.strip()
    if not name:
        raise SourceValidationError("name mag niet leeg zijn")
    return name


def validate_type(value: Any) -> str:
    """`type` is verplicht en exact `rss` of `atom` (geen casefold)."""
    if not isinstance(value, str) or value not in SOURCE_TYPES:
        raise SourceValidationError("type moet exact 'rss' of 'atom' zijn")
    return value


def validate_language(value: Any) -> str:
    """Taal: verplicht, naar lowercase, uitsluitend uit de expliciete lijst."""
    if not isinstance(value, str):
        raise SourceValidationError("language moet een tekstwaarde zijn")
    language = value.lower()
    if language not in LANGUAGES:
        raise SourceValidationError("language staat niet in de codelijst")
    return language


def validate_reliability(value: Any) -> int | None:
    """`null` of een echte integer 1..5; bool, string en decimaal zijn ongeldig."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SourceValidationError("reliability moet null of een integer 1..5 zijn")
    if not 1 <= value <= 5:
        raise SourceValidationError("reliability moet tussen 1 en 5 liggen")
    return value


def validate_is_active(value: Any) -> bool:
    if not isinstance(value, bool):
        raise SourceValidationError("is_active moet een boolean zijn")
    return value


def validate_wordlist(value: Any, allowed: Sequence[str], label: str) -> tuple[str, ...]:
    """Lijstveld: verplichte lijst, onbekende waarden en duplicaten -> fout."""
    if not isinstance(value, (list, tuple)):
        raise SourceValidationError(f"{label} moet een lijst zijn")
    items = list(value)
    seen: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise SourceValidationError(f"{label} bevat geen tekstwaarde")
        if item not in allowed:
            raise SourceValidationError(f"{label} bevat een onbekende waarde")
        if item in seen:
            raise SourceValidationError(f"{label} bevat een dubbele waarde")
        seen.append(item)
    if label == "topics":
        return tuple(slug for slug in TOPIC_SLUGS if slug in seen)
    return tuple(label_item for label_item in allowed if label_item in seen)


@dataclass(frozen=True)
class SourceInput:
    """Volledig gevalideerde eindtoestand van een bronrecord."""

    name: str
    feed_url: str
    feed_url_key: str
    website_url: str | None
    type: str
    language: str
    reliability: int | None
    is_active: bool
    topics: tuple[str, ...]
    cloud_labels: tuple[str, ...]

    def as_payload(self) -> dict[str, Any]:
        """Catalogusvelden zoals de API ze teruggeeft (geen interne sleutels)."""
        return {
            "name": self.name,
            "feed_url": self.feed_url,
            "website_url": self.website_url,
            "type": self.type,
            "language": self.language,
            "reliability": self.reliability,
            "is_active": self.is_active,
            "topics": list(self.topics),
            "cloud_labels": list(self.cloud_labels),
        }


def validate_source(payload: Mapping[str, Any]) -> SourceInput:
    """Valideert een volledig bronrecord (POST) of een gemergede eindtoestand."""
    unknown = sorted(set(payload) - SOURCE_FIELDS)
    if unknown:
        raise SourceValidationError("payload bevat onbekende velden")
    for veld in SOURCE_FIELDS:
        if veld not in payload:
            raise SourceValidationError(f"{veld} ontbreekt")
    if payload["website_url"] is None:
        website_url = None
    else:
        website_url = canonicalize_url(payload["website_url"])

    feed_url_trimmed = payload["feed_url"].strip() if isinstance(payload["feed_url"], str) else payload["feed_url"]
    feed_url_key = canonicalize_url(payload["feed_url"])

    return SourceInput(
        name=validate_name(payload["name"]),
        feed_url=feed_url_trimmed,
        feed_url_key=feed_url_key,
        website_url=website_url,
        type=validate_type(payload["type"]),
        language=validate_language(payload["language"]),
        reliability=validate_reliability(payload["reliability"]),
        is_active=validate_is_active(payload["is_active"]),
        topics=validate_wordlist(payload["topics"], TOPIC_SLUGS, "topics"),
        cloud_labels=validate_wordlist(payload["cloud_labels"], CLOUD_LABELS, "cloud_labels"),
    )


def validate_patch(payload: Mapping[str, Any], existing: Mapping[str, Any]) -> SourceInput:
    """PATCH-regels: lege body -> fout, `null` alleen waar het mag, dan de
    volledige gemergede eindtoestand opnieuw volledig valideren."""
    if not isinstance(payload, Mapping) or not payload:
        raise SourceValidationError("PATCH bevat geen velden")
    unknown = sorted(set(payload) - SOURCE_FIELDS)
    if unknown:
        raise SourceValidationError("payload bevat onbekende velden")
    for key, value in payload.items():
        if value is None and key not in NULLABLE_FIELDS:
            raise SourceValidationError(f"null is niet toegestaan voor {key}")
    merged = dict(existing)
    merged.update(payload)
    return validate_source(merged)
