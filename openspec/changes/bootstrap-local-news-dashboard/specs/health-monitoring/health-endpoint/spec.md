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

### Requirement: External frontend smoke verification
Het systeem SHALL externe frontend smoke verificatie bieden die frontend bereikbaarheid verifieert na Docker Compose startup afzonderlijk van backend health endpoint.

#### Scenario: Externe frontend smoke verificatie
- **Given** Docker Compose startup voltooid is
- **When** browser of HTTP client frontend's bestaande publieke URL aanvraagt
- **Then** ontvangt client verwachte frontend pagina response met HTTP 200

### Requirement: Health endpoint test assertions
Het systeem SHALL test assertions bieden voor elke response: status, JSON fields/body, headers en timestamp format.

#### Scenario: Health endpoint test assertions
- **Given** health endpoint response ontvangen wordt
- **When** response wordt geanalyseerd
- **Then** wordt HTTP status code, Content-Type header, JSON body structure, timestamp format en component statusen gevalideerd

**Note:** Test assertions zijn implementatie-neutraal maar actionable voor elke response type.