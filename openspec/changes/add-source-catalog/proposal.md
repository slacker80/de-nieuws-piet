# Proposal

## Why

De backend heeft wel een lokale SQLite-bootstrap en een exact `/health`-contract, maar nog geen gestructureerde, bewerkbare opslag voor de publicatiekanalen (feeds) die de nieuwssite moet gebruiken. Deze change voegt die broncatalogus volledig lokaal toe: FastAPI-beheer op uitsluitend lokale SQLite, met deterministische validatie en een handmatig beoordeelde starterset, zodat bronattributie en deduplicatie vanaf nu in de database zijn vastgelegd in plaats van los.

## What Changes

- **Nieuwe capability `source-catalog`**: een relationeel model voor bronrecords (= publicatiekanalen/feeds) met de velden `name`, `feed_url` (verplicht), `website_url` (optioneel), `type` (`rss|atom`, verplicht), `language` (verplicht, expliciete ISO 639-1-lijst plus `und` en `mul`), `reliability` (null of integer 1..5), `is_active` (standaard `false`), `topics` en meerdere `cloudlabels`.
- **Database-migratie v1 → v2**: additieve tabellen `sources`, `topics`, `source_topics` en `source_cloud_labels`, transactioneel, met database-uniekheid voor de afgeleide `feed_url_key` over actieve én inactieve bronnen.
- **Offline URL-validatie**: canonicalisatie zonder netwerk, met deterministische IDNA-normalisatie en een strikte rejectielijst (fragment, credentials, controltekens, interne whitespace, backslashes, ongeldige percent-escapes, dot-segmenten).
- **API**: `GET /api/sources`, `GET /api/sources/{id}`, `POST /api/sources`, `PATCH /api/sources/{id}` en één `GET /api/source-options`. Geen `DELETE`, geen opties-CRUD, geen upsert/merge, geen onderbreking van de lijst in deelantwoorden.
- **Seed**: een expliciete, lokale, idempotente operatie voor vooraf handmatig beoordeelde officiële startbronnen; insert-only, geen netwerk, los van de applicatie-start.
- **Tests en documentatie**: validatie-, migratie-, API-, regressie- en backuptests plus lokale ontwikkelingsdocumentatie voor catalogus, validatieregels en seed.

Niet in scope: feed-ophaling, scraping, artikelen, samenvattingen, ranking, LLM, scheduler, notificaties, netwerkvalidatie van URLs, externe opslag, frontend-werk en elke wijziging aan het `/health`-contract.

## Capabilities

### New Capabilities
- `source-catalog`: lokaal bronbeheer (publicatiekanalen) met veldvalidatie, offline URL-canonicalisatie, unieke feed-identiteit, gecontroleerde woordenlijsten, FastAPI-beheerroutes, foutafhandeling, idempotente seed en database-migratie/backup-invarianten.

### Modified Capabilities
Geen. De bestaande capabilities `database/local-sqlite`, `documentation/local-dev`, `health-monitoring/health-endpoint` en `local-development/setup` worden op requirementniveau niet gewijzigd: de catalogus is een additieve tabelset in dezelfde database, en het `/health`-contract blijft exact zoals gespecificeerd.

## Impact

- **Code (backend/app)**: nieuwe router, repositorylaag, validatiemodule en seedmodule; één aanvulling op de bestaande verbindingscontext (`PRAGMA foreign_keys=ON` per verbinding). `health.py` en de `/health`-route blijven ongewijzigd.
- **Database**: additieve v2-tabellen en -indexen in de bestaande `news.db` op named volume `nieuws_piet_sqlite_data`; `app_meta.schema_version` gaat van 1 naar 2.
- **API**: nieuwe routes onder `/api/sources` en `/api/source-options`; bestaande routes ongewijzigd; foutsemantiek 404/409/422/503 met vaste, niet-lekkende foutbodies.
- **Configuratie/data**: één lokaal seedbestand in de repo met de handmatig beoordeelde starterset; geen nieuwe omgevingvariabelen buiten een optioneel padargument.
- **Dependencies**: geen; uitsluitend de Python-standaardbibliotheek (`urllib.parse`, `sqlite3`) en de bestaande FastAPI-stack.
- **Tests**: nieuwe testmodules naast de bestaande suite; de bestaande health- en rollbacktests blijven staan en worden aangevuld met een regressietest op exact `/health`.
- **Documentatie**: lokale ontwikkelingsdocumentatie voor de catalogus, de validatieregels, de seed en een kanttekening bij de bestaande backup/restore-documentatie.
- **Operatie**: geen accounts, geen betaalde diensten, geen publieke hosting, geen extra services in `compose.yaml`.

## Niet-doelen

- Geen frontend, geen artikelen, geen samenvattingen en geen ranking.
- Geen uitbreiding van `/health` met catalogusvelden of cataloguschecks; alleen een regressietest.
- Geen scheduler, notificaties, feed-ophaling of enige runtime-netwerkactiviteit.
- Geen herimplementatie van het bestaande backup-/restoreproces.

## Risico's

- **Canonicalisatie-afwijking**: als de regels afwijken van wat latere onderdelen verwachten, ontstaan schijnbare duplicaten → mitigatie: één zuivere functie, gouden testtabel uit de delta-spec.
- **Migratiefout op de named volume**: een gefaalde migratie mag geen half schema achterlaten → mitigatie: alles in één transactie, versie pas na succes, backup vóór uitvoering.
- **Seed overschrijft gebruikerswerk**: → mitigatie: insert-if-absent, nooit updaten, herhaaltest met een gewijzigd record.
- **Parallelle schrijvers met dezelfde feed-URL** → mitigatie: database-uniekheid plus `BEGIN IMMEDIATE`, gemapt naar 409.

## Privacy-impact

Geen. Er komen geen externe accounts, geen betaalde API's en geen publieke hosting bij kijken; alle data blijft in de lokale SQLite-database op de eigen machine/LAN. Er worden geen persoonsgegevens verwerkt: de catalogus bevat alleen door de eigenaar ingevoerde metadata over publicatiekanalen (naam, URLs, type, taal, betrouwbaarheid, status, onderwerpen en cloudlabels). Er verlaat geen enkel pakket het lokale netwerk; validatie en canonicalisatie zijn offline.

## Rollback

De rollback is voorwaardelijk: er geldt géén onvoorwaardelijke garantie zonder dataverlies, omdat het herstellen van de v1-backup alle na de migratie gemaakte cataloguswijzigingen verliest. Code en database moeten als één compatibele set worden teruggengezet.

1. **Eerst eventuele v2-data veiligstellen**: wil je latere cataloguswijzigingen behouden, maak dan vóór de restore eerst een kopie van de actuele v2-database (niet-destructieve backup via `scripts/db-rollback.sh`) en bewaar die naast de pre-migratie-v1-backup. Die kopie wordt niet automatisch teruggezet; ze is alleen beschikbaar voor latere handmatige overname.
2. **Code-revert alleen samen met herstel van de backup**: revert van de nieuwe modules is uitsluitend veilig in combinatie met het herstellen van de gevalideerde pre-migratie-v1-backup via de bestaande data-safe procedure (`scripts/db-rollback.sh`).
3. **Start de oude v1-code nooit tegen de v2-database**: de bestaande bootstrap-v1-code schrijft bij init `schema_version` terug naar `1`, waardoor de versie-marker wordt gewijzigd terwijl de v2-tabellen nog aanwezig zijn. Dat levert een onondersteunde code/schema-combinatie op en maakt bovendien de werkelijke migratiestatus onleesbaar. Ondersteund is uitsluitend de combinatie "v1-code + v1-database uit de backup".
4. **Validatie vóór terugzetten**: de pre-migratie-backup moet `PRAGMA integrity_check` exact `ok` retourneren; bij elk ander resultaat wordt de restore niet uitgevoerd.
5. **Verificatie na rollback**: `schema_version` is 1, `PRAGMA integrity_check` geeft `ok`, de bootstrap-data-marker is aanwezig en `GET /health` volgt exact het bestaande contract.
