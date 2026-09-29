# Tasks

## 1. Database-migratie v1 → v2

- [x] 1.1 Implementeer de transactionele migratie (tabellen `sources`, `topics`, `source_topics`, `source_cloud_labels`, PK's/FK's/CHECK's, `UNIQUE`-index op `feed_url_key`, zoekindexen en gevulde woordenlijst) waarbij `schema_version` pas als laatste stap binnen de transactie naar 2 gaat; verifieer met de migratietest v1 → v2: versie is 2, alle tabellen bestaan en `PRAGMA foreign_key_check` retourneert geen rijen.
- [x] 1.2 Implementeer noop- en weigergedrag voor een reeds gemigreerde of onbekende versie; verifieer met de tests v2-noop (versie blijft 2, geen tabel/index/rij gewijzigd) en newer-reject (versie > 2 of onbekende waarde → weigering zonder enige schrijfactie).
- [x] 1.3 Implementeer rollback bij een fout tijdens de migratie; verifieer met de migratierollbacktest (geforceerde fout midden in de migratie → alle wijzigingen teruggedraaid, versie blijft 1, geen halve tabellen).
- [x] 1.4 Zet `PRAGMA foreign_keys=ON` op elke verse verbinding in de bestaande connectiecontext; verifieer met een test dat een insert van een bronrelatie naar een niet-bestaand record op een nieuwe verbinding door SQLite wordt geweigerd.
- [x] 1.5 Documenteer de versiegestuurde migratiestappen lokaal; verifieer dat de gedocumenteerde stappen exact overeenkomen met de uitgevoerde migratietests.

## 2. URL-canonicalisatie en validatie

- [x] 2.1 Implementeer `canonicalize_url` met `urllib.parse` uit de Python standaardbibliotheek (trimmen, lowercase scheme/host, standaardpoort weg, leeg pad naar `/`, behoud van `www`, scheme, padhoofdletters, niet-lege trailing slash, queryvolgorde/-waarden en overige percent-encoding); verifieer met de gouden tabeltests voor al deze normalisatieregels.
- [x] 2.2 Implementeer de rejectieregels (fragment, credentials, controltekens, interne ongecodeerde whitespace, backslashes, ongeldige percent-escapes, dot-segmenten, relatieve of niet-http(s)-URL, ongeldige poort); verifieer met tests dat elk van deze gevallen HTTP 422 geeft en geen record opslaat.
- [x] 2.3 Implementeer deterministische IDNA-hostnormalisatie zonder netwerk; verifieer met de test dat hoofdlettervarianten van dezelfde niet-ASCII-host exact dezelfde `feed_url_key` opleveren en dat de canonicalisatie geen socket opent.
- [x] 2.4 Implementeer validatie van `type`, `language` en `reliability`; verifieer met de edge-casetests: `type` ontbreekt/ongeldig → 422, `language` ontbreekt → 422, `NL` normaliseert naar `nl`, code buiten de expliciete lijst → 422, `und`/`mul` worden geaccepteerd, `reliability` boolean/decimale notatie/0/6 → 422 en `reliability` null → opgeslagen als null.
- [x] 2.5 Implementeer woordenlijstvalidatie voor `topics` en `cloudlabels` inclusief dubbele items; verifieer met tests: onbekend onderwerp → 422, dubbel onderwerp → 422, onbekend cloudlabel → 422, dubbel cloudlabel → 422 en geen automatische afleiding van cloudlabels.
- [x] 2.6 Documenteer de URL-regels, het taalbeleid en de woordenlijsten in de lokale ontwikkelingsdocumentatie; verifieer dat elk gedocumenteerd voorbeeld terug te vinden is als assertie in de tests van 2.1 tot en met 2.5.

## 3. Repository, transacties en foutmapping

- [x] 3.1 Implementeer de repository- en leespaden die het databasepad uitsluitend uit `app.state.db_path` halen; verifieer met de test op afzonderlijke applicatie-databasepaden: twee `create_app`-instanties met verschillende `db_path` delen geen bronrecords.
- [x] 3.2 Implementeer de insert van een bronrecord binnen `BEGIN IMMEDIATE` met de `UNIQUE`-index als autoriteit; verifieer met de tests inactieve duplicate (409 tegenover een inactieve bron), gedeelde website (twee kanalen met dezelfde `website_url` leveren beide 201) en concurrency-UNIQUE (twee gelijktijdige inserts met dezelfde `feed_url_key`: precies één slaagt, geen duplicaat, geen corruptie).
- [x] 3.3 Implementeer PATCH als één transactie over bronrecord én relaties, met volledige eindtoestandvalidatie; verifieer met de PATCH-atomiciteittest (ongeldige eindtoestand → 422 en bronrecord plus relaties onveranderd) en de conflicttest (409 en alles onveranderd).
- [x] 3.4 Implementeer vervangende lijstsemantiek voor `topics` en `cloud_labels` in PATCH; verifieer met tests dat een aanwezige lijst de volledige set vervangt en dat `[]` alle relaties wist.
- [x] 3.5 Implementeer foutmapping naar 404/409/422/503 met vaste foutbodies; verifieer met tests dat een onbereikbare database een begrensde HTTP 503 met vaste melding geeft en dat geen enkele foutrespons SQL-tekst, stacktrace of lokaal pad bevat.

## 4. API voor bronbeheer

- [x] 4.1 Implementeer `GET /api/sources` met standaard inclusief inactieve bronnen, oplopende id-sortering, AND-filters `is_active`/`topic`/`cloud_label` en HTTP 200 met `[]` bij een lege catalogus; verifieer met tests voor sortering, filter-combinatie, ongeldige filterwaarde → 422 en de lege catalogus.
- [x] 4.2 Implementeer `GET /api/sources/{id}` en `PATCH /api/sources/{id}` met 200/404; verifieer met tests dat een onbekend id 404 geeft en dat PATCH op een onbekend id geen record aanmaakt (geen upsert).
- [x] 4.3 Implementeer `POST /api/sources` met HTTP 201 en de gedeelde foutsemantiek; verifieer met integratietests voor 201, 409 bij duplicate feed-identiteit, 422 bij ongeldige invoer en 404 bij onbekend id.
- [x] 4.4 Documenteer het API-contract (routes, requestvelden, responsvelden, filters en statuscodes) in de lokale ontwikkelingsdocumentatie; verifieer dat de documentatie exact de vijf routes uit de delta-spec noemt en geen andere routes suggereert.

## 5. Eén opties-endpoint

- [x] 5.1 Implementeer één `GET /api/source-options` die onderwerpen, typen (`rss`, `atom`), het taalbeleid (expliciete codelijst plus `und` en `mul`) en de cloudlabels teruggeeft; verifieer met de test dat de respons deze vier onderdelen bevat en dat de cloudlabels exact `azure`, `aws`, `t-cloud`, `otc`, `multi-cloud` en `sovereign-cloud` zijn.
- [x] 5.2 Verifieer dat er geen aanvullende opties-routes en geen opties-wijzigingsroutes bestaan; verifieer met tests dat een benadering van een niet-gedeclareerde route 404 geeft en dat de opties onveranderd blijven na een catalogusschrijfactie.

## 6. Handmatig beoordeelde seed

- [x] 6.1 Stel de starterset samen uit uitsluitend officiële publicatiekanalen die handmatig zijn beoordeeld en vastgelegd in een lokaal seedbestand in de repo; verifieer met een test dat elke seed-entry de URL-validatie uit 2.1 en 2.2 doorstaat en dat er geen onbevestigde URL's in het bestand staan.
- [x] 6.2 Implementeer de expliciete, insert-only seedoperatie op `feed_url_key`, los van de applicatie-start en van de migratiestap; verifieer met de tests eerste run vult de starters, herhaling is idempotent, seed-no-overwrite (een handmatig gewijzigd starter-record blijft ongewijzigd) en een ontbrekende starter wordt aangevuld terwijl bestaande records onveranderd blijven.
- [x] 6.3 Verifieer dat de seed volledig offline verloopt; verifieer met de no-networktest (socket-guard rond de seed-operatie) dat er geen sockets naar externe hosts worden geopend.
- [x] 6.4 Documenteer hoe de seed handmatig wordt gestart en wat de beoordelingscriteria voor een starter zijn; verifieer dat de documentatie beschrijft dat herhaling nooit bestaande records wijzigt.

## 7. Regressie, offline-garanties en backup/restore

- [x] 7.1 Leg het bestaande `/health`-contract vast in een regressietest op een applicatie met een gemigreerde, gevulde catalogusdatabase; verifieer dat statuscode, Content-Type en JSON-body exact overeenkomen met het bestaande contract, zonder catalogusvelden en zonder extra componenten, en dat de catalogus geen componenten of velden aan dat contract heeft toegevoegd.
- [x] 7.2 Verifieer de offline-garantie over de volledige catalogussuite met een socket-guard; verificatie: geen enkele test opent een socket naar een externe host.
- [x] 7.3 Verifieer dat de bestaande backup/restore met v2-catalogusdata werkt; verificatie: backup van een gevulde v2-database, integriteitsvalidatie met `PRAGMA integrity_check` = `ok`, restore en daarna exact dezelfde catalogusrijen en relaties plus `ok`. Uitvoeren rondom het bestaande proces, niet als nieuwe backupfunctie.
- [x] 7.4 Documenteer backup en restore met catalogusdata in de bestaande lokale documentatie; verificatie: de documentatie beschrijft de bestaande procedure en noemt de catalogus als bewaarde data bij restore.
- [x] 7.5 Draai de volledige backend-testsuite; verificatie: alle nieuwe tests en alle bestaande tests (inclusief de gezondheids- en rollbacktests) slagen.
