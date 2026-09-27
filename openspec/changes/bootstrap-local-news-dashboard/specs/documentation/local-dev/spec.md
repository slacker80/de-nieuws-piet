# Spec Delta

## Doel

Creëert uitgebreide lokale ontwikkeldocumentatie voor het opzetten en draaien van de persoonlijke nieuwssite applicatie.

## TOEVOEGDE Requirements

### Requirement: Lokale ontwikkelingsopstelling documentatie
Het systeem SHALL complete documentatie bieden voor het opzetten van de lokale ontwikkelomgeving.

#### Scenario: Setup documentatie beschikbaarheid
- **Given** ontwikkelaar setup instructies nodig heeft
- **When** ontwikkelaar setup documentatie sectie opent
- **Then** is complete setup documentatie beschikbaar met stapsgewijze instructies

### Requirement: Docker Compose setup documentatie
Het systeem SHALL documentatie bieden voor Docker Compose configuratie en gebruik.

#### Scenario: Docker Compose documentatie
- **Given** ontwikkelaar Docker Compose instructies nodig heeft
- **When** ontwikkelaar Docker Compose documentatie sectie opent
- **Then** bevat documentatie Docker installatie, compose file uitleg en startup commando's

### Requirement: Docker Compose acceptatie documentatie
Het systeem SHALL documentatie bieden voor reproduceerbare Docker Compose acceptatie met exacte `docker compose` commando's, service namen, frontend/backend URLs/ports, readiness conditions en curl/assertie commando's.

#### Scenario: Docker Compose acceptatie documentatie
- **Given** ontwikkelaar Docker Compose acceptatie instructies nodig heeft
- **When** ontwikkelaar Docker Compose acceptatie documentatie sectie opent
- **Then** bevat documentatie exacte `docker compose up -d` commando's, service namen, poorttoewijzingen (frontend:3000, backend:8000), readiness conditions en curl/assertie commando's voor verificatie

### Requirement: Data-safe rollback plan documentatie
Het systeem SHALL documentatie bieden voor data-safe rollback plan met exacte Compose stop/down commando's, onderscheid tussen preserving versus deleting SQLite volume/database, niet-destructieve backup voorafgaand aan destructieve actie, restauratie procedure en verificatie na herstel.

#### Scenario: Data-safe rollback plan documentatie
- **Given** ontwikkelaar rollback instructies nodig heeft
- **When** ontwikkelaar rollback plan documentatie sectie opent
- **Then** bevat documentatie exacte Compose stop/down commando's, SQLite volume/database preservation versus deletion strategie, niet-destructieve backup procedure, restauratie commando's en verificatie na herstel

### Requirement: Next.js ontwikkelingsdocumentatie
Het systeem SHALL documentatie bieden voor Next.js applicatie ontwikkeling.

#### Scenario: Next.js ontwikkelingsdocumentatie
- **Given** ontwikkelaar Next.js instructies nodig heeft
- **When** ontwikkelaar Next.js ontwikkelingsdocumentatie sectie opent
- **Then** bevat documentatie projectstructuur, ontwikkelcommando's en implementatieopties

### Requirement: FastAPI backend documentatie
Het systeem SHALL documentatie bieden voor FastAPI backend ontwikkeling.

#### Scenario: FastAPI ontwikkelingsdocumentatie
- **Given** ontwikkelaar FastAPI instructies nodig heeft
- **When** ontwikkelaar FastAPI documentatie sectie opent
- **Then** bevat documentatie API endpoints, data modellen en ontwikkelcommando's

### Requirement: SQLite database documentatie
Het systeem SHALL documentatie bieden voor SQLite database setup en gebruik.

#### Scenario: SQLite documentatie
- **Given** ontwikkelaar database instructies nodig heeft
- **When** ontwikkelaar SQLite documentatie sectie opent
- **Then** bevat documentatie database path, initialisatie, lifecycle, persistentie en health verificatie

### Requirement: Healthcheck documentatie
Het systeem SHALL documentatie bieden voor healthcheck tests en monitoring.

#### Scenario: Healthcheck documentatie
- **Given** ontwikkelaar healthcheck instructies nodig heeft
- **When** ontwikkelaar healthcheck documentatie sectie opent
- **Then** bevat documentatie health endpoint gebruik, test commando's en troubleshooting

### Requirement: Failure testing documentatie
Het systeem SHALL documentatie bieden voor deterministische en test-only failure testing met fault-injection mechanism voor SQLite-only failure, SQLite probe timeout (500ms), backend internal self-check failure en simultaneous failures.

#### Scenario: Failure testing documentatie
- **Given** ontwikkelaar failure testing instructies nodig heeft
- **When** ontwikkelaar failure testing documentatie sectie opent
- **Then** bevat documentatie test configuratie (environment variables), fault injection mechanism, test assertions voor status/JSON/fields/headers/timestamp en test-only nature

### Requirement: Mobiele responsiviteit documentatie
Het systeem SHALL documentatie bieden voor reproduceerbare mobiele acceptatie bij 360px breedte met Playwright/framework, exacte viewport/expected empty-state assertions, geen horizontale scrolling, zichtbare primaire content/navigation, toegankelijke health/state.

#### Scenario: Mobiele responsiviteit documentatie
- **Given** ontwikkelaar mobiele responsiviteit instructies nodig heeft
- **When** ontwikkelaar mobiele responsiviteit documentatie sectie opent
- **Then** bevat documentatie exacte Playwright test commando's, 360px viewport configuratie, empty-state assertions, horizontale scrolling verificatie, primaire content/navigation zichtbaarheid en health/state toegankelijkheid

**Note:** Mobiele acceptatie is implementatie-neutral maar concrete en actionable. Gebruikt `@playwright/test` dependency, version pinned in project lockfile, verbant accounts/API keys/SaaS/browser cloud/paid services/external APIs voor alle tests.

### Requirement: Exact Playwright test configuratie
Het systeem SHALL exacte Playwright test configuratie bieden met version pinned dependency en verbod op externe services.

#### Scenario: Exact Playwright test configuratie
- **Given** mobiele test configuratie wordt opgezet
- **When** project dependencies worden geïnstalleerd
- **Then** wordt `@playwright/test` dependency exact version pinned in project lockfile
- **And** test commando `npm run test:e2e` wordt gedefinieerd
- **And** alle tests verbannen:
  - Accounts/API keys
  - SaaS/browser cloud services
  - Paid services
  - External APIs

### Requirement: Exact Playwright test implementatie
Het systeem SHALL exacte Playwright test implementatie bieden met 360px viewport en exacte assertions.

#### Scenario: Exact Playwright test implementatie
- **Given** mobiele test wordt uitgevoerd
- **When** `npm run test:e2e` commando wordt uitgevoerd
- **Then** wordt volgende exacte Playwright test uitgevoerd:

```javascript
// Exacte mobiele test implementatie
const { test, expect } = require('@playwright/test');

test('mobile responsive acceptance at 360px width', async ({ page }) => {
  // Start local frontend beforehand with Compose readiness
  await page.goto('http://localhost:3000/', { waitUntil: 'networkidle' });
  
  // Set exact viewport
  await page.setViewportSize({ width: 360, height: 800 });
  
  // Assert marker text
  await expect(page.locator('text=Nieuws Piet')).toBeVisible();
  
  // Assert visible nav landmark
  await expect(page.locator('nav')).toBeVisible();
  
  // Assert visible main landmark
  await expect(page.locator('main')).toBeVisible();
  
  // Assert empty state text
  await expect(page.locator('text=Nog geen nieuws beschikbaar')).toBeVisible();
  
  // Assert no horizontal scrolling
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
});
```

**Note:** Test verbant expliciet accounts/API keys/SaaS/browser cloud/paid services/external APIs voor alle tests. Gebruikt alleen lokale test environment.

### Requirement: Troubleshooting documentatie
Het systeem SHALL troubleshooting documentatie bieden voor gemeenschappelijke problemen.

#### Scenario: Troubleshooting documentatie
- **Given** ontwikkelaar problemen tegenkomt
- **When** ontwikkelaar troubleshooting documentatie sectie opent
- **Then** biedt documentatie stapsgewijze troubleshooting gidsen

### Requirement: Lokale ontwikkelomgeving documentatie
Het systeem SHALL documentatie bieden voor lokale ontwikkelomgeving vereisten.

#### Scenario: Omgeving vereisten documentatie
- **Given** ontwikkelaar systeem vereisten nodig heeft
- **When** ontwikkelaar omgeving vereisten documentatie sectie opent
- **Then** bevat documentatie minimum systeem vereisten en installatie instructies