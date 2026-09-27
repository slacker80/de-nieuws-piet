# Design

## Context

Het project vereist een lokale, mobiele persoonlijke nieuwssite met een monorepo-structuur. Dit wijzigingsvoorstel vestigt de fundamentele lokale ontwikkelomgeving die alle daaropvolgende features zal ondersteunen. De architectuur volgt de bestaande projectvisie: lokale ontwikkeling met Docker Compose, Next.js PWA frontend, FastAPI backend en SQLite database. Dit wijzigingsvoorstel richt zich op het vestigen van de basisinfrastructuur zonder externe afhankelijkheden of publieke toegang.

## Doelen / Niet-doelen

**Doelen:**
- Vestig een complete lokale ontwikkelomgeving met alle noodzakelijke componenten
- Creëer een reproduceerbare opstelling die werkt op een standaard Linux ontwikkelmachine
- Bied health monitoring capabilities voor alle applicatiecomponenten
- Implementeer uitgebreide lokale documentatie voor toekomstige ontwikkelaars
- Zorg dat het systeem met één commando kan worden gestart

**Niet-doelen:**
- Implementeer RSS feed ingang of externe API-integraties
- Creëer gebruikersauthenticatie of accountbeheer
- Stel publieke toegang of HTTPS in
- Implementeer LLM-gebaseerde samenvatting of externe AI-services
- Creëer Telegram notificatiesysteem
- Stel Kubernetes of cloud implementatie in

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

### Compose Acceptance Beslissing
**Beslissing**: Implementeer reproduceerbare Docker Compose acceptatie met exacte `docker compose` commando's, service namen, frontend/backend URLs/ports, readiness conditions en curl/assertie commando's.

**Redenering**: Reproduceerbare Compose acceptatie zorgt ervoor dat alle ontwikkelaars dezelfde opstelling hebben en kan snel verifiëren dat de applicatie correct werkt. Exacte commando's en verificatie elimineren raadplegen en zorgen voor consistente testresultaten.

**Alternatieven Overwogen**:
- Handmatige acceptatie: Zou inconsistent zijn tussen teamleden
- Geen acceptatie: Zou problemen later in het proces laten ontdekken

### Data-Safe Rollback Beslissing
**Beslissing**: Implementeer concrete data-safe rollback plan met exacte Compose stop/down commando's, onderscheid tussen preserving versus deleting SQLite volume/database, niet-destructieve backup voorafgaand aan destructieve actie, restauratie procedure en verificatie na herstel.

**Redenering**: Data-safe rollback beschermt tegen gegevensverlies en biedt zekerheid dat het systeem kan herstellen van storingen. Exacte commando's en procedures zorgen ervoor dat het rollback plan kan worden uitgevoerd zonder twijfel.

**Alternatieven Overwogen**:
- Geen rollback plan: Zou risico's introduceren voor gegevensverlies
- Extern backup: Zou externe afhankelijkheden introduceren

### Failure Testing Beslissing
**Beslissing**: Implementeer deterministische en test-only failure testing met fault-injection mechanism voor SQLite-only failure, SQLite probe timeout (500ms), backend internal self-check failure en simultaneous failures.

**Redenering**: Deterministische failure testing zorgt ervoor dat het systeem kan worden getest onder verschillende storingen zonder externe afhankelijkheden. Test-only fault injection beschermt productieomgevingen van storingen.

**Alternatieven Overwogen**:
- Onbetrouwbare failure testing: Zou onbetrouwbare testresultaten produceren
- Externe failure testing: Zou externe afhankelijkheden introduceren

### Mobile Acceptance Beslissing
**Beslissing**: Implementeer reproduceerbare mobiele acceptatie bij 360px breedte met Playwright/framework, exacte viewport/expected empty-state assertions, geen horizontale scrolling, zichtbare primaire content/navigation, toegankelijke health/state.

**Redenering**: Reproduceerbare mobiele acceptatie zorgt ervoor dat de applicatie correct werkt op mobiele apparaten. Exacte viewport en assertions elimineren raadplegen en zorgen voor consistente mobiele testresultaten.

**Alternatieven Overwogen**:
- Handmatige mobiele acceptatie: Zou inconsistent zijn tussen apparaten
- Geen mobiele acceptatie: Zou mobiele problemen later in het proces laten ontdekken

## Risico's / Trade-offs

### Risico: Docker afhankelijkheid
**Risico**: Ontwikkelaars hebben mogelijk Docker niet geïnstalleerd of hebben problemen met Docker configuratie.

**Mitigatie**: Bied duidelijke installatie-instructies en alternatieve setup methoden in documentatie. Neem fallback instructies op voor systemen zonder Docker.

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

**Mitigatie**: Gebruik duidelijke environment variable namen (bijvoorbeeld `TEST_FAILURE_INJECTION`) en documenteer dat deze uitsluitend voor testomgevingen moeten worden gebruikt.

### Risico: Mobiele test afhankelijkheid
**Risico**: Mobiele test afhankelijkheid kan problemen introduceren als Playwright niet correct is geïnstalleerd.

**Mitigatie**: Bied duidelijke installatie-instructies en alternatieve test methoden in documentatie.

## Migratie Plan

### Fase 1: Initiële Setup
1. Clone de repository
2. Installeer Docker en Docker Compose
3. Voer `docker-compose up -d` uit om alle services te starten
4. Open de applicatie op `http://localhost:3000`

### Fase 2: Ontwikkeling
1. Maak wijzigingen aan frontend code in `frontend/` directory
2. Maak wijzigingen aan backend code in `backend/` directory
3. Voer `docker-compose restart` uit om wijzigingen toe te passen
4. Gebruik health endpoint op `http://localhost:8000/health` om systeembron te verifiëren

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