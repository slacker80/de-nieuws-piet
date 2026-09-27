# Taken

## 1. Repository Structuur Setup

- [ ] 1.1 Creëer monorepo directory structuur met frontend/, backend/, docker/, docs/ directories
- [ ] 1.2 Initialiseer git repository en configureer basis projectstructuur
- [ ] 1.3 Creëer package.json en package-lock.json voor Node.js afhankelijkheden
- [ ] 1.4 Creëer requirements.txt voor Python afhankelijkheden
- [ ] 1.5 Initialiseer .gitignore met geschikte patronen

## 2. Docker Compose Configuratie

- [ ] 2.1 Creëer Compose bestand `compose.yaml` met alleen `frontend` en `backend` services (SQLite is nooit een service)
- [ ] 2.2 Configureer frontend service met Next.js build en ontwikkelingsopstelling
- [ ] 2.3 Configureer backend service met FastAPI applicatie en afhankelijkheden
- [ ] 2.4 Stel backend-mounted SQLite named volume `nieuws_piet_sqlite_data` in met exacte `name:` identiteit (zonder Compose project prefix), mount `/app/data` en database file `/app/data/news.db`
- [ ] 2.5 Stel netwerkconfiguratie en service afhankelijkheden in
- [ ] 2.6 Valideer Compose configuratie met `docker compose config` (v2 syntax, nooit `docker-compose`)
- [ ] 2.7 Implementeer persistentie verificatie voor SQLite database
- [ ] 2.8 Implementeer reproduceerbare Compose acceptatie met exact `docker compose up -d --build`, service namen, frontend/backend URLs/ports, readiness conditions en curl/assertie commando's
- [ ] 2.9 Implementeer uitvoerbare data-safe rollback/restore met read-only backup bron, backup-integriteitsvalidatie, feitelijk restore voor preserve én destructive pad, en `docker compose down -v` uitsluitend als opt-in (volgorde: backup → validatie → opt-in `down -v` → restore in het opnieuw aangemaakte volume → verificatie; restore nooit vóór `down -v`)

## 3. Next.js PWA Skelet

- [ ] 3.1 Initialiseer Next.js project met PWA-capaciteiten
- [ ] 3.2 Creëer basis applicatie structuur met pages/ en components/ directories
- [ ] 3.3 Implementeer responsief ontwerp met mobile-first aanpak
- [ ] 3.4 Creëer landing page met lege staat voor nieuwsartikelen bij 360px mobiele breedte
- [ ] 3.5 Configureer PWA manifest met valid linked manifest
- [ ] 3.6 Stel service-worker/offline status expliciet in (uitgesloten of alleen skelet)
- [ ] 3.7 Test Next.js applicatie lokaal

## 4. FastAPI Health Endpoint

- [ ] 4.1 Creëer FastAPI applicatie met health endpoint op /health
- [ ] 4.2 Implementeer health checks voor backend en SQLite componenten alleen
- [ ] 4.3 Configureer FastAPI met deterministische minimale contract: exact JSON success/failure body en HTTP codes
- [ ] 4.4 Implementeer gebonden SQLite check/timeout strategie met server probe budget <=500ms
- [ ] 4.5 Voeg health endpoint toe aan Docker Compose health checks
- [ ] 4.6 Test health endpoint met curl en verifieer response formaat
- [ ] 4.7 Implementeer gezonde en failure verificatie
- [ ] 4.8 Test exact JSON success response met Content-Type application/json en HTTP 200
- [ ] 4.9 Test exact JSON SQLite failure response met Content-Type application/json en HTTP 503
- [ ] 4.10 Test exact JSON backend failure response met Content-Type application/json en HTTP 500
- [ ] 4.11 Test exact JSON backend fault injection test response met Content-Type application/json en HTTP 500
- [ ] 4.12 Test `sqlite_timeout` fault met server probe budget <=500ms en client assertion budget <=1000ms
- [ ] 4.13 Test SQLite onbeschikbaarheid via test double (geen verwijderen of wijzigen van database bestanden)
- [ ] 4.14 Implementeer externe frontend smoke verificatie op `http://localhost:3000/` na Docker Compose startup (NOOIT `/health`)
- [ ] 4.15 Implementeer deterministische en test-only failure testing met fault-injection voor SQLite-only failure, SQLite probe timeout, backend internal self-check failure en simultaneous failures
- [ ] 4.16 Implementeer test assertions voor elke response: status, JSON fields/body, headers en timestamp format
- [ ] 4.17 Implementeer test-only fault configuratie via `APP_ENV=test` guard en `APP_HEALTH_FAULT` whitelist (`sqlite`, `sqlite_timeout`, `backend`, `all`) zonder externe API/account/service afhankelijkheid
- [ ] 4.18 Implementeer app-factory/proces-isolatie per health test en reset cleanup zonder filesystem database mutaties
- [ ] 4.19 Test deterministisch gedrag bij onbekende `APP_HEALTH_FAULT` waarden en bij `APP_ENV` ≠ `test` (normale gezonde respons)

## 5. SQLite Database Configuratie

- [ ] 5.1 Creëer SQLite database met minimale configuratie en connectie lifecycle
- [ ] 5.2 Implementeer database initialisatiescript voor connectiviteit en persistentie
- [ ] 5.3 Stel SQLite connectie management in zonder pooling
- [ ] 5.4 Test database operaties en persistentie
- [ ] 5.5 Verifieer SQLite init/persistence across backend container recreation
- [ ] 5.6 Verifieer volume identiteit `nieuws_piet_sqlite_data` in Compose én in losse `docker run` containers (zelfde volume, geen project prefix)

## 6. Lokale Documentatie

- [ ] 6.1 Creëer uitgebreide README.md met setup instructies
- [ ] 6.2 Creëer Docker Compose documentatie (v2 syntax `docker compose`; vermeld dat het pullen van publieke OCI images uitsluitend een bootstrap-afhankelijkheid is — geen runtime externe service, geen account, geen kosten — en pin geen digest zolang de feitelijke digest onbekend is)
- [ ] 6.3 Creëer ontwikkelingsopstelling documentatie
- [ ] 6.4 Creëer troubleshooting documentatie
- [ ] 6.5 Creëer API documentatie voor health endpoint
- [ ] 6.6 Verifieer dat alle documentatie toegankelijk en compleet is
- [ ] 6.7 Creëer data-safe rollback/restore documentatie (preserve versus destructive, read-only backup, integriteitsvalidatie, opt-in `docker compose down -v` alléén na geslaagde backup en validatie, restore direct ná `down -v` in het opnieuw aangemaakte volume, verificatie na herstel)
- [ ] 6.8 Creëer failure testing documentatie (`APP_ENV=test`, `APP_HEALTH_FAULT` whitelist, budgets 500ms/1000ms, geen filesystem mutatie)
- [ ] 6.9 Creëer mobiele Playwright acceptatie documentatie (`npm ci`, lokale browser, readiness vóór `npm run test:e2e`)

## 7. Healthcheck Tests

- [ ] 7.1 Creëer geautomatiseerde healthcheck tests voor backend, SQLite en frontend componenten
- [ ] 7.2 Implementeer tests voor Docker Compose services
- [ ] 7.3 Implementeer tests voor Next.js applicatie
- [ ] 7.4 Implementeer tests voor FastAPI health endpoint
- [ ] 7.5 Implementeer tests voor SQLite database
- [ ] 7.6 Voer healthcheck tests uit en verifieer dat alle tests slagen
- [ ] 7.7 Documenteer health test commando's

## 8. Integratietests

- [ ] 8.1 Test complete applicatie startup met `docker compose up -d --build` (clean-checkout)
- [ ] 8.2 Verifieer dat frontend en backend toegankelijk zijn
- [ ] 8.3 Test health endpoint integratie met Docker Compose
- [ ] 8.4 Verifieer mobiele responsiviteit van Next.js applicatie bij 360px
- [ ] 8.5 Test applicatie functionaliteit met lege staat
- [ ] 8.6 Documenteer succesvolle integratietest resultaten
- [ ] 8.7 Implementeer reproduceerbare mobiele acceptatie bij 360x800 met Playwright, exacte viewport/expected empty-state assertions, geen horizontale scrolling, zichtbare primaire content/navigation
- [ ] 8.8 Voer de frontend/backend readiness loop uit en laat die slagen vóór `npm run test:e2e`

## 9. Exacte Verificatie Taken

### 9.1 Data-safe Rollback Verificatie
- [ ] 9.1.1 Verifieer exacte DB rollback named volume `nieuws_piet_sqlite_data` met exacte Docker volume identiteit (zonder Compose project prefix)
- [ ] 9.1.2 Verifieer backend mount `/app/data` en database file `/app/data/news.db`
- [ ] 9.1.3 Verifieer host backup `./backups/news.db.<UTC timestamp>.bak` outside named volume
- [ ] 9.1.4 Verifieer exacte shell command sequence met `docker compose`/`docker` en standaard shell (geen `docker-compose` v1)
- [ ] 9.1.5 Verifieer stop backend, `mkdir -p backups`, backup vanaf READ-ONLY named volume mount, non-destructive `docker compose down`
- [ ] 9.1.6 Verifieer backup-integriteitsvalidatie met `PRAGMA integrity_check` = `ok` vóór elke destructieve actie; bij falen stopt de procedure
- [ ] 9.1.7 Verifieer feitelijk restore: backup terugzetten naar `/app/data/news.db` in het named volume voor preserve pad én voor destructive reset pad (destructive pad: pas ná opt-in `docker compose down -v`, in het opnieuw aangemaakte volume; nooit vóór `down -v`)
- [ ] 9.1.8 Verifieer `docker compose up -d --build` na restore en integriteitsverificatie via `docker compose exec -i backend python` (`PRAGMA integrity_check` + ten minste één tabel)
- [ ] 9.1.9 Verifieer `curl` /health assertie (exact HTTP 200 én JSON body `status: healthy`)
- [ ] 9.1.10 Verifieer `docker compose down -v` uitsluitend als opt-in en alléén na geslaagde backup en integriteitsvalidatie, met restore direct ná `down -v` in het opnieuw aangemaakte volume `nieuws_piet_sqlite_data` en verificatie van integriteit, data-marker en health direct na restore; verifieer dat GEEN enige stap restore vóór `down -v` voorschrijft

### 9.2 Health Test-only Config Verificatie
- [ ] 9.2.1 Verifieer health test-only exact config: ONLY when `APP_ENV=test`
- [ ] 9.2.2 Verifieer `APP_HEALTH_FAULT` whitelist exact `sqlite`, `sqlite_timeout`, `backend`, `all`
- [ ] 9.2.3 Verifieer deterministisch gedrag bij onbekende `APP_HEALTH_FAULT` waarden en bij `APP_ENV` ≠ `test` (normale gezonde respons)
- [ ] 9.2.4 Verifieer vijf exacte named tests met exacte assertions: `test_healthy_system`, `test_sqlite_failure`, `test_sqlite_timeout`, `test_backend_failure`, `test_combined_failure`
- [ ] 9.2.5 Verifieer `sqlite_timeout` server probe budget <=500ms
- [ ] 9.2.6 Verifieer client assertion budget <=1000ms
- [ ] 9.2.7 Verifieer app-factory/proces-isolatie en reset cleanup per test
- [ ] 9.2.8 Verifieer geen filesystem database mutaties in fault tests (test doubles alleen)

### 9.3 Compose Exact Command Verificatie
- [ ] 9.3.1 Verifieer exact command: `docker compose up -d --build`
- [ ] 9.3.2 Verifieer only `frontend` and `backend` services
- [ ] 9.3.3 Verifieer exact paths URLs
- [ ] 9.3.4 Verifieer copyable shell loop die frontend `http://localhost:3000/` zelfstandig checkt op exact HTTP 200 én body marker `Nieuws Piet`
- [ ] 9.3.5 Verifieer backend `http://localhost:8000/health` op exact HTTP 200 én JSON body `status: healthy`
- [ ] 9.3.6 Verifieer max 30 attempts, sleep 1, curl `--max-time 5`
- [ ] 9.3.7 Verifieer only success if BOTH flags true, otherwise exit nonzero after loop
- [ ] 9.3.8 Verifieer SQLite never a service
- [ ] 9.3.9 Verifieer frontend externe smoke gebruikt `http://localhost:3000/` en NOOIT `/health`

### 9.4 Mobile Exact Verificatie
- [ ] 9.4.1 Verifieer local dev dependency `@playwright/test` version pinned in project lockfile
- [ ] 9.4.2 Verifieer command `npm run test:e2e`
- [ ] 9.4.3 Verifieer start local frontend beforehand met `docker compose up -d --build` + readiness loop
- [ ] 9.4.4 Verifieer `npm ci` en lokale browser setup met `npx playwright install chromium` (geen cloud browser)
- [ ] 9.4.5 Verifieer test `http://localhost:3000/` met localhost `baseURL`, viewport 360x800 ingesteld VÓÓR navigatie
- [ ] 9.4.6 Verifieer assert marker text `Nieuws Piet`
- [ ] 9.4.7 Verifieer visible nav landmark
- [ ] 9.4.8 Verifieer visible main landmark
- [ ] 9.4.9 Verifieer text `Nog geen nieuws beschikbaar`
- [ ] 9.4.10 Verifieer `scrollWidth <= clientWidth`
- [ ] 9.4.11 Verifieer stabiele UI readiness met auto-retry assertions (geen vaste slaaptijd) en netwerkisolatie (alleen localhost toegestaan)
- [ ] 9.4.12 Verifieer explicitly ban accounts/API keys/SaaS/browser cloud/paid services/external APIs for all tests

## 10. Discrete Verified Tasks

### 10.1 Database/local-sqlite Spec Updates
- [ ] 10.1.1 Verifieer DB rollback named volume `nieuws_piet_sqlite_data` (exacte volume identiteit) in spec
- [ ] 10.1.2 Verifieer backend mount `/app/data` and database file `/app/data/news.db` in spec
- [ ] 10.1.3 Verifieer host backup `./backups/news.db.<UTC timestamp>.bak` outside named volume in spec
- [ ] 10.1.4 Verifieer exact shell command sequence met read-only backup bron in spec
- [ ] 10.1.5 Verifieer backup-integriteitsvalidatie, non-destructive `docker compose down` en feitelijk restore in spec
- [ ] 10.1.6 Verifieer `docker compose down -v` uitsluitend als opt-in in spec, met volgorde backup → validatie → `down -v` → restore → verificatie (geen restore vóór `down -v`)

### 10.2 Health-monitoring/health-endpoint Spec Updates
- [ ] 10.2.1 Verifieer health test-only exact config: ONLY when `APP_ENV=test`
- [ ] 10.2.2 Verifieer `APP_HEALTH_FAULT` whitelist `sqlite`, `sqlite_timeout`, `backend`, `all`
- [ ] 10.2.3 Verifieer vijf exacte named tests met exacte assertions inclusief `test_sqlite_timeout`
- [ ] 10.2.4 Verifieer `sqlite_timeout` server probe budget <=500ms
- [ ] 10.2.5 Verifieer client assertion budget <=1000ms
- [ ] 10.2.6 Verifieer app-factory/proces-isolatie, reset cleanup en geen filesystem database mutaties

### 10.3 Local-development/setup Spec Updates
- [ ] 10.3.1 Verifieer exact command: `docker compose up -d --build`
- [ ] 10.3.2 Verifieer only `frontend` and `backend` services
- [ ] 10.3.3 Verifieer copyable shell loop met exacte HTTP status én body assertions voor frontend en backend
- [ ] 10.3.4 Verifieer max 30 attempts, sleep 1, curl `--max-time 5`
- [ ] 10.3.5 Verifieer SQLite never a service
- [ ] 10.3.6 Verifieer frontend smoke op `http://localhost:3000/` en NOOIT `/health`

### 10.4 Documentation/local-dev Spec Updates
- [ ] 10.4.1 Verifieer mobile exact: local dev dependency `@playwright/test` version pinned
- [ ] 10.4.2 Verifieer command `npm run test:e2e` na geslaagde readiness loop
- [ ] 10.4.3 Verifieer test `http://localhost:3000/`, viewport 360x800 vóór navigatie
- [ ] 10.4.4 Verifieer assert marker text `Nieuws Piet`, visible nav landmark, visible main landmark
- [ ] 10.4.5 Verifieer text `Nog geen nieuws beschikbaar`, and `scrollWidth <= clientWidth`
- [ ] 10.4.6 Verifieer explicitly ban accounts/API keys/SaaS/browser cloud/paid services/external APIs
- [ ] 10.4.7 Verifieer rollback-, failure testing- en Playwright documentatie bevatten de exacte commando's en budgetten

### 10.5 Design.md Updates
- [ ] 10.5.1 Verifieer design decisions reflect new requirements
- [ ] 10.5.2 Verifieer architecture decisions align with exact specifications
- [ ] 10.5.3 Verifieer technology stack decisions support all requirements
- [ ] 10.5.4 Verifieer risk mitigation strategies address new requirements
- [ ] 10.5.5 Verifieer migration plan uses `docker compose up -d --build` en bevat geen verouderde `docker-compose` commando's

### 10.6 Tasks.md Updates
- [ ] 10.6.1 Verifieer discrete verified tasks for each acceptance
- [ ] 10.6.2 Verifieer use Dutch prose but exact SHALL/MUST and Given/When/Then in specs
- [ ] 10.6.3 Verifieer ensure no duplicate timeout/rollback
- [ ] 10.6.4 Verifieer all tasks are actionable and testable
- [ ] 10.6.5 Verifieer geen verouderde `docker-compose` (v1) commando's of obsolete taken meer voorkomen
