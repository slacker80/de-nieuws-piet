# Spec

## Purpose

Biedt health monitoring capabilities voor de persoonlijke nieuwssite applicatie met een speciale health check endpoint die deterministische minimale contracten volgt en een deterministische, test-only fault-injection met app-factory isolatie.

## Requirements

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

### Requirement: Health endpoint test-only fault injection configuration
Het systeem SHALL test-only fault injection configuratie bieden die EXACT alleen actief is wanneer `APP_ENV` exact de waarde `test` heeft EN `APP_HEALTH_FAULT` een waarde uit de whitelist is.

#### Scenario: Fault injection alleen in test-omgeving
- **Given** FastAPI applicatie start met `APP_ENV=test` en `APP_HEALTH_FAULT=sqlite`
- **When** `/health` endpoint wordt aangevraagd
- **Then** wordt de SQLite check deterministisch als ongezond gerapporteerd volgens het SQLite failure contract (HTTP 503)

#### Scenario: Normaal gedrag buiten test-omgeving
- **Given** FastAPI applicatie start zonder `APP_ENV`, of met `APP_ENV` anders dan exact `test` (bijvoorbeeld `dev`, `prod`, leeg)
- **When** `/health` endpoint wordt aangevraagd met `APP_HEALTH_FAULT=sqlite`
- **Then** wordt de fault genegeerd
- **And** geldt het normale gezonde contract (HTTP 200)

#### Scenario: Exacte whitelist van `APP_HEALTH_FAULT`
- **Given** `APP_ENV=test` is gezet
- **When** `APP_HEALTH_FAULT` wordt gelezen
- **Then** is de whitelist exact: `sqlite`, `sqlite_timeout`, `backend`, `all`
- **And** wordt elke andere waarde deterministisch genegeerd

#### Scenario: Deterministisch gedrag bij onbekende waarden
- **Given** `APP_ENV=test` is gezet en `APP_HEALTH_FAULT` bevat een niet-whitelisted waarde (bijvoorbeeld `random`, `sqlite_timeout;drop`, leeg of hoofdlettervariant)
- **When** `/health` endpoint twee keer wordt aangevraagd met exact dezelfde input
- **Then** retourneert elke aanvraag exact dezelfde normale gezonde respons (HTTP 200)
- **And** wordt nooit een onbekende, niet-gedefinieerde of willekeurige foutrespons teruggegeven

**Note:** Dit is een test-only configuratiemechanisme, geen externe API/account/service. De implementatie MUST geen bestands systeem mutaties aan de database uitvoeren; fault injection werkt uitsluitend met test doubles.

### Requirement: Health endpoint test-only fault injection gedrag
Het systeem SHALL test arrangement bieden om backend health check en SQLite health check intern te verifiëren zonder externe API/account/service afhankelijkheid.

#### Scenario: Backend fault injection test
- **Given** `APP_ENV=test` en `APP_HEALTH_FAULT=backend`
- **When** `/health` endpoint wordt aangevraagd
- **Then** wordt de backend self-check intern als ongezond gerapporteerd volgens het backend failure contract (HTTP 500)

#### Scenario: Geen filesystem database mutatie
- **Given** een fault (`sqlite`, `sqlite_timeout`, `backend`, `all`) actief is
- **When** `/health` endpoint wordt aangevraagd
- **Then** wordt GEEN database bestand aangemaakt, geschreven, hernoemd of verwijderd
- **And** wordt de echte database onaangetast gelaten

**Note:** Onbereikbare externe API's vallen buiten het `/health` contract en worden niet als fault injection mechanisme gebruikt.

### Requirement: Health endpoint test isolatie en reset
Het systeem SHALL elke health test uitvoeren op een via app-factory nieuw geconstrueerde applicatie-instance en elke test volledig resetten.

#### Scenario: App-factory isolatie per test
- **Given** health test wordt gestart
- **When** test de applicatie-factory (bijvoorbeeld `create_app()`) aanroept met test-environment variabelen
- **Then** wordt een nieuwe, onafhankelijke applicatie-instance gebouwd
- **And** leest die instance `APP_ENV` en `APP_HEALTH_FAULT` bij constructie
- **And** deelt geen module-globale state met eerdere tests

#### Scenario: Proces- of instance-isolatie bij fault tests
- **Given** meerdere fault tests achter elkaar draaien
- **When** een test een fault instelt
- **Then** bereikt die fault geen andere testinstance of de normale testserver

#### Scenario: Reset cleanup
- **Given** health test voltooid is
- **When** test cleanup wordt uitgevoerd
- **Then** worden `APP_ENV` en `APP_HEALTH_FAULT` verwijderd uit de testomgeving
- **And** wordt de applicatie-instance weggegooid (niet hergebruikt)
- **And** worden GEEN database bestanden gewijzigd

### Requirement: Health endpoint test assertions
Het systeem SHALL test assertions bieden voor elke response: status, JSON fields/body, headers en timestamp format.

#### Scenario: Health endpoint test assertions
- **Given** health endpoint response ontvangen wordt
- **When** response wordt geanalyseerd
- **Then** wordt HTTP status code, Content-Type header, JSON body structure, timestamp format en component statusen gevalideerd

**Note:** Test assertions zijn implementatie-neutraal maar actionable voor elk response type.

### Requirement: Health endpoint test scenarios
Het systeem SHALL vijf exacte named tests bieden met deterministische assertions en reset cleanup.

#### Scenario: Test 1 - `test_healthy_system`
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

#### Scenario: Test 2 - `test_sqlite_failure`
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

#### Scenario: Test 3 - `test_sqlite_timeout`
- **Given** FastAPI applicatie start met `APP_ENV=test` en `APP_HEALTH_FAULT=sqlite_timeout`
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
  - Server-side probe budget: de SQLite probe MUST worden afgekapt binnen <=500ms
  - Client-side assertion budget: totale response MUST voltooid zijn binnen <=1000ms
  - Alle andere fields exact

**Note:** De timeout fault gebruikt een test double en voert GEEN filesystem database mutatie uit. Hetzelfde SQLite failure contract geldt; de test onderscheidt zich door de expliciete 500ms/1000ms budget assertions.

#### Scenario: Test 4 - `test_backend_failure`
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

#### Scenario: Test 5 - `test_combined_failure`
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
- **Given** health test voltooid is
- **When** test cleanup wordt uitgevoerd
- **Then** wordt de testomgeving gereset:
  - `APP_ENV` en `APP_HEALTH_FAULT` environment variables worden verwijderd
  - De applicatie-instance wordt weggegooid (app-factory isolatie)
  - Er zijn GEEN filesystem database mutaties uitgevoerd
  - De volgende test start met een schone, normale health check status

**Note:** Alle tests gebruiken test doubles en veroorzaken nooit filesystem database mutatie. `sqlite_timeout` server probe budget is <=500ms; client assertion budget is <=1000ms, waardoor race conditions vermeden worden.

(End of file - total 304 lines)