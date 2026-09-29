# Discrete Verified Tasks Documentatie

## Overzicht

Dit document beschrijft de discrete verified tasks voor Nieuws Piet. Het dekt alle stappen af voor elke acceptance met exacte assertions en verificatie.

## Doel

- Implementeer discrete verified tasks voor elke acceptance
- Zorg ervoor dat elke taak actionable en testable is
- Gebruik Dutch prose maar exact SHALL/MUST en Given/When/Then in specs
- Zorg ervoor dat er geen duplicate timeout/rollback taken zijn
- Zorg ervoor dat er geen verouderde `docker-compose` (v1) commando's of obsolete taken meer voorkomen

## Vereisten

### Systeemvereisten

- **Node.js**: >= 20
- **Python**: >= 3.10
- **Docker**: Versie 20.10 of hoger (Compose v2 plugin)
- **pytest**: Testrunner voor backend
- **httpx**: HTTP client voor tests

### Aanbevolen Tools

- **VS Code** met Python en Docker extensies
- **GitHub Desktop** (optioneel) voor Git GUI
- **Postman** of **Insomnia** voor API testing (optioneel)

## Discrete Verified Tasks

### 1. Database/local-sqlite Spec Updates

#### 1.1 Verifieer DB rollback named volume `nieuws_piet_sqlite_data` (exacte volume identiteit) in spec

**Doel**: Controleer dat het SQLite named volume exacte identiteit `nieuws_piet_sqlite_data` heeft (zonder Compose project prefix)

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md`

**Verificatie**:

```bash
# Controleer volume definitie in compose.yaml
grep -A 5 "volumes:" compose.yaml | grep "nieuws_piet_sqlite_data"

# Controleer volume naam in compose.yaml
grep "name: nieuws_piet_sqlite_data" compose.yaml

# Controleer dat volume identiteit exact is (geen project prefix)
# Volledige volume naam moet exact `nieuws_piet_sqlite_data` zijn
```

**Expected Resultaat**:
- Volume definitie in compose.yaml: `name: nieuws_piet_sqlite_data`
- Geen project prefix in volume naam
- Volume wordt gebruikt in backend service

#### 1.2 Verifieer backend mount `/app/data` and database file `/app/data/news.db` in spec

**Doel**: Controleer dat backend SQLite database file exacte pad `/app/data/news.db` heeft

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md`

**Verificatie**:

```bash
# Controleer backend volume mount in compose.yaml
grep -A 10 "backend:" compose.yaml | grep "volumes:"

# Controleer dat volume mount `/app/data` is
# Backend volume mount moet `- nieuws_piet_sqlite_data:/app/data` zijn

# Controleer database file pad in backend Dockerfile
grep "COPY" backend/Dockerfile | grep "news.db"
```

**Expected Resultaat**:
- Backend volume mount: `- nieuws_piet_sqlite_data:/app/data`
- Database file pad: `/app/data/news.db`
- Database file wordt gemaakt door backend init script

#### 1.3 Verifieer host backup `./backups/news.db.<UTC timestamp>.bak` outside named volume in spec

**Doel**: Controleer dat host backup pad exacte `./backups/news.db.<UTC timestamp>.bak` is (buiten het named volume)

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md`

**Verificatie**:

```bash
# Controleer backup commando in rollback script
grep -A 5 "backup" scripts/preserve-rollback.sh | grep "backups/"

# Controleer backup pad in backup script
grep "BACKUP_NAME" scripts/preserve-rollback.sh

# Controleer dat backup directory buiten volume is
# Backup moet naar `./backups/` op host zijn
```

**Expected Resultaat**:
- Backup pad: `./backups/news.db.<UTC timestamp>.bak`
- Backup directory buiten named volume
- Backup commando gebruikt read-only volume mount

#### 1.4 Verifieer exact shell command sequence met read-only backup bron in spec

**Doel**: Controleer dat exacte shell commando sequence met read-only backup bron wordt gebruikt

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md`

**Verificatie**:

```bash
# Controleer backup script in spec.md
grep -A 20 "Scenario: Backup met read-only bron" openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md

# Controleer dat script:
# 1. Backend stoppen
docker compose stop backend

# 2. Backup directory maken
mkdir -p backups

# 3. Backup met read-only volume mount
# Gebruik alpine:3.20 met -v nieuws_piet_sqlite_data:/source:ro
```

**Expected Resultaat**:
- Exacte shell sequence in spec
- Read-only volume mount (`:ro`)
- Backup commando gebruikt `alpine:3.20`
- Backup file wordt gekopieerd naar host

#### 1.5 Verifieer backup-integriteitsvalidatie, non-destructive `docker compose down` en feitelijk restore in spec

**Doel**: Controleer dat backup-integriteitsvalidatie, non-destructive `docker compose down` en feitelijk restore worden beschreven in spec

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md`

**Verificatie**:

```bash
# Controleer integriteitsvalidatie script in spec.md
grep -A 20 "Scenario: Backup integriteitsvalidatie" openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md

# Controleer dat script:
# 1. Backup read-only opent
# 2. PRAGMA integrity_check wordt uitgevoerd
# 3. Exact resultaat `ok` vereist
# 4. Ongeldige backup stopt procedure

# Controleer non-destructive down
grep -A 10 "Scenario: Preserve pad zonder volume verlies" openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md

# Controleer feitelijk restore
grep -A 10 "Scenario: Feitelijk restore van backup naar named volume" openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md
```

**Expected Resultaat**:
- Backup integriteitsvalidatie met `PRAGMA integrity_check`
- Non-destructive `docker compose down` (volume behouden)
- Feitelijk restore van backup naar named volume
- Verificatie na herstel

#### 1.6 Verifieer `docker compose down -v` uitsluitend als opt-in in spec, met volgorde backup → validatie → `down -v` → restore → verificatie (geen restore vóór `down -v`)

**Doel**: Controleer dat `docker compose down -v` uitsluitend als opt-in wordt beschreven in spec

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md`

**Verificatie**:

```bash
# Controleer opt-in only voor `docker compose down -v`
grep -A 10 "Scenario: Opt-in only voor `docker compose down -v`" openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md

# Controleer dat script:
# 1. Standaard stap: `docker compose down` zonder `-v`
# 2. Opt-in stap: `docker compose down -v` alléén na geslaagde backup en validatie
# 3. Restore volgt DIRECT NA down -v (nooit ervóór)
# 4. Restore in het opnieuw aangemaakte volume
# 5. Verificatie van integriteit, data-marker en health
```

**Expected Resultaat**:
- `docker compose down` als standaard (volume behouden)
- `docker compose down -v` uitsluitend als opt-in
- Restore DIRECT NA `down -v` (nooit ervóór)
- Volledige verificatie na herstel

### 2. Health-monitoring/health-endpoint Spec Updates

#### 2.1 Verifieer health test-only exact config: ONLY when `APP_ENV=test`

**Doel**: Controleer dat health test-only exact config alleen actief is wanneer `APP_ENV` exact de waarde `test` heeft

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md`

**Verificatie**:

```bash
# Controleer test-only config in spec.md
grep -A 10 "Scenario: Normaal gedrag buiten test-omgeving" openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md

# Controleer dat script:
# 1. APP_ENV=test is gezet
# 2. APP_HEALTH_FAULT wordt gelezen
# 3. Normale gezonde contract (HTTP 200) geldt
# 4. Geen fault injection buiten test-omgeving
```

**Expected Resultaat**:
- Test-only config alleen actief met `APP_ENV=test`
- Normale gezonde respons buiten test-omgeving
- Geen side-effect op productieomgeving

#### 2.2 Verifieer `APP_HEALTH_FAULT` whitelist `sqlite`, `sqlite_timeout`, `backend`, `all`

**Doel**: Controleer dat `APP_HEALTH_FAULT` exacte whitelist heeft (`sqlite`, `sqlite_timeout`, `backend`, `all`)

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md`

**Verificatie**:

```bash
# Controleer whitelist in spec.md
grep -A 5 "Scenario: Exacte whitelist van `APP_HEALTH_FAULT`" openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md

# Controleer dat script:
# 1. Whitelist exact: `sqlite`, `sqlite_timeout`, `backend`, `all`
# 2. Elke andere waarde deterministisch genegeerd
# 3. Onbekende waarden worden genegeerd
```

**Expected Resultaat**:
- Exacte whitelist van vier waarden
- Onbekende waarden deterministisch genegeerd
- Geen valse positieve fault injection

#### 2.3 Verifieer vijf exacte named tests met exacte assertions inclusief `test_sqlite_timeout`

**Doel**: Controleer dat vijf exacte named tests met exacte assertions worden beschreven

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md`

**Verificatie**:

```bash
# Controleer test scenarios in spec.md
grep -A 30 "### Requirement: Health endpoint test scenarios" openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md

# Controleer dat script:
# 1. Test 1 - `test_healthy_system`
# 2. Test 2 - `test_sqlite_failure`
# 3. Test 3 - `test_sqlite_timeout`
# 4. Test 4 - `test_backend_failure`
# 5. Test 5 - `test_combined_failure`
# Elke test met exacte assertions
```

**Expected Resultaat**:
- Vijf exacte named tests
- Elke test met exacte assertions
- `test_sqlite_timeout` inclusief
- Deterministische test uitvoering

#### 2.4 Verifieer `sqlite_timeout` server probe budget <=500ms

**Doel**: Controleer dat `sqlite_timeout` server probe budget <=500ms wordt geverifieerd

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md`

**Verificatie**:

```bash
# Controleer server probe budget in spec.md
grep -A 5 "Server-side probe budget: de SQLite probe MUST worden afgekapt binnen <=500ms" openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md

# Controleer dat script:
# 1. Server probe budget: <=500ms
# 2. Client assertion budget: <=1000ms
# 3. Race conditions voorkomen
```

**Expected Resultaat**:
- Server probe budget: <=500ms
- Client assertion budget: <=1000ms
- Race conditions voorkomen

#### 2.5 Verifieer client assertion budget <=1000ms

**Doel**: Controleer dat client assertion budget <=1000ms wordt geverifieerd

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md`

**Verificatie**:

```bash
# Controleer client assertion budget in spec.md
grep -A 5 "Client-side assertion budget: totale response MUST voltooid zijn binnen <=1000ms" openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md

# Controleer dat script:
# 1. Client assertion budget: <=1000ms
# 2. Totale response voltooid binnen budget
# 3. Geen valse positieve timeouts
```

**Expected Resultaat**:
- Client assertion budget: <=1000ms
- Totale response voltooid binnen budget
- Geen valse positieve timeouts

#### 2.6 Verifieer app-factory/proces-isolatie, reset cleanup en geen filesystem database mutaties

**Doel**: Controleer dat app-factory/proces-isolatie, reset cleanup en geen filesystem database mutaties worden beschreven

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md`

**Verificatie**:

```bash
# Controleer app-factory isolatie in spec.md
grep -A 15 "### Requirement: Health endpoint test isolatie en reset" openspec/changes/bootstrap-local-news-dashboard/specs/health-monitoring/health-endpoint/spec.md

# Controleer dat script:
# 1. Elke test op een via app-factory nieuw geconstrueerde applicatie-instance
# 2. Reset cleanup per test
# 3. GEEN module-globale state met eerdere tests
# 4. GEEN database bestanden gewijzigd
# 5. Volgende test start met schone, normale health check status
```

**Expected Resultaat**:
- App-factory isolatie per test
- Reset cleanup per test
- Geen module-globale state lekken
- Geen filesystem database mutaties
- Schone test state

### 3. Local-development/setup Spec Updates

#### 3.1 Verifieer exact command: `docker compose up -d --build`

**Doel**: Controleer dat exact `docker compose up -d --build` wordt gebruikt voor start, herstart na wijzigingen en als precondition voor readiness verificatie

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md`

**Verificatie**:

```bash
# Controleer exact compose command in spec.md
grep -A 10 "### Requirement: Exact compose command" openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md

# Controleer dat script:
# 1. Exact `docker compose up -d --build` gebruikt
# 2. EXCLUSIEF laten starten op frontend en backend services
# 3. SQLite is backend-volume mounted, nooit een service
```

**Expected Resultaat**:
- Exact `docker compose up -d --build`
- Alleen frontend en backend services
- SQLite is backend-volume mounted
- Geen andere services

#### 3.2 Verifieer only `frontend` and `backend` services

**Doel**: Controleer dat alleen `frontend` en `backend` services worden gestart

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md`

**Verificatie**:

```bash
# Controleer service definitie in spec.md
grep -A 10 "### Requirement: Docker Compose service definitie" openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md

# Controleer dat script:
# 1. Alleen `frontend` en `backend` services gedefinieerd
# 2. SQLite is backend-volume mounted (`nieuws_piet_sqlite_data`)
# 3. Geen andere services
```

**Expected Resultaat**:
- Alleen `frontend` en `backend` services
- SQLite is backend-volume mounted
- Geen andere services

#### 3.3 Verifieer copyable shell loop met exacte HTTP status én body assertions voor frontend en backend

**Doel**: Controleer dat copyable shell loop met exacte HTTP status en body assertions wordt beschreven

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md`

**Verificatie**:

```bash
# Controleer readiness shell loop in spec.md
grep -A 50 "### Requirement: Exacte readiness shell loop" openspec/changes/bootstrap-local-news-dashboard/specs/local-development/setup/spec.md

# Controleer dat script:
# 1. Frontend `http://localhost:3000/` gecontroleerd op HTTP 200 EN marker `Nieuws Piet`
# 2. Backend `http://localhost:8000/health` gecontroleerd op HTTP 200 EN JSON body `status: healthy`
# 3. Exacte shell loop met status en body assertions
# 4. Alleen frontend en backend worden gecheckt
```

**Expected Resultaat**:
- Frontend HTTP 200 + marker `Nieuws Piet`
- Backend HTTP 200 + JSON body `status: healthy`
- Exacte shell loop
- Alleen frontend en backend gecheckt

### 4. Documentation/local-dev Spec Updates

#### 4.1 Verifieer mobile exact: local dev dependency `@playwright/test` version pinned

**Doel**: Controleer dat mobile exact: local dev dependency `@playwright/test` version pinned in project lockfile

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md`

**Verificatie**:

```bash
# Controleer exact Playwright test configuratie in spec.md
grep -A 10 "### Requirement: Exact Playwright test configuratie" openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md

# Controleer dat script:
# 1. `@playwright/test` als lokale dev dependency exact version pinned
# 2. In project lockfile (`package-lock.json`)
# 3. Dependencies geïnstalleerd met `npm ci`
# 4. Browser lokaal geïnstalleerd met `npx playwright install chromium`
```

**Expected Resultaat**:
- `@playwright/test` exact version pinned
- In project lockfile
- Dependencies geïnstalleerd met `npm ci`
- Browser lokaal geïnstalleerd

#### 4.2 Verifieer command `npm run test:e2e` na geslaagde readiness loop

**Doel**: Controleer dat command `npm run test:e2e` na geslaagde readiness loop

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md`

**Verificatie**:

```bash
# Controleer readiness precondition voor e2e in spec.md
grep -A 10 "### Requirement: Readiness precondition voor e2e" openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md

# Controleer dat script:
# 1. Eerst `docker compose up -d --build` uitgevoerd
# 2. Frontend/backend readiness loop slaagt voordat `npm run test:e2e` start
# 3. Test commando `npm run test:e2e` gedefinieerd
```

**Expected Resultaat**:
- `docker compose up -d --build` eerst uitgevoerd
- Frontend/backend readiness loop slaagt
- `npm run test:e2e` start na readiness

#### 4.3 Verifieer test `http://localhost:3000/`, viewport 360x800 vóór navigatie

**Doel**: Controleer dat test `http://localhost:3000/`, viewport 360x800 vóór navigatie

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md`

**Verificatie**:

```bash
# Controleer exact Playwright test implementatie in spec.md
grep -A 30 "### Requirement: Exact Playwright test implementatie" openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md

# Controleer dat script:
# 1. Viewport 360x800 wordt ingesteld VÓÓÓR navigatie
# 2. Navigatie naar `http://localhost:3000/`
# 3. Exacte assertions: marker `Nieuws Piet`, zichtbare `nav` landmark, zichtbare `main` landmark
# 4. Text `Nog geen nieuws beschikbaar` en `scrollWidth <= clientWidth`
```

**Expected Resultaat**:
- Viewport 360x800 vóór navigatie
- Test `http://localhost:3000/`
- Exacte assertions
- Mobiele responsiviteit

#### 4.4 Verifieer assert marker text `Nieuws Piet`, visible nav landmark, visible main landmark

**Doel**: Controleer dat assert marker text `Nieuws Piet`, visible nav landmark, visible main landmark

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md`

**Verificatie**:

```bash
# Controleer exact assertions in spec.md
grep -A 10 "await expect(page.getByText('Nieuws Piet').first()).toBeVisible();" openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md

# Controleer dat script:
# 1. await expect(page.getByText('Nieuws Piet').first()).toBeVisible();
# 2. await expect(page.locator('nav')).toBeVisible();
# 3. await expect(page.locator('main')).toBeVisible();
# 4. await expect(page.getByText('Nog geen nieuws beschikbaar')).toBeVisible();
```

**Expected Resultaat**:
- Marker `Nieuws Piet` zichtbaar
- Nav landmark zichtbaar
- Main landmark zichtbaar
- Text `Nog geen nieuws beschikbaar` zichtbaar

#### 4.5 Verifieer text `Nog geen nieuws beschikbaar`, and `scrollWidth <= clientWidth`

**Doel**: Controleer dat text `Nog geen nieuws beschikbaar`, and `scrollWidth <= clientWidth`

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md`

**Verificatie**:

```bash
# Controleer scrollWidth assertie in spec.md
grep -A 5 "expect(scrollWidth).toBeLessThanOrEqual(clientWidth);" openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md

# Controleer dat script:
# 1. await expect(page.getByText('Nog geen nieuws beschikbaar')).toBeVisible();
# 2. const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
# 3. const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
# 4. expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
```

**Expected Resultaat**:
- Text `Nog geen nieuws beschikbaar` zichtbaar
- scrollWidth <= clientWidth
- Geen horizontale scrolling

#### 4.6 Verifieer explicitly ban accounts/API keys/SaaS/browser cloud/paid services/external APIs

**Doel**: Controleer dat expliciet ban accounts/API keys/SaaS/browser cloud/paid services/external APIs

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md`

**Verificatie**:

```bash
# Controleer netwerkisolatie in spec.md
grep -A 10 "Netwerkisolatie: alleen localhost/127.0.0.1 wordt toegestaan" openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md

# Controleer dat script:
# 1. page.route('**/*', (route) => {
# 2.   const { hostname } = new URL(route.request().url());
# 3.   if (hostname === 'localhost' || hostname === '127.0.0.1') {
# 4.     return route.continue();
# 5.   }
# 6.   return route.abort();
# 7. })
# 8. Alleen lokale test environment op localhost
```

**Expected Resultaat**:
- Alleen localhost/127.0.0.1 verkeer toegestaan
- Niet-localhost verkeer geblokkeerd
- Geen externe API's

#### 4.7 Verifieer rollback-, failure testing- en Playwright documentatie bevatten de exacte commando's en budgetten

**Doel**: Controleer dat rollback-, failure testing- en Playwright documentatie de exacte commando's en budgetten bevatten

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md`

**Verificatie**:

```bash
# Controleer dat documentatie exacte commando's en budgetten bevat
grep -A 5 "budgetten: server probe <=500ms en client assertion <=1000ms" openspec/changes/bootstrap-local-news-dashboard/specs/documentation/local-dev/spec.md

# Controleer dat script:
# 1. Rollback commando's met exacte volume identiteit
# 2. Failure testing commando's met exacte budgetten
# 3. Playwright commando's met exacte viewport
# 4. Alle commando's exact en actionable
```

**Expected Resultaat**:
- Rollback commando's exact
- Failure testing commando's exact
- Playwright commando's exact
- Budgetten gedefinieerd

### 5. Design.md Updates

#### 5.1 Verifieer design decisions reflect new requirements

**Doel**: Controleer dat design decisions new requirements reflecteren

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/design.md`

**Verificatie**:

```bash
# Controleer design decisions in design.md
grep -A 10 "## Beslissingen" openspec/changes/bootstrap-local-news-dashboard/design.md

# Controleer dat script:
# 1. Technology Stack Beslissing
# 2. Architectuur Beslissing
# 3. Health Monitoring Beslissing
# 4. Documentatie Beslissing
# 5. Datamodel, API-contracten en foutafhandeling
# 6. Modulegrenzen
# 7. Teststrategie
# 8. Compose Acceptance Beslissing
# 9. Data-Safe Rollback Beslissing
# 10. Failure Testing Beslissing
# 11. Mobile Acceptance Beslissing
```

**Expected Resultaat**:
- Design decisions new requirements reflecteren
- Elke beslissing met redenering
- Alternatieven overwogen

#### 5.2 Verifieer architecture decisions align with exact specifications

**Doel**: Controleer dat architecture decisions exact specifications aligneren

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/design.md`

**Verificatie**:

```bash
# Controleer architectuur beslissing in design.md
grep -A 10 "### Architectuur Beslissing" openspec/changes/bootstrap-local-news-dashboard/design.md

# Controleer dat script:
# 1. Monorepo-structuur met duidelijke scheiding van zorgen
# 2. Frontend (`frontend/`), backend (`backend/`) en infrastructuur
# 3. Duidelijke modulegrenzen
# 4. Consistentie behouden
```

**Expected Resultaat**:
- Architectuur beslissing specifications aligneren
- Duidelijke modulegrenzen
- Consistentie behouden

#### 5.3 Verifieer technology stack decisions support all requirements

**Doel**: Controleer dat technology stack decisions all requirements ondersteunen

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/design.md`

**Verificatie**:

```bash
# Controleer technology stack beslissing in design.md
grep -A 15 "### Technology Stack Beslissing" openspec/changes/bootstrap-local-news-dashboard/design.md

# Controleer dat script:
# 1. Gebruik Docker Compose voor lokale ontwikkeling
# 2. Next.js voor frontend
# 3. FastAPI voor backend
# 4. SQLite voor database
# 5. Moderne, Python-gebaseerde backend met React-gebaseerde frontend
# 6. Beide containerized voor consistentie
```

**Expected Resultaat**:
- Technology stack decisions requirements ondersteunen
- Moderne stack
- Consistentie behouden

#### 5.4 Verifieer risk mitigation strategies address new requirements

**Doel**: Controleer dat risk mitigation strategies new requirements addresseren

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/design.md`

**Verificatie**:

```bash
# Controleer risk mitigation in design.md
grep -A 20 "## Risico's / Trade-offs" openspec/changes/bootstrap-local-news-dashboard/design.md

# Controleer dat script:
# 1. Risico: Docker afhankelijkheid
# 2. Mitigatie: Duidelijke installatie-instructies
# 3. Risico: SQLite beperkingen
# 4. Mitigatie: Acceptabel voor lokale ontwikkeling
# 5. Risico: Complexiteit van monorepo
# 6. Mitigatie: Begin met eenvoudige structuur
# 7. Trade-off: Ontwikkeling vs. Productie
# 8. Mitigatie: Documenteer verschillen duidelijk
```

**Expected Resultaat**:
- Risk mitigation strategies requirements addresseren
- Elke risico met mitigatie
- Trade-offs gedocumenteerd

#### 5.5 Verifieer migration plan uses `docker compose up -d --build` en bevat geen verouderde `docker-compose` commando's

**Doel**: Controleer dat migration plan `docker compose up -d --build` gebruikt en geen verouderde `docker-compose` commando's bevat

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/design.md`

**Verificatie**:

```bash
# Controleer migratie plan in design.md
grep -A 15 "## Migratie Plan" openspec/changes/bootstrap-local-news-dashboard/design.md

# Controleer dat script:
# 1. Fase 1: Initiële Setup
# 2. Fase 2: Ontwikkeling
# 3. Fase 3: Productie Migratie
# 4. Gebruik `docker compose up -d --build` (v2 syntax)
# 5. Geen verouderde `docker-compose` (v1) commando's
```

**Expected Resultaat**:
- Migratie plan `docker compose up -d --build` gebruikt
- Geen verouderde `docker-compose` commando's
- Duidelijke migratie stappen

### 6. Tasks.md Updates

#### 6.1 Verifieer discrete verified tasks for each acceptance

**Doel**: Controleer dat discrete verified tasks for each acceptance worden geverifieerd

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/tasks.md`

**Verificatie**:

```bash
# Controleer discrete verified tasks in tasks.md
grep -A 10 "## 10. Discrete Verified Tasks" openspec/changes/bootstrap-local-news-dashboard/tasks.md

# Controleer dat script:
# 1. Elke acceptance met discrete verified tasks
# 2. Tasks actionable en testable
# 3. Geen duplicate timeout/rollback
# 4. Gebruik Dutch prose maar exact SHALL/MUST en Given/When/Then in specs
```

**Expected Resultaat**:
- Discrete verified tasks voor elke acceptance
- Tasks actionable en testable
- Geen duplicate taken
- Exacte spec syntax

#### 6.2 Verifieer use Dutch prose but exact SHALL/MUST and Given/When/Then in specs

**Doel**: Controleer dat Dutch prose maar exact SHALL/MUST en Given/When/Then in specs worden gebruikt

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/tasks.md`

**Verificatie**:

```bash
# Controleer Dutch prose in spec.md
grep -A 5 "Het systeem SHALL" openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md

# Controleer exact SHALL/MUST in spec
grep -A 5 "SHALL" openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md

# Controleer Given/When/Then in spec
grep -A 5 "Given" openspec/changes/bootstrap-local-news-dashboard/specs/database/local-sqlite/spec.md
```

**Expected Resultaat**:
- Dutch prose in spec
- Exact SHALL/MUST keywords
- Given/When/Then in scenarios
- Geen verouderde syntax

#### 6.3 Verifieer ensure no duplicate timeout/rollback

**Doel**: Controleer dat er geen duplicate timeout/rollback taken zijn

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/tasks.md`

**Verificatie**:

```bash
# Controleer op duplicate timeout/rollback
grep -i "timeout\|rollback" openspec/changes/bootstrap-local-news-dashboard/tasks.md | sort | uniq -c

# Controleer dat script:
# 1. Geen duplicate timeout taken
# 2. Geen duplicate rollback taken
# 3. Elke taak uniek
```

**Expected Resultaat**:
- Geen duplicate timeout taken
- Geen duplicate rollback taken
- Elke taak uniek

#### 6.4 Verifieer all tasks are actionable and testable

**Doel**: Controleer dat alle taken actionable en testable zijn

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/tasks.md`

**Verificatie**:

```bash
# Controleer dat elke taak actionable en testable is
grep "- \[" openspec/changes/bootstrap-local-news-dashboard/tasks.md | wc -l

# Controleer dat elke taak een checkbox heeft
# Alle taken moeten - [ ] of - [x] hebben
```

**Expected Resultaat**:
- Alle taken actionable
- Alle taken testable
- Elke taak met checkbox

#### 6.5 Verifieer geen verouderde `docker-compose` (v1) commando's of obsolete taken meer voorkomen

**Doel**: Controleer dat er geen verouderde `docker-compose` (v1) commando's of obsolete taken meer voorkomen

**Spec**: `openspec/changes/bootstrap-local-news-dashboard/tasks.md`

**Verificatie**:

```bash
# Controleer op verouderde docker-compose commando's
grep "docker-compose" openspec/changes/bootstrap-local-news-dashboard/tasks.md

# Controleer op obsolete taken
grep -i "obsolete\|deprecated\|legacy" openspec/changes/bootstrap-local-news-dashboard/tasks.md

# Controleer dat script:
# 1. Geen verouderde `docker-compose` (v1) commando's
# 2. Geen obsolete taken meer voorkomen
# 3. Alleen moderne `docker compose` (v2) commando's
```

**Expected Resultaat**:
- Geen verouderde `docker-compose` commando's
- Geen obsolete taken
- Alleen moderne `docker compose` commando's

## Snelstartgids

### 1. Controleer Spec Updates

```bash
# Controleer dat alle spec updates worden geverifieerd
cd /home/peter/git/de-nieuws-piet
openspec status --change "bootstrap-local-news-dashboard" --json
```

### 2. Voer Discrete Verified Tasks Uit

```bash
# Voer discrete verified tasks uit
# (Implementatie-specifiek)
```

### 3. Verifieer Tasks.md Updates

```bash
# Controleer dat alle taken worden geverifieerd
grep "- \[" openspec/changes/bootstrap-local-news-dashboard/tasks.md | wc -l
```

## Ondersteuning

### 1. Problemen

- Open een issue op GitHub
- Geef reproduceerbare stappen
- Voeg test logs toe
- Voeg spec validatie toe

### 2. Documentatie

- Lees deze documentatie
- Controleer spec implementatie
- Raadpleeg bijvallen in de code

## Referenties

- OpenSpec documentatie: https://openspec.dev/
- Docker Compose documentatie: https://docs.docker.com/compose/
- Playwright documentatie: https://playwright.dev/
- FastAPI documentatie: https://fastapi.tiangolo.com/

---

*Discrete verified tasks documentatie gegenereerd door OpenSpec bootstrap-local-news-dashboard change*