# Ontwikkelingsopstelling Documentatie

## Overzicht

Dit document beschrijft de lokale ontwikkelomgeving setup voor Nieuws Piet. Het dekt alle stappen af om de frontend en backend te ontwikkelen, testen en debuggen op een lokale machine.

## Vereisten

### Systeemvereisten

- **Docker**: Versie 20.10 of hoger (Compose v2 plugin)
- **Node.js**: >= 20 (voor frontend)
- **Python**: >= 3.10 (voor backend)
- **Git**: Voor repository beheer

### Aanbevolen Tools

- **VS Code** met Docker, Node.js en Python extensies
- **GitHub Desktop** (optioneel) voor Git GUI
- **Postman** of **Insomnia** voor API testing (optioneel)

## Installatie

### 1. Docker Installatie

#### Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

#### macOS

```bash
brew install --cask docker
open /Applications/Docker.app
```

#### Windows

Download en installeer Docker Desktop van https://www.docker.com/products/docker-desktop/

### 2. Node.js Installatie

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y nodejs npm

# macOS
brew install node

# Windows
# Download van https://nodejs.org/
```

### 3. Python Installatie

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

# macOS
brew install python

# Windows
# Download van https://www.python.org/downloads/
```

## Repository Setup

### Clone de Repository

```bash
git clone https://github.com/username/nieuws-piet.git
cd nieuws-piet
```

### Initialiseer Submodules (als van toepassing)

```bash
git submodule update --init --recursive
```

## Frontend Setup

### 1. Frontend Directory Navigatie

```bash
cd nieuws-piet/frontend
```

### 2. Dependencies Installeren

```bash
# Gebruik npm ci voor reproduceerbare installatie (vereist package-lock.json)
npm ci
```

### 3. Frontend Dependencies

De frontend gebruikt volgende dependencies:

- **Next.js**: 15.5.26 (React framework)
- **React**: 19.3.0
- **React-DOM**: 19.3.0
- **@playwright/test**: 1.63.0 (e2e testing)

### 4. Frontend Scripts

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "test": "node --test tests/",
    "test:e2e": "playwright test"
  }
}
```

### 5. Frontend Development

#### Lokale Ontwikkeling

```bash
# Start development server met hot-reload
npm run dev

# Open http://localhost:3000 in browser
```

#### Frontend Bouwen

```bash
# Bouw voor productie
npm run build

# Start statische server
npm start
```

#### Frontend Testen

```bash
# Unit tests
npm run test

# E2E tests met Playwright
npm run test:e2e
```

## Backend Setup

### 1. Backend Directory Navigatie

```bash
cd /home/peter/git/de-nieuws-piet/backend
```

### 2. Virtual Environment Aanmaken

```bash
# Python 3.10+ aanbevolen
python3 -m venv venv

# Windows
python -m venv venv

# Activeer virtuele omgeving
# Ubuntu/Debian/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Dependencies Installeren

```bash
# Gebruik pip install -r voor eenvoudige installatie
pip install -r requirements.txt

# Of met pipenv (als van toepassing)
pipenv install
```

### 4. Backend Dependencies

De backend gebruikt volgende dependencies:

- **FastAPI**: 0.141.1 (webframework)
- **uvicorn**: 0.54.0 (ASGI server)
- **pytest**: 9.1.1 (testrunner)
- **httpx**: 0.28.1 (HTTP client)

### 5. Backend Scripts

```python
# backend/scripts/
# Various deployment and setup scripts
```

### 6. Backend Development

#### Lokale Backend Starten

```bash
# Start backend met uvicorn
cd backend
uvicorn app.main:app --reload
```

#### Backend Testen

```bash
# Backend health tests
python -m pytest tests/ -v

# Specifieke test suites
python -m pytest tests/test_health.py -v
python -m pytest tests/test_sqlite.py -v
```

## Docker Compose Setup

### 1. Hoofdcompose.yaml

Het hoofdcompose.yaml bestand bevat de productieopstelling. Het laadt **geen** ontwikkelingsoverrides automatisch.

### 2. Ontwikkelingsopstelling

Voor ontwikkeling met hot-reload en bind mounts:

```bash
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

### 3. Productieopstelling

Voor reproduceerbare acceptatie:

```bash
docker compose up -d --build
```

## Frontend/Backend Synchronisatie

### 1. Frontend in Docker

De frontend draait in een container met:

- **Build**: Multi-stage Dockerfile (dependencies -> builder -> runner)
- **Command**: `next start` voor productie
- **Volumes**: Bind mount voor ontwikkeling, separate node_modules

### 2. Backend in Docker

De backend draait in een container met:

- **Build**: Python afhankelijkheden uit `backend/requirements.txt`
- **Command**: `uvicorn app.main:app`
- **Volumes**: SQLite database volume gemount op `/app/data`

## Frontend/Backend Communicatie

### 1. Frontend Requests

- **API Endpoints**: `/api/*` (als toegevoegd in latere changes)
- **Health Checks**: Directe HTTP requests naar backend
- **WebSocket**: Als toegevoegd in latere changes

### 2. Backend Responses

- **JSON**: FastAPI standaard JSON responses
- **CORS**: Geconfigureerd voor frontend origins
- **Authentication**: Als toegevoegd in latere changes

## Testomgeving

### 1. Backend Testomgeving

```bash
# Testomgeving variabelen
cd backend
export APP_ENV=test
export APP_HEALTH_FAULT=sqlite

# Voer tests uit
python -m pytest tests/ -v
```

### 2. Frontend Testomgeving

```bash
# Testomgeving variabelen
cd frontend
export NEXT_PUBLIC_API_URL=http://localhost:8000

# Voer e2e tests uit
npm run test:e2e
```

### 3. Integratietests

```bash
# Start volledige opstelling
docker compose up -d --build

# Wacht op readiness
./scripts/readiness-loop.sh

# Voer e2e tests uit
cd frontend
npm run test:e2e
```

## Mobiele Testen

### 1. Playwright Installatie

```bash
cd frontend
npx playwright install chromium
```

### 2. Mobiele Viewport Configuratie

```javascript
// playwright.config.js
module.exports = {
  projects: [
    {
      name: 'chromium',
      use: {
        browserName: 'chromium',
        viewport: { width: 360, height: 800 },
      },
    },
  ],
};
```

### 3. Mobiele Test Cases

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

## Foutopsporing

### 1. Frontend Foutopsporing

```bash
# Frontend logs
docker logs frontend

# Frontend container exec
docker exec -it frontend bash

# Frontend netwerk
curl -v http://localhost:3000
```

### 2. Backend Foutopsporing

```bash
# Backend logs
docker logs backend

# Backend container exec
docker exec -it backend bash

# Backend health
 curl -v http://localhost:8000/health
```

### 3. SQLite Foutopsporing

```bash
# SQLite database status
docker exec backend ls -la /app/data

# SQLite integriteit
docker exec backend sqlite3 /app/data/news.db "PRAGMA integrity_check;"

# SQLite tabellen
docker exec backend sqlite3 /app/data/news.db "SELECT name FROM sqlite_master WHERE type='table';"
```

### 4. Readiness Problemen

#### Frontend Bereikbaarheid

```bash
# Controleer frontend status
curl -s http://localhost:3000/ | grep "Nieuws Piet"

# Controleer frontend poort
netstat -tlnp | grep :3000
```

#### Backend Bereikbaarheid

```bash
# Controleer backend status
curl -s http://localhost:8000/health | jq .

# Controleer backend poort
netstat -tlnp | grep :8000
```

### 5. Docker Probleme

#### Docker Daemon Niet Starten

```bash
sudo systemctl start docker
sudo systemctl enable docker
```

#### Docker Compose Versie

```bash
docker compose version
```

## Ontwikkelingsworkflows

### 1. Frontend Ontwikkeling

1. Start frontend development server
2. Maak wijzigingen in `frontend/` directory
3. Voer `npm run build` uit voor productie builds
4. Test met `npm run test:e2e`

### 2. Backend Ontwikkeling

1. Start backend met hot-reload
2. Maak wijzigingen in `backend/app/` directory
3. Voer backend tests uit met `pytest`
4. Test health endpoint met `curl`

### 3. Full Stack Ontwikkeling

1. Start volledige Docker Compose opstelling
2. Wacht op readiness loop
3. Test frontend en backend integratie
4. Voer e2e tests uit

## Configuratie

### 1. Frontend Configuratie

```javascript
// frontend/config.js
module.exports = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  appName: 'Nieuws Piet',
  appDescription: 'Lokale persoonlijke nieuwsdashboard voor één gebruiker.',
};
```

### 2. Backend Configuratie

```python
# backend/config.py
import os

class Config:
    # Database
    SQLITE_PROBE_BUDGET_MS = int(os.getenv('SQLITE_PROBE_BUDGET_MS', '500'))
    
    # Health checks
    HEALTH_CHECK_INTERVAL = int(os.getenv('HEALTH_CHECK_INTERVAL', '10'))
    HEALTH_CHECK_TIMEOUT = int(os.getenv('HEALTH_CHECK_TIMEOUT', '5'))
    
    # Server
    HOST = os.getenv('HOST', '127.0.0.1')
    PORT = int(os.getenv('PORT', '8000'))
```

## Milieuvariabelen

### Backend Milieuvariabelen

```bash
# Testomgeving
export APP_ENV=test
export APP_HEALTH_FAULT=sqlite
export APP_DB_PATH=/app/data/news.db

# Productieomgeving
export APP_ENV=production
export APP_HEALTH_FAULT=none
```

### Frontend Milieuvariabelen

```bash
# Frontend
export NEXT_PUBLIC_API_URL=http://localhost:8000
export NEXT_PUBLIC_APP_NAME=Nieuws Piet
```

## Back-up en Herstel

### 1. SQLite Database Back-up

```bash
# Maak backup van database
docker exec backend cp /app/data/news.db /tmp/news.db.backup

# Of met Docker Compose
docker compose exec backend cp /app/data/news.db /tmp/news.db.backup
```

### 2. Database Herstel

```bash
# Herstel database
docker exec backend cp /tmp/news.db.backup /app/data/news.db
```

## Prestatieoptimalisatie

### 1. Frontend Optimalisatie

- Gebruik `npm run build` voor productie builds
- Configureer CDN voor statische assets
- Implementeer caching strategieën

### 2. Backend Optimalisatie

- Gebruik connection pooling voor database
- Implementeer caching voor health checks
- Configureer rate limiting

## Beveiliging

### 1. Docker Beveiliging

- Gebruik minimale privileges
- Isolate services met netwerken
- Gebruik read-only volumes waar mogelijk

### 2. Applicatie Beveiliging

- Valideer alle inputs
- Gebruik HTTPS in productie
- Implementeer authenticatie en autorisatie

## Onderhoud

### 1. Regelmatige Updates

```bash
# Update Docker
docker system prune -a

# Update dependencies
cd frontend && npm update
cd backend && pip install -r requirements.txt
```

### 2. Log Rotatie

```bash
# Docker log rotatie
sudo logrotate /etc/logrotate.d/docker
```

## Snelstartgids

### 1. Snelle Setup

```bash
# Clone en setup
git clone https://github.com/username/nieuws-piet.git
cd nieuws-piet

# Start volledige opstelling
docker compose up -d --build

# Wacht op readiness
./scripts/readiness-loop.sh

# Open applicatie
open http://localhost:3000
```

### 2. Snelle Testing

```bash
# Backend tests
cd backend
python -m pytest tests/ -v

# Frontend tests
cd frontend
npm run test:e2e

# Integratietests
docker compose up -d --build
./scripts/readiness-loop.sh
cd frontend && npm run test:e2e
```

## Ondersteuning

### 1. Problemen

- Open een issue op GitHub
- Geef reproduceerbare stappen
- Voeg logs en configuratie toe

### 2. Documentatie

- Lees deze documentatie
- Controleer API documentatie
- Raadpleeg bijvallen in de code

## Bijdragen

### 1. Code Stijl

- Volg bestaande code stijl
- Voeg tests toe voor nieuwe functionaliteit
- Schrijf duidelijke documentatie

### 2. Pull Requests

- Fork het repository
- Maak een feature branch
- Voer tests uit
- Maak een pull request

## Licentie

Dit project is gelicentieerd onder de MIT-licentie. Zie LICENSE voor meer details.

---

*Ontwikkelingsopstelling documentatie gegenereerd door OpenSpec bootstrap-local-news-dashboard change*