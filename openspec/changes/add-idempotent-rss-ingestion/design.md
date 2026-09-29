# Design

## Context

Zie `proposal.md` (Why) voor de motivatie. Deze change bouwt voort op de bestaande backend: een FastAPI app-factory (`create_app()`), `sqlite3` op schema-versie 2 met `sources`/`topics`/`source_topics`/`source_cloud_labels`, een additieve migratie `1 → 2` in `db_migrate.py`, een idempotente offline seed (`python -m app.source_seed`) en een exact `/health`-contract. De broncatalogus levert de te verwerken bronnen: `id`, `type` (`rss`|`atom`), `is_active`, `feed_url` (plus de afgeleide `feed_url_key`) en strikte offline canonicalisatie via `sources_validation.canonicalize_url`.

Wat de code vandaag níet heeft: itemtabellen, HTTP-ophaling, feedparsen, datumnormalisatie en enige vorm van retries of redirects. De tests draaien onder een `socket_guard` die elke verbinding of DNS-resolutie naar een externe host afbreekt (`backend/tests/conftest.py`), met een dekkingscontrole in `backend/tests/test_source_offline.py`. Projectregels uit `openspec/config.yaml`: alle artifacts in het Nederlands, structuurhoofdingen en `SHALL`/`MUST` in het Engels, backend-tests verplicht, geen duplicaten bij herhaalde imports, geen externe accounts, betaalde API's of publieke hosting zonder toestemming.

De gedragsafspraken staan in `specs/rss-ingestion/spec.md` en de delta op `specs/source-catalog/spec.md`; dit document legt vast hoe dat technisch wordt vormgegeven.

## Goals / Non-Goals

**Goals:**
- Eén afzonderlijke, zelfstandige ingestiemodule (frontend, backend en ingestie blijven gescheiden) met een CLI-entrypoint dat de bestaande `python -m app.<module>`-conventie volgt.
- Een additief, versiegestuurd datamodel (schema 3) met brongebonden itemidentiteit in een aparte aliastabel (database-uniekheid als sluitende deduplicatiegarantie) plus de laatste operationele status per bron.
- Een volledig vervangbare netwerklaag, klok en slaapvoorziening, zodat de hele keten zonder internet en zonder echte wachttijd testbaar is.
- Eén duidelijke foutmapping: per bron exact één stabiele foutcode, gedeterministische exitcode, geen lekkage van interne details.
- Expliciete verklaring van extern netwerkgebruik, datastromen, kosten en het ontbreken van LLM/provider-keuzes.

**Non-Goals (designniveau):**
- Geen verandering aan `sources_api.py`, `sources_repository.py`, `sources_validation.py`, `health.py`, de vijf catalogusroutes of het `/health`-contract.
- Geen scheduler, achtergrondtaak, frontend-werk of item-API-route; de CLI is in deze change het enige ingangspunt.
- Geen nieuwe Python-afhankelijkheden (stdlib-only) en geen nieuwe compose-services.
- Geen opslag van artikelinhoud en geen importgeschiedenistabel: per bron wordt alleen de laatste operationele status bewaard, nooit een reeks runresultaten.

## Decisions

### Beslissing 1: Modulegrenzen en CLI-contract
**Beslissing**: de ingestie wordt een aparte subpackage `backend/app/rss_ingest/` met daarin `cli.py` (`main(argv) -> int`), `transport.py`, `parser.py`, `normalize.py`, `store.py` en `errors.py`, plus een `__main__.py` die `main()` aanroept. Daarnaast exporteert `app/rss_ingest/__init__.py` `main`, zodat tests het commando rechtstreeks kunnen aanroepen zonder subprocess.

Argumenten (met `argparse`, iets wat bestaande modules nog niet gebruiken maar hier de meerdere optionele flags afdwingt):
- `python -m app.rss_ingest` → alle geselecteerde actieve bronnen;
- een optioneel positief databasepadargument (conform `source_seed`);
- `--source <id>` → expliciet één bron (ook inactief/onthandeld → foutcode).

Exitcodes: `0` als elke geselecteerde bron zonder fout én zonder conflict is verwerkt (of de selectie leeg is), `1` in elk ander geval. Uitvoer: één regel per bron in oplopende id-volgorde, `bron=<id> status=ok|not_modified|fout toegevoegd=<n> bijgewerkt=<n> ongewijzigd=<n> overgeslagen=<n> conflicten=<n> [code=<code>]`; de statusset is `ok`, `not_modified` en `fout`, `[code=<code>]` verschijnt uitsluitend bij status `fout` en komt uit de gesloten foutcodeset uit de spec (waarin `not_modified` niet voorkomt). Fouten op `stderr`, samenvatting op `stdout`.

**Afgewogen alternatieven**: (a) losse platte modules `app/rss_ingest.py` + helpers → minder bestanden, maar vermengt de ingestie met de bestaande platte catalogusmodules; (b) een FastAPI-route → expliciet buiten scope van deze change (handmatig commando eerst).

### Beslissing 2: Datamodel en schema-versie 3
**Beslissing**: één additieve statementset die elke versie-1- of versie-2-database binnen één `BEGIN IMMEDIATE` naar versie 3 brengt; `app_meta.schema_version` gaat pas als laatste stap naar `3`, net als bij de bestaande migratie. De bestaande classificatielogica wordt uitgebreid: `3` = noop, `> 3` of niet-numeriek = weigeren zonder schrijfactie.

```sql
CREATE TABLE IF NOT EXISTS items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     INTEGER NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
    original_url  TEXT,                       -- gepubliceerde link (opgelost)
    title         TEXT,                       -- getrimd, NULL bij leeg
    published_at  TEXT,                       -- ISO-8601 UTC of NULL
    content_hash  TEXT NOT NULL               -- wijzigingsindicatie, nooit identiteit
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_items_id_source
    ON items (id, source_id);
CREATE INDEX IF NOT EXISTS ix_items_source_published
    ON items (source_id, published_at, id);

CREATE TABLE IF NOT EXISTS item_identity_aliases (
    item_id     INTEGER NOT NULL,
    source_id   INTEGER NOT NULL,
    alias_type  TEXT    NOT NULL CHECK (alias_type IN ('external_id', 'canonical_url')),
    alias_value TEXT    NOT NULL CHECK (length(trim(alias_value)) > 0),
    PRIMARY KEY (source_id, alias_type, alias_value),
    FOREIGN KEY (item_id, source_id) REFERENCES items (id, source_id)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_item_aliases_item
    ON item_identity_aliases (item_id);

CREATE TABLE IF NOT EXISTS source_feed_state (
    source_id            INTEGER PRIMARY KEY REFERENCES sources (id) ON DELETE CASCADE,
    etag                 TEXT,
    last_modified        TEXT,
    last_attempt_at      TEXT,                -- ISO-8601 UTC van de laatste ophaalpoging
    last_success_at      TEXT,                -- ISO-8601 UTC of NULL
    last_error_code      TEXT,                -- NULL na succes of na not_modified
    last_error_detail    TEXT,                -- gesaneerd, maximaal 200 tekens
    last_http_status     INTEGER,             -- NULL bij niet-HTTP-fouten
    consecutive_failures INTEGER NOT NULL DEFAULT 0
);
```

**Redenering**:
- `item_identity_aliases` is de *autoriteit* voor "maximaal eenmaal per bron": de primairsleutel op `(source_id, alias_type, alias_value)` dwingt de unieke identiteit af, ook zonder dat de CLI het conflict ziet; een alias bestaat of bestaat niet, dus er zijn geen `NULL`-aliassen en de partiele-indextruc is overbodig.
- De samengestelde foreign key `(item_id, source_id) → items(id, source_id)` (mogelijk gemaakt door `ux_items_id_source`) dwingt op databaseniveau af dat alias en item altijd tot dezelfde bron behoren: een alias van bron 2 kan nooit op een item van bron 1 wijzen. Bronconsistentie is daarmee databaseauthoritatief, niet slechts een toepassingsregel.
- Aliassen zijn **additief**: een gewijzigde GUID of item-URL levert een nieuwe aliasrij op hetzelfde item en de eerdere alias blijft staan. Daarom dragen `items` géén identity-kolommen: een enkelvoudige kolom zou de bestaande alias moeten overschrijven en zou de additieve belofte onmogelijk maken.
- De regel "geen identiteit → geen rij" leeft nu in de opslaglaag: een `items`-rij ontstaat uitsluitend samen met minstens één aliasrij in dezelfde transactie. Een `CHECK` kan dit niet afdwingen (een trigger ziet de latere aliasrij niet); de regel is testbaar via de opslaglaag.
- `source_feed_state` staat bewust níet in `sources`: daarmee blijft de catalogusveldset uit de `source-catalog`-spec ongewijzigd en raakt de ingestie de catalogustabel alleen via een foreign key. Naast de validators bewaart zij de laatste operationele status per bron — één rij per bron, dus geen runhistorie.
- Geen `first_seen_at`/`last_seen_at` op items: een "ongewijzigde run" moet byte-voor-byte geen rij in `items` of `item_identity_aliases` raken. De klok wordt wél gebruikt voor deadlines én voor de operationele tijdstippen in `source_feed_state` (`last_attempt_at`, `last_success_at`); `published_at` is nooit "nu".
- `content_hash` dekt de inhoudsvelden (`title`, `published_at`, `original_url`) en bewust níét de identiteitsvelden: hij mag helpen wijzigingen te herkennen, maar bepaalt nooit of twee items hetzelfde zijn.

**Afgewogen alternatieven**: (a) tabellen zonder versiebump (`CREATE TABLE IF NOT EXISTS` bij de eerste run) → minder ripple, maar breekt de versie-invariant ("welke tabellen horen bij welke versie") en laat `classificeer_database` twee waarheden vertellen; (b) een tweede meta-sleutel naast `schema_version` → twee versie-assen, meer foutbronnen; (c) identity-kolommen op `items` met twee partiele unieke indexen → de klassieke aanpak, maar een gewijzigde GUID zou de kolom moeten overschrijven, waardoor de additieve aliasbelofte en de conflictvrije historie van aliassen verloren gaan. Alle drie afgewezen.

### Beslissing 3: Identiteitsresolutie per kandidaat
**Beslissing**: per feeditem wordt eerst genormaliseerd, daarna wordt binnen de schrijftransactie van die bron in deze volgorde geresolveerd (altijd via de aliastabel, met de bron als deel van elke sleutel):

1. zoek een aliasrij `(source_id, 'external_id', waarde)` (alleen als `external_id` niet `NULL` is) → item A;
2. zoek een aliasrij `(source_id, 'canonical_url', waarde)` (alleen als `canonical_url` niet `NULL` is) → item B;
3. A én B bestaan en A ≠ B → `identity_conflict`: deze kandidaat wordt niet geschreven, niet gemerged, beide items onaangeroerd, teller `conflicted`;
4. precies één van beide bestaat → update van dat item en, wanneer de aliaswaarde nieuw is, een extra aliasrij;
5. geen van beide bestaat → insert van één `items`-rij plus minstens één aliasrij (alleen mogelijk als er minstens één alias is, anders veilig overslaan met teller `overgeslagen`);
6. geen van beide bestaat en er is geen alias → overslaan, geen fout.

Aliassen zijn **additief**: resolven en schrijven voegen een alias toe en verwijderen of overschrijven er nooit een. Een feed die zijn guid tijdelijk niet publiceert, kan zo geen tweede rij veroorzaken; een alias die al aan een *ander* item toebehoort, valt onder regel 3. De samengestelde foreign key uit Beslissing 2 maakt het onmogelijk om een alias aan een item van een andere bron te koppelen.

**Volgorde binnen een run**: kandidaten worden in feedvolgorde verwerkt, met resolutie tegen de live leesstand binnen dezelfde transactie. Twee kandidaten met dezelfde identiteit in één feed komen zo op één item uit (eerste bepaalt de basis, tweede wordt `onveranderd` of `bijgewerkt`). De uitkomst is deterministisch: feedvolgorde.

**Afgewogen alternatieven**: (a) resolven op `contenthash` → faalt bij gewijzigde titels en merge-tegenscenario's, dus expliciet verboden door de spec; (b) globale (niet-brongebonden) identiteit → publicaties die dezelfde guid-structuur delen zouden in elkaar overlopen; (c) merge bij conflict → precies het risico dat de spec uitsluit.

### Beslissing 4: Idempotentie
**Beslissing**: dezelfde feed opnieuw verwerken leidt tot `onveranderd` voor items waarvan `content_hash` gelijk is (geen `UPDATE`-statement, geen geraakte rij), tot een in-place `UPDATE` bij andere inhoud, en nooit tot een tweede itemrij of een tweede alias. Na een geslaagde run is de eindtoestand van `items` en `item_identity_aliases` een pure functie van de feedinhoud. Items die uit de feed verdwijnen blijven staan (geen pruning): een feed die tijdelijk een subset publiceert mag geen data vernietigen. De byte-voor-byte-garantie geldt uitsluitend voor die twee tabellen; de operationele statusvelden in `source_feed_state` (validators, laatste poging, laatste succes, laatste fout) mogen per run veranderen en zijn dus geen onderdeel van de idempotentie.

**Afgewogen alternatief**: (a) first-write-wins (nooit updaten) → eenvoudiger, maar een gecorrigeerde titel of datum blijft dan eeuwig verouderd en "idempotent" wordt in de praktijk "versteend"; afgewezen.

### Beslissing 5: Ophalen, redirects en SSRF
**Beslissing**: één vervangbare `transport.py`-laag met een `HttpTransport`-protocol; de productie-implementatie bouwt op `socket`, `ssl` en `http.client` (stdlib), de testimplementatie is een gescripte fake. Zelfredirects volgen: het transport volgt redirects nooit automatisch maar geeft ze terug aan de runner, zodat de runner per hop kan tellen (maximaal 3), valideren en opnieuw resolven.

Per hop:
1. scheme moet `http` of `https` zijn; geen credentials in de URL;
2. `socket.getaddrinfo` → alle opgeloste adressen controleren met `ipaddress`: alleen `is_global`-unicastadressen, expliciet weg voor privé-, loopback-, link-local-, multicast-, reserved-, unspecified- en unieke-IPv6-adressen, inclusief het ontrafelen van IPv4-mapped-IPv6 (`::ffff:127.0.0.1`);
3. verbinden met het **gevalideerde adres**, terwijl Host-header en TLS-SNI de oorspronkelijke hostnaam behouden → er is geen moment waarop tussen validatie en connectie een andere host kan worden opgelost (DNS-rebinding-TOCTOU dicht);
4. aparte timeouts: 5 s voor het verbinden, 10 s per leesoperatie, 30 s totaalbudget per bron (afgedwongen met de injecteerbare klok); het overschrijden van dat budget stopt de bron onmiddellijk met `source_timeout` — geen verdere pogingen, geen schrijfactie;
5. lichamen worden stroomgewijs gelezen en bij 2 MiB afgebroken met `body_too_large`; pas daarna wordt geparseerd;
6. voor `https` wordt de TLS-handshake en de certificaat- en hostnaamvalidatie expliciet gecontroleerd; een mislukking levert `tls_failure` op, zonder herhaling en zonder schrijfactie. `connect_timeout` en `read_timeout` blijven de codes voor een uitgevallen verbindings- respectievelijk leesoperatie binnen één poging.

**Afgewogen alternatieven**: (a) `urllib.request` met automatische redirects → kan per hop niet valideren, kent één timeout en pinnt het adres niet; (b) een nieuwe dependency (`requests`, `httpx`) → niet als directe runtime-afhankelijkheid gepind in `backend/requirements.txt`, en de library kan adressenpinning niet afdwingen; (c) `feedparser` voor het hele ophaalpad → mengt netwerk en parsing.

### Beslissing 6: Retries en conditionele requests
**Beslissing**: de runner doet maximaal 3 pogingen per bron (1 + 2 herhalingen) met vaste backoff 0,5 s en 1 s via de injecteerbare slaapvoorziening, uitsluitend bij verbindings-/leestimeouts, verbreekfouten en HTTP 429/502/503/504. Alles andere faalt direct, waaronder `source_timeout` (harde brondeadline, dus geen tijd meer voor een herhaling) en `tls_failure` (configuratie-/certificaatprobleem dat een herhaling niet oplost), naast overige 4xx/5xx, `parse_error`, `blocked_address`, `too_many_redirects`, `too_many_items`, `body_too_large` en databasefouten. Bekende `ETag`/`Last-Modified` gaan als `If-None-Match`/`If-Modified-Since` mee; `304` betekent `not_modified`: geen parse en geen itemtransactie — uitsluitend validators en de operationele bronstatus worden in een afzonderlijke, kleine transactie bijgewerkt (Beslissing 9). Bij een `200` worden validators én de successstatus in dezelfde itemtransactie geschreven, samen met de items (Beslissing 8 en 9).

### Beslissing 7: Parser en normalisatie zonder nieuwe dependencies
**Beslissing**: een strikte, namespace-bewuste subset-parser op `xml.etree.ElementTree` voor RSS 2.0, RSS 1.0/RDF en Atom 1.0, met een voorafse controleregel die `DOCTYPE`/`ENTITY`-declaraties weigert (billion-laughs-/XXE-afweer) en een itemlimiet van 500 voor het parsen. Elementkeuze: RSS `item/guid` (met `isPermaLink`), Atom `entry/id` en `link[rel=alternate|geen rel]`; titel `title`/`title`+`type=text`; datum RSS `pubDate`/`dc:date` via `email.utils.parsedate_to_datetime`, Atom `published`/`updated` via `datetime.fromisoformat`.

Normalisatie met `urllib.parse`: relatieve links oplossen tegen de `feed_url`, fragment verwijderen, query behouden, daarna dezelfde canonicalisatiestappen als de catalogus (lowercase scheme/host, IDNA, standaardpoort weg, leeg pad `/`, dot-segmenten oplossen) — met één bewust verschil: bij itemlinks worden fragmenten en dot-segmenten *verwijderd/opgelost* in plaats van geweigerd, zoals de spec voorschrijft. Datums: timezone-aware → UTC (`+00:00`), tijdzoneloos/ongeldig/ontbrekend → `NULL`; `content_hash` = SHA-256 over de genormaliseerde inhoudsvelden.

**Afgewogen alternatieven**: (a) `feedparser` als dependency → breedste dekking, maar een nieuwe pinned runtime-afhankelijkheid en een extra supply-chain-items voor een persoonlijke, gecontroleerde bronnenset; (b) handmatige datumparser → onnodig, `email.utils` dekt RFC 822/1123. Wanneer echte feeds later consequent `parse_error` geven, kan de parserachter hetzelfde contract worden vervangen zonder de specs of taken te wijzigen (zie Open Questions).

### Beslissing 8: Transacties en foutafhandeling
**Beslissing**: per bron vier stappen met een expliciete transactiesemantiek: (1) ophalen + redirect-/SSRF-/TLS-afhandeling buiten de database; (2) parsen en normaliseren buiten de database; (3) resolven + schrijven van items en aliassen in één `BEGIN IMMEDIATE`-transactie met `PRAGMA foreign_keys=ON` via de bestaande connectiecontext — inclusief de successstatus en de validators bij een `200`, zodat die atomair met de items tot stand komen; (4) registratie van de operationele bronstatus in een afzonderlijke, kleine transactie, uitsluitend voor een `304` en voor alle foutuitkomsten (Beslissing 9). Een fout in fase 1 of 2 betekent `ROLLBACK`-loos geen schrijfactie aan `items` of `item_identity_aliases`; een fout in fase 3 draait die tabellen terug naar de situatie vóór die bron en neemt de successstatus van die run mee terug, terwijl de foutstatus van fase 4 daarbuiten blijft en de mislukking vastlegt. De runner vangt alle excepties op en mapt ze op één code uit de gesloten set uit de spec; onbekende/uitzonderlijke fouten worden `db_unavailable`-achtig afgevangen als databasegerelateerd of als algemene `parse_error`-vanger — in alle gevallen geldt: geen SQL-tekst, geen stacktrace, geen pad, geen credentials, geen antwoordlichaam in de uitvoer. Wanneer de database zelf onbereikbaar is kan de statusregistratie niet slagen: de CLI-uitvoer en de exitcode blijven dan leidend en de statusregistratie wordt overgeslagen zonder herstelcircus. De volledige run zet één fout bij één bron niet stop: de overige bronnen draaien door en de exitcode wordt `1`.

**Afgewogen alternatieven**: (a) één transactie over alle bronnen → atomiciteit over de hele run, maar één slechte bron laat dan niets achter en schaadt de "fout per bron"-belofte; (b) statusregistratie uitsluitend in een aparte transactie, ook bij een `200` → twee writes per bron en een successstatus die na een rollback van fase 3 kan blijven staan terwijl er niets geschreven is; afgewezen; (c) statusregistratie in dezelfde transactie, ook bij fouten → dan rolt een mislukte schrijffase de melding van de mislukking terug en verdwijnt de fout juist wanneer zij het hardst nodig is; afgewezen. De gekozen mix (successatomair, fouten apart) dekt beide bezwaren.

### Beslissing 9: Per-bron operationele status in `source_feed_state`
**Beslissing**: per bron wordt uitsluitend de *laatste* status bewaard (één rij per bron, geen runhistorie) naast de validators: `last_attempt_at`, `last_success_at`, `last_error_code`, `last_error_detail` (gesaneerd: geen SQL, stacktrace, pad, credentials of antwoordlichaam; hard begrensd op 200 tekens), `last_http_status` en `consecutive_failures`. Semantiek per uitkomst:

- **200 met verwerking**: in dezelfde per-bron itemtransactie worden validators, `last_attempt_at` en `last_success_at` bijgewerkt, de foutvelden gewist en `consecutive_failures` op 0 gezet;
- **304 `not_modified`**: kleine eigen transactie — `last_attempt_at` en `last_success_at` bijwerken, foutvelden wissen, `consecutive_failures` op 0, validators ongewijzigd, item- en aliastabellen onaangeroerd;
- **ophaal-, parse- of schrijffout**: kleine eigen transactie ná de mislukking — `last_attempt_at`, `last_error_code`, `last_error_detail`, `last_http_status` (indien van toepassing) en `consecutive_failures + 1`, waarbij de item- en aliastabellen onaangeroerd blijven;
- **selectiefouten** (`unknown_source`, `source_inactive`, `unsupported_type`): geen statuswijziging, alleen rapportage, conform "niets geschreven";
- **databasefout**: geen eis op persistente status; rapportage gebeurt via uitvoer en exitcode.

`not_modified` is een status, geen foutcode: het woord komt niet voor in de gesloten foutcodeset en telt niet mee voor de exitcode. De statusvelden staan buiten de idempotentie (Beslissing 4) en vallen onder de offline teststrategie (Beslissing 11).

**Afgewogen alternatief**: (a) een runhistorietabel met één rij per run → zou "geen persistente importgeschiedenis" schenden en onbeperkt groeien; (b) status uitsluitend in de uitvoer → voldoet aan de rapportage-eis maar laat de laatste fout verdwijnen zodra de terminal dicht is; in combinatie gekozen: uitvoer blijft leidend, de laatste staat wordt daarnaast persist vastgelegd.

### Beslissing 10: Numerieke ontwerpdefaults
| Grens | Waarde | Motivatie |
| --- | --- | --- |
| Connect-timeout | 5 s | lang genoeg voor trage CDN's, kort genoeg om één bron niet het hele commando te laten blokkeren |
| Leestimeout | 10 s per operatie | feeds zijn klein; 10 s vangt haperingen zonder onbeperkt wachten |
| Budget per bron | 30 s | bound op de totale run (~10 actieve bronnen ≈ 5 min incl. backoff); overschrijding stopt de bron met `source_timeout` |
| Redirects | 3 | http→https en www-omleidingen dekken de praktijk; meer wijst op een loop of omleiding |
| Reactielichaam | 2 MiB | reële feeds zitten ruim onder 1 MiB; begrenst geheugen én parser-uitbreiding |
| Items per feed | 500 | nieuwssites publiceren zelden >200 items per run; marge + bound op parse- en transactietijd |
| Pogingen | 3 (1 + 2) | vangt een korte 503-oplaging, blijft binnen het budget |
| Backoff | 0,5 s en 1 s | korte, vaste wachttijden; volledig injecteerbaar, dus kost niets in tests |
| Foutdetail | 200 tekens | houdt ruimtelijke foutteksten en eventuele antwoordresten buiten de database |
| Tijdlijnen | ISO-8601 UTC | `last_attempt_at`/`last_success_at` delen hetzelfde formaat als `published_at` |

Alle waarden staan als vaste, testbare grenzen in `specs/rss-ingestion/spec.md`; ze zijn bewust configuratievrij gehouden (een omgevingvariërbel erbij zou de tests en de specs fragmenteren).

### Beslissing 11: Teststrategie
**Beslissing**: drie testlagen, allemaal offline:
1. **Pure eenheidstests** — gouden tabellen voor URL-normalisatie, datumnormalisatie, identiteitsresolutie en foutmapping (klok/slaap/transport zijn hier nog niet nodig).
2. **Ketenstests met fakes** — een `FakeTransport` met gescripte responsen per URL (status, headers, lichaam, redirects, excepties), een `FakeClock` voor het 30 s-budget en een slaap-recorder; XML-fixtures in `backend/tests/fixtures/feeds/` met uitsluitend `example.com`/`example.org` en verzonnen tekst (RSS 2.0, RDF, Atom, lege feed, te grote feed, 501 items, defecte XML). Hierin horen ook de statussen: 200 wist een eerdere fout, 304 wist de foutstatus zonder itemtransactie, een ophaalfout legt code + teller vast, het foutdetail blijft binnen 200 tekens en er blijft per bron één statusrij bestaan.
3. **CLI- en regressietests** — exitcodes, uitvoervolgorde (inclusief de statusset `ok`/`not_modified`/`fout`), migratie 1/2/3 + noop + weigering + rollback, en een regressie dat de vijf catalogusroutes en `/health` exact ongewijzigd zijn gebleven (ook met itemdata in de database). Idempotentietests vergelijken `items` en `item_identity_aliases` byte-voor-byte en negeren de operationele statusvelden.

De bestaande `socket_guard` blijft de harde grens: de nieuwe testmodules worden aan `OFFLINE_MODULES` in `backend/tests/test_source_offline.py` toegevoegd, zodat de dekkingscontrole en de strenge sweep ook over de ingestie lopen. Elke test die een exception raise't door een geblokkeerde socket telt als mislukking, niet als skip (bestaande sessie-regel blijft gelden).

**Afgewogen alternatief**: (a) één integrationstest met een lokale `http.server` → oefent de socket-laag wel uit, maar faalt onder de socket-guard-regel en maakt tests langzamer; alleen toegestaan als latere aanvulling, niet als dekking van de kern.

### Beslissing 12: Extern netwerk, datastromen, kosten, LLM
- **Extern netwerk**: alleen uitgaand HTTP(S) vanaf de eigen machine, uitsluitend wanneer `python -m app.rss_ingest` handmatig wordt gestart, alleen naar `feed_url`-waarden uit de lokale catalogus en hun redirects, uitsluitend naar publieke adressen. Geen inbound verkeer, geen webhooks, geen polling.
- **Datastromen**: catalogus (lokaal) → GET-verzoek (URL, `User-Agent`, `Accept`, optionele `ETag`/`Last-Modified`) → feed-body (max 2 MiB) → itemmetadata → `items`- en `item_identity_aliases`-tabellen plus de laatste bronstatus in `source_feed_state` in `news.db`. Er verlaat geen enkele rij de database; er wordt niets doorgestuurd.
- **Kosten**: €0. Geen accounts, geen API-sleutels, geen betaalde diensten; alleen eigen bandbreedte. Geen extra services of volumes in `compose.yaml`.
- **LLM/providers**: geen. Er wordt niets gegenereerd, geclassificeerd of gerankt; er is geen providerkeuze en geen prompt.

## Risks / Trade-offs

- [SSRF via redirect of DNS-rebinding] → per-hop hercontrole, alleen `is_global`-adressen, verbinden op het gevalideerde adres met behoud van Host/SNI, maximaal 3 redirects, tests met privé/loopback/link-local/multicast-voorbeelden.
- [Subset-parser dekt echte feeds onvoldoende] → per bron `parse_error` zonder gevolgen voor andere bronnen; fixtures dekken de drie formaten; parser is achter één contract vervangbaar zonder specwijziging.
- [Conflictmelding blokkeert geen items maar wel de exitcode] → de teller is expliciet in de uitvoer, gebruiker ziet het verschil tussen "fout" en "conflict"; geen stilzwijgende merge.
- [Schema-ripple naar versie 3] (`source_seed`-versiecheck, migratietests, documentatie) → één additieve statementset, versie pas na succes, expliciete noop-/weiger- en rollbackszenariën in de taken, backup vóór de migratie.
- [Begrenzingen wijzen geldige grote feeds af] → expliciete codes `body_too_large`/`too_many_items` in plaats van stilzwijgende truncatie; waarden zijn als ontwerpdefault in de spec vastgelegd en dus aanpasbaar via een nieuwe change.
- [Handmatig commando wordt vergeten] → bewuste keuze voor deze change (geen scheduler); een latere change kan dit just-in-time oppakken.
- [Adressenpinnning maakt de transportlaag complexer dan `urllib`] → de laag is klein, achter een protocol afgeschermd en volledig door fakes vervangen in tests.
- [Statusvelden veranderen bij elke run en breken dan de byte-voor-byte-garantie] → de garantie is expliciet beperkt tot `items` en `item_identity_aliases` (Beslissing 4); idempotentietests negeren de statusvelden, statussen hebben eigen testen (Beslissing 11).
- [Een databasefout voorkomt de persistente status] → bewust geaccepteerd: uitvoer en exitcode blijven leidend, de registratie wordt overgeslagen zonder herstelcircus (Beslissing 8).

## Migration Plan

1. **Vooraf**: niet-destructieve backup via `scripts/db-rollback.sh` (pre-migratie-v2-stand bewaren).
2. **Deploy**: code uit deze change op de bestaande backend-container; geen nieuwe services, geen nieuwe omgevingssleutels.
3. **Migratie**: `python -m app.db_migrate` handmatig uitvoeren (de ingestiecli migreert niet automatisch); verificatie: versie 3, `PRAGMA integrity_check = ok`, `PRAGMA foreign_key_check` leeg, catalogusdata ongewijzigd.
4. **Eerste run**: `python -m app.rss_ingest` op een enkele actieve bron, daarna alle actieve bronnen; foutcodes per bron beoordelen.
5. **Verificatie**: volledige backend-suite offline, plus een handmatige controle dat `GET /api/sources` en `GET /health` exact ongewijzigd zijn.
6. **Rollback**: code revert + herstel van de pre-migratie-v2-backup wanneer de oude code weer moet draaien (die weigert versie 3); alternatief zonder restore: nieuwe code laten staan en de v3-tabellen ongebruikt laten. Zie `proposal.md` (Rollback).

## Open Questions

- Moeten er in een latere change item- of importroutes (`GET /api/items`, importstatus) komen? Nu expliciet buiten scope; beslissen nadat de eerste imports in de praktijk zijn bekeken (raakt alleen een latere specdelta, niet dit ontwerp).
- Volstaat de subset-parser voor alle catalogusbronnen in de praktijk, of is een zwaardere parser gewenst? Pas beslissen op basis van echte `parse_error`-meldingen; het transport-/parsercontract en de foutcodes blijven dan gelijk.
