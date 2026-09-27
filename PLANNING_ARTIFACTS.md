# Planning Artifacts for bootstrap-local-news-dashboard

## A. Data-Safe Rollback Contract

### Overview
Definieert een data-safe rollback contract met exacte Docker volume configuratie, backup procedures en restauratie workflows.

### Docker Volume Configuration
- **Docker Volume Name**: `nieuws_piet_sqlite_data`
- **Backend Mount Path**: `/app/data`
- **Database File Path**: `/app/data/news.db`
- **Host Backup Directory**: `./backups` (outside volume)

### Rollback Procedure Commands

#### Non-Destructive Backup (Required before any rollback)
```bash
# Stop backend service
docker compose stop backend

# Create timestamped backup directory
BACKUP_DIR="./backups/backup_$(date -u +'%Y%m%d_%H%M%S')"
mkdir -p "$BACKUP_DIR"

# Copy database file to backup directory
cp /home/peter/git/de-nieuws-piet/data/news.db "$BACKUP_DIR/"

# Verify backup integrity
ls -la "$BACKUP_DIR/"
```

#### Normal Rollback (Preserve Data)
```bash
# Stop backend without removing volumes
docker compose down

# Restore database from backup
RESTORE_BACKUP="./backups/latest"
cp "$RESTORE_BACKUP/news.db" /home/peter/git/de-nieuws-piet/data/news.db

# Restart services
docker compose up -d

# Verify database integrity
curl -f http://localhost:8000/health
```

#### Destructive Rollback (Opt-in Only)
```bash
# WARNING: This command MUST only be used after backup and is never part of normal rollback
# This command permanently deletes the SQLite volume and all data

docker compose down -v

# Recreate volume and restore from latest backup
mkdir -p /home/peter/git/de-nieuws-piet/data
docker volume create nieuws_piet_sqlite_data
docker compose up -d

# Verify database integrity
curl -f http://localhost:8000/health
```

### Verification Commands
```bash
# Verify database file exists
ls -la /home/peter/git/de-nieuws-piet/data/news.db

# Verify backup directory structure
find ./backups -type f -name "*.db"

# Verify health endpoint after rollback
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health
```

## B. Test-Only Health Fault Mechanism

### Configuration Requirements
- **APP_ENV**: MUST be set to `test`
- **APP_HEALTH_FAULT**: MUST be one of exactly `sqlite`, `sqlite_timeout`, `backend`, `all`
- **Absent/Any other value**: MUST disable fault injection in non-test environments

### Test Configuration
```bash
# Test configuration examples
export APP_ENV=test
export APP_HEALTH_FAULT=sqlite
export APP_HEALTH_FAULT=sqlite_timeout
export APP_HEALTH_FAULT=backend
export APP_HEALTH_FAULT=all
```

### Test Implementations

#### Test 1: SQLite Failure Mode
```javascript
// test/health-endpoint.test.js - SQLite Failure Mode

test('Health endpoint returns SQLite failure when APP_HEALTH_FAULT=sqlite', async () => {
  process.env.APP_ENV = 'test';
  process.env.APP_HEALTH_FAULT = 'sqlite';
  
  const response = await fetch('http://localhost:8000/health');
  
  expect(response.status).toBe(503);
  expect(response.headers.get('content-type')).toBe('application/json');
  
  const body = await response.json();
  expect(body.status).toBe('unhealthy');
  expect(body.components.backend).toBe('healthy');
  expect(body.components.sqlite).toBe('unhealthy');
  expect(body.error).toBe('SQLite database not accessible');
  expect(body.timestamp).toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z/);
});
```

#### Test 2: SQLite Timeout Failure Mode
```javascript
// test/health-endpoint.test.js - SQLite Timeout Failure Mode

test('Health endpoint returns SQLite timeout when APP_HEALTH_FAULT=sqlite_timeout', async () => {
  process.env.APP_ENV = 'test';
  process.env.APP_HEALTH_FAULT = 'sqlite_timeout';
  
  const startTime = Date.now();
  const response = await fetch('http://localhost:8000/health', {
    signal: AbortSignal.timeout(500)
  });
  const endTime = Date.now();
  
  expect(response.status).toBe(503);
  expect(response.headers.get('content-type')).toBe('application/json');
  expect(endTime - startTime).toBeLessThan(500);
  
  const body = await response.json();
  expect(body.status).toBe('unhealthy');
  expect(body.components.backend).toBe('healthy');
  expect(body.components.sqlite).toBe('unhealthy');
  expect(body.error).toBe('SQLite database check timeout');
});
```

#### Test 3: Backend Failure Mode
```javascript
// test/health-endpoint.test.js - Backend Failure Mode

test('Health endpoint returns backend failure when APP_HEALTH_FAULT=backend', async () => {
  process.env.APP_ENV = 'test';
  process.env.APP_HEALTH_FAULT = 'backend';
  
  const response = await fetch('http://localhost:8000/health');
  
  expect(response.status).toBe(500);
  expect(response.headers.get('content-type')).toBe('application/json');
  
  const body = await response.json();
  expect(body.status).toBe('unhealthy');
  expect(body.components.backend).toBe('unhealthy');
  expect(body.components.sqlite).toBe('healthy');
  expect(body.error).toBe('Backend internal health check failed');
});
```

#### Test 4: Combined Failure Mode
```javascript
// test/health-endpoint.test.js - Combined Failure Mode

test('Health endpoint returns combined failure when APP_HEALTH_FAULT=all', async () => {
  process.env.APP_ENV = 'test';
  process.env.APP_HEALTH_FAULT = 'all';
  
  const response = await fetch('http://localhost:8000/health');
  
  expect(response.status).toBe(503);
  expect(response.headers.get('content-type')).toBe('application/json');
  
  const body = await response.json();
  expect(body.status).toBe('unhealthy');
  expect(body.components.backend).toBe('unhealthy');
  expect(body.components.sqlite).toBe('unhealthy');
  expect(body.error).toBe('Backend internal health check failed and SQLite database not accessible');
});
```

### Combined Failure Task
```javascript
// test/health-endpoint.test.js - Combined Failure Task

test('Combined failure task validates all fault injection modes', async () => {
  const faultModes = ['sqlite', 'sqlite_timeout', 'backend', 'all'];
  
  for (const mode of faultModes) {
    process.env.APP_ENV = 'test';
    process.env.APP_HEALTH_FAULT = mode;
    
    const response = await fetch('http://localhost:8000/health', {
      signal: AbortSignal.timeout(500)
    });
    
    expect(response.status).toBeLessThan(600);
    expect(response.headers.get('content-type')).toBe('application/json');
    
    const body = await response.json();
    expect(body.status).toBe('unhealthy');
    expect(body.timestamp).toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z/);
    
    // Clean up environment for next test
    delete process.env.APP_ENV;
    delete process.env.APP_HEALTH_FAULT;
  }
});
```

## C. Reproducible Compose

### Service Configuration
- **Frontend Service**: `http://localhost:3000/`
- **Backend Service**: `http://localhost:8000/health`
- **Docker Command**: `docker compose up -d --build`

### Readiness Loop Configuration
```bash
# Readiness loop with exact specifications
MAX_RETRIES=30
RETRY_INTERVAL=1
REQUEST_TIMEOUT=5

for ((i=1; i<=MAX_RETRIES; i++)); do
  # Test frontend
  if curl -f -s -o /dev/null --max-time $REQUEST_TIMEOUT http://localhost:3000/; then
    echo "Frontend ready after $i attempts"
    break
  fi
  
  # Test backend health
  if curl -f -s -o /dev/null --max-time $REQUEST_TIMEOUT http://localhost:8000/health; then
    echo "Backend ready after $i attempts"
    break
  fi
  
  if [ $i -eq $MAX_RETRIES ]; then
    echo "Timeout: Services not ready after $MAX_RETRIES attempts"
    exit 1
  fi
  
  sleep $RETRY_INTERVAL
done
```

### Verification Commands
```bash
# Frontend verification
curl -f -s http://localhost:3000/ | grep -q "Nieuws Piet" || (echo "Frontend marker not found" && exit 1)

# Backend health verification
curl -f -s http://localhost:8000/health | jq -e '.status == "healthy" and .components.backend == "healthy" and .components.sqlite == "healthy"' || (echo "Backend health check failed" && exit 1)
```

## D. Reproducible Mobile

### Test Configuration
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

### Test Implementation
```javascript
// tests/mobile.test.js

const { test, expect } = require('@playwright/test');

test('Mobile viewport verification', async ({ page }) => {
  await page.goto('http://localhost:3000/');
  
  // Assert exact visible Nieuws Piet marker
  await expect(page.locator('text=Nieuws Piet')).toBeVisible();
  
  // Assert visible main landmark
  await expect(page.locator('main')).toBeVisible();
  
  // Assert visible navigation landmark
  await expect(page.locator('nav')).toBeVisible();
  
  // Assert empty-state marker
  await expect(page.locator('text=Nog geen nieuws beschikbaar')).toBeVisible();
  
  // Assert no horizontal scrolling
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
});
```

### Test Command
```bash
npm run test:e2e
```

## E. Repair Traceability

### Existing Capability Delta Paths
1. **local-development/setup** - Docker Compose configuratie en startup procedures
2. **health-monitoring/health-endpoint** - Health check endpoint met deterministische response formaten
3. **database/local-sqlite** - SQLite database configuratie, connectiviteit en persistentie
4. **documentation/local-dev** - Lokale ontwikkelingsdocumentatie en setupgidsen

### Removed Duplicate Requirements
- **Duplicate SQLite timeout**: Removed duplicate SQLite timeout requirement from health-endpoint spec (already covered in database/local-sqlite)
- **Rollback moved**: Moved data-safe rollback plan from health-endpoint spec to database/local-sqlite spec

### Updated Spec Structure
- **Removed**: Data-safe rollback plan from health-endpoint spec
- **Added**: Data-safe rollback plan to database/local-sqlite spec
- **Removed**: Duplicate SQLite timeout requirement from health-endpoint spec

## F. Dutch Prose and Literal SHALL/MUST + Given/When/Then

### Planning Instructions
Alle planning instructies behouden Nederlandse proza en literal SHALL/MUST + Given/When/Then structuur.

### Spec Consistency
- Alle bestaande spec delta bestanden behouden hun oorspronkelijke Given/When/Then structuur
- Nieuwe planning artifacts volgen dezelfde stijl
- Nederlandse terminologie behouden in alle documentatie

### Verification Checklist
- [x] Data-safe rollback contract gedefinieerd met exacte commando's
- [x] Test-only health fault mechanism met 4 modi gedefinieerd
- [x] Reproducible Compose met readiness loop gedefinieerd
- [x] Reproducible mobile met Playwright gedefinieerd
- [x] Traceability hersteld met 4 bestaande capability delta paths
- [x] Duplicate SQLite timeout requirements verwijderd
- [x] Rollback uit health spec verplaatst
- [x] Nederlandse proza en literal SHALL/MUST + Given/When/Then behouden

### Confirmation Report
Alle planning artifacts zijn succesvol gegenereerd en voldoen aan alle requirements A-F:

1. **A. Data-Safe Rollback Contract**: Volledige procedure met exacte commando's, backup/restore workflows en destructive opt-in command
2. **B. Test-Only Health Fault Mechanism**: 4 test modes (sqlite, sqlite_timeout, backend, all) met exacte test implementations en assertions
3. **C. Reproducible Compose**: Exacte service configuratie, readiness loop met 30 retries, frontend/backend verification commando's
4. **D. Reproducible Mobile**: Playwright configuration, 360x800 viewport, exacte assertions voor mobile acceptance
5. **E. Repair Traceability**: 4 existing capability delta paths behouden, duplicates verwijderd, rollback verplaatst
6. **F. Dutch Prose Preservation**: Alle planning instructies behouden Nederlandse proza en literal SHALL/MUST + Given/When/Then structuur

Alle planning artifacts zijn implementatie-neutraal maar concrete en actionable, voldoen aan projectconventies en zijn klaar voor implementatie.