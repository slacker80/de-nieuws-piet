# Mobile Playwright Acceptance Documentatie

## Overzicht

Dit document beschrijft de reproduceerbare mobiele acceptatie testing voor Nieuws Piet met Playwright. Het dekt alle stappen af om mobiele responsiviteit te testen op 360x800 viewport met exacte assertions.

## Doel

- Implementeer reproduceerbare mobiele acceptatie bij 360x800 met Playwright
- Test exacte viewport/expected empty-state assertions
- Zorg ervoor dat er geen horizontale scrolling is
- Zorg ervoor dat primaire content/navigation zichtbaar is
- Gebruik lokale browser (geen cloud/SaaS)

## Vereisten

### Systeemvereisten

- **Node.js**: >= 20
- **Docker**: Versie 20.10 of hoger (Compose v2 plugin)
- **Playwright**: Chromium browser geïnstalleerd
- **Docker Compose**: V2 plugin (inclusief met Docker Desktop)

### Aanbevolen Tools

- **VS Code** met Node.js en Docker extensies
- **GitHub Desktop** (optioneel) voor Git GUI
- **Postman** of **Insomnia** voor API testing (optioneel)

## Installatie

### 1. Node.js Installatie

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y nodejs npm

# macOS
brew install node

# Windows
# Download van https://nodejs.org/
```

### 2. Playwright Installatie

```bash
# Installeer Playwright dependencies
cd frontend
npm ci

# Installeer browsers
npx playwright install chromium
```

### 3. Docker Installatie

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y docker.io docker-compose-plugin

# macOS
brew install --cask docker

# Windows
# Download van https://www.docker.com/products/docker-desktop/
```

## Setup

### 1. Frontend Directory Navigatie

```bash
cd /home/peter/git/de-nieuws-piet/frontend
```

### 2. Dependencies Installeren

```bash
# Gebruik npm ci voor reproduceerbare installatie (vereist package-lock.json)
npm ci
```

### 3. Project Configuratie

#### package.json

```json
{
  "name": "nieuws-piet-frontend",
  "version": "0.1.0",
  "private": true,
  "description": "Nieuws Piet - lokale mobiele nieuwsdashboard (Next.js PWA)",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "test": "node --test tests/",
    "test:e2e": "playwright test"
  },
  "dependencies": {
    "next": "15.5.26",
    "react": "19.3.0",
    "react-dom": "19.3.0"
  },
  "devDependencies": {
    "@playwright/test": "1.63.0"
  },
  "engines": {
    "node": ">=20"
  }
}
```

### 4. Playwright Configuratie

#### playwright.config.js

```javascript
// playwright.config.js
module.exports = {
  testDir: './tests',
  timeout: 30000,
  expect: {
    timeout: 5000
  },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  projects: [
    {
      name: 'chromium',
      use: {
        browserName: 'chromium',
        viewport: { width: 360, height: 800 },
        ignoreHTTPSErrors: true,
        headless: false, // true voor CI/CD
      },
    },
  ],
  webServer: {
    command: 'npm run build && npm start',
    port: 3000,
    reuseExistingServer: !process.env.CI,
  },
};
```

## Mobiele Test Implementatie

### 1. Test Bestanden Structuur

```
frontend/
├── tests/
│   ├── mobile.spec.js
│   ├── fixtures/
│   └── utils/
├── playwright.config.js
└── package.json
```

### 2. Mobiele Test Implementatie

#### tests/mobile.spec.js

```javascript
// tests/mobile.spec.js
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

### 3. Test Fixtures

#### tests/fixtures/mobile-fixtures.js

```javascript
// tests/fixtures/mobile-fixtures.js
const { test } = require('@playwright/test');

module.exports = {
  mobileViewport: { width: 360, height: 800 },
  desktopViewport: { width: 1920, height: 1080 },
  
  // Mobiele test helper
  mobileTest: test.extend({
    viewport: { width: 360, height: 800 },
    async setupMobileContext({ page }) {
      await page.setViewportSize(this.viewport);
      // Forceer mobiele user agent
      await page.setExtraHTTPHeaders({
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36'
      });
    }
  }),
};
```

### 4. Test Utilities

#### tests/utils/mobile-helpers.js

```javascript
// tests/utils/mobile-helpers.js
const { expect } = require('@playwright/test');

class MobileHelper {
  constructor(page) {
    this.page = page;
  }
  
  // Controleer mobiele responsiviteit
  async checkMobileResponsiveness() {
    const viewport = this.page.viewportSize();
    expect(viewport.width).toBe(360);
    expect(viewport.height).toBe(800);
    
    // Controleer scrollWidth <= clientWidth
    const scrollWidth = await this.page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await this.page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  }
  
  // Controleer zichtbare elementen
  async checkVisibleElements() {
    await expect(this.page.getByText('Nieuws Piet').first()).toBeVisible();
    await expect(this.page.locator('nav')).toBeVisible();
    await expect(this.page.locator('main')).toBeVisible();
    await expect(this.page.getByText('Nog geen nieuws beschikbaar')).toBeVisible();
  }
  
  // Controleer navigatie
  async checkNavigation() {
    const navLinks = await this.page.locator('nav a').allTextContents();
    expect(navLinks.length).toBeGreaterThan(0);
  }
  
  // Controleer empty state
  async checkEmptyState() {
    await expect(this.page.getByText('Nog geen nieuws beschikbaar')).toBeVisible();
  }
}

module.exports = MobileHelper;
```

### 5. Geavanceerde Mobiele Tests

#### tests/mobile-advanced.spec.js

```javascript
// tests/mobile-advanced.spec.js
const { test, expect } = require('@playwright/test');
const MobileHelper = require('./utils/mobile-helpers');

test('mobile advanced interactions', async ({ page }) => {
  const helper = new MobileHelper(page);
  
  // Setup mobile viewport
  await page.setViewportSize({ width: 360, height: 800 });
  
  // Netwerkisolatie
  await page.route('**/*', (route) => {
    const { hostname } = new URL(route.request().url());
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return route.continue();
    }
    return route.abort();
  });
  
  // Navigatie
  await page.goto('http://localhost:3000/', { waitUntil: 'load' });
  
  // Wacht op UI readiness
  await page.waitForSelector('[data-testid="news-piet-title"]');
  
  // Voer mobiele checks uit
  await helper.checkMobileResponsiveness();
  await helper.checkVisibleElements();
  await helper.checkNavigation();
  await helper.checkEmptyState();
  
  // Test touch interactions
  await page.touchscreen.tap('[data-testid="menu-toggle"]');
  await expect(page.locator('[data-testid="mobile-menu"]')).toBeVisible();
});
```

## Test Uitvoering

### 1. Lokale Test Uitvoering

```bash
# Voer mobiele tests uit
cd frontend
npm run test:e2e

# Voer tests met verbose output
npm run test:e2e -- --verbose

# Voer tests met headful browser (voor debugging)
HEADLESS=false npm run test:e2e
```

### 2. CI/CD Test Uitvoering

```bash
# GitHub Actions example
name: Playwright Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - uses: actions/setup-node@v3
      with:
        node-version: 20
        cache: 'npm'
    - run: cd frontend && npm ci
    - run: cd frontend && npx playwright install chromium
    - run: cd frontend && npm run test:e2e
    - uses: actions/upload-artifact@v3
      if: always()
      with:
        name: playwright-report
        path: frontend/playwright-report/
        retention-days: 30
```

### 3. Test Rapportage

```bash
# Genereer HTML rapport
npx playwright show-report

# Open test results in browser
npx playwright test --reporter=html

# Controleer test resultaten
npx playwright test --reporter=list
```

## Testomgeving

### 1. Testomgeving Variabelen

```bash
# Frontend testomgeving
cd frontend
export NEXT_PUBLIC_API_URL=http://localhost:8000
export NEXT_PUBLIC_APP_NAME=Nieuws Piet

# Playwright testomgeving
export HEADLESS=true
export BROWSER=chromium
```

### 2. Readiness Precondition

```javascript
// tests/fixtures/readiness-fixture.js
const { test } = require('@playwright/test');

test.use({
  // Wacht op frontend/backend readiness voordat tests draaien
  async beforeEach({ page }) {
    // Controleer of frontend bereikbaar is
    await page.goto('http://localhost:3000/', { waitUntil: 'load' });
    
    // Controleer of backend bereikbaar is
    const healthResponse = await page.goto('http://localhost:8000/health');
    expect(healthResponse.status()).toBe(200);
    
    const healthData = await healthResponse.json();
    expect(healthData.status).toBe('healthy');
  },
});
```

## Foutopsporing

### 1. Playwright Installatie Problemen

**Symptom**: `Browser not found` of `Failed to install browser`

**Oplossing**:

```bash
# Installeer browsers expliciet
cd frontend
npx playwright install chromium

# Of gebruik exacte browser versie
npx playwright install chromium@1.63.0

# Controleer browser installatie
npx playwright show-browsers
```

### 2. Test Uitvoering Problemen

**Symptom**: `Navigation timeout` of `TimeoutError`

**Oplossing**:

```bash
# Verhoog timeout
cd frontend
npm run test:e2e -- --timeout 60000

# Voer tests met headful browser
HEADLESS=false npm run test:e2e

# Controleer browser logs
npx playwright show-browsers
```

### 3. Mobiele Viewport Problemen

**Symptom**: `Viewport not set correctly` of `ScrollWidth > ClientWidth`

**Oplossing**:

```bash
# Controleer viewport instellingen
cd frontend
npx playwright config

# Test viewport in test
await page.setViewportSize({ width: 360, height: 800 });

# Controleer viewport
const viewport = page.viewportSize();
console.log(`Viewport: ${viewport.width}x${viewport.height}`);
```

### 4. Netwerkisolatie Problemen

**Symptom**: `Network error: net::ERR_FAILED` of `CORS policy error`

**Oplossing**:

```bash
# Controleer netwerkisolatie configuratie
await page.route('**/*', (route) => {
  const { hostname } = new URL(route.request().url());
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return route.continue();
  }
  return route.abort();
});

# Controleer als er externe requests zijn
page.on('requestfailed', (request) => {
  console.log(`Failed request: ${request.url()}`);
});
```

## Prestatie Optimalisatie

### 1. Test Prestatie

```bash
# Voer tests met parallelle uitvoering
npx playwright test --workers=4

# Voer tests met headless browser (sneller)
HEADLESS=true npm run test:e2e

# Voer tests met cache (sneller)
npx playwright test --cache-dir=/tmp/playwright-cache
```

### 2. Browser Prestatie

```javascript
// tests/performance.spec.js
const { test, expect } = require('@playwright/test');

test('mobile page load performance', async ({ page }) => {
  // Meet page load time
  const startTime = Date.now();
  await page.goto('http://localhost:3000/', { waitUntil: 'load' });
  const loadTime = Date.now() - startTime;
  
  // Zorg ervoor dat page load < 5 seconden is
  expect(loadTime).toBeLessThan(5000);
  
  // Meet largest contentful paint
  const lcp = await page.evaluate(() => {
    return new Promise((resolve) => {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.name.includes('http://localhost:3000/')) {
            resolve(entry.startTime);
            return;
          }
        }
      }).observe({type: 'largest-contentful-paint'});
    });
  });
  
  expect(lcp).toBeLessThan(2500);
});
```

## Beveiliging

### 1. Netwerkisolatie

```javascript
// tests/security.spec.js
const { test, expect } = require('@playwright/test');

test('mobile network isolation', async ({ page }) => {
  // Zorg ervoor dat alleen localhost verkeer wordt toegestaan
  const blockedRequests = [];
  
  page.on('requestfailed', (request) => {
    const url = request.url();
    if (!url.startsWith('http://localhost:') && !url.startsWith('http://127.0.0.1:')) {
      blockedRequests.push(url);
    }
  });
  
  await page.goto('http://localhost:3000/', { waitUntil: 'load' });
  
  // Zorg ervoor dat er geen externe requests zijn
  expect(blockedRequests.length).toBe(0);
});
```

### 2. Content Security Policy

```javascript
// tests/csp.spec.js
const { test, expect } = require('@playwright/test');

test('mobile CSP headers', async ({ page }) => {
  const response = await page.goto('http://localhost:3000/');
  const cspHeader = response.headers()['content-security-policy'];
  
  // Controleer CSP headers
  expect(cspHeader).toContain('default-src');
  expect(cspHeader).toContain('script-src');
  expect(cspHeader).toContain('style-src');
});
```

## Testrapportage

### 1. HTML Rapport

```bash
# Genereer HTML rapport
npx playwright test --reporter=html

# Open rapport in browser
npx playwright show-report
```

### 2. JSON Rapport

```bash
# Genereer JSON rapport
npx playwright test --reporter=json

# Parse JSON rapport
npx playwright test --reporter=json > test-results.json
```

### 3. JUnit Rapport

```bash
# Genereer JUnit rapport
npx playwright test --reporter=junit

# Open JUnit rapport
open playwright-junit.xml
```

## Test Automatisering

### 1. GitHub Actions

```yaml
# .github/workflows/playwright.yml
name: Playwright Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - uses: actions/setup-node@v3
      with:
        node-version: 20
        cache: 'npm'
    - run: cd frontend && npm ci
    - run: cd frontend && npx playwright install chromium
    - run: cd frontend && npm run test:e2e
    - uses: actions/upload-artifact@v3
      if: always()
      with:
        name: playwright-report
        path: frontend/playwright-report/
        retention-days: 30
```

### 2. GitLab CI

```yaml
# .gitlab-ci.yml
stages:
  - test

test_mobile:
  stage: test
  image: node:20
  before_script:
    - cd frontend
    - npm ci
    - npx playwright install chromium
  script:
    - npm run test:e2e
  artifacts:
    reports:
      junit: playwright-junit.xml
    when: always
```

## Snelstartgids

### 1. Installatie

```bash
# Clone repository
git clone https://github.com/username/nieuws-piet.git
cd nieuws-piet/frontend

# Installeer dependencies
npm ci

# Installeer browsers
npx playwright install chromium
```

### 2. Test Uitvoering

```bash
# Voer mobiele tests uit
npm run test:e2e

# Voer tests met verbose output
npm run test:e2e -- --verbose

# Genereer rapport
npx playwright show-report
```

### 3. Test Ontwikkeling

```bash
# Voer tests in development mode
HEADLESS=false npm run test:e2e

# Voer tests met specifiche
npx playwright test tests/mobile.spec.js

# Voer tests met filter
npx playwright test -g "mobile responsive"
```

## Ondersteuning

### 1. Problemen

- Open een issue op GitHub
- Geef reproduceerbare stappen
- Voeg test logs toe
- Voeg browser logs toe

### 2. Documentatie

- Lees deze documentatie
- Controleer Playwright documentatie
- Raadpleeg bijvallen in de code

## Referenties

- Playwright documentatie: https://playwright.dev/
- Next.js documentatie: https://nextjs.org/docs
- Mobile testing best practices: https://playwright.dev/docs/mobile-testing
- Responsieve design: https://developer.mozilla.org/en-US/docs/Learn/CSS/CSS_layout/Responsive_Design

---

*Mobiele Playwright acceptatie documentatie gegenereerd door OpenSpec bootstrap-local-news-dashboard change*