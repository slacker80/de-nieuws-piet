# Broncatalogus (source-catalog)

Lokale, offline catalogus van publicatiekanalen: veldvalidatie, URL-canonicalisatie,
unieke feed-identiteit, gecontroleerde woordenlijsten, een kleine FastAPI-beheerinterface
en een handmatig gestarte seed — uitsluitend op lokale SQLite.

Grens: dit document beschrijft **uitsluitend** broncatalogusmetadata. Er wordt geen feed
opgehaald, niet gescraapt, geen artikel opgeslagen en geen URL extern gevalideerd.

---

## 1. Versiegestuurde migratie (v1 → v2)

De migratie draait in de `lifespan` van de applicatie, direct na `init_database`, en is
ook handmatig uit te voeren:

```bash
# in de backend-container of lokaal in backend/
python -m app.db_migrate            # standaardpad /app/data/news.db
APP_DB_PATH=/pad/naar/news.db python -m app.db_migrate
python -m app.db_migrate /pad/naar/news.db
```

Exit codes: `0` = uitgevoerd of noop, `1` = fout (met melding op stderr).

### Stappen, exact in deze volgorde

De hele migratie draait in **één** transactie (`BEGIN IMMEDIATE`); `schema_version`
gaat pas als **laatste stap** van 1 naar 2.

| # | Stap |
|---|------|
| 1 | `topics` (woordlijsttabel, `slug TEXT PRIMARY KEY`, `name TEXT NOT NULL`) vullen |
| 2 | `sources` met `id INTEGER PRIMARY KEY`, `name`, `feed_url`, `feed_url_key`, `website_url`, `type`, `language`, `reliability`, `is_active` |
| 3 | `source_topics` (`source_id` → `sources`, `topic_slug` → `topics`) |
| 4 | `source_cloud_labels` (`source_id` → `sources`, `cloud_label`) |
| 5 | `UNIQUE`-index `ux_sources_feed_url_key` op `feed_url_key` |
| 6 | zoekindexen op `is_active`, `topic_slug` en `cloud_label` |
| 7 | `app_meta.schema_version` = `2` |

Controles na afloop (`PRAGMA foreign_key_check` leeg, versie 2, alle tabellen aanwezig)
worden in `tests/test_source_migration.py` afgedwongen.

### Gedrag per uitgangssituatie

| Situatie | Resultaat |
|----------|-----------|
| versie 1 | `migrated`; versie wordt 2, tabellen/indexen/woordenlijst aangemaakt |
| versie 2 | `noop`; geen tabel, index of rij gewijzigd |
| versie > 2 of onbekende waarde | weigering, **niets** gewijzigd |
| fout midden in de migratie | volledige rollback; versie blijft 1, geen halve tabellen |
| `PRAGMA foreign_keys` | staat op **elke** verse verbinding aan (`app.db.connect`) |

Het aantal databasepogingen per aanroep is vast: er wordt nooit herprobeerd.

### Bootstrap classificeert read-only vóór elke schrijfactie

`init_database` — de stap vóór de migratie in de `lifespan` — classificeert een
**bestaande** database allereerst read-only (`sqlite3` met `mode=ro`) op
`app_meta.schema_version`. Pas ná die classificatie volgt er DDL/DML:

| Situatie bij start | Gedrag |
|--------------------|--------|
| bestand ontbreekt of is 0 bytes | bootstrap: v1-tabellen, data-marker en `schema_version = 1`, daarna migratie naar 2 |
| marker `1` | alleen de noodzakelijke bootstrap (tabellen/marker aanvullen), daarna migratie naar 2 |
| marker `2` | **geen enkele** write: herstart van een gezonde versie-2 database schrijft **geen enkele byte** |
| marker > `2` of niet-numeriek | `MigrationError`, **geen enkele** write — geen `CREATE TABLE`, geen `bootstrap_marker`, geen sidecar; de app-start faalt |
| marker ontbreekt (bestaat wel tabel) | `schema_version = 1` en verder volgens rij `marker 1` |

De versiemarker wordt nooit overschreven: `migrate` blijft de enige eigenaar van de
overgang 1 → 2. Een mislukte migratie laat marker én schema volledig intact (rollback).
De data-marker (`bootstrap_marker.initialized = nieuws-piet`) wordt alleen aangevuld in
de paden die sowieso mogen schrijven. `PRAGMA foreign_keys=ON` is connection-lokaal en
geen persistente schrijfactie.

Gedwongen door `tests/test_db_lifespan.py`, dat de volledige startsequentie via
`create_app`/lifespan uitvoert — inclusief minimalistische bestaande databases met
alléén `app_meta` (geen `bootstrap_marker`), waarvan na een weigering `sqlite_master`,
de marker én de bytes exact gelijk moeten blijven.

### Concurrerende starters: herclassificatie onder het schrijfslot

De read-only classificatie is een momentopname (TOCTOU): tussen die lezing en de
schrijffase mag een andere starter of migrator `2` (of nieuwer/ongekend) committen.
Daarom heeft **elke** schrijffase twee classificaties:

1. de snelle read-only classificatie — bepaalt of er überhaupt een slot nodig is;
2. een verplichte herclassificatie **ná** `BEGIN IMMEDIATE`, vóór de eerste
   `CREATE TABLE`/`INSERT`.

`BEGIN IMMEDIATE` is een SQLite-native slot: alle normale SQLite-writers worden
daarmee geserialiseerd, dus de uitkomst van de hercheck kan niet meer veranderen
tot wij `COMMIT` of `ROLLBACK` doen. Die hercheck beslist:

| Hercheck onder het slot | Actie |
|-------------------------|-------|
| `2` | `ROLLBACK` en terugkeren als noop — **geen** persistente write |
| > `2` of niet-numeriek | `ROLLBACK` + `MigrationError` — **geen** persistente write, ook geen `bootstrap_marker` |
| `1` of `leeg` | bootstrap/migratie binnen dezelfde transactie; `schema_version` blijft de laatste stap en een fout rolt alles terug |

`init_database` én `migrate` hebben elk zo'n eigen beschermd fase en elke fase
classificeert opnieuw, zodat de volgorde init → migratie ook bij gelijktijdige
starters klopt. Er ontstaan geen nested-transactiefouten: beide fases zetten
`isolation_level = None` en sturen `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK` zelf.

**Onderscheid zijeffect vs. contract.** Het nemen van een schrijfslot mag een
*tijdelijk* rollback-journal aanmaken; dat bestand verdwijnt bij `ROLLBACK` of
`COMMIT`. Het extern waarneembare contract — en wat de tests afdwingen — is dat de
hoofddatabase byte-identiek blijft, `sqlite_master` en de rijen niet veranderen en
er na afloop geen sidecar (`.journal`/`.shm`) overblijft.

Gedwongen door `tests/test_db_concurrency.py`: deterministische races (hooks én een
echte tweede verbinding met `BEGIN IMMEDIATE`) waarin actor A als `v1` classificeert
en actor B intussen `2`, `3` of `onbekend` commit't.

---

## 2. URL-regels, taalbeleid en woordenlijsten

### 2.1 Canonicalisatie (offline, `app.sources_validation.canonicalize_url`)

| Regel | Voorbeeld | Resultaat |
|-------|-----------|-----------|
| trimmen, scheme+host lowercase, standaardpoort weg, leeg pad → `/` | ` HTTPS://WWW.Example.COM:443  ` | `https://www.example.com/` |
| padhoofdletters en trailing slash behouden | `https://Example.com/News/RSS/` | `https://example.com/News/RSS/` |
| queryvolgorde en -waarden behouden | `https://example.com/feed?b=2&a=1` | `https://example.com/feed?b=2&a=1` |
| niet-standaardpoort behouden | `http://example.com:8080/x` | `http://example.com:8080/x` |
| standaardpoort 80 vervalt bij http | `http://example.com:80/y` | `http://example.com/y` |
| geldige poort (1..65535) blijft behouden | `http://example.com:65535/x` | `http://example.com:65535/x` |
| `www` behouden, leeg pad → `/` | `https://www.example.com` | `https://www.example.com/` |
| overige percent-encoding behouden | `https://example.com/a%2Fb` | `https://example.com/a%2Fb` |

### 2.2 Geweigerd (elk geval geeft HTTP 422, nooit een opgeslagen record)

fragment (`https://example.com/feed#section`), credentials (`https://user:pass@example.com/feed`),
controletekens, interne ongecodeerde whitespace (`https://example.com/ feed`), backslashes
(`https://example.com\feed`), ongeldige percent-escapes (`https://example.com/%zz`),
dot-segmenten (`https://example.com/a/../b`), relatieve of niet-http(s)-URL (`/feed.xml`,
`ftp://example.com/feed.xml`) en een ongeldige poort: buiten bereik
(`https://example.com:99999/feed`), niet numeriek (`https://example.com:abc/feed`),
nul (`https://example.com:0/feed`) of leeg (`https://example.com:/feed`). De poort moet
numeriek zijn en tussen **1** en **65535** liggen; bij IPv6 gelden dezelfde regels na de
brackets (`http://[::1]:0/x`, `http://[::1]:/x`).

### 2.3 IDNA zonder netwerk

De host wordt per label via de ingebouwde IDNA-codec genormaliseerd en lowercase gemaakt.
Hoofdlettervarianten van dezelfde niet-ASCII-host leveren **dezelfde** `feed_url_key`:
`https://BÜCHER.example/feed` en `https://bücher.example/feed` worden allebei
`https://xn--bcher-kva.example/feed`. Er wordt geen socket geopend en niet geresolveerd.

### 2.4 Veldregels

- `name`: verplicht, na trimmen niet leeg.
- `feed_url`: verplicht; de **originele** (getrimde) waarde wordt bewaard, de canonieke
  sleutel staat in `feed_url_key`.
- `website_url`: optioneel, dezelfde URL-regels; wordt canoniek opgeslagen.
- `type`: verplicht, exact `rss` of `atom` — geen casefold, geen automatische bepaling.
- `language`: verplicht, eerst naar lowercase, daarna uitsluitend uit de expliciete lijst;
  elke waarde daarbuiten is 422.
- `reliability`: `null` of een echte integer 1..5; boolean, string en decimale notatie
  (`4.5`, `"4"`) zijn ongeldig; `0` en `6` liggen buiten het bereik.
- `is_active`: boolean met standaard `false`; uitsluitend de seed zet een starter op
  `true` na handmatige beoordeling.
- `topics` / `cloud_labels`: lijsten zonder automatische afleiding; onbekende en dubbele
  items in één request zijn 422.

### 2.5 Woordenlijsten (expliciet, nooit afgeleid of extern opgehaald)

- **Onderwerpen (13 stabiele slugs):** `ai`, `ai-tools`, `aws`, `azure`,
  `digital-sovereignty`, `ethereum`, `geopolitics`, `kubernetes`, `linux`, `middle-east`,
  `open-telekom-cloud`, `t-cloud-public`, `ukraine`.
- **Cloudlabels (exact):** `azure`, `aws`, `t-cloud`, `otc`, `multi-cloud`,
  `sovereign-cloud`.
- **Typen (exact):** `rss`, `atom`.
- **Taalbeleid:** 184 ISO 639-1-codes, aangevuld met `und` en `mul` (186 waarden),
  allemaal lowercase; de lijst staat als tekst in `app/sources_validation.py`.
  Voorbeelden van geldige codes: `nl`, `en`, `de`, `uk`, `ar`; een code buiten de
  lijst — bijvoorbeeld `zz` of `nl-NL` — geeft HTTP 422. `NL` wordt eerst naar
  `nl` genormaliseerd en is daarna geldig.

Deze vier lijsten zijn ook op te vragen via `GET /api/source-options`.

---

## 3. API-contract

Precies **vijf** routes; geen `DELETE`, geen opties-CRUD, geen upsert en geen pagination.

| Methode | Pad | Succes | Fouten |
|---------|-----|--------|--------|
| `GET` | `/api/sources` | 200, volledige catalogus in één respons | 422 (ongeldige filterwaarde), 503 |
| `GET` | `/api/sources/{id}` | 200, detail inclusief relaties | 404, 503 |
| `POST` | `/api/sources` | 201, opgeslagen record | 409, 422, 503 |
| `PATCH` | `/api/sources/{id}` | 200, bijgewerkt record | 404, 409, 422, 503 |
| `GET` | `/api/source-options` | 200, `topics` + `types` + `languages` + `cloud_labels` | 503 |

### Filters op `GET /api/sources`

`is_active=true|false`, `topic=<slug>`, `cloud_label=<label>` — optioneel en als **AND**
gecombineerd. Standaard worden actieve én inactieve bronnen meegeleverd, gesorteerd op
oplopend `id`. Een lege catalogus geeft 200 met `[]`. Een filterwaarde buiten de
woordenlijst geeft 422.

### Requestvelden

| Veld | POST | PATCH |
|------|------|-------|
| `name` | verplicht | optioneel |
| `feed_url` | verplicht | optioneel |
| `website_url` | optioneel (`null` toegestaan) | optioneel, `null` wist |
| `type` | verplicht (`rss`/`atom`) | optioneel |
| `language` | verplicht | optioneel |
| `reliability` | optioneel (`null` toegestaan) | optioneel, `null` wist |
| `is_active` | optioneel, default `false` | optioneel |
| `topics`, `cloud_labels` | optioneel, hele set | optioneel; aanwezige lijst **vervangt** de hele set, `[]` wist alles |

Onbekende velden zijn 422. Een PATCH zonder velden is 422. `null` mag alleen bij
`website_url` en `reliability`. De eindtoestand wordt altijd volledig gevalideerd;
bronrecord én relaties worden in één transactie geschreven, dus bij elke fout blijft
alles onveranderd. Een onbekend id wordt nooit aangemaakt.

### Responsvelden

```json
{
  "id": 1,
  "name": "Kubernetes Blog",
  "feed_url": "https://kubernetes.io/feed.xml",
  "website_url": "https://kubernetes.io/",
  "type": "rss",
  "language": "en",
  "reliability": 5,
  "is_active": true,
  "topics": ["kubernetes"],
  "cloud_labels": []
}
```

`feed_url_key` is een interne sleutel en komt **niet** in de respons.

### Vaste foutbodies

| Code | `detail` |
|------|----------|
| 404 | `bron bestaat niet` |
| 409 | `feed-URL bestaat al` (ook tegenover een inactieve bron) |
| 422 | vaste Nederlandse melding (bijv. `ongeldige invoer`) |
| 503 | `database onbereikbaar` |

Geen enkele foutrespons bevat SQL-tekst, een stacktrace of een lokaal pad.
`GET /health` is ongewijzigd en kent geen catalogusvelden of extra componenten.

---

## 4. Handmatig gestarte seed

### Starten

```bash
# in de backend-container
python -m app.source_seed                 # standaardpad /app/data/news.db
APP_DB_PATH=/pad/naar/news.db python -m app.source_seed
python -m app.source_seed /pad/naar/news.db
```

Exit codes: `0` = uitgevoerd, `1` = fout (bijvoorbeeld een database die niet op
schema-versie 2 staat: voer eerst `python -m app.db_migrate` uit).

De seed draait **nooit** bij applicatie-start en **niet** tijdens de migratie: het is
een expliciete, losse stap. Er wordt geen netwerkverkeer gebruikt (insert-only, alle
sleutels worden offline afgeleid).

### Beoordelingscriteria voor een starter

- uitsluitend officiële publicatiekanalen van organisaties uit de bronstrategie;
- de feed-URL is vóór opname handmatig geopend en als RSS- of Atom-feed herkend;
- geen aggregators, geen gelinkte landingspagina's en geen URL zonder die beoordeling;
- elke entry in `backend/app/source_seed.json` draagt een `reviewed`-datum.

### Herhaling

De seed is insert-only op `feed_url_key`: bij herhaling worden **alleen** ontbrekende
starters toegevoegd. Bestaande records — inclusief wijzigingen die de gebruiker zelf
heeft gedaan — worden nooit gewijzigd of overschreven. Een ongeldige entry blokkeert
de hele run: er blijft nooit een halve seed achter.

---

## 5. Backup en restore met catalogusdata

De bestaande data-safe procedure uit [`data-safe-rollback-restore.md`](data-safe-rollback-restore.md)
blijft ongewijzigd; er is geen aparte catalogus-backupfunctie toegevoegd. De broncatalogus
staat in dezelfde SQLite-database als de bootstrap-data en wordt daarom **altijd meegenomen**:

```bash
scripts/db-rollback.sh backup                       # backup + PRAGMA integrity_check
scripts/db-rollback.sh validate [backupnaam]        # alleen validatie (exact `ok`)
scripts/db-rollback.sh restore  [backupnaam]        # terugzetten na validatie
scripts/db-rollback.sh preserve [--data-only]       # non-destructief pad
scripts/db-rollback.sh reset --allow-volume-removal # opt-in destructief pad
```

Wat er bij restore behouden blijft:

- alle catalogusrijen uit `sources` (inclusief `feed_url_key` en `is_active`);
- alle onderwerprelaties uit `source_topics`;
- alle cloudlabel-relaties uit `source_cloud_labels`;
- de woordenlijst in `topics` en de schema-versie 2 in `app_meta`.

Na restore toetst het bestaande proces `PRAGMA integrity_check` (exact `ok`), ten minste
één tabel en de data-marker `bootstrap_marker.initialized = nieuws-piet`; de standaardpaden
verifiëren bovendien `/health`. De feitelijke gelijkheid van catalogusrijen en relaties
wordt in `tests/test_source_backup_restore.py` tegen het bestaande script bewezen.
