# Failure Testing Documentatie

## Overzicht

Dit document beschrijft de deterministische en test-only failure testing voor Nieuws Piet. Het dekt alle stappen af voor fault-injection testing met `APP_ENV=test` guard en `APP_HEALTH_FAULT` whitelist (`sqlite`, `sqlite_timeout`, `backend`, `all`).

## Doel

- Implementeer deterministische en test-only failure testing
- Gebruik `APP_ENV=test` als guard
- Implementeer `APP_HEALTH_FAULT` whitelist (`sqlite`, `sqlite_timeout`, `backend`, `all`)
- Zorg ervoor dat onbekende `APP_HEALTH_FAULT` waarden deterministisch worden genegeerd
- Implementeer app-factory/proces-isolatie per test
- Zorg ervoor dat er GEEN filesystem database mutaties plaatsvinden
- Implementeer budgetten: server probe <=500ms, client assertion <=1000ms voor `sqlite_timeout`

## Vereisten

### Systeemvereisten

- **Node.js**: >= 20
- **Python**: >= 3.10
- **Docker**: Versie 20.10 of hoger (Compose v2 plugin)
- **pytest**: Testrunner voor backend
- **httpx**: HTTP client voor tests

### Aanbevolen Tools

- **VS Code** met Python en Docker extensies
- **GitHub Desktop** (optioneel) voor Git GUI
- **Postman** of **Insomnia** voor API testing (optioneel)

## Installatie

### 1. Python Dependencies

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

# macOS
brew install python

# Windows
# Download van https://www.python.org/downloads/
```

### 2. Backend Dependencies

```bash
# Activeer virtuele omgeving
cd backend
source venv/bin/activate

# Installeer dependencies
pip install -r requirements.txt

# Of gebruik pipenv
pipenv install
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

## Failure Testing Overzicht

### 1. Testomgeving Variabelen

```bash
# Testomgeving
export APP_ENV=test
export APP_HEALTH_FAULT=sqlite

# Gecombineerde failure
export APP_HEALTH_FAULT=all

# Geen failure (gezonde systeem)
unset APP_HEALTH_FAULT
```

### 2. Fault Injection Configuratie

```bash
# Exacte whitelist van `APP_HEALTH_FAULT`
# Alleen deze waarden zijn geldig:
# - sqlite: SQLite-only failure
# - sqlite_timeout: SQLite probe timeout
# - backend: Backend internal self-check failure
# - all: Alle componenten falen

# Onbekende waarden worden deterministisch genegeerd
export APP_HEALTH_FAULT=unknown  # Wordt genegeerd, gezond systeem
```

## Test Scenarios

### 1. Gezonde Systeem Test

**Doel**: Test normale gezonde respons buiten test-omgeving

**Configuratie**:
```bash
# Zet APP_ENV=test maar geen APP_HEALTH_FAULT
export APP_ENV=test
unset APP_HEALTH_FAULT
```

**Verwachte Resultaat**:
- HTTP Status: 200
- JSON Body: `{"status": "healthy", "components": {"backend": "healthy", "sqlite": "healthy"}}`

**Test Script**:
```bash
#!/bin/bash
# test_healthy_system.sh

export APP_ENV=test
unset APP_HEALTH_FAULT

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

**Doel**: Test SQLite-only failure met fault injection

**Configuratie**:
```bash
export APP_ENV=test
export APP_HEALTH_FAULT=sqlite
```

**Verwachte Resultaat**:
- HTTP Status: 503
- JSON Body: `{"status": "unhealthy", "components": {"backend": "healthy", "sqlite": "unhealthy"}, "error": "SQLite database not accessible"}`

**Test Script**:
```bash
#!/bin/bash
# test_sqlite_failure.sh

export APP_ENV=test
export APP_HEALTH_FAULT=sqlite

response=$(curl -s -w "%{http_code}" -o /tmp/health_response.json http://localhost:8000/health)
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

### 3. SQLite Timeout Test

**Doel**: Test SQLite probe timeout met server probe budget <=500ms en client assertion budget <=1000ms

**Configuratie**:
```bash
export APP_ENV=test
export APP_HEALTH_FAULT=sqlite_timeout
```

**Verwachte Resultaat**:
- HTTP Status: 503
- JSON Body: SQLite failure contract (zelfde als `sqlite`)
- Server probe budget: <= 500ms
- Client assertion budget: <= 1000ms

**Test Script**:
```bash
#!/bin/bash
# test_sqlite_timeout.sh

export APP_ENV=test
export APP_HEALTH_FAULT=sqlite_timeout

# Start backend met timeout fault
docker compose up -d --build

# Wacht op readiness
./scripts/readiness-loop.sh

# Voer test uit met timing
start_time=$(date +%s%N)
response=$(curl -s -w "%{http_code}" -o /tmp/health_response.json http://localhost:8000/health)
end_time=$(date +%s%N)
client_time=$(( (end_time - start_time) / 1000000 ))
status_code=${response: -3}

if [ "$status_code" = "503" ]; then
    echo "✓ SQLite timeout test geslaagd"
    echo "Client assertion tijd: ${client_time}ms"
    if [ $client_time -le 1000 ]; then
        echo "✓ Client assertion budget <= 1000ms"
    else
        echo "✗ Client assertion budget overschreden: ${client_time}ms"
        exit 1
    fi
    cat /tmp/health_response.json | jq .
else
    echo "✗ SQLite timeout test mislukt: HTTP $status_code"
    cat /tmp/health_response.json
    exit 1
fi

# Cleanup
docker compose down
```

### 4. Backend Failure Test

**Doel**: Test backend internal self-check failure

**Configuratie**:
```bash
export APP_ENV=test
export APP_HEALTH_FAULT=backend
```

**Verwachte Resultaat**:
- HTTP Status: 500
- JSON Body: `{"status": "unhealthy", "components": {"backend": "unhealthy", "sqlite": "healthy"}, "error": "Backend internal health check failed"}`

**Test Script**:
```bash
#!/bin/bash
# test_backend_failure.sh

export APP_ENV=test
export APP_HEALTH_FAULT=backend

response=$(curl -s -w "%{http_code}" -o /tmp/health_response.json http://localhost:8000/health)
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

### 5. Gecombineerde Failure Test

**Doel**: Test alle componenten falen

**Configuratie**:
```bash
export APP_ENV=test
export APP_HEALTH_FAULT=all
```

**Verwachte Resultaat**:
- HTTP Status: 503
- JSON Body: Gecombineerde error `{"status": "unhealthy", "components": {"backend": "unhealthy", "sqlite": "unhealthy"}, "error": "Backend internal health check failed and SQLite database not accessible"}`

**Test Script**:
```bash
#!/bin/bash
# test_combined_failure.sh

export APP_ENV=test
export APP_HEALTH_FAULT=all

response=$(curl -s -w "%{http_code}" -o /tmp/health_response.json http://localhost:8000/health)
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

## Test Implementatie

### 1. Backend Test Implementatie

#### tests/test_health.py

```python
# tests/test_health.py
import os
import pytest
import httpx
from app.main import create_app

class TestHealthEndpoint:
    """Health endpoint tests met fault injection"""
    
    @pytest.fixture
    def healthy_env(self):
        """Gezonde testomgeving"""
        return {"APP_ENV": "test"}
    
    @pytest.fixture
    def sqlite_fault_env(self):
        """SQLite fault testomgeving"""
        return {"APP_ENV": "test", "APP_HEALTH_FAULT": "sqlite"}
    
    @pytest.fixture
    def backend_fault_env(self):
        """Backend fault testomgeving"""
        return {"APP_ENV": "test", "APP_HEALTH_FAULT": "backend"}
    
    @pytest.fixture
    def combined_fault_env(self):
        """Gecombineerde fault testomgeving"""
        return {"APP_ENV": "test", "APP_HEALTH_FAULT": "all"}
    
    def test_healthy_system(self, healthy_env):
        """Test gezonde systeem"""
        app = create_app(environ=healthy_env)
        client = app.test_client()
        
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["components"]["backend"] == "healthy"
        assert data["components"]["sqlite"] == "healthy"
        assert "error" not in data
    
    def test_sqlite_failure(self, sqlite_fault_env):
        """Test SQLite failure"""
        app = create_app(environ=sqlite_fault_env)
        client = app.test_client()
        
        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["components"]["backend"] == "healthy"
        assert data["components"]["sqlite"] == "unhealthy"
        assert data["error"] == "SQLite database not accessible"
    
    def test_backend_failure(self, backend_fault_env):
        """Test backend failure"""
        app = create_app(environ=backend_fault_env)
        client = app.test_client()
        
        response = client.get("/health")
        assert response.status_code == 500
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["components"]["backend"] == "unhealthy"
        assert data["components"]["sqlite"] == "healthy"
        assert data["error"] == "Backend internal health check failed"
    
    def test_combined_failure(self, combined_fault_env):
        """Test gecombineerde failure"""
        app = create_app(environ=combined_fault_env)
        client = app.test_client()
        
        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["components"]["backend"] == "unhealthy"
        assert data["components"]["sqlite"] == "unhealthy"
        assert data["error"] == "Backend internal health check failed and SQLite database not accessible"
    
    def test_unknown_fault_ignored(self):
        """Test dat onbekende fault waarden worden genegeerd"""
        app = create_app(environ={"APP_ENV": "test", "APP_HEALTH_FAULT": "unknown"})
        client = app.test_client()
        
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["components"]["backend"] == "healthy"
        assert data["components"]["sqlite"] == "healthy"
    
    def test_non_test_env_healthy(self):
        """Test dat APP_ENV ≠ test normale gezonde respons geeft"""
        app = create_app(environ={"APP_ENV": "production"})
        client = app.test_client()
        
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["components"]["backend"] == "healthy"
        assert data["components"]["sqlite"] == "healthy"
```

### 2. Test Fixtures

#### tests/conftest.py

```python
# tests/conftest.py
import pytest
import os
from app.main import create_app

@pytest.fixture
def test_client():
    """Test client fixture"""
    app = create_app(environ={"APP_ENV": "test"})
    return app.test_client()

@pytest.fixture
def sqlite_fault_client():
    """SQLite fault test client"""
    app = create_app(environ={"APP_ENV": "test", "APP_HEALTH_FAULT": "sqlite"})
    return app.test_client()

@pytest.fixture
def backend_fault_client():
    """Backend fault test client"""
    app = create_app(environ={"APP_ENV": "test", "APP_HEALTH_FAULT": "backend"})
    return app.test_client()

@pytest.fixture
def combined_fault_client():
    """Gecombineerde fault test client"""
    app = create_app(environ={"APP_ENV": "test", "APP_HEALTH_FAULT": "all"})
    return app.test_client()
```

### 3. Test Utilities

#### tests/utils/test-helpers.py

```python
# tests/utils/test-helpers.py
import pytest
import httpx
from app.main import create_app

class HealthTestHelper:
    """Helper class voor health tests"""
    
    def __init__(self, app=None):
        self.app = app or create_app()
        self.client = self.app.test_client()
    
    def get_health(self, **kwargs) -> dict:
        """Haal health status op"""
        response = self.client.get("/health", **kwargs)
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
    
    def assert_healthy(self):
        """Assert dat systeem gezond is"""
        health = self.get_health()
        assert health["status"] == "healthy"
        assert health["components"]["backend"] == "healthy"
        assert health["components"]["sqlite"] == "healthy"
        assert "error" not in health
    
    def assert_sqlite_failure(self):
        """Assert dat SQLite faalt"""
        health = self.get_health()
        assert health["status"] == "unhealthy"
        assert health["components"]["backend"] == "healthy"
        assert health["components"]["sqlite"] == "unhealthy"
        assert health["error"] == "SQLite database not accessible"
    
    def assert_backend_failure(self):
        """Assert dat backend faalt"""
        health = self.get_health()
        assert health["status"] == "unhealthy"
        assert health["components"]["backend"] == "unhealthy"
        assert health["components"]["sqlite"] == "healthy"
        assert health["error"] == "Backend internal health check failed"
    
    def assert_combined_failure(self):
        """Assert dat beide componenten falen"""
        health = self.get_health()
        assert health["status"] == "unhealthy"
        assert health["components"]["backend"] == "unhealthy"
        assert health["components"]["sqlite"] == "unhealthy"
        assert health["error"] == "Backend internal health check failed and SQLite database not accessible"

# Globale helper voor gebruik in tests
@pytest.fixture
def helper():
    return HealthTestHelper()
```

## Test Uitvoering

### 1. Backend Tests

```bash
# Voer backend health tests uit
cd backend
python -m pytest tests/ -v

# Voer specifieke test suites
python -m pytest tests/test_health.py -v
python -m pytest tests/test_health.py::TestHealthEndpoint -v

# Voer tests met verbose output
python -m pytest tests/ -v --tb=short
```

### 2. Testomgeving

```bash
# Testomgeving variabelen
cd backend
export APP_ENV=test
export APP_HEALTH_FAULT=sqlite

# Voer tests uit
python -m pytest tests/ -v

# Of gebruik pytest met environment variabelen
APP_ENV=test APP_HEALTH_FAULT=sqlite python -m pytest tests/ -v
```

### 3. CI/CD Test Uitvoering

```yaml
# .github/workflows/backend-tests.yml
name: Backend Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.10, 3.11, 3.12]
    
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v3
      with:
        python-version: ${{ matrix.python-version }}
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r backend/requirements.txt
    - name: Run tests
      run: |
        cd backend
        python -m pytest tests/ -v
      env:
        APP_ENV: test
        APP_HEALTH_FAULT: sqlite
```

## Foutopsporing

### 1. Test Import Problemen

**Symptom**: `ModuleNotFoundError: No module named 'app.main'`

**Oplossing**:

```bash
# Controleer Python path
cd backend
python -c "import sys; print(sys.path)"

# Controleer app structuur
ls -la app/

# Installeer backend in development mode
pip install -e .
```

### 2. Test Execution Problemen

**Symptom**: `ImportError: cannot import name 'create_app' from 'app.main'`

**Oplossing**:

```bash
# Controleer main.py
nano app/main.py

# Controleer create_app functie
python -c "from app.main import create_app; print('Import successful')"
```

### 3. Fault Injection Problemen

**Symptom**: `Test faalt omdat fault niet wordt toegepast`

**Oplossing**:

```bash
# Controleer environment variabelen
export APP_ENV=test
export APP_HEALTH_FAULT=sqlite

# Controleer app configuratie
python -c "
from app.main import create_app
app = create_app()
print('App created successfully')
"
```

### 4. Test Isolation Problemen

**Symptom**: `Test state lekken tussen tests`

**Oplossing**:

```bash
# Gebruik fixtures voor test isolatie
@pytest.fixture
def clean_env():
    # Stel clean environment in
    original_env = os.environ.copy()
    yield
    # Herstel original environment
    os.environ.clear()
    os.environ.update(original_env)
```

## Prestatie Optimalisatie

### 1. Test Snelheid

```bash
# Voer tests met parallelle uitvoering
python -m pytest tests/ -v -n auto

# Voer tests met cache
python -m pytest tests/ --cache-clear
```

### 2. Memory Usage

```bash
# Controleer memory usage
python -m pytest tests/ --co -q
```

## Beveiliging

### 1. Testomgeving Beveiliging

```bash
# Gebruik testomgeving variabelen
export APP_ENV=test
export APP_HEALTH_FAULT=sqlite

# Zorg ervoor dat productieomgeving niet wordt gebruikt
unset APP_ENV
unset APP_HEALTH_FAULT
```

### 2. Input Validatie

```python
# tests/test_input_validation.py
import pytest
from app.main import create_app

def test_no_input_accepted():
    """Test dat health endpoint geen input accepteert"""
    app = create_app()
    client = app.test_client()
    
    # Test met query parameters (moeten worden genegeerd)
    response = client.get("/health?foo=bar")
    assert response.status_code == 200
    
    # Test met POST request (moet 405 retourneren)
    response = client.post("/health")
    assert response.status_code == 405
```

## Snelstartgids

### 1. Installatie

```bash
# Clone repository
git clone https://github.com/username/nieuws-piet.git
cd nieuws-piet/backend

# Maak virtuele omgeving
python3 -m venv venv

# Activeer virtuele omgeving
source venv/bin/activate

# Installeer dependencies
pip install -r requirements.txt
```

### 2. Test Uitvoering

```bash
# Voer backend health tests uit
cd backend
python -m pytest tests/ -v

# Voer tests met testomgeving
APP_ENV=test APP_HEALTH_FAULT=sqlite python -m pytest tests/ -v

# Voer tests met specific fault
APP_ENV=test APP_HEALTH_FAULT=backend python -m pytest tests/test_health.py -v
```

### 3. Test Ontwikkeling

```bash
# Voer tests in development mode
cd backend
python -m pytest tests/ -v --tb=short

# Voer tests met verbose output
python -m pytest tests/ -v -s

# Voer tests met coverage
python -m pytest tests/ --cov=app --cov-report=html
```

## Ondersteuning

### 1. Problemen

- Open een issue op GitHub
- Geef reproduceerbare stappen
- Voeg test logs toe
- Voeg test configuratie toe

### 2. Documentatie

- Lees deze documentatie
- Controleer test implementatie
- Raadpleeg bijvallen in de code

## Referenties

- FastAPI documentatie: https://fastapi.tiangolo.com/
- pytest documentatie: https://docs.pytest.org/
- httpx documentatie: https://www.python-httpx.org/
- Python testing best practices: https://docs.python.org/3/tutorial/testing.html

---

*Failure testing documentatie gegenereerd door OpenSpec bootstrap-local-news-dashboard change*