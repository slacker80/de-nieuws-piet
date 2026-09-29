# Proposal

## Why

De broncatalogus bevat inmiddels actieve RSS- en Atom-kanalen, maar de backend heeft nog geen enkele manier om de items uit die feeds lokaal op te slaan: `backend/app` bevat geen itemtabellen, geen HTTP-ophaling, geen feedparser en geen datumnormalisatie. Zonder die eerste, handmatige ingestiestap kan de kwaliteitsregel "geen duplicaten bij herhaalde imports" en de verplichting dat elke samenvatting bronlink en datum draagt, niet worden waargemaakt.

## What Changes

- **Nieuwe capability `rss-ingestion`**: een handmatig gestart CLI-commando (`python -m app.rss_ingest`, met `main(argv) -> int`) dat de actieve catalogusbronnen (`is_active`, `type` `rss` of `atom`) ophaalt en de items idempotent in SQLite zet. Geen scheduler, geen API-route voor ingestie in deze change.
- **Datamodel**: drie additieve tabellen — `items` (itemmetadata), `item_identity_aliases` (genormaliseerde, brongebonden identity-aliassen met `UNIQUE(source_id, alias_type, alias_value)` en een foreign key die alias en item op dezelfde bron vastspijkeren) en `source_feed_state` (feed-validatoren `ETag`/`Last-Modified` plus de laatste operationele bronstatus); een additieve, transactionele migratie naar schema-versie 3.
- **Identiteit en deduplicatie**: hetzelfde bronitem wordt per bron maximaal eenmaal opgeslagen; identity-aliassen worden als aparte rijen bewaard en zijn additief (een gewijzigde GUID of item-URL voegt een alias toe; de eerdere alias blijft behouden); `contenthash` is alleen een wijzigingsindicatie en nooit primair identiteit; candidates die naar twee verschillende bestaande items wijzen leveren een conflict zonder merge; een item zonder bruikbare identiteit wordt veilig overgeslagen.
- **Normalisatie**: GUID/Atom-id of canonical item-URL, titel, publicatiedatum (timezone-aware naar UTC; ongeldig of tijdzoneloos wordt `NULL`, nooit "nu"), bron en originele link; relatieve itemlinks worden opgelost, fragmenten verwijderd, query behouden.
- **Ophaling met begrenzingen**: begrensde verbindings- en leestimeouts, een harde brondeadline van 30 seconden per bron, body-/itemlimieten, maximaal 3 redirects met SSRF-hercontrole per hop, uitsluitend publieke adressen, retries uitsluitend bij transient fouten, conditionele `ETag`/`Last-Modified` met `304`-afhandeling, netwerk buiten de database-transactie en een atomair transcript per bron.
- **Fouten per bron**: stabiele, gesaneerde bronfoutcodes (geen SQL-tekst, stacktraces, lokale paden of credentials) in de CLI-uitvoer, met exitcode 0/1, plus de laatste operationele status per bron in de database (laatste poging, laatste succes, foutcode, HTTP-status, begrensd foutdetail en opeenvolgende mislukkingen) — één statusrij per bron, dus geen runhistorie. `not_modified` is een status, geen foutcode.
- **Tests**: uitsluitend synthetische lokale XML-fixtures met een fake transport-, clock- en sleep-laag; het bestaande socket-guard-principe blijft gelden: geen live internet in tests.
- **Delta op `source-catalog`**: expliciete afbakening (de catalogus zelf blijft offline; itemophaling en -opslag vallen uitsluitend onder `rss-ingestion`), de migratie-eis wordt bijgewerkt naar additief `1`/`2` → `3`, en de vijf bestaande API-routes plus het exacte `/health`-contract worden expliciet onveranderd verklaard.

Niet in scope: scraping van artikelpagina's, scheduler/periodieke ophaling, classificatie, ranking, clustering, LLM-toepassingen, notificaties, frontend-werk, een HTTP-status- of importroute voor items, en elke wijziging aan de vijf catalogusroutes of aan `/health`.

## Capabilities

### New Capabilities
- `rss-ingestion`: handmatige, idempotente RSS/Atom-import van actieve catalogusbronnen naar lokale item- en aliastabellen, inclusief identiteitsafspraken, veldnormalisatie, ophaalbegrenzingen (SSRF, redirects, retries, `304`), per-bron transacties, gestandaardiseerde foutcodes en per-bron persistente laatste bronstatus (geen runhistorie), het CLI-contract en de offline teststrategie met synthetische fixtures.

### Modified Capabilities
- `source-catalog`: (1) de scope-requirement wordt afgebakend zodat ophaling en opslag van items uitsluitend onder `rss-ingestion` valt en de catalogusoperaties zelf offline blijven; (2) de migratie-requirement loopt voortaan additief door naar schema-versie 3 met noop op 3 en weigering van nieuwere/ongekende versies; (3) de vijf API-routes, de PATCH-/foutsemantiek, de seed en het exacte `/health`-contract blijven op requirementniveau ongewijzigd en worden niet uitgebreid.

## Impact

- **Code (backend/app)**: nieuwe modulen voor transport, parser, normalisatie en de ingestie-CLI; `db.py` en `db_migrate.py` krijgen de additieve v3-statementset; de versiecheck in `source_seed` en de migratietests gaan mee naar versie 3. `sources_api.py`, `sources_repository.py`, `sources_validation.py` en `health.py` blijven qua gedrag ongewijzigd.
- **Database**: drie additieve tabellen (`items`, `item_identity_aliases`, `source_feed_state`) met de primairsleutel op `(source_id, alias_type, alias_value)` in de aliastabel, de unieke composite parent-index `ux_items_id_source` op `items` en een zoekindex, in de bestaande `news.db` op named volume `nieuws_piet_sqlite_data`; `app_meta.schema_version` gaat van 2 naar 3 binnen één transactie, versie pas na succes. Catalogusdata blijft onaangeroerd; bestaande backup/restore kopieert het volledige bestand en beslaat daarmee ook item-, alias- en feed-state-data.
- **API**: geen nieuwe routes; de vijf bestaande catalogusroutes en `/health` blijven exact zoals gespecificeerd.
- **Netwerk**: voor het eerst uitgaand HTTP(S)-verkeer vanaf de eigen machine, uitsluitend wanneer het handmatige commando wordt gestart, alleen naar `feed_url`-waarden uit de catalogus (plus redirects), met publieke-adrescontrole per hop.
- **Dependencies**: geen nieuwe pakketten; uitsluitend de Python-standaardbibliotheek (`urllib`, `xml.etree`, `email.utils`, `ipaddress`, `sqlite3`).
- **Tests/Documentatie**: nieuwe testmodules met XML-fixtures naast de bestaande suite; lokale ontwikkelingsdocumentatie voor het ingestiecommando, de foutcodes en de begrenzingen.
- **Operatie**: geen accounts, geen betaalde API's, geen publieke hosting, geen extra services in `compose.yaml`.

## Niet-doelen

- Geen automatische of periodieke ophaling en geen achtergrondtaak in de backend.
- Geen opslag van artikelinhoud/HTML (alleen metadata: identiteit, titel, datum, links, bron).
- Geen classificatie, rangorde, clustering, samenvattingen of notificaties.
- Geen uitbreiding van de catalogus-API of van het `/health`-contract.
- Geen persistente importgeschiedenis: per bron wordt uitsluitend de laatste operationele status (validators, laatste poging, laatste succes, laatste fout) bewaard; eerdere runresultaten worden niet als historietabel weggeschreven.

## Risico's

- **SSRF/DNS-rebinding**: een feed-URL of redirect mag niet naar interne adressen leiden → mitigatie: scheme-, adres- en poortcontrole op elke hop, resulven en pinnen van het gevalideerde adres, maximaal 3 redirects, uitsluitend publieke adressen, met tests op privé-/loopback-/link-local-/multicasttargets.
- **Identiteitsconflicten in echte feeds** (gedeelde guid's of gewijzigde links) → mitigatie: strikte conflictregel zonder merge, zichtbare teller en exitcode 1; geen risico op het samenvoegen van twee artikelen.
- **Parser-coverage**: een strikte subset-parser kan vreemde feeds afwijzen → mitigatie: fout wordt per bron als `parse_error` gerapporteerd zonder dat andere bronnen lijden; fixtures dekken RSS 2.0, RSS 1.0/RDF en Atom 1.0.
- **Versieripple**: schema 3 raakt de bestaande migratie- en seedtests → mitigatie: één additieve statementset, versie pas na succes, noop- en weigerbewijzen opnieuw vastgelegd.
- **Begrenzingen hakken data af** (`body_too_large`, `too_many_items`) → mitigatie: expliciete foutcodes in de uitvoer in plaats van stilzwijgende truncatie.
- **Statusvelden veranderen bij elke run** → mitigatie: de idempotentie geldt uitsluitend voor `items` en `item_identity_aliases`; tests vergelijken die twee tabellen byte-voor-byte en laten de operationele statusvelden met rust.
- **Database-fout voorkomt persistente status** → mitigatie: de CLI-uitvoer en de exitcode blijven leidend, de statusregistratie wordt overgeslagen zonder herstelcircus.

## Privacy-impact

Geen accounts, geen betaalde diensten en geen publieke hosting. Het commando verstuurt uitsluitend standaard HTTP-verzoeken (inclusief optionele `ETag`/`Last-Modified`) naar feed-URL's die de gebruiker zelf in de lokale catalogus heeft gezet; er worden geen inloggegevens, cookies of persoonsgegevens verzonden en geen data naar derden gedeeld. Doelbinding is beperkt tot het ophalen van publieke feeds; SSRF-begrenzing voorkomt dat het commando interne of niet-publieke adressen aanspreekt. Alle opgeslagen data blijft in de lokale SQLite-database op de eigen machine/LAN.

## Rollback

De rollback is voorwaardelijk, net als bij de cataloguschange: de code- en databasekant moeten als één compatibele set worden teruggengezet.

1. **Vóór de migratie een niet-destructieve backup maken** via het bestaande `scripts/db-rollback.sh`-proces; die backup geldt als pre-migratie-v2-stand.
2. **Code revert** van de ingestiemodulen en de v3-statementset; de vijf catalogusroutes en `/health` zijn niet aangeraakt en blijven werken zolang de database op versie 2 staat.
3. **Herstel van de pre-migratie-v2-backup** is verplicht als ook de oude code weer opstart: die code classificeert versie 3 als nieuwere/ongekende versie en weigert dan. Itemdata gaat bij deze restore verloren (verwacht: die bestond vóór de change niet).
4. **Alternatief zonder restore**: de nieuwe code blijft staan en de v3-tabellen blijven ongebruikt; er is geen write-pad dat zonder de ingestiecli wordt geactiveerd.
