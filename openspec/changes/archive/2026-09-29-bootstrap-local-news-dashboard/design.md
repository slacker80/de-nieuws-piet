# Design

## Context

Het project vereist een lokale, mobiele persoonlijke nieuwssite met een monorepo-structuur. Dit wijzigingsvoorstel vestigt de complete lokale ontwikkelomgeving met alle noodzakelijke componenten die de fundamentele basis vormen voor daaropvolgende features. De architectuur volgt de bestaande projectvisie: lokale ontwikkeling met Docker Compose, Next.js PWA frontend, FastAPI backend en SQLite database. Dit wijzigingsvoorstel richt zich op het vestigen van de basisinfrastructuur zonder externe afhankelijkheden of publieke toegang (de enige publieke netwerkafhankelijkheid is het eenmalig pullen van publieke OCI images als bootstrap-stap, niet als runtime-afhankelijkheid).

## Doelen / Niet-doelen

**Doelen:**
- Vestig een complete lokale ontwikkelomgeving met alle noodzakelijke componenten
- Creëer een reproduceerbare opstelling die werkt op een standaard Linux ontwikkelmachine
- Bied health monitoring capabilities voor alle applicatiecomponenten
- Implementeer uitgebreide lokale documentatie voor toekomstige ontwikkelaars
- Zorg dat het systeem met één commando (`docker compose up -d --build`) kan worden gestart
- Implementeer uitvoerbare data-safe rollback/restore met concrete shell commando's, read-only backup bron, backup-integriteitsvalidatie en feitelijk restore
- Implementeer deterministische en test-only failure testing met `APP_ENV=test` guard en `APP_HEALTH_FAULT` whitelist
- Implementeer reproduceerbare mobiele acceptatie bij 360x800 met lokaal gepinde Playwright tests

**Niet-doelen:**
- Implementeer RSS feed ingang of externe API-integraties
- Creëer gebruikersauthenticatie of accountbeheer
- Stel publieke toegang of HTTPS in
- Implementeer LLM-gebaseerde samenvatting of externe AI-services
- Creëer Telegram notificatiesysteem
- Stel Kubernetes of cloud implementatie in
- Gebruik accounts, API keys, SaaS, browser cloud, betaalde diensten of externe API's in tests

## Beslissingen

### Technology Stack Beslissing
**Beslissing**: Gebruik Docker Compose voor lokale ontwikkeling, Next.js voor frontend, FastAPI voor backend en SQLite voor database.

**Redenering**: Deze stack biedt een moderne, Python-gebaseerde backend met een React-gebaseerde frontend, beide containerized voor consistentie. SQLite is gekozen vanwege zijn eenvoud en zero-configuratie aard, perfect voor lokale ontwikkeling. Docker Compose zorgt ervoor dat alle services naadloos samenwerken.

**Alternatieven Overwogen**:
- PostgreSQL/MySQL in plaats van SQLite: SQLite is eenvoudiger voor lokale ontwikkeling en vereist geen setup
- Express.js in plaats van FastAPI: FastAPI biedt betere API-documentatie en validatie
- Create React in plaats van Next.js: Next.js biedt betere SEO en PWA-capaciteiten out of the box

### Architectuur Beslissing
**Beslissing**: Gebruik een monorepo-structuur met duidelijke scheiding van zorgen tussen frontend, backend en infrastructuur.

**Redenering**: Monorepo vereenvoudigt dependency management en biedt een enkele bron van waarheid voor het project. Duidelijke scheiding stelt teams in staat om onafhankelijk aan verschillende componenten te werken terwijl consistentie behouden blijft.

**Alternatieven Overwogen**:
- Separate repositories: Zou dependency management en CI/CD compliceren
- Monolithische architectuur: Zou moeilijker te onderhouden en te schalen zijn

### Health Monitoring Beslissing
**Beslissing**: Implementeer een gecentraliseerde health endpoint die alle applicatiecomponenten bewaken.

**Redenering**: Gecentraliseerde health monitoring biedt een enkel punt van waarheid voor systeembron en vereenvoudigt probleemoplossing. Het integreert ook goed met Docker Compose health checks.

**Alternatieven Overwogen**:
- Separate health endpoints voor elke component: Zou clients dwingen om meerdere endpoints te controleren
- Geen health monitoring: Zou probleemoplossing moeilijker maken

### Documentatie Beslissing
**Beslissing**: Creëer uitgebreide lokale ontwikkeldocumentatie als onderdeel van het bootstrap wijzigingsvoorstel.

**Redenering**: Goede documentatie reduceert onboarding tijd en zorgt voor consistentie tussen teamleden. Het dient ook als levende documentatie voor de systeemarchitectuur.

**Alternatieven Overwogen**:
- Minimale documentatie: Zou onboarding tijd verhogen en kennis silos creëren
- Externe documentatie alleen: Zou moeilijker te synchroniseren zijn met de codebase

### Datamodel, API-contracten en foutafhandeling
**Beslissing**: Deze bootstrap beperkt het datamodel tot lokale persistentie in SQLite (database file `/app/data/news.db` in named volume `nieuws_piet_sqlite_data`) zonder externe bronnen; het volledige artikel-datamodel volgt in latere wijzigingen. Het API-contract van deze bootstrap is exact het `/health` contract: HTTP 200 gezond, HTTP 503 SQLite-ongezond (en combinatie), HTTP 500 backend-ongezond, met vaste JSON bodies en dynamische RFC3339 UTC timestamp.

**Redenering**: Een exact, klein API-contract maakt readiness verificatie en fault tests deterministisch. Foutafhandeling gebeurt via de health status codes en `error` velden; onbekende fault-waarden worden expliciet genegeerd in plaats van als interne fout te verschijnen.

**Alternatieven Overwogen**:
- Alleen generieke 500-fouten: Zou onderscheid tussen backend- en database-storingen wegnemen
- Datamodel nu al uitbreiden met ingestie: Zou buiten de scope van deze bootstrap vallen

### Modulegrenzen
**Beslissing**: Houd frontend (`frontend/`), backend (`backend/`) en toekomstige ingestie als afzonderlijke modules met eigen dependencies en documentatie; de Compose configuratie is de enige plek waar ze samenkomen.

**Redenering**: Duidelijke modulegrenzen maken het mogelijk om frontend en backend onafhankelijk te testen (health tests alleen in de backend, e2e tests alleen tegen de frontend) en houden de lokale opstelling reproduceerbaar.

**Alternatieven Overwogen**:
- Gedeelde dependencies tussen frontend en backend: Zou versieconflicten introduceren

### Teststrategie
**Beslissing**: Test in drie lagen: (1) unit/integration tests van de FastAPI health contracten met app-factory isolatie en `APP_ENV=test` fault configuratie; (2) Compose readiness verificatie met exacte status- en body-asserties via `docker compose up -d --build`; (3) lokale Playwright e2e op 360x800 met `npm run test:e2e` na de readiness loop, zonder accounts, SaaS, browser cloud, betaalde diensten of externe API's.

**Redenering**: De lagen zijn onafhankelijk van elkaar te draaien en gebruiken allemaal dezelfde exacte contracten uit de delta specs; lokale uitvoering houdt tests reproduceerbaar en kostenvrij.

**Alternatieven Overwogen**:
- Alleen handmatige tests: Zou regressies niet vroeg detecteren
- Tests via cloud/browser-SaaS: Zou accounts en betaalde diensten introduceren

### Compose Acceptance Beslissing
**Beslissing**: Implementeer reproduceerbare Docker Compose acceptatie met exact `docker compose up -d --build` (v2 syntax), alleen services `frontend` en `backend`, frontend/backend URLs/ports, een copyable readiness loop met exacte HTTP status 200 assertions én body assertions, en curl/assertie commando's.

**Redenering**: Reproduceerbare Compose acceptatie zorgt ervoor dat alle ontwikkelaars dezelfde opstelling hebben en kan snel verifiëren dat de applicatie correct werkt. Exacte status- en body-asserties (frontend marker `Nieuws Piet`, backend JSON `status: healthy`) elimineren valse positieven; uitsluitend frontend en backend worden gecheckt omdat SQLite geen service is.

**Alternatieven Overwogen**:
- Handmatige acceptatie: Zou inconsistent zijn tussen teamleden
- Geen acceptatie: Zou problemen later in het proces laten ontdekken
- `docker compose up -d` zonder `--build`: Zou stale images kunnen serveren
- Frontend smoke op `/health`: Zou een backend endpoint als frontend controle gebruiken

### Data-Safe Rollback Beslissing
**Beslissing**: Implementeer uitvoerbare data-safe rollback/restore op named volume `nieuws_piet_sqlite_data` (exacte Docker volume identiteit via `name:`, backend mount `/app/data`, database file `/app/data/news.db`) met host backup `./backups/news.db.<UTC timestamp>.bak` buiten het volume, backup vanaf een read-only mount (`:ro`), `PRAGMA integrity_check` validatie van de backup vóór elke destructieve actie, feitelijk restore voor zowel preserve als destructive pad, en `docker compose down -v` uitsluitend als opt-in. Vaste volgorde op het destructive pad: backup → integriteitsvalidatie → opt-in `docker compose down -v` → restore in het opnieuw aangemaakte volume → verificatie van integriteit, data-marker en health; restore vindt nooit vóór `docker compose down -v` plaats.

**Redenering**: Data-safe rollback beschermt tegen gegevensverlies. Een gevalideerde backup vóór elke destructieve actie voorkomt herstel op basis van een corrupt bestand; een feitelijk restore-commando (niet alleen een procedurebeschrijving) maakt beide paden uitvoerbaar; de expliciete volume identiteit zorgt dat Compose en losse `docker run` commando's hetzelfde volume gebruiken.

**Alternatieven Overwogen**:
- Geen rollback plan: Zou risico's introduceren voor gegevensverlies
- Extern backup: Zou externe afhankelijkheden introduceren
- `docker compose down -v` als standaard stap: Zou altijd volumeverlies veroorzaken
- Alleen backup zonder integriteitsvalidatie: Zou een corrupte backup als herstelbron gebruiken

### Failure Testing Beslissing
**Beslissing**: Implementeer deterministische en test-only failure testing met `APP_ENV=test` als guard en `APP_HEALTH_FAULT` whitelist `sqlite`, `sqlite_timeout`, `backend`, `all`. Onbekende waarden worden deterministisch genegeerd. Elke test bouwt een nieuwe applicatie-instance via een app-factory (proces-/instance-isolatie) en reset de environment na afloop. Fault injection gebruikt uitsluitend test doubles en voert nooit filesystem database mutaties uit. Budgetten: server probe <=500ms, client assertion <=1000ms.

**Redenering**: Deterministische failure testing zorgt ervoor dat het systeem kan worden getest onder verschillende storingen zonder externe afhankelijkheden. De `APP_ENV=test` guard sluit productiegebruik uit; app-factory isolatie voorkomt state-leak tussen tests; het verbod op filesystem mutatie beschermt de echte database; de gescheiden 500ms/1000ms budgetten voorkomen race conditions.

**Alternatieven Overwogen**:
- Onbetrouwbare failure testing: Zou onbetrouwbare testresultaten produceren
- Externe failure testing: Zou externe afhankelijkheden introduceren
- Fault injection via databasebestand hernoemen/verwijderen: Zou filesystem mutatie en onvoorspelbare state introduceren
- Module-globale fault vlag: Zou state tussen tests lekken

### Mobile Acceptance Beslissing
**Beslissing**: Implementeer reproduceerbare mobiele acceptatie met lokaal gepinde `@playwright/test` in de lockfile, `npm ci` plus lokale browser setup (`npx playwright install chromium`), `npm run test:e2e` pas na een geslaagde Compose readiness loop, viewport 360x800 vóór navigatie, stabiele UI readiness via auto-retry assertions, localhost `baseURL` met netwerkisolatie, en exacte assertions op marker `Nieuws Piet`, `nav`, `main`, `Nog geen nieuws beschikbaar` en `scrollWidth <= clientWidth`.

**Redenering**: Reproduceerbare mobiele acceptatie zorgt ervoor dat de applicatie correct werkt op mobiele apparaten. Pinnen in de lockfile plus lokale browser setup vermijdt cloud browsers en niet-reproduceerbare versies; viewport vóór navigatie voorkomt layout-metingen op verkeerde breedte; netwerkisolatie houdt alle testverkeer op localhost.

**Alternatieven Overwogen**:
- Handmatige mobiele acceptatie: Zou inconsistent zijn tussen apparaten
- Geen mobiele acceptatie: Zou mobiele problemen later in het proces laten ontdekken
- Cloud browser/SaaS testdiensten: Zou accounts, betaalde diensten en externe API's introduceren
- Vaste slaaptijd als readiness: Zou flauwe tests produceren

## Risico's / Trade-offs

### Risico: Docker afhankelijkheid
**Risico**: Ontwikkelaars hebben mogelijk Docker niet geïnstalleerd of hebben problemen met Docker configuratie.

**Mitigatie**: Bied duidelijke installatie-instructies en alternatieve setup methoden in documentatie. Neem fallback instructies op voor systemen zonder Docker.

**Klarering OCI images**: Het eenmalig pullen van publieke OCI images (basisbeelden plus `alpine:3.20` voor backup/restore) is uitsluitend een bootstrap-afhankelijkheid van `docker compose up -d --build`; het is GEEN runtime-afhankelijkheid, geen externe dienst, geen account en geen kost — na de eerste pull zijn de beelden lokaal en draait de opstelling volledig offline. Er wordt geen digest gepind zolang de feitelijke digest niet bekend is; images worden bij tag geadresseerd.

### Risico: SQLite beperkingen
**Risico**: SQLite kan niet zo goed presteren als productiedatabases met hoge verkeersbelasting.

**Mitigatie**: Dit is acceptabel voor lokale ontwikkeling en het systeem kan gemakkelijk gemigreerd worden naar een productiedatabase later.

### Risico: Complexiteit van monorepo
**Risico**: Monorepo kan complex worden naarmate het project groeit.

**Mitigatie**: Begin met een eenvoudige structuur en refactor indien complexiteit een probleem wordt.

### Trade-off: Ontwikkeling vs. Productie
**Trade-off**: De lokale ontwikkelopstelling kan significant verschillen van productieopstelling.

**Mitigatie**: Documenteer de verschillen duidelijk en plan voor migratie naarmate het project groeit.

### Risico: Test-only configuratie
**Risico**: Test-only configuratie kan per ongeluk in productie terechtkomen.

**Mitigatie**: Gebruik de guard `APP_ENV=test` in combinatie met de whitelist `APP_HEALTH_FAULT` (`sqlite`, `sqlite_timeout`, `backend`, `all`), negeer elke andere waarde deterministisch en documenteer dat deze configuratie uitsluitend voor testomgevingen is.

### Risico: Onjuiste of corrupte backup
**Risico**: Een rollback op basis van een corrupte of ontbrekende backup kan tot dataverlies leiden.

**Mitigatie**: Valideer elke backup met `PRAGMA integrity_check` (exact `ok`) vóór elke destructieve actie, voer restore altijd uit vanaf een read-only host-backup buiten het named volume (op het destructive pad pas ná opt-in `docker compose down -v`, in het opnieuw aangemaakte volume) en verifieer database-integriteit, data-marker (ten minste één tabel) én health endpoint direct na herstel. `docker compose down -v` blijft uitsluitend opt-in en alléén na geslaagde backup en validatie; restore staat nooit vóór `down -v`.

### Risico: Mobiele test afhankelijkheid
**Risico**: Mobiele test afhankelijkheid kan problemen introduceren als Playwright of de lokale browser niet correct is geïnstalleerd.

**Mitigatie**: Pin `@playwright/test` in de lockfile, installeer met `npm ci` en documenteer de lokale browser setup (`npx playwright install chromium`) plus een fallback handmatige check van 360px breedte.

## Migratie Plan

### Fase 1: Initiële Setup
1. Clone de repository
2. Installeer Docker en Docker Compose (v2 plugin, commando `docker compose`)
3. Voer `docker compose up -d --build` uit om de `frontend` en `backend` services te starten
4. Voer de frontend/backend readiness loop uit (max 30 attempts, `sleep 1`, `curl --max-time 5`)
5. Open de applicatie op `http://localhost:3000`

### Fase 2: Ontwikkeling
1. Maak wijzigingen aan frontend code in `frontend/` directory
2. Maak wijzigingen aan backend code in `backend/` directory
3. Voer `docker compose up -d --build` uit om wijzigingen toe te passen
4. Voer de readiness loop opnieuw uit en controleer daarna `npm run test:e2e` voor mobiele acceptatie
5. Gebruik health endpoint op `http://localhost:8000/health` (nooit als frontend controle) om systeemstatus te verifiëren

### Fase 3: Productie Migratie
1. Vervang SQLite met PostgreSQL/MySQL
2. Stel reverse proxy (nginx) in voor HTTPS
3. Configureer load balancing
4. Stel monitoring en logging in

## Open Vragen

### Vraag: Database migratie strategie
**Vraag**: Wat is de beste aanpak voor het migreren van SQLite naar een productiedatabase?

**Impact**: Deze beslissing beïnvloedt het databaseschema en migratie-strategie.

### Vraag: Frontend build proces
**Vraag**: Wat is de optimale build proces voor de Next.js applicatie?

**Impact**: Dit beïnvloedt ontwikkelworkflow en implementatiestrategie.

### Vraag: Backend API versioning
**Vraag**: Moet de FastAPI backend API versioning vanaf het begin bevatten?

**Impact**: Dit beïnvloedt API-ontwerp en toekomstige wijzigingen.

### Vraag: Docker image optimalisatie
**Vraag**: Wat is de optimale strategie voor Docker image optimalisatie?

**Impact**: Dit beïnvloedt implementatie performance en resource usage.