# Spec Delta

## Doel

Biedt health monitoring capabilities voor de persoonlijke nieuwssite applicatie met een speciale health check endpoint die deterministische minimale contracten volgt.

## TOEVOEGDE Requirements

### Requirement: Health endpoint beschikbaarheid
Het systeem SHALL een health check endpoint op `/health` bieden die de operationele status van backend en SQLite componenten teruggeeft.

#### Scenario: Health endpoint toegankelijkheid
- **Given** client `/health` endpoint acceseert
- **When** client `/health` endpoint aanvraagt
- **Then** geeft endpoint deterministische health status terug met HTTP 200 wanneer beide backend en SQLite componenten gezond zijn

### Requirement: Health endpoint response formaat
Het systeem SHALL deterministische minimale health status in JSON formaat teruggeven met exacte success/failure body en HTTP codes.

#### Scenario: Health endpoint JSON response
- **Given** health endpoint geaccesseerd wordt
- **When** health endpoint aanvraag wordt verwerkt
- **Then** geeft response JSON met statusvelden voor backend en SQLite componenten terug

### Requirement: Health endpoint success response
Het systeem MUST exacte success JSON teruggeven met Content-Type application/json wanneer alle componenten gezond zijn.

#### Scenario: Health endpoint success response
- **Given** alle componenten gezond zijn
- **When** health endpoint aanvraag wordt verwerkt
- **Then** geeft HTTP 200 met Content-Type application/json en volgende JSON terug:
```json
{
  "status": "healthy",
  "timestamp": "<RFC3339_UTC_TIMESTAMP>",
  "components": {
    "backend": "healthy",
    "sqlite": "healthy"
  }
}
```

**Note:** timestamp field MUST be dynamic RFC3339 UTC timestamp. All other fields are exact.

### Requirement: Health endpoint SQLite failure response
Het systeem MUST HTTP 503 met Content-Type application/json teruggeven wanneer SQLite component ongezond is EN backend component gezond is.

#### Scenario: Health endpoint SQLite failure response
- **Given** SQLite component ongezond is en backend component gezond is
- **When** health endpoint aanvraag wordt verwerkt
- **Then** geeft HTTP 503 met Content-Type application/json en volgende JSON terug:
```json
{
  "status": "unhealthy",
  "timestamp": "<RFC3339_UTC_TIMESTAMP>",
  "components": {
    "backend": "healthy",
    "sqlite": "unhealthy"
  },
  "error": "SQLite database not accessible"
}
```

**Note:** timestamp field MUST be dynamic RFC3339 UTC timestamp. All other fields are exact.

### Requirement: Health endpoint backend failure response
Het systeem MUST HTTP 500 met Content-Type application/json teruggeven wanneer backend component ongezond is EN SQLite component gezond is.

#### Scenario: Health endpoint backend failure response
- **Given** backend component ongezond is en SQLite component gezond is
- **When** health endpoint aanvraag wordt verwerkt
- **Then** geeft HTTP 500 met Content-Type application/json en volgende JSON terug:
```json
{
  "status": "unhealthy",
  "timestamp": "<RFC3339_UTC_TIMESTAMP>",
  "components": {
    "backend": "unhealthy",
    "sqlite": "healthy"
  },
  "error": "Backend internal health check failed"
}
```

**Note:** timestamp field MUST be dynamic RFC3339 UTC timestamp. All other fields are exact.

### Requirement: Health endpoint combined failure response
Het systeem MUST HTTP 503 met Content-Type application/json teruggeven wanneer beide backend en SQLite componenten ongezond zijn.

#### Scenario: Health endpoint combined failure response
- **Given** beide backend en SQLite componenten ongezond zijn
- **When** health endpoint aanvraag wordt verwerkt
- **Then** geeft HTTP 503 met Content-Type application/json en volgende JSON terug:
```json
{
  "status": "unhealthy",
  "timestamp": "<RFC3339_UTC_TIMESTAMP>",
  "components": {
    "backend": "unhealthy",
    "sqlite": "unhealthy"
  },
  "error": "Backend internal health check failed and SQLite database not accessible"
}
```

**Note:** timestamp field MUST be dynamic RFC3339 UTC timestamp. All other fields are exact.

### Requirement: Health endpoint backend fault injection test
Het systeem SHALL test arrangement bieden om backend health check intern te verifiëren zonder externe API/account/service afhankelijkheid.

#### Scenario: Backend fault injection test
- **Given** backend fault injection test wordt uitgevoerd
- **When** backend fault injection test wordt uitgevoerd
- **Then** kan backend health check intern veroorzaakt worden om te falen voor test (bijvoorbeeld via configuratievlag)

**Note:** This is a narrowly scoped test-only fault injection/configuration mechanism, not an external API/account/service. An unreachable API is a client connection failure outside `/health` contract.

### Requirement: Health endpoint test-only fault injection configuration
Het systeem SHALL test-only fault injection configuratie bieden die EXACT alleen actief is wanneer `APP_ENV=test` en `APP_HEALTH_FAULT` specifieke waarden toestaat.

#### Scenario: Health endpoint test-only fault injection
- **Given** FastAPI applicatie start met test configuratie
- **When** health endpoint aanvraag wordt verwerkt met test environment
- **Then** fault injection mechanism werkt EXCLUSIEF wanneer:
  - `APP_ENV=test` environment variable is gezet
  - `APP_HEALTH_FAULT` is een van: `sqlite`, `sqlite_timeout`, `backend`, `all`
  - Alle andere `APP_HEALTH_FAULT` waarden worden genegeerd/rejected
  - Normale health behavior blijft actief wanneer `APP_ENV` niet `test` is

**Note:** This is a test-only configuration mechanism, niet een externe API/account/service. Fault injection gebruikt een test double en veroorzaakt nooit filesystem mutation.

### Requirement: Health endpoint test assertions
Het systeem SHALL test assertions bieden voor elke response: status, JSON fields/body, headers en timestamp format.

#### Scenario: Health endpoint test assertions
- **Given** health endpoint response ontvangen wordt
- **When** response wordt geanalyseerd
- **Then** wordt HTTP status code, Content-Type header, JSON body structure, timestamp format en component statusen gevalideerd

**Note:** Test assertions zijn implementatie-neutraal maar actionable voor elke response type.

### Requirement: Health endpoint test scenarios
Het systeem SHALL vier exacte named tests bieden met deterministische assertions en reset cleanup.

#### Scenario: Test 1 - Healthy system
- **Given** FastAPI applicatie start met `APP_ENV=test` en geen `APP_HEALTH_FAULT`
- **When** `/health` endpoint wordt aangevraagd
- **Then** response moet:
  - HTTP status: 200
  - Content-Type: application/json
  - JSON body:
    ```json
    {
      "status": "healthy",
      "timestamp": "<RFC3339_UTC_TIMESTAMP>",
      "components": {
        "backend": "healthy",
        "sqlite": "healthy"
      }
    }
    ```
  - Timestamp format: RFC3339 UTC
  - Alle andere fields exact

#### Scenario: Test 2 - SQLite failure
- **Given** FastAPI applicatie start met `APP_ENV=test` en `APP_HEALTH_FAULT=sqlite`
- **When** `/health` endpoint wordt aangevraagd
- **Then** response moet:
  - HTTP status: 503
  - Content-Type: application/json
  - JSON body:
    ```json
    {
      "status": "unhealthy",
      "timestamp": "<RFC3339_UTC_TIMESTAMP>",
      "components": {
        "backend": "healthy",
        "sqlite": "unhealthy"
      },
      "error": "SQLite database not accessible"
    }
    ```
  - Timestamp format: RFC3339 UTC
  - Alle andere fields exact

#### Scenario: Test 3 - Backend failure
- **Given** FastAPI applicatie start met `APP_ENV=test` en `APP_HEALTH_FAULT=backend`
- **When** `/health` endpoint wordt aangevraagd
- **Then** response moet:
  - HTTP status: 500
  - Content-Type: application/json
  - JSON body:
    ```json
    {
      "status": "unhealthy",
      "timestamp": "<RFC3339_UTC_TIMESTAMP>",
      "components": {
        "backend": "unhealthy",
        "sqlite": "healthy"
      },
      "error": "Backend internal health check failed"
    }
    ```
  - Timestamp format: RFC3339 UTC
  - Alle andere fields exact

#### Scenario: Test 4 - Combined failure
- **Given** FastAPI applicatie start met `APP_ENV=test` en `APP_HEALTH_FAULT=all`
- **When** `/health` endpoint wordt aangevraagd
- **Then** response moet:
  - HTTP status: 503
  - Content-Type: application/json
  - JSON body:
    ```json
    {
      "status": "unhealthy",
      "timestamp": "<RFC3339_UTC_TIMESTAMP>",
      "components": {
        "backend": "unhealthy",
        "sqlite": "unhealthy"
      },
      "error": "Backend internal health check failed and SQLite database not accessible"
    }
    ```
  - Timestamp format: RFC3339 UTC
  - Alle andere fields exact

#### Scenario: Test cleanup
- **Given** health endpoint test voltooid is
- **When** test cleanup wordt uitgevoerd
- **Then** wordt test environment gereset:
  - `APP_ENV` en `APP_HEALTH_FAULT` environment variables worden verwijderd
  - SQLite database wordt hersteld naar normale health check status
  - Backend health check wordt gereset naar normale status

**Note:** Alle tests gebruiken test doubles en veroorzaken nooit filesystem mutation. `sqlite_timeout` server probe budget is <=500ms; client assertion budget is <=1000ms, voorkomende race condition.