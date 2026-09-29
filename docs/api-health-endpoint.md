# API Documentatie - Health Endpoint

## Overzicht

Dit document beschrijft de FastAPI health endpoint API voor Nieuws Piet. De health endpoint biedt deterministische monitoring capabilities voor backend en SQLite componenten met exacte JSON/HTTP contracten.

## API Overzicht

### Base URL

```
http://localhost:8000
```

### Health Endpoint

```
GET /health
```

## Response Formats

### Gezonde Response (HTTP 200)

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "backend": "healthy",
    "sqlite": "healthy"
  }
}
```

### SQLite Failure Response (HTTP 503)

```json
{
  "status": "unhealthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "backend": "healthy",
    "sqlite": "unhealthy"
  },
  "error": "SQLite database not accessible"
}
```

### Backend Failure Response (HTTP 500)

```json
{
  "status": "unhealthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "backend": "unhealthy",
    "sqlite": "healthy"
  },
  "error": "Backend internal health check failed"
}
```

### Gecombineerde Failure Response (HTTP 503)

```json
{
  "status": "unhealthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "backend": "unhealthy",
    "sqlite": "unhealthy"
  },
  "error": "Backend internal health check failed and SQLite database not accessible"
}
```

## Request Details

### HTTP Method

```
GET
```

### Headers

| Header | Vereist | Beschrijving |
|--------|----------|-------------|
| `Content-Type` | Nee | `application/json` (response) |
| `User-Agent` | Nee | Client identificatie |

### Query Parameters

| Parameter | Vereist | Beschrijving |
|-----------|----------|-------------|
| `None` | Nee | Geen query parameters |

## Response Details

### HTTP Status Codes

| Status Code | Beschrijving |
|-------------|-------------|
| `200` | Gezond - beide backend en SQLite componenten zijn gezond |
| `500` | Backend ongezond - backend faalt, SQLite gezond |
| `503` | SQLite ongezond - SQLite faalt, backend gezond |
| `503` | Gecombineerde failure - beide backend en SQLite zijn ongezond |

### Response Headers

| Header | Waarde | Beschrijving |
|--------|-------|-------------|
| `Content-Type` | `application/json` | JSON response |
| `Server` | `uvicorn` | Server software |
| `Date` | RFC1123 | Response timestamp |

### Response Body Schema

#### Gezonde Response Schema

```json
{
  "status": "string",
  "timestamp": "string (RFC3339 UTC)",
  "components": {
    "backend": "string",
    "sqlite": "string"
  }
}
```

#### Failure Response Schema

```json
{
  "status": "string",
  "timestamp": "string (RFC3339 UTC)",
  "components": {
    "backend": "string",
    "sqlite": "string"
  },
  "error": "string"
}
```

### Field Beschrijvingen

#### status
- **Waarden**: `healthy`, `unhealthy`
- **Beschrijving**: Algemene health status van het systeem

#### timestamp
- **Formaat**: RFC3339 UTC (bijv. `2024-01-15T10:30:00Z`)
- **Beschrijving**: Exacte timestamp van response generatie

#### components.backend
- **Waarden**: `healthy`, `unhealthy`
- **Beschrijving**: Backend component status

#### components.sqlite
- **Waarden**: `healthy`, `unhealthy`
- **Beschrijving**: SQLite component status

#### error
- **Beschrijving**: Menselijk leesbare error bericht (alleen in failure responses)
- **Waarden**: 
  - `SQLite database not accessible`
  - `Backend internal health check failed`
  - `Backend internal health check failed and SQLite database not accessible`

## Test Scenarios

### Scenario 1: Gezonde Systeem

**Request**:
```bash
curl -s http://localhost:8000/health
```

**Expected Response**:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "backend": "healthy",
    "sqlite": "healthy"
  }
}
```

**Voorwaarden**:
- HTTP Status: 200
- Content-Type: application/json
- Alle componenten: healthy

### Scenario 2: SQLite Failure

**Request**:
```bash
curl -s -H "APP_ENV=test" -H "APP_HEALTH_FAULT=sqlite" http://localhost:8000/health
```

**Expected Response**:
```json
{
  "status": "unhealthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "backend": "healthy",
    "sqlite": "unhealthy"
  },
  "error": "SQLite database not accessible"
}
```

**Voorwaarden**:
- HTTP Status: 503
- Content-Type: application/json
- Backend: healthy
- SQLite: unhealthy
- Error: SQLite database not accessible

### Scenario 3: Backend Failure

**Request**:
```bash
curl -s -H "APP_ENV=test" -H "APP_HEALTH_FAULT=backend" http://localhost:8000/health
```

**Expected Response**:
```json
{
  "status": "unhealthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "backend": "unhealthy",
    "sqlite": "healthy"
  },
  "error": "Backend internal health check failed"
}
```

**Voorwaarden**:
- HTTP Status: 500
- Content-Type: application/json
- Backend: unhealthy
- SQLite: healthy
- Error: Backend internal health check failed

### Scenario 4: Gecombineerde Failure

**Request**:
```bash
curl -s -H "APP_ENV=test" -H "APP_HEALTH_FAULT=all" http://localhost:8000/health
```

**Expected Response**:
```json
{
  "status": "unhealthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "backend": "unhealthy",
    "sqlite": "unhealthy"
  },
  "error": "Backend internal health check failed and SQLite database not accessible"
}
```

**Voorwaarden**:
- HTTP Status: 503
- Content-Type: application/json
- Backend: unhealthy
- SQLite: unhealthy
- Error: Gecombineerde error

## Test Scripts

### 1. Gezonde Systeem Test

```bash
#!/bin/bash
# test_healthy_system.sh

response=$(curl -s -w "%{http_code}" -o /tmp/health_response.json http://localhost:8000/health)
status_code=${response: -3}

if [ "$status_code" = "200" ]; then
    echo "✓ Gezonde systeem test geslaagd"
    cat /tmp/health_response.json | jq .
else
    echo "✗ Gezonde systeem test mislukt: HTTP $status_code"
    cat /tmp/health_response.json
    exit 1
fi
```

### 2. SQLite Failure Test

```bash
#!/bin/bash
# test_sqlite_failure.sh

response=$(curl -s -w "%{http_code}" -o /tmp/health_response.json -H "APP_ENV=test" -H "APP_HEALTH_FAULT=sqlite" http://localhost:8000/health)
status_code=${response: -3}

if [ "$status_code" = "503" ]; then
    echo "✓ SQLite failure test geslaagd"
    cat /tmp/health_response.json | jq .
else
    echo "✗ SQLite failure test mislukt: HTTP $status_code"
    cat /tmp/health_response.json
    exit 1
fi
```

### 3. Backend Failure Test

```bash
#!/bin/bash
# test_backend_failure.sh

response=$(curl -s -w "%{http_code}" -o /tmp/health_response.json -H "APP_ENV=test" -H "APP_HEALTH_FAULT=backend" http://localhost:8000/health)
status_code=${response: -3}

if [ "$status_code" = "500" ]; then
    echo "✓ Backend failure test geslaagd"
    cat /tmp/health_response.json | jq .
else
    echo "✗ Backend failure test mislukt: HTTP $status_code"
    cat /tmp/health_response.json
    exit 1
fi
```

### 4. Gecombineerde Failure Test

```bash
#!/bin/bash
# test_combined_failure.sh

response=$(curl -s -w "%{http_code}" -o /tmp/health_response.json -H "APP_ENV=test" -H "APP_HEALTH_FAULT=all" http://localhost:8000/health)
status_code=${response: -3}

if [ "$status_code" = "503" ]; then
    echo "✓ Gecombineerde failure test geslaagd"
    cat /tmp/health_response.json | jq .
else
    echo "✗ Gecombineerde failure test mislukt: HTTP $status_code"
    cat /tmp/health_response.json
    exit 1
fi
```

## Client Bibliotheken

### 1. Python Client

```python
import httpx
import json
from datetime import datetime

class HealthClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.Client()
    
    def get_health(self, **kwargs) -> dict:
        """Haal health status op"""
        response = self.client.get(f"{self.base_url}/health", **kwargs)
        response.raise_for_status()
        return response.json()
    
    def is_healthy(self) -> bool:
        """Controleer of systeem gezond is"""
        health = self.get_health()
        return health.get("status") == "healthy"
    
    def get_components(self) -> dict:
        """Haal component status op"""
        health = self.get_health()
        return health.get("components", {})

# Gebruik
client = HealthClient()
health = client.get_health()
print(f"Status: {health['status']}")
print(f"Components: {health['components']}")
```

### 2. JavaScript Client

```javascript
class HealthClient {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
        this.client = fetch;
    }
    
    async getHealth() {
        const response = await this.client.fetch(`${this.baseUrl}/health`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    }
    
    async isHealthy() {
        const health = await this.getHealth();
        return health.status === 'healthy';
    }
    
    async getComponents() {
        const health = await this.getHealth();
        return health.components || {};
    }
}

// Gebruik
const client = new HealthClient();

async function checkHealth() {
    const health = await client.getHealth();
    console.log(`Status: ${health.status}`);
    console.log(`Components: ${JSON.stringify(health.components, null, 2)}`);
}

checkHealth();
```

## Error Handling

### 1. HTTP Errors

```python
import httpx

client = HealthClient()

try:
    health = client.get_health()
    print(f"Health status: {health['status']}")
except httpx.HTTPStatusError as e:
    print(f"HTTP error: {e.response.status_code}")
    print(f"Response: {e.response.text}")
except httpx.RequestError as e:
    print(f"Request error: {e}")
```

### 2. JSON Parsing Errors

```python
try:
    health = client.get_health()
    print(f"Status: {health['status']}")
except json.JSONDecodeError as e:
    print(f"JSON parsing error: {e}")
except KeyError as e:
    print(f"Missing key in response: {e}")
```

## Monitoring en Alerting

### 1. Health Check Script

```bash
#!/bin/bash
# health-monitor.sh

HEALTH_URL="http://localhost:8000/health"
LOG_FILE="/var/log/health-monitor.log"
ALERT_EMAIL="admin@example.com"

check_health() {
    response=$(curl -s -w "%{http_code}" -o /tmp/health_check.json "$HEALTH_URL")
    status_code=${response: -3}
    
    if [ "$status_code" = "200" ]; then
        echo "$(date): Health check PASSED" >> "$LOG_FILE"
        return 0
    else
        echo "$(date): Health check FAILED - HTTP $status_code" >> "$LOG_FILE"
        echo "$(date): Health check FAILED - HTTP $status_code" | mail -s "Health Check Alert" "$ALERT_EMAIL"
        return 1
    fi
}

check_health
```

### 2. Health Check Dashboard

```python
# health-dashboard.py
import time
import json
from datetime import datetime
from health_client import HealthClient

class HealthDashboard:
    def __init__(self, client: HealthClient):
        self.client = client
        self.history = []
    
    def collect_health_data(self):
        """Verzamel health data"""
        try:
            health = self.client.get_health()
            data = {
                "timestamp": datetime.now().isoformat(),
                "status": health.get("status"),
                "components": health.get("components", {}),
                "error": health.get("error")
            }
            self.history.append(data)
            return data
        except Exception as e:
            return {
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "error": str(e)
            }
    
    def get_summary(self) -> dict:
        """Haal health samenvatting op"""
        if not self.history:
            return {"status": "unknown", "last_check": None}
        
        latest = self.history[-1]
        return {
            "status": latest["status"],
            "last_check": latest["timestamp"],
            "components": latest.get("components", {}),
            "error": latest.get("error")
        }

# Gebruik
dashboard = HealthDashboard(HealthClient())
while True:
    dashboard.collect_health_data()
    summary = dashboard.get_summary()
    print(f"Health: {summary['status']}")
    time.sleep(60)  # Check elke minuut
```

## Security Considerations

### 1. Authentication

De health endpoint vereist **geen** authenticatie. Dit is opzettelijk voor monitoring purposes. In productieomgevingen:

- Gebruik firewall rules om toegang te beperken
- Implementeer API key authenticatie (als toegevoegd in latere changes)
- Gebruik HTTPS voor transport beveiliging

### 2. Rate Limiting

De health endpoint heeft **geen** rate limiting. In productieomgevingen:

- Implementeer rate limiting per IP
- Monitor voor abuse
- Stel limieten in voor CI/CD pipelines

### 3. Input Validatie

De health endpoint accepteert **geen** input. Alle request parameters worden genegeerd.

## Performance Considerations

### 1. Response Time

- Gezonde response: < 100ms
- Failure responses: < 500ms
- Server probe budget: <= 500ms
- Client assertion budget: <= 1000ms

### 2. Resource Usage

- CPU: < 1% per request
- Memory: < 10MB per request
- Database: Read-only queries

## Integration met Docker Compose

### 1. Healthcheck Configuratie

```yaml
healthcheck:
  test:
    [
      "CMD",
      "python",
      "-c",
      "import json,urllib.request;r=urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4);d=json.load(r);assert r.status==200 and d.get('status')=='healthy',d",
    ]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 15s
```

### 2. Readiness Verificatie

```bash
#!/bin/bash
# readiness-loop.sh

FRONTEND_URL="http://localhost:3000/"
BACKEND_URL="http://localhost:8000/health"
MAX_ATTEMPTS=30
SLEEP_SECONDS=1
CURL_MAX_TIME=5

fetch() {
  local url="$1"
  local response
  response=$(curl -s -w $'\n%{http_code}' --max-time "${CURL_MAX_TIME}" "${url}" 2>/dev/null || true)
  LAST_STATUS=$(printf '%s' "${response}" | tail -n 1)
  LAST_BODY=$(printf '%s' "${response}" | sed '$d')
  [ -n "${LAST_STATUS}" ] || LAST_STATUS="000"
}

FRONTEND_OK=false
BACKEND_OK=false

for i in $(seq 1 "${MAX_ATTEMPTS}"); do
  fetch "${FRONTEND_URL}"
  f_status="${LAST_STATUS}"
  f_body="${LAST_BODY}"
  if [ "${f_status}" = "200" ] && printf '%s' "${f_body}" | grep -q "Nieuws Piet"; then
    FRONTEND_OK=true
  else
    FRONTEND_OK=false
  fi

  fetch "${BACKEND_URL}"
  b_status="${LAST_STATUS}"
  b_body="${LAST_BODY}"
  if [ "${b_status}" = "200" ] && printf '%s' "${b_body}" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"healthy"'; then
    BACKEND_OK=true
  else
    BACKEND_OK=false
  fi

  if [ "${FRONTEND_OK}" = "true" ] && [ "${BACKEND_OK}" = "true" ]; then
    echo "Both frontend and backend are ready"
    exit 0
  fi

  echo "Attempt ${i}/${MAX_ATTEMPTS}: Frontend=${FRONTEND_OK} (${f_status}), Backend=${BACKEND_OK} (${b_status})"
  sleep "${SLEEP_SECONDS}"
done

echo "Error: Frontend or backend not ready after ${MAX_ATTEMPTS} attempts"
exit 1
```

## API Contract

### 1. Contract Definities

- **Health Endpoint**: `/health` GET endpoint
- **Response Format**: JSON met exacte veldnamen en types
- **Error Handling**: HTTP status codes en error messages
- **Timestamp Format**: RFC3339 UTC

### 2. Contract Verificatie

```bash
#!/bin/bash
# contract-validation.sh

# Test gezonde response
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "200"

# Test failure responses
curl -s -o /dev/null -w "%{http_code}" -H "APP_ENV=test" -H "APP_HEALTH_FAULT=sqlite" http://localhost:8000/health | grep -q "503"

# Test JSON schema
response=$(curl -s http://localhost:8000/health)
# Voer JSON schema validatie uit (implementatie-specifiek)
```

## Documentatie Index

- [Health Endpoint API](#health-endpoint-api)
- [Response Formats](#response-formats)
- [Test Scenarios](#test-scenarios)
- [Test Scripts](#test-scripts)
- [Client Bibliotheken](#client-bibliotheken)
- [Error Handling](#error-handling)
- [Monitoring en Alerting](#monitoring-en-alerting)
- [Security Considerations](#security-considerations)
- [Performance Considerations](#performance-considerations)
- [Integration met Docker Compose](#integration-met-docker-compose)
- [API Contract](#api-contract)

---

*API documentatie gegenereerd door OpenSpec bootstrap-local-news-dashboard change*