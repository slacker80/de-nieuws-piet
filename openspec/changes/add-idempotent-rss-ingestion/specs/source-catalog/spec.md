# Spec Delta

## MODIFIED Requirements

### Requirement: Scope van de capability
De broncatalogus SHALL uitsluitend broncatalogusmetadata (publicatiekanalen) beheren. Het ophalen van RSS/Atom-feeds en het opslagen van items vallen uitsluitend onder de capability `rss-ingestion` en SHALL niet plaatsvinden via catalogusoperaties. De catalogusoperaties zelf SHALL GEEN feed- of RSS-ophaling, scraping, artikelopslag, samenvattingen, ranking, LLM-toepassingen, scheduler, notificaties of externe opslag uitvoeren, en SHALL geen netwerkvalidatie van URLs toepassen. De vijf bestaande API-routes (`GET /api/sources`, `GET /api/sources/{id}`, `POST /api/sources`, `PATCH /api/sources/{id}` en `GET /api/source-options`) en het exacte `/health`-contract blijven de enige API en SHALL ongewijzigd blijven; zij SHALL niet met item-, ingestie- of importstatusvelden worden uitgebreid.

#### Scenario: Geen netwerk tijdens catalogusoperaties
- **GIVEN** de broncatalogus is beschikbaar op een lokale SQLite-database
- **WHEN** een bronrecord wordt aangemaakt, gewijzigd, opgevraagd of gevalideerd
- **THEN** worden er geen sockets geopend naar externe hosts
- **AND** worden er geen HTTP-verzoeken, DNS-resoluties of redirects uitgevoerd

#### Scenario: Responsen bevatten uitsluitend catalogusvelden
- **GIVEN** er bestaan bronrecords in de catalogus
- **WHEN** een lijst- of detailrespons wordt opgevraagd
- **THEN** bevat die respons uitsluitend catalogusvelden
- **AND** bevat die respons geen artikelen, samenvattingen of rangorden

#### Scenario: Itemdata blijft buiten de catalogusrespons
- **GIVEN** er staan naast bronrecords ook items in dezelfde database
- **WHEN** `GET /api/sources` wordt uitgevoerd
- **THEN** bevat de respons uitsluitend catalogusvelden
- **AND** bevat de respons geen items en geen importstatus

#### Scenario: Geen ingestie- of itemroute
- **GIVEN** de broncatalogus is beschikbaar
- **WHEN** een niet-gedeclareerde route zoals `GET /api/items` of `POST /api/sources/{id}/import` wordt benaderd
- **THEN** wordt HTTP 404 geretourneerd
- **AND** is er geen import gestart

### Requirement: Migratie, database-invarianten en backup
Het systeem SHALL de additieve databasemigratie transactioneel uitvoeren van schema-versie 1 of 2 naar schema-versie 3 (eerst de catalogustabellen uit de versie-2-set wanneer die ontbreken — de historische overgang 1 → 2 —, daarna de ingestietabellen `items`, `item_identity_aliases` en `source_feed_state`) en de versie pas na succes vastleggen. Het systeem SHALL een reeds gemigreerde versie-3-database als noop behandelen, SHALL een nieuwere of onbekende versie weigeren zonder iets te wijzigen, SHALL per verbinding `PRAGMA foreign_keys=ON` activeren en SHALL de uniekheid van `feed_url_key` op databaseniveau afdwingen. Het bestaande `/health`-contract SHALL exact ongewijzigd blijven en SHALL niet worden uitgebreid met catalogusvelden, itemvelden of catalogus-/ingestiechecks. Bestaande backup en restore SHALL de catalogusdata én de ingestiedata (items, aliassen en feed-state) bewaren.

#### Scenario: Migratie van versie 1 naar versie 2
- **GIVEN** een database op schema-versie 1 zonder catalogustabellen
- **WHEN** de migratie wordt uitgevoerd
- **THEN** zijn eerst alle catalogustabellen uit de versie-2-set aangemaakt
- **AND** is de schema-versie na afloop 3 en bestaan ook de ingestietabellen (`items`, `item_identity_aliases`, `source_feed_state`)
- **AND** retourneert `PRAGMA foreign_key_check` geen rijen

#### Scenario: Migratie op versie 2 is een noop
- **GIVEN** een database op schema-versie 2 met catalogusdata maar zonder ingestietabellen
- **WHEN** de migratie wordt uitgevoerd
- **THEN** verandert er geen enkele catalogustabel, -index of -rij: de catalogusstap is een noop
- **AND** worden uitsluitend de ingestietabellen (`items`, `item_identity_aliases`, `source_feed_state`) toegevoegd
- **AND** is de schema-versie na afloop 3

#### Scenario: Migratie op versie 3 is een noop
- **GIVEN** een database op schema-versie 3
- **WHEN** de migratie opnieuw wordt uitgevoerd
- **THEN** blijft de schema-versie 3
- **AND** verandert er geen enkele tabel, index of rij

#### Scenario: Nieuwere of onbekende versie wordt geweigerd
- **GIVEN** een database met een schema-versie hoger dan 3 of met een onbekende waarde
- **WHEN** de migratie wordt uitgevoerd
- **THEN** wordt de migratie geweigerd
- **AND** wordt er niets gewijzigd

#### Scenario: Mislukte migratie rolt terug
- **GIVEN** een database op schema-versie 1 of 2
- **WHEN** een fout optreedt tijdens de migratie
- **THEN** worden alle migratiewijzigingen teruggedraaid
- **AND** blijft de schema-versie die vóór de migratie gold

#### Scenario: Foreign keys zijn per verbinding actief
- **GIVEN** een verbinding met de catalogusdatabase wordt geopend
- **WHEN** die verbinding probeert een bronrelatie naar een niet-bestaand record te schrijven
- **THEN** wordt die schrijfactie door de database geweigerd

#### Scenario: Unieke feed-identiteit wordt op databaseniveau afgedwongen
- **GIVEN** twee gelijktijdige schrijfacties bieden dezelfde `feed_url_key` aan
- **WHEN** beide schrijfacties worden uitgevoerd
- **THEN** slaagt precies één van beide
- **AND** wordt de andere geweigerd zonder dat er een duplicaat of corruptie ontstaat

#### Scenario: `/health` blijft exact ongewijzigd
- **GIVEN** de broncatalogus is gemigreerd, bevat data en er zijn items geïmporteerd
- **WHEN** `GET /health` wordt uitgevoerd
- **THEN** wordt exact het bestaande health-contract geretourneerd
- **AND** bevat de respons geen catalogusvelden, geen itemvelden en geen extra componenten

#### Scenario: Backup en restore bewaren de catalogus
- **GIVEN** een backup bestaat van een versie-3-database met catalogus- en ingestiedata
- **WHEN** die backup wordt gerestaureerd
- **THEN** zijn alle catalogusrijen, alle item-, alias- en feed-state-rijen en hun relaties behouden
- **AND** retourneert `PRAGMA integrity_check` exact `ok`
