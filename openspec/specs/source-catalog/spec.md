# Spec

## Purpose

Beheert een volledig lokale, offline catalogus van publicatiekanalen (feeds) voor de persoonlijke nieuwssite: veldvalidatie, offline URL-canonicalisatie, unieke feed-identiteit, gecontroleerde woordenlijsten, een kleine FastAPI-beheerinterface en een idempotente seed, uitsluitend op lokale SQLite.

## Requirements

### Requirement: Scope van de capability
Het systeem SHALL uitsluitend broncatalogusmetadata (publicatiekanalen) beheren. Het systeem SHALL GEEN feed- of RSS-ophaling, scraping, artikelopslag, samenvattingen, ranking, LLM-toepassingen, scheduler, notificaties of externe opslag uitvoeren, en SHALL geen netwerkvalidatie van URLs toepassen.

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

### Requirement: Bronrecord is een publicatiekanaal
Het systeem SHALL elk bronrecord behandelen als een publicatiekanaal (feed) en opslaan met de velden `name`, `feed_url`, `website_url`, `type`, `language`, `reliability`, `is_active`, `topics` en `cloud_labels`, waarbij geldt:

- `name` is verplicht en SHALL na trimmen niet leeg zijn.
- `feed_url` is verplicht.
- `website_url` is optioneel.
- `type` is verplicht en SHALL exact een waarde uit het enum `rss` of `atom` zijn; automatische typebepaling SHALL niet plaatsvinden.
- `language` is verplicht en SHALL worden gekozen uit een expliciet opgesomde lijst van ISO 639-1-codes, aangevuld met `und` en `mul`; de invoer wordt eerst naar lowercase genormaliseerd; elke waarde buiten de lijst resulteert in HTTP 422.
- `reliability` is ofwel `null` ofwel een echte integer 1..5; booleans, strings en decimale notaties zijn ongeldig en resulteren in HTTP 422; het veld heeft geen rangorde- of rankingbetekenis.
- `is_active` is een boolean met standaardwaarde `false`; uitsluitend een seed kan een starter expliciet op `true` zetten na handmatige beoordeling.
- `topics` en `cloud_labels` zijn lijsten zonder automatische afleiding.

#### Scenario: Geldig bronrecord met standaardstatus inactief
- **GIVEN** een payload met geldige `name`, `feed_url`, `type` en `language` en zonder `is_active`
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 201 geretourneerd met het opgeslagen bronrecord
- **AND** is de waarde van `is_active` `false`

#### Scenario: `type` ontbreekt
- **GIVEN** een payload zonder `type`
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 422 geretourneerd
- **AND** wordt geen bronrecord opgeslagen

#### Scenario: `type` buiten het enum
- **GIVEN** een payload met `type` gelijk aan `json`
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: `language` ontbreekt
- **GIVEN** een payload zonder `language`
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 422 geretourneerd
- **AND** wordt geen bronrecord opgeslagen

#### Scenario: `language` wordt naar lowercase genormaliseerd
- **GIVEN** een payload met `language` gelijk aan `NL`
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt het record opgeslagen met `language` gelijk aan `nl`

#### Scenario: `language` buiten de codelijst
- **GIVEN** een payload met `language` gelijk aan een code die niet in de expliciete lijst voorkomt
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: `language` `und` en `mul` zijn geldig
- **GIVEN** een payload met `language` gelijk aan `und`
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 201 geretourneerd met `language` gelijk aan `und`

#### Scenario: `reliability` als boolean
- **GIVEN** een payload met `reliability` gelijk aan `true`
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: `reliability` als decimale notatie
- **GIVEN** een payload met `reliability` gelijk aan `4.5`
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: `reliability` buiten het bereik 1..5
- **GIVEN** een payload met `reliability` gelijk aan `0`
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: `reliability` expliciet null
- **GIVEN** een payload met `reliability` gelijk aan `null`
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 201 geretourneerd met `reliability` gelijk aan `null`

### Requirement: Offline URL-validatie en canonicalisatie
Het systeem SHALL `feed_url` en `website_url` uitsluitend offline valideren en canonicaliseren met de volgende regels:

- Buitenste whitespace wordt verwijderd.
- Alleen absolute http- of https-URL's met een geldige host en, indien aanwezig, een geldige poort worden geaccepteerd.
- Scheme en host worden lowercase.
- De host wordt deterministisch via IDNA genormaliseerd; dezelfde invoer levert altijd dezelfde canonieke host op, zonder netwerkgebruik.
- De standaardpoort (80 bij http, 443 bij https) wordt verwijderd; andere geldige poorten blijven behouden.
- Een leeg pad wordt `/`.
- Behouden blijven: `www`, het scheme, hoofdletters in het pad, een niet-lege trailing slash, de volgorde en waarden van de query en overige percent-encoding.
- Geweigerd worden: een fragment, credentials in de URL, controltekens, interne ongecodeerde whitespace, backslashes, ongeldige percent-escapes en dot-segmenten in het pad.
- Redirects, DNS-resolutie en elke andere netwerkhandeling SHALL niet plaatsvinden.

#### Scenario: Scheme en host worden lowercase, standaardpoort vervalt, leeg pad wordt `/`
- **GIVEN** een invoer van ` HTTPS://WWW.Example.COM:443  `
- **WHEN** de URL wordt gecanonicaliseerd
- **THEN** is het resultaat `https://www.example.com/`
- **AND** zijn buitenste whitespace en de standaardpoort verwijderd

#### Scenario: Hoofdletters in het pad en trailing slash blijven behouden
- **GIVEN** een invoer van `https://Example.com/News/RSS/`
- **WHEN** de URL wordt gecanonicaliseerd
- **THEN** is het resultaat `https://example.com/News/RSS/`

#### Scenario: Queryvolgorde en querywaarden blijven behouden
- **GIVEN** een invoer van `https://example.com/feed?b=2&a=1`
- **WHEN** de URL wordt gecanonicaliseerd
- **THEN** is het resultaat `https://example.com/feed?b=2&a=1`

#### Scenario: Niet-standaardpoort blijft behouden
- **GIVEN** een invoer van `http://example.com:8080/x`
- **WHEN** de URL wordt gecanonicaliseerd
- **THEN** is het resultaat `http://example.com:8080/x`

#### Scenario: IDNA-normalisatie is deterministisch
- **GIVEN** twee invoeren die alleen in hoofdletters van de niet-ASCII-host verschillen
- **WHEN** beide URLs worden gecanonicaliseerd
- **THEN** leveren beide URLs exact dezelfde afgeleide `feed_url_key` op

#### Scenario: Fragment wordt geweigerd
- **GIVEN** een invoer van `https://example.com/feed#section`
- **WHEN** de URL wordt gevalideerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: Credentials worden geweigerd
- **GIVEN** een invoer van `https://user:pass@example.com/feed`
- **WHEN** de URL wordt gevalideerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: Controltekens worden geweigerd
- **GIVEN** een invoer die een controlekarakter bevat
- **WHEN** de URL wordt gevalideerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: Interne ongecodeerde whitespace wordt geweigerd
- **GIVEN** een invoer van `https://example.com/ feed`
- **WHEN** de URL wordt gevalideerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: Backslashes worden geweigerd
- **GIVEN** een invoer van `https://example.com\\feed`
- **WHEN** de URL wordt gevalideerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: Ongeldige percent-escapes worden geweigerd
- **GIVEN** een invoer van `https://example.com/%zz`
- **WHEN** de URL wordt gevalideerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: Dot-segmenten worden geweigerd
- **GIVEN** een invoer van `https://example.com/a/../b`
- **WHEN** de URL wordt gevalideerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: Relatieve of niet-http(s)-URL's worden geweigerd
- **GIVEN** een invoer van `/feed.xml`
- **WHEN** de URL wordt gevalideerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: Ongeldige poort wordt geweigerd
- **GIVEN** een invoer van `https://example.com:99999/feed`
- **WHEN** de URL wordt gevalideerd
- **THEN** wordt HTTP 422 geretourneerd

### Requirement: Feed-identiteit is uniek over actieve en inactieve bronnen
Het systeem SHALL uitsluitend de afgeleide `feed_url_key` (de canonieke uitvoer van `feed_url`) uniek afdwingen, over actieve én inactieve bronnen, op databaseniveau. `website_url` SHALL niet uniek zijn; meerdere publicatiekanalen mogen dezelfde website delen. Elke poging om een bestaande feed-identiteit te hergebruiken resulteert in HTTP 409 zonder dat er iets wordt gewijzigd.

#### Scenario: Duplicate feed-identiteit bij aanmaken
- **GIVEN** er bestaat al een actieve bron met dezelfde canonieke feed-URL
- **WHEN** `POST /api/sources` dezelfde feed-URL aanbiedt
- **THEN** wordt HTTP 409 geretourneerd
- **AND** wordt het bestaande bronrecord niet gewijzigd

#### Scenario: Duplicate feed-identiteit tegenover een inactieve bron
- **GIVEN** er bestaat een inactieve bron met dezelfde canonieke feed-URL
- **WHEN** `POST /api/sources` dezelfde feed-URL aanbiedt
- **THEN** wordt HTTP 409 geretourneerd

#### Scenario: Gedeelde website-URL is toegestaan
- **GIVEN** er bestaat al een bron met `website_url` gelijk aan `https://example.com/`
- **WHEN** `POST /api/sources` een ander publicatiekanaal met `website_url` gelijk aan `https://example.com/` aanbiedt
- **THEN** wordt HTTP 201 geretourneerd

#### Scenario: Wijziging naar een bestaande feed-identiteit
- **GIVEN** een bestaand bronrecord met een eigen feed-URL
- **WHEN** `PATCH /api/sources/{id}` de feed-URL van een ander record overneemt
- **THEN** wordt HTTP 409 geretourneerd
- **AND** blijven bronrecord en relaties onveranderd

### Requirement: Onderwerpen zijn een gecontroleerde woordenlijst
Het systeem SHALL onderwerpen uitsluitend accepteren als waarden uit een gecontroleerde woordenlijst met stabiele slugs. Onbekende waarden en dubbele waarden binnen één request resulteren in HTTP 422. In een PATCH vervangen aanwezige lijsten de volledige set; een lege lijst wist alle relaties.

#### Scenario: Geldig onderwerp wordt gerelateerd
- **GIVEN** het onderwerp bestaat in de woordenlijst
- **WHEN** `POST /api/sources` dat onderwerp in `topics` aanbiedt
- **THEN** wordt HTTP 201 geretourneerd
- **AND** bevat het record exact dat onderwerp

#### Scenario: Onbekend onderwerp wordt geweigerd
- **GIVEN** het onderwerp bestaat niet in de woordenlijst
- **WHEN** `POST /api/sources` dat onderwerp in `topics` aanbiedt
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: Dubbel onderwerp in één request wordt geweigerd
- **GIVEN** dezelfde slug twee keer in `topics` voorkomt
- **WHEN** `POST /api/sources` die lijst aanbiedt
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: PATCH vervangt de volledige onderwerpen-set
- **GIVEN** een bronrecord met twee onderwerpen
- **WHEN** `PATCH /api/sources/{id}` een nieuwe lijst met één ander onderwerp aanbiedt
- **THEN** bevat het record na de wijziging exact dat ene onderwerp
- **AND** zijn de eerdere onderwerpen verwijderd

#### Scenario: PATCH met lege onderwerpen-set wist de relaties
- **GIVEN** een bronrecord met minstens één onderwerp
- **WHEN** `PATCH /api/sources/{id}` `topics` gelijk aan `[]` aanbiedt
- **THEN** heeft het record na de wijziging geen onderwerpen meer

### Requirement: Cloudlabels zijn exact gedefinieerd
Het systeem SHALL cloudlabels uitsluitend accepteren als waarden uit exact `azure`, `aws`, `t-cloud`, `otc`, `multi-cloud` en `sovereign-cloud`. Meerdere cloudlabels per bron zijn toegestaan; er SHALL geen automatische afleiding plaatsvinden. Onbekende en dubbele requestitems resulteren in HTTP 422. In een PATCH vervangen aanwezige lijsten de volledige set; een lege lijst wist alle cloudlabels.

#### Scenario: Meerdere cloudlabels worden geaccepteerd
- **GIVEN** een payload met `cloud_labels` gelijk aan `["azure", "multi-cloud"]`
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 201 geretourneerd met exact die twee cloudlabels

#### Scenario: Onbekend cloudlabel wordt geweigerd
- **GIVEN** een payload met `cloud_labels` gelijk aan `["google-cloud"]`
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: Dubbel cloudlabel in één request wordt geweigerd
- **GIVEN** een payload met `cloud_labels` gelijk aan `["aws", "aws"]`
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: Geen automatische afleiding van cloudlabels
- **GIVEN** een payload zonder `cloud_labels` wiens naam en URL's verwijzen naar een provider
- **WHEN** `POST /api/sources` wordt uitgevoerd
- **THEN** heeft het opgeslagen record een lege cloudlabel-set

#### Scenario: PATCH vervangt de volledige cloudlabel-set
- **GIVEN** een bronrecord met cloudlabel `azure`
- **WHEN** `PATCH /api/sources/{id}` `cloud_labels` gelijk aan `["otc"]` aanbiedt
- **THEN** heeft het record na de wijziging exact het cloudlabel `otc`

#### Scenario: PATCH met lege cloudlabel-set wist de labels
- **GIVEN** een bronrecord met minstens één cloudlabel
- **WHEN** `PATCH /api/sources/{id}` `cloud_labels` gelijk aan `[]` aanbiedt
- **THEN** heeft het record na de wijziging geen cloudlabels meer

### Requirement: API voor bronbeheer
Het systeem SHALL de volgende FastAPI-routes bieden en GEEN andere:

- `GET /api/sources` met HTTP 200, de volledige catalogus in één respons, standaard inclusief inactieve bronnen, gesorteerd op id, met de optionele filters `is_active`, `topic` en `cloud_label` die als AND worden gecombineerd; een lege catalogus levert HTTP 200 met `[]`.
- `GET /api/sources/{id}` met HTTP 200 voor een bestaand id en HTTP 404 voor een onbekend id.
- `POST /api/sources` met HTTP 201 bij succes.
- `PATCH /api/sources/{id}` met HTTP 200 bij succes en HTTP 404 voor een onbekend id.

Een niet-bestaand id SHALL nooit worden aangemaakt. Het systeem SHALL geen `DELETE`-route, geen CRUD-routes voor opties en geen upsert- of mergegedrag bieden. Elke filterwaarde die niet bij de gecontroleerde opties hoort resulteert in HTTP 422.

#### Scenario: Lege catalogus
- **GIVEN** de catalogus bevat geen bronrecords
- **WHEN** `GET /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 200 geretourneerd met een lege lijst
- **AND** wordt er geen fout geretourneerd

#### Scenario: Standaard inclusief inactieve bronnen met id-sortering
- **GIVEN** de catalogus bevat actieve én inactieve bronnen
- **WHEN** `GET /api/sources` zonder filters wordt uitgevoerd
- **THEN** worden alle bronrecords geretourneerd
- **AND** zijn ze gesorteerd op oplopend id

#### Scenario: Filters worden als AND gecombineerd
- **GIVEN** de catalogus bevat bronnen die elk aan slechts een deel van de filters voldoen
- **WHEN** `GET /api/sources` met `is_active=true`, een geldig `topic` en een geldig `cloud_label` wordt uitgevoerd
- **THEN** worden uitsluitend bronrecords geretourneerd die aan alle drie de filters voldoen

#### Scenario: Ongeldige filterwaarde
- **GIVEN** `topic` verwijst naar een waarde buiten de woordenlijst
- **WHEN** `GET /api/sources` met dat filter wordt uitgevoerd
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: Detail ophalen van een bestaand record
- **GIVEN** een bronrecord met id 1 bestaat
- **WHEN** `GET /api/sources/1` wordt uitgevoerd
- **THEN** wordt HTTP 200 geretourneerd met dat bronrecord inclusief onderwerpen en cloudlabels

#### Scenario: Detail ophalen van een onbekend id
- **GIVEN** geen bronrecord met het gevraagde id bestaat
- **WHEN** `GET /api/sources/{id}` wordt uitgevoerd
- **THEN** wordt HTTP 404 geretourneerd

#### Scenario: Wijzigen van een bestaand record
- **GIVEN** een bestaand bronrecord
- **WHEN** `PATCH /api/sources/{id}` met een geldige veldwijziging wordt uitgevoerd
- **THEN** wordt HTTP 200 geretourneerd met het bijgewerkte record

#### Scenario: PATCH op een onbekend id maakt geen record aan
- **GIVEN** geen bronrecord met het gevraagde id bestaat
- **WHEN** `PATCH /api/sources/{id}` wordt uitgevoerd
- **THEN** wordt HTTP 404 geretourneerd
- **AND** wordt geen bronrecord aangemaakt

### Requirement: PATCH-semantiek
Het systeem SHALL een PATCH uitsluitend toepassen met de volgende regels:

- Weggelaten velden blijven ongewijzigd.
- `null` is alleen toegestaan voor de velden `website_url` en `reliability`; `null` voor een ander veld resulteert in HTTP 422.
- Een PATCH zonder velden resulteert in HTTP 422.
- De eindtoestand SHALL volledig worden gevalideerd: URL-regels, woordenlijsten, enum, taal, betrouwbaarheid en feed-identiteit gelden voor de resulterende record als geheel.
- Bronrecord én relaties SHALL in één transactie worden geschreven; bij elke fout blijft alles onveranderd.

#### Scenario: Weggelaten velden blijven ongewijzigd
- **GIVEN** een bestaand bronrecord met ingevulde `language` en `reliability`
- **WHEN** `PATCH /api/sources/{id}` uitsluitend `name` aanbiedt
- **THEN** is alleen `name` gewijzigd
- **AND** zijn `language` en `reliability` onveranderd

#### Scenario: `null` wist een nullable veld
- **GIVEN** een bestaand bronrecord met ingevulde `reliability`
- **WHEN** `PATCH /api/sources/{id}` `reliability` gelijk aan `null` aanbiedt
- **THEN** is `reliability` na de wijziging `null`

#### Scenario: `null` voor een niet-nullable veld
- **GIVEN** een bestaand bronrecord
- **WHEN** `PATCH /api/sources/{id}` `name` gelijk aan `null` aanbiedt
- **THEN** wordt HTTP 422 geretourneerd
- **AND** is het record onveranderd

#### Scenario: Lege PATCH
- **GIVEN** een bestaand bronrecord
- **WHEN** `PATCH /api/sources/{id}` met een lege body wordt uitgevoerd
- **THEN** wordt HTTP 422 geretourneerd
- **AND** is het record onveranderd

#### Scenario: Ongeldige eindtoestand laat alles onveranderd
- **GIVEN** een bestaand bronrecord met onderwerpen en cloudlabels
- **WHEN** `PATCH /api/sources/{id}` een ongeldig veld combineert met een geldige relatie-wijziging
- **THEN** wordt HTTP 422 geretourneerd
- **AND** zijn bronrecord en beide relaties onveranderd

#### Scenario: Conflict laat alles onveranderd
- **GIVEN** een bestaand bronrecord met onderwerpen en cloudlabels
- **WHEN** `PATCH /api/sources/{id}` een feed-URL aanbiedt die al aan een ander record toebehoort
- **THEN** wordt HTTP 409 geretourneerd
- **AND** zijn bronrecord en relaties onveranderd

### Requirement: Eén opties-endpoint
Het systeem SHALL precies één opties-route bieden: `GET /api/source-options` met HTTP 200, met de gecontroleerde onderwerpen, de toegestane typen `rss` en `atom`, het taalbeleid (de expliciete lijst van geaccepteerde taalcodes inclusief `und` en `mul`) en de cloudlabels. Het systeem SHALL GEEN aanvullende opties-routes en GEEN opties-wijzigingsroutes bieden.

#### Scenario: Opties opvragen
- **GIVEN** de gecontroleerde woordenlijsten zijn beschikbaar
- **WHEN** `GET /api/source-options` wordt uitgevoerd
- **THEN** wordt HTTP 200 geretourneerd
- **AND** bevat de respons de sleutels voor onderwerpen, typen, taalbeleid en cloudlabels

#### Scenario: Cloudlabels in de opties komen exact overeen met de toegestane set
- **GIVEN** `GET /api/source-options` is beschikbaar
- **WHEN** de cloudlabel-waarden uit de respons worden vergeleken met de toegestane set
- **THEN** is die set exact `azure`, `aws`, `t-cloud`, `otc`, `multi-cloud` en `sovereign-cloud`

### Requirement: Foutafhandeling
Het systeem SHALL de volgende deterministische foutcodes hanteren: HTTP 404 voor een onbekend id, HTTP 409 voor een duplicate feed-identiteit, HTTP 422 voor ongeldige invoer of ongeldige opties, en HTTP 503 met een begrensde, vaste foutmelding wanneer de database onbereikbaar is. Foutresponsen SHALL GEEN SQL-tekst, GEEN stacktraces en GEEN lokale paden bevatten.

#### Scenario: Onbekend id
- **GIVEN** geen bronrecord met het gevraagde id bestaat
- **WHEN** `GET /api/sources/{id}` wordt uitgevoerd
- **THEN** wordt HTTP 404 geretourneerd

#### Scenario: Duplicate feed-identiteit
- **GIVEN** de canonieke feed-URL bestaat al, actief of inactief
- **WHEN** `POST of PATCH` die feed-URL aanbiedt
- **THEN** wordt HTTP 409 geretourneerd

#### Scenario: Ongeldige invoer of opties
- **GIVEN** een payload met een veld of optie-waarde buiten de toegestane set
- **WHEN** die payload wordt verwerkt
- **THEN** wordt HTTP 422 geretourneerd

#### Scenario: Database onbereikbaar
- **GIVEN** de lokale SQLite-database is tijdelijk onbereikbaar
- **WHEN** `GET /api/sources` wordt uitgevoerd
- **THEN** wordt HTTP 503 geretourneerd met een vaste, begrensde foutmelding
- **AND** blijft het aantal databasepogingen binnen een vaste begrenzing

#### Scenario: Foutresponsen lekken geen interne details
- **GIVEN** een van de bovenstaande fouten optreedt
- **WHEN** de foutrespons wordt gecontroleerd
- **THEN** bevat die respons geen SQL-tekst, geen stacktrace en geen lokaal bestandspad

### Requirement: Idempotente seed van officiële startbronnen
Het systeem SHALL een expliciete, lokale en idempotente seed-operatie bieden die uitsluitend vooraf handmatig beoordeelde officiële startbronnen toevoegt. De seed-operatie SHALL NIET worden uitgevoerd tijdens applicatie-start, SHALL GEEN netwerkverkeer gebruiken en SHALL bij herhaling alleen ontbrekende starters toevoegen: bestaande records, inclusief wijzigingen door de gebruiker, worden nooit gewijzigd of overschreven. Onbevestigde URL's SHALL niet in de seed worden opgenomen.

#### Scenario: Eerste seed-uitvoering vult de starters
- **GIVEN** een lege catalogus op een gemigreerde v2-database
- **WHEN** de seed-operatie één keer wordt uitgevoerd
- **THEN** worden alle vooraf beoordeelde starters toegevoegd
- **AND** wordt er geen netwerkverkeer uitgevoerd

#### Scenario: Seed-herhaling is idempotent
- **GIVEN** de starters staan al in de catalogus
- **WHEN** de seed-operatie opnieuw wordt uitgevoerd
- **THEN** worden geen records toegevoegd, gewijzigd of verwijderd

#### Scenario: Seed-herhaling bewaart gebruikerswijzigingen
- **GIVEN** een gebruiker heeft een starter-record na de eerste seed gewijzigd
- **WHEN** de seed-operatie opnieuw wordt uitgevoerd
- **THEN** is dat gewijzigde record onveranderd

#### Scenario: Ontbrekende starter wordt aangevuld
- **GIVEN** één starter ontbreekt en de overige starters bestaan
- **WHEN** de seed-operatie opnieuw wordt uitgevoerd
- **THEN** is de ontbrekende starter toegevoegd
- **AND** zijn de bestaande records onveranderd

### Requirement: Migratie, database-invarianten en backup
Het systeem SHALL de catalogusmigratie transactioneel uitvoeren van schema-versie 1 naar 2 en de versie pas na succes vastleggen. Het systeem SHALL een reeds gemigreerde versie-2-database als noop behandelen, SHALL een nieuwere of onbekende versie weigeren zonder iets te wijzigen, SHALL per verbinding `PRAGMA foreign_keys=ON` activeren en SHALL de uniekheid van `feed_url_key` op databaseniveau afdwingen. Het bestaande `/health`-contract SHALL exact ongewijzigd blijven en SHALL niet worden uitgebreid met catalogusvelden of cataloguschecks. Bestaande backup en restore SHALL de catalogusdata bewaren.

#### Scenario: Migratie van versie 1 naar versie 2
- **GIVEN** een database op schema-versie 1 zonder catalogustabellen
- **WHEN** de migratie wordt uitgevoerd
- **THEN** is de schema-versie na afloop 2
- **AND** bestaan alle catalogustabellen
- **AND** retourneert `PRAGMA foreign_key_check` geen rijen

#### Scenario: Migratie op versie 2 is een noop
- **GIVEN** een database op schema-versie 2
- **WHEN** de migratie opnieuw wordt uitgevoerd
- **THEN** blijft de schema-versie 2
- **AND** verandert er geen enkele tabel, index of rij

#### Scenario: Nieuwere of onbekende versie wordt geweigerd
- **GIVEN** een database met een schema-versie hoger dan 2 of met een onbekende waarde
- **WHEN** de migratie wordt uitgevoerd
- **THEN** wordt de migratie geweigerd
- **AND** wordt er niets gewijzigd

#### Scenario: Mislukte migratie rolt terug
- **GIVEN** een database op schema-versie 1
- **WHEN** een fout optreedt tijdens de migratie
- **THEN** worden alle migratiewijzigingen teruggedraaid
- **AND** blijft de schema-versie 1

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
- **GIVEN** de broncatalogus is gemigreerd en bevat data
- **WHEN** `GET /health` wordt uitgevoerd
- **THEN** wordt exact het bestaande health-contract geretourneerd
- **AND** bevat de respons geen catalogusvelden en geen extra componenten

#### Scenario: Backup en restore bewaren de catalogus
- **GIVEN** een backup bestaat van een v2-database met catalogusdata
- **WHEN** die backup wordt gerestaureerd
- **THEN** zijn alle catalogusrijen en hun relaties behouden
- **AND** retourneert `PRAGMA integrity_check` exact `ok`
