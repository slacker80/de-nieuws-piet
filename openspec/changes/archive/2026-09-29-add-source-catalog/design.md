# Design

## Context

Zie proposal.md (Why) voor de motivatie. Deze change bouwt voort op de bestaande backend: een FastAPI app-factory (`create_app()`), een SQLite-bootstrap op schema-versie 1 (`app_meta`, `bootstrap_marker`) met een connectie-per-operatie zonder pooling, en een exact `/health`-contract met test-only fault injection. De database leeft op `APP_DB_PATH` / `/app/data/news.db` in named volume `nieuws_piet_sqlite_data`; backup en restore lopen via het bestaande `scripts/db-rollback.sh`-proces. De catalogus voegt daar een nieuw v2-datamodel, validatielogica, vier beheerroutes en één opties-route aan toe, zonder de bestaande modules qua gedrag te raken.

## Goals / Non-Goals

**Goals:**
- Een relationeel, uitsluitend lokaal datamodel voor publicatiekanalen met de velden uit de delta-spec.
- Deterministische, offline URL-validatie en canonicalisatie met een afgeleide `feed_url_key` als enige unieke sleutel.
- Transactionele, versiegestuurde migratie v1 → v2 met rollback bij falen.
- Vier beheerroutes plus één opties-route met de foutsemantiek 404/409/422/503.
- Een expliciete, idempotente, offline seed voor vooraf handmatig beoordeelde startbronnen.

**Non-Goals (designniveau):**
- Geen verandering aan `health.py`, het `/health`-contract, de fault-injectionconfiguratie of de healthtests.
- Geen feed-ophaling, scraping, artikelen, samenvattingen, ranking, LLM, scheduler, notificaties of externe opslag.
- Geen frontend-werk, geen aanpassing van `scripts/db-rollback.sh` (alleen verificatie dat het proces met v2-data werkt).
- Geen nieuwe externe Python-afhankelijkheden.

## Decisions

### Beslissing 1: Datamodel
**Beslissing**: Vier tabellen, aangebracht in één additieve migratie:

```sql
CREATE TABLE sources (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL CHECK (length(trim(name)) > 0),
    feed_url      TEXT    NOT NULL,          -- oorspronkelijke URL, alleen getrimd
    feed_url_key  TEXT    NOT NULL,          -- afgeleide canonieke sleutel
    website_url   TEXT,                      -- optioneel, oorspronkelijke waarde
    type          TEXT    NOT NULL CHECK (type IN ('rss', 'atom')),
    language      TEXT    NOT NULL CHECK (language <> '' AND language = lower(language)),
    reliability   INTEGER CHECK (reliability IS NULL
                                 OR (typeof(reliability) = 'integer'
                                     AND reliability BETWEEN 1 AND 5)),
    is_active     INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1))
);

CREATE UNIQUE INDEX ux_sources_feed_url_key ON sources (feed_url_key);
CREATE INDEX ix_sources_is_active   ON sources (is_active);
CREATE INDEX ix_sources_website_url ON sources (website_url);

CREATE TABLE topics (
    slug TEXT PRIMARY KEY,                   -- stabiele slug, nooit hernoemd
    name TEXT NOT NULL
);

CREATE TABLE source_topics (
    source_id  INTEGER NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
    topic_slug TEXT    NOT NULL REFERENCES topics (slug),
    PRIMARY KEY (source_id, topic_slug)
);
CREATE INDEX ix_source_topics_slug ON source_topics (topic_slug);

CREATE TABLE source_cloud_labels (
    source_id   INTEGER NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
    cloud_label TEXT    NOT NULL
                    CHECK (cloud_label IN ('azure', 'aws', 't-cloud',
                                           'otc', 'multi-cloud', 'sovereign-cloud')),
    PRIMARY KEY (source_id, cloud_label)
);
CREATE INDEX ix_source_cloud_labels_label ON source_cloud_labels (cloud_label);
```

**Redenering**:
- `feed_url` bewaart de oorspronkelijke, getrimde invoer voor weergave en audit; `feed_url_key` is de canonieke afgeleide en draagt de `UNIQUE`-index. Die index is bewust niet-gedeeltelijk: uniekheid geldt over actieve én inactieve bronnen.
- `website_url` krijgt géén sleutel en géén unique index: meerdere kanalen mogen dezelfde website delen; de index op `website_url` is alleen een zoekindex.
- Cloudlabels staan als kolom met `CHECK` in de koppeltabel; er is bewust geen losse lookup-tabel nodig omdat de set exact en klein is en de opties-route de set uit code levert.
- `topics` is wél een tabel: de woordenlijst is de autoriteit voor validatie van `source_topics.topic_slug` via de FK.
- Booleans expliciet op app-niveau weigeren vóór binding: SQLite zou `True` als integer `1` opslaan en daarmee de `BETWEEN 1 AND 5`-check passeren.

**Alternatieven overwogen**:
- JSON-array in `sources` voor relaties: geen FK-integriteit, geen eenvoudige filter queries.
- Losse `cloud_labels`-lookuptabel: extra tabel zonder voordeel, want de set is vastgelegd in de `CHECK`.

**Verplichting per verbinding**: elke verbinding voert direct na openen `PRAGMA foreign_keys=ON` uit (in de bestaande `connect()`-contextmanager), zodat FK-integriteit niet afhangt van de standaardwaarde 0 van SQLite.

### Beslissing 2: URL-validatie met de Python standaardbibliotheek
**Beslissing**: Parsing en heropbouw via `urllib.parse` uit de Python standaardbibliotheek; validatie- en canonicalisatieregels worden in één zuivere functie (`canonicalize_url`) toegepast die een `feed_url_key` teruggeeft of een validatiefout opwerpt.

**Redenering**: `urllib.parse` is onderdeel van de standaardbibliotheek en levert daarmee een parser zonder enige nieuwe dependency, precies wat de scope eist. De regels uit de delta-spec worden expliciet toegevoegd rondom de parser, omdat `urlsplit` zelf geen van deze garanties geeft:

1. Buitenste whitespace trimmen; daarna elke resterende controle of whitespace en elke backslash weigeren.
2. `urlsplit`; scheme moet exact `http` of `https` zijn (na lowercase), anders weigeren (geen automatische upgrade).
3. `netloc`: `@` (credentials) weigeren; host verplicht en niet leeg; poort numeriek 1..65535 (fout → weigeren).
4. Host deterministisch IDNA-normaliseren: elk label afzonderlijk via de ingebouwde IDNA-codec (nameprep + ToASCII) omzetten en daarna lowercase, met heropbouw van het hostdeel; een Unicode-fout betekent weigeren. Dezelfde invoer levert altijd exact dezelfde sleutel op en er wordt geen DNS of netwerk bij gebruikt.
5. Standaardpoort 80/443 voor het respectieve scheme verwijderen; andere poorten behouden.
6. Leeg pad → `/`; padhoofdletters, niet-lege trailing slash en overige percent-encoding ongewijzigd laten; dot-segmenten (`.` en `..` als padsegment) weigeren in plaats van op te lossen.
7. Vervolgensequenties `%` moeten exact op `%[0-9A-Fa-f]{2}` passen; anders weigeren.
8. Fragment weigeren; query ongewijzigd (volgorde en waarden) overnemen.
9. Herbouwen met `urlunsplit`; nooit `requests`, `httpx`, sockets of redirectlogica aanroepen.

**Alternatieven overwogen**:
- Externe canonicalisatielibrary (bijv. `rfc3986`): die voegt een nieuwe runtime-afhankelijkheid toe, tegen de scope in.
- Eigen handgeschreven tokenizer: meer kans op afwijking van RFC-gedrag zonder voordeel.
- Canonicaliseren met netwerkcontrole (DNS/redirects): tegen de offline-eis.

### Beslissing 3: Migratie v1 → v2
**Beslissing**: Eén versiegestuurde, transactionele migratie met de volgende stappen:

1. `PRAGMA foreign_keys=ON` op de verbindingscontext.
2. `app_meta.schema_version` lezen.
   - `1` (of ontbrekend op een bootstrap-database) → doorgaan naar stap 3.
   - `2` → noop: niets doen, geen enkele schrijfactie.
   - hoger dan 2 of onbekend → weigeren met een fout, zonder een enkele schrijfactie.
3. `BEGIN IMMEDIATE` (write-lock vroeg vastleggen).
4. De vier tabellen en indexen aanmaken met `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`.
5. Woordenlijst `topics` vullen met `INSERT OR IGNORE` uit de vaste, in code vastgelegde slug-set.
6. `PRAGMA foreign_key_check` uitvoeren; resultaatrijen betekenen rollback.
7. Als laatste stap binnen dezelfde transactie `schema_version` op `2` zetten — de versie wordt dus pas na succes van elke voorgaande stap vastgelegd.
8. `COMMIT`; bij elke fout `ROLLBACK`, waarna de versie 1 blijft en er geen half aangelegde tabellen bestaan.

**Redenering**: DDL is in SQLite transactieel, dus versie en schema zijn atomair. Een falende migratie laat de database exact in de v1-toestand achter; een opnieuw uitvoeren is daardoor veilig.

**Alternatieven overwogen**:
- Versie eerst verhogen: zou een gefaalde migratie als succes markeren.
- Losse DDL zonder transactie: kans op half aangelegde tabellen.

### Beslissing 4: Concurrency en foutmapping
**Beslissing**: Writes (`POST`, `PATCH`, seed) lopen in één transactie met `BEGIN IMMEDIATE`; de bestaande `busy_timeout` van 5 seconden vangt lees-schrijfconflicten op. Onder de motorkap is de `UNIQUE`-index de autoriteit: `sqlite3.IntegrityError` op `ux_sources_feed_url_key` wordt gemapt naar HTTP 409, `sqlite3.OperationalError` (onbereikbaar/locked buiten de timeout) naar een begrensde HTTP 503 met een vaste, generieke melding. Validatiefouten zijn 422, onbekende id 404. Foutbodies bevatten uitsluitend vaste, in code vastgelegde teksten: geen SQL, geen stacktrace, geen paden; details gaan alleen naar de serverlog.

**Redenering**: Dubbele schrijvers omzeilen nooit de database-uniekheid, ook niet als de applicatiecontrole zou worden overgeslagen. De begrensde 503 voorkomt dat er onbegrensd wordt herprobeerd.

**Alternatieven overwogen**: Alleen applicatierij-controle (racegevoelig), of een apart slot per record (overbodig bij één lokale schrijver).

### Beslissing 5: API-oppervlak
**Beslissing**: Eén nieuwe router met exact deze routes: `GET /api/sources`, `GET /api/sources/{id}`, `POST /api/sources`, `PATCH /api/sources/{id}` en `GET /api/source-options`. Filters zijn `is_active`, `topic` en `cloud_label`, gecombineerd met AND; de lijstrespons bevat altijd de volledige catalogus in één antwoord, standaard inclusief inactieve bronnen en gesorteerd op oplopend `id`. De opties-route keert in één respons de onderwerpen (uit `topics`), de typen `rss`/`atom`, het taalbeleid en de cloudlabels terug. Validatieregels (enum, taal, betrouwbaarheid, woordenlijsten, URL-regels) worden vóór de schrijfactie op de hele eindtoestand toegepast, inclusief bij PATCH.

**Redenering**: Eén opties-route houdt het oppervlak minimaal en voorkomt aparte CRUD-routes voor woordenlijsten. Volledige lijst in één antwoord past bij de omvang van een persoonlijke catalogus en bij de eis om het antwoord niet in delen te leveren.

**Alternatieven overwogen**: aparte opties-routes per woordenlijst, upsert-semantiek bij POST, of PATCH die alleen de opgegeven relaties wijzigt — alle drie in strijd met de delta-spec.

### Beslissing 6: `app.state.db_path`-isolatie
**Beslissing**: De repositories en de validatielaag lezen het databasepad uitsluitend uit `app.state.db_path` (via een FastAPI-afhankelijkheid), nooit uit een moduleglobale variabele of direct uit `os.environ`. De seed-operatie en de migratiefunctie krijgen het pad als expliciete parameter, met `APP_DB_PATH` alleen als terugvaloptie.

**Redenering**: `create_app(db_path=...)` levert zo een volledig geïsoleerde instance: twee applicaties met verschillende paden delen geen data, wat tests en fault-injection veilig houdt. Het bestaande gedrag van `create_app()` en de healthservice blijft ongewijzigd.

**Alternatieven overwogen**: een moduleglobale verbinding of gedeelde pool — breekt app-factory-isolatie en de testreset.

### Beslissing 7: Seed is een expliciete operatie, geen schema-migratie
**Beslissing**: De seed leest een lokaal, in de repo opgenomen JSON-bestand met de vooraf handmatig beoordeelde officiële startbronnen en voert per entry een insert-if-absent uit op `feed_url_key` binnen één transactie: ontbrekende starters worden toegevoegd, bestaande records worden nooit geüpdatet. De operatie wordt aangeroepen via een expliciet, handmatig gestart entrypoint (CLI-module of testoproep) en is bewust **niet** gekoppeld aan de lifespan van de app, aan `create_app()` of aan de migratiestap. Ze opent geen sockets en volgt geen URL's; de seed is dus geen schema-migratie en vindt niet tijdens de applicatie-start plaats.

**Redenering**: Idempotent insert-only gedrag maakt herhaling veilig en bewaart gebruikerswijzigingen. Loshouden van de migratie betekent dat schema en inhoud onafhankelijk evolueren en dat een start van de applicatie de catalogus nooit stilzwijgend aanvult.

**Alternatieven overwogen**: seed als onderdeel van de schema-migratie (inhoud en schema vermengd), of opvullen bij het eerste verzoek (verborgen schrijfactie tijdens runtime).

**Beoordelingscriteria voor de starterset**: uitsluitend officiële publicatiekanalen bij de onderwerpen uit de projectconfiguratie, met een feed-URL die de validatieregels doorstaat, handmatig beoordeeld en vastgelegd vóór opname. De exacte set en de exacte URL's worden tijdens de implementatiereview van de seed-taak vastgesteld; dat is een reviewtaak, geen open ontwerpbesluit, en er worden in dit document geen onbevestigde URL's genoteerd.

### Beslissing 8: Geen uitbreiding van `/health`
**Beslissing**: `health.py`, de fault-injectionconfiguratie, de componentenlijst (`backend`, `sqlite`) en de JSON-contracten blijven exact zoals ze zijn. De catalogus voegt geen component, geen check en geen veld toe. Het enige werk is een regressietest die het bestaande contract ook met een gemigreerde, gevulde catalogusdatabase vastlegt.

**Redenering**: Uitbreiding van het health-contract zou de bestaande healthspec en de vijf exacte benoemde healthtests raken, wat buiten deze change valt.

## Risks / Trade-offs

- [Risk] Canonicalisatie wijkt af van wat een externe tool later verwacht → [Mitigation] Gouden testtabel met de voorbeelden uit de delta-spec plus extra randgevallen; één pure functie als enige implementatiepad.
- [Risk] Twee schrijvers tegelijk met dezelfde feed-URL → [Mitigation] Unieke index op databaseniveau plus `BEGIN IMMEDIATE`; `IntegrityError` → 409; concurrencytest.
- [Risk] Migratie faalt halverwege op de named volume → [Mitigation] Backup vóór de migratie via het bestaande rollback-proces; alles in één transactie; versie pas na succes.
- [Risk] Seed overschrijft gebruikerswerk → [Mitigation] Insert-if-absent, nooit updaten; herhaaltest met een handmatig gewijzigd record.
- [Risk] Woordenlijst en opties-route lopen uiteen → [Mitigation] Beide lezen uit dezelfde code-constanten en de `topics`-tabel; één test vergelijkt de opties-response met de geldige waarden.
- [Risk] Validatie lekt SQL of paden naar de client → [Mitigation] Vaste foutbodies, centrale foutafhandeling, test die op SQL-tekst en paden controleert.
- [Risk] Betrouwbaarheidsvalidatie te soepel omdat boolean in Python een integertype is → [Mitigation] Expliciete typecontrole vóór binding en randgevalstests.

## Migration Plan

1. **Backup**: niet-destructieve backup via het bestaande `scripts/db-rollback.sh`-proces vóór de eerste uitvoering op een echte database.
2. **Schema**: transactionele migratie v1 → v2 volgens Beslissing 3; `PRAGMA foreign_key_check` en `PRAGMA integrity_check` na afloop.
3. **Code**: validatielaag, repositories en router toevoegen; bestaande modules alleen uitbreiden met de verbindingsoptie `PRAGMA foreign_keys=ON`, zonder gedragswijziging voor `/health`.
4. **Seed**: na de review van de starterset de expliciete seed uitvoeren; optioneel en herhaalbaar, nooit automatisch.
5. **Verificatie**: volledige testsuite, inclusief de regressietest op exact `/health`, offline-checks en backup/restore met v2-catalogusdata.
6. **Rollback**: code en database worden als één compatibele set teruggezet: de codewijziging reverten én de gevalideerde pre-migratie-v1-backup herstellen via de bestaande data-safe procedure (`PRAGMA integrity_check` = `ok` vereist vóór elke restore). Er wordt geen aanspraak gemaakt op het veilig negeren van v2-tabellen door v1-code: de bestaande bootstrap-v1-code schrijft bij init `schema_version` terug naar `1`, dus de oude code tegen de v2-database starten geeft een onondersteunde code/schema-combinatie en een valse versie-marker. Wie latere cataloguswijzigingen wil behouden, maakt vóór de restore eerst een kopie van de actuele v2-database; zonder die kopie gaan die wijzigingen bij het herstel verloren. Na het herstel worden `schema_version` 1, `PRAGMA integrity_check`, de bootstrap-data-marker en exact `GET /health` geverifieerd.

## Open Questions

Geen. Alle ontwerpbeslissingen in dit document zijn genomen en de delta-spec legt het gedrag vast. De exacte officiële starterset wordt vastgesteld tijdens de implementatiereview van de seed-taak en is een reviewtaak, geen open ontwerpbesluit.
