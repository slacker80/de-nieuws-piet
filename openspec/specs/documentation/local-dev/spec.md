# Spec

## Purpose

Creëert uitgebreide lokale ontwikkeldocumentatie voor het opzetten en draaien van de persoonlijke nieuwssite applicatie.

## Requirements

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
- **And** gebruikt uitsluitend de v2 syntax `docker compose` (de v1 syntax `docker-compose` is obsolete en mag niet voorkomen)

### Requirement: Docker Compose acceptatie documentatie
Het systeem SHALL documentatie bieden voor reproduceerbare Docker Compose acceptatie met exacte `docker compose` commando's, service namen, frontend/backend URLs/ports, readiness conditions en curl/assertie commando's.

#### Scenario: Docker Compose acceptatie documentatie
- **Given** ontwikkelaar Docker Compose acceptatie instructies nodig heeft
- **When** ontwikkelaar Docker Compose acceptatie documentatie sectie opent
- **Then** bevat documentatie exact `docker compose up -d --build` als startcommando, service namen, poorttoewijzingen (frontend:3000, backend:8000), readiness conditions en curl/assertie commando's voor verificatie
- **And** bevat documentatie de copyable readiness loop met exacte HTTP status 200 assertions én body assertions (`Nieuws Piet` voor frontend, JSON `status: healthy` voor backend) met max 30 attempts, `sleep 1` en `curl --max-time 5`
- **And** vermeldt documentatie dat SQLite nooit een service is

### Requirement: Data-safe rollback plan documentatie
Het systeem SHALL uitvoerbare documentatie bieden voor data-safe rollback/restore met exacte Compose commando's, onderscheid tussen preserve en destructive reset, niet-destructieve backup met read-only bron, backup-integriteitsvalidatie, feitelijk restore en verificatie na herstel.

#### Scenario: Data-safe rollback documentatie
- **Given** ontwikkelaar rollback instructies nodig heeft
- **When** ontwikkelaar rollback documentatie sectie opent
- **Then** bevat documentatie de exacte volume identiteit `nieuws_piet_sqlite_data`, backend mount `/app/data`, database file `/app/data/news.db` en host backup `./backups/news.db.<UTC timestamp>.bak` buiten het named volume
- **And** bevat documentatie de backup commando's met read-only volume mount (`:ro`)
- **And** bevat documentatie de backup-integriteitsvalidatie met `PRAGMA integrity_check` (exact `ok`)
- **And** bevat documentatie de restore commando's die de backup feitelijk terugzetten in het named volume voor zowel preserve als destructive pad, waarbij restore op het destructive pad DIRECT NA `docker compose down -v` plaatsvindt in het opnieuw aangemaakte volume
- **And** bevat documentatie `docker compose down` als standaard en `docker compose down -v` uitsluitend als opt-in, alléén na geslaagde backup en integriteitsvalidatie; de restore volgt pas NA `docker compose down -v` (nooit ervóór), direct in het opnieuw aangemaakte volume `nieuws_piet_sqlite_data`, en wordt direct gevolgd door verificatie van integriteit, data-marker en health

#### Scenario: Verificatie na herstel documentatie
- **Given** ontwikkelaar rollback heeft uitgevoerd
- **When** ontwikkelaar de verificatiestappen doorloopt
- **Then** beschrijft documentatie de integriteitsverificatie (`PRAGMA integrity_check` plus ten minste één tabel) en de health assertie (HTTP 200 plus JSON `status: healthy`)

### Requirement: Next.js ontwikkelingsdocumentatie
Het systeem SHALL documentatie bieden voor Next.js applicatie ontwikkeling.

#### Scenario: Next.js ontwikkelingsdocumentatie
- **Given** ontwikkelaar Next.js instructies nodig heeft
- **When** ontwikkelaar Next.js documentatie sectie opent
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
- **And** bevat documentatie de exacte volume identiteit `nieuws_piet_sqlite_data`

### Requirement: Healthcheck documentatie
Het systeem SHALL documentatie bieden voor healthcheck tests en monitoring.

#### Scenario: Healthcheck documentatie
- **Given** ontwikkelaar healthcheck instructies nodig heeft
- **When** ontwikkelaar healthcheck documentatie sectie opent
- **Then** bevat documentatie health endpoint gebruik, test commando's en troubleshooting

### Requirement: Failure testing documentatie
Het systeem SHALL documentatie bieden voor deterministische en test-only failure testing met fault-injection mechanism voor SQLite-only failure, SQLite probe timeout, backend internal self-check failure en simultaneous failures.

#### Scenario: Failure testing documentatie
- **Given** ontwikkelaar failure testing instructies nodig heeft
- **When** ontwikkelaar failure testing documentatie sectie opent
- **Then** bevat documentatie de exacte test configuratie: `APP_ENV=test` als guard en `APP_HEALTH_FAULT` met whitelist `sqlite`, `sqlite_timeout`, `backend`, `all`
- **And** beschrijft documentatie dat onbekende `APP_HEALTH_FAULT` waarden deterministisch worden genegeerd en dat `APP_ENV` anders dan `test` altijd normale gezonde respons geeft
- **And** bevat documentatie de app-factory/proces-isolatie en reset cleanup per test
- **And** bevat documentatie de budgetten: server probe <=500ms en client assertion <=1000ms voor `sqlite_timeout`
- **And** benadrukt documentatie dat fault injection nooit filesystem database mutaties uitvoert
- **And** bevat documentatie test assertions voor status/JSON/fields/headers/timestamp

### Requirement: Mobiele responsiviteit documentatie
Het systeem SHALL documentatie bieden voor reproduceerbare mobiele acceptatie bij 360x800 viewport met Playwright, exacte viewport/expected empty-state assertions, geen horizontale scrolling, zichtbare primaire content/navigation en lokale test uitvoering.

#### Scenario: Mobiele responsiviteit documentatie
- **Given** ontwikkelaar mobiele responsiviteit instructies nodig heeft
- **When** ontwikkelaar mobiele responsiviteit documentatie sectie opent
- **Then** bevat documentatie exacte Playwright opzet (`npm ci`, lokale browser installatie) en het commando `npm run test:e2e`
- **And** beschrijft documentatie dat de Compose readiness loop eerst slaagt voordat `npm run test:e2e` draait
- **And** bevat documentatie dat viewport 360x800 wordt ingesteld VÓÓR navigatie naar `http://localhost:3000/`
- **And** bevat documentatie de exacte assertions: marker `Nieuws Piet`, zichtbare `nav` landmark, zichtbare `main` landmark, tekst `Nog geen nieuws beschikbaar` en `scrollWidth <= clientWidth`

**Note:** Mobiele acceptatie is implementatie-neutral maar concreet en actionable. Gebruikt `@playwright/test` dependency, version pinned in project lockfile, zonder accounts, API keys, SaaS, browser cloud, paid services of external API's voor alle tests.

### Requirement: Exact Playwright test configuratie
Het systeem SHALL exacte Playwright test configuratie bieden met version pinned dependency, lokale browser setup, localhost baseURL en verbod op externe services.

#### Scenario: Exact Playwright test configuratie
- **Given** mobiele test configuratie wordt opgezet
- **When** project dependencies worden geïnstalleerd
- **Then** wordt `@playwright/test` als lokale dev dependency exact version pinned in project lockfile (`package-lock.json`)
- **And** worden dependencies geïnstalleerd met `npm ci`
- **And** wordt de browser lokaal geïnstalleerd met `npx playwright install chromium` (geen cloud browser)
- **And** wordt test commando `npm run test:e2e` gedefinieerd
- **And** is `baseURL` exact `http://localhost:3000`
- **And** verbieden alle tests:
  - Accounts/API keys
  - SaaS/browser cloud services
  - Paid services
  - External API's

#### Scenario: Readiness precondition voor e2e
- **Given** e2e tests moeten draaien
- **When** het testcommando wordt voorbereid
- **Then** wordt eerst `docker compose up -d --build` uitgevoerd
- **And** slaagt de frontend/backend readiness loop voordat `npm run test:e2e` start

### Requirement: Exact Playwright test implementatie
Het systeem SHALL exacte Playwright test implementatie bieden met 360x800 viewport vóór navigatie, stabiele UI readiness, localhost netwerkisolatie en exacte assertions.

#### Scenario: Exact Playwright test implementatie
- **Given** mobiele test wordt uitgevoerd
- **When** `npm run test:e2e` commando wordt uitgevoerd
- **Then** wordt volgende exacte Playwright test uitgevoerd:

```javascript
// Exacte mobiele test implementatie (lokaal, geen cloud/SaaS/betaalde/externe API's)
const { test, expect } = require('@playwright/test');

test('mobile responsive acceptance at 360x800', async ({ page }) => {
  // Netwerkisolatie: alleen localhost/127.0.0.1 wordt toegestaan
  await page.route('**/*', (route) => {
    const { hostname } = new URL(route.request().url());
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return route.continue();
    }
    return route.abort();
  });

  // Viewport 360x800 wordt ingesteld VÓÓR navigatie
  await page.setViewportSize({ width: 360, height: 800 });

  // Navigatie naar lokale frontend (baseURL http://localhost:3000)
  await page.goto('http://localhost:3000/', { waitUntil: 'load' });

  // Stabiele UI readiness: auto-retry assertions in plaats van vaste slaaptijd
  await expect(page.getByText('Nieuws Piet').first()).toBeVisible();
  await expect(page.locator('nav')).toBeVisible();
  await expect(page.locator('main')).toBeVisible();
  await expect(page.getByText('Nog geen nieuws beschikbaar')).toBeVisible();

  // Geen horizontale scrolling
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
});
```

**Note:** Test verbant expliciet accounts/API keys/SaaS/browser cloud/paid services/external API's voor alle tests. Alleen lokale test environment op localhost; niet-localhost verkeer wordt geblokkeerd. Viewport wordt vóór navigatie ingesteld en readiness gebruikt auto-retry assertions (geen vaste timeouts).

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

(End of file - total 192 lines)