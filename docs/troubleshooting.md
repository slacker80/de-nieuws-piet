# Troubleshooting Documentatie

## Overzicht

Dit document biedt stapsgewijze gidsen voor gemeenschappelijke problemen en fouten die kunnen optreden tijdens het opzetten, ontwikkelen en testen van Nieuws Piet. Het dekt frontend, backend en Docker Compose problemen af.

## Index

1. Docker Probleme
2. Frontend Probleme
3. Backend Probleme
4. Database Probleme
5. Test Probleme
6. Prestatie Probleme
7. Beveiligingsproblemen

## 1. Docker Probleme

### 1.1 Docker Daemon Niet Starten

**Symptom**: `docker: Cannot connect to the Docker daemon at unix:///var/run/docker.sock`

**Oplossing**:

```bash
# Ubuntu/Debian
sudo systemctl start docker
sudo systemctl enable docker

# macOS
open /Applications/Docker.app

# Windows
# Start Docker Desktop applicatie
```

**Preventie**:

- Voeg gebruiker toe aan docker group: `sudo usermod -aG docker $USER`
- Herstart Docker daemon na systeembijwerking

### 1.2 Docker Compose Versie Probleem

**Symptom**: `docker-compose: command not found`

**Oplossing**:

```bash
# Gebruik docker compose (v2) in plaats van docker-compose (v1)
docker compose version

# Als docker-compose nog nodig is, installeer v1 plugin
apt install docker-compose
```

**Preventie**:

- Gebruik altijd `docker compose` in scripts en documentatie
- Controleer Docker Compose versie in CI/CD pipelines

### 1.3 Poortconflicten

**Symptom**: `docker: Error response from daemon: driver failed programming external connectivity: listen tcp 0.0.0.0:3000: bind: address already in use`

**Oplossing**:

```bash
# Vind proces die poort 3000 gebruikt
netstat -tlnp | grep :3000
lsof -i :3000

# Stop het proces
kill -9 <PID>

# Of gebruik andere poorten
# Wijzig frontend poort in compose.yaml
ports:
  - "127.0.0.1:3001:3000"
```

**Preventie**:

- Gebruik unieke poorten voor ontwikkeling
- Controleer poortgebruik voor CI/CD
- Gebruik poort forwarding in Docker Desktop

### 1.4 Volume Problemen

**Symptom**: `docker: Error response from daemon: driver failed programming external connectivity: mkdir /var/lib/docker/volumes/...: permission denied`

**Oplossing**:

```bash
# Controleer volume permissies
ls -la /var/lib/docker/volumes/

# Maak volume met sudo
docker volume create nieuws_piet_sqlite_data

# Of gebruik bind mount in plaats van named volume
volumes:
  - ./data:/app/data
```

**Preventie**:

- Gebruik sudo voor volume beheer
- Controleer diskruimte
- Back-up volumes regelmatig

## 2. Frontend Probleme

### 2.1 Next.js Development Server Probleme

**Symptom**: `Failed to connect to webpack dev server`

**Oplossing**:

```bash
# Controleer frontend container logs
docker logs frontend

# Start frontend opnieuw
docker compose -f compose.yaml -f compose.dev.yaml up -d --build frontend

# Controleer frontend status
curl -s http://localhost:3000
```

**Preventie**:

- Controleer frontend Dockerfile voor correcte poort toewijzing
- Controleer package.json scripts
- Voer `npm run build` voor productie builds

### 2.2 Node.js Dependencies Probleem

**Symptom**: `npm: command not found` of `Cannot find module 'react'`

**Oplossing**:

```bash
# Installeer Node.js
# Ubuntu/Debian
sudo apt update
sudo apt install -y nodejs npm

# macOS
brew install node

# Windows
# Download van https://nodejs.org/

# Herinstalleer dependencies
cd frontend
npm ci
```

**Preventie**:

- Gebruik Node.js version manager (nvm, fnm)
- Controleer package-lock.json
- Gebruik CI/CD voor reproduceerbare builds

### 2.3 Frontend Bouw Probleme

**Symptom**: `Module not found 'styled-jsx'` of andere missing modules

**Oplossing**:

```bash
# Herinstalleer alle dependencies
cd frontend
rm -rf node_modules package-lock.json
npm init -y
npm install

# Of gebruik exacte versies uit package-lock.json
npm ci
```

**Preventie**:

- Gebruik `npm ci` in plaats van `npm install` voor productie
- Controleer package.json voor correcte versies
- Gebruik lockfile versie controle

### 2.4 Playwright Test Probleme

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

**Preventie**:

- Pin `@playwright/test` versie in package.json
- Controleer CI/CD browser installatie
- Gebruik lokale browser installatie in plaats van cloud

## 3. Backend Probleme

### 3.1 FastAPI Server Probleme

**Symptom**: `uvicorn: Could not find the 'app.main:app' object`

**Oplossing**:

```bash
# Controleer backend structuur
cd backend
ls -la app/

# Controleer main.py
nano app/main.py

# Start backend opnieuw
docker compose up -d --build backend
```

**Preventie**:

- Controleer FastAPI app structuur
- Gebruik absolute imports
- Test backend lokaal voor Docker

### 3.2 Python Dependencies Probleem

**Symptom**: `ModuleNotFoundError: No module named 'fastapi'`

**Oplossing**:

```bash
# Activeer virtuele omgeving
cd backend
source venv/bin/activate

# Installeer dependencies
pip install -r requirements.txt

# Of gebruik pipenv
pipenv install
```

**Preventie**:

- Gebruik virtuele omgevingen
- Controleer requirements.txt
- Gebruik CI/CD voor reproduceerbare omgevingen

### 3.3 Health Endpoint Probleme

**Symptom**: `curl: (7) Failed to connect to localhost port 8000 after 0 ms: Connection refused`

**Oplossing**:

```bash
# Controleer backend status
docker ps

# Controleer backend logs
docker logs backend

# Start backend opnieuw
docker compose up -d --build backend

# Test health endpoint directly
curl -v http://localhost:8000/health
```

**Preventie**:

- Controleer backend healthcheck configuratie
- Test health endpoint lokaal
- Monitor backend logs

## 4. Database Probleme

### 4.1 SQLite Database Probleme

**Symptom**: `sqlite3: unable to open database file: /app/data/news.db`

**Oplossing**:

```bash
# Controleer volume status
docker volume inspect nieuws_piet_sqlite_data

# Controleer backend mount
docker exec backend ls -la /app/data

# Herstel database van backup
# (zie data-safe rollback procedures)
```

**Preventie**:

- Controleer volume mount paden
- Back-up database regelmatig
- Test database integriteit

### 4.2 Database Integriteitsproblemen

**Symptom**: `PRAGMA integrity_check` retourneert `not ok`

**Oplossing**:

```bash
# Controleer database bestandsgrootte
docker exec backend du -h /app/data/news.db

# Herstel van backup
# Volg exacte restore commando's uit data-safe rollback

# Of maak nieuwe database aan
# (verlies van data!)
```

**Preventie**:

- Voer integriteitsvalidatie regelmatig uit
- Gebruik data-safe rollback procedures
- Back-up database vóór elke wijziging

## 5. Test Probleme

### 5.1 Backend Test Probleme

**Symptom**: `pytest: command not found` of test failures

**Oplossing**:

```bash
# Controleer pytest installatie
cd backend
pip install pytest

# Of gebruik virtuele omgeving
pip install -r requirements.txt

# Voer tests uit
python -m pytest tests/ -v
```

**Preventie**:

- Controleer test dependencies
- Gebruik CI/CD voor reproduceerbare tests
- Voer tests regelmatig uit

### 5.2 Frontend Test Probleme

**Symptom**: `npm run test:e2e` faalt of Playwright tests mislukken

**Oplossing**:

```bash
# Controleer Playwright installatie
cd frontend
npx playwright install chromium

# Controleer browser status
npx playwright show-browsers

# Voer tests uit met verbose output
npm run test:e2e -- --verbose
```

**Preventie**:

- Pin test dependencies
- Controleer CI/CD test setup
- Monitor test resultaten

## 6. Prestatie Probleme

### 6.1 Langzame Frontend Laden

**Symptom**: `Frontend laadt langzaam (> 5 seconden)`

**Oplossing**:

```bash
# Controleer frontend bundles
cd frontend
npm run build

# Controleer netwerk
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:3000

# Of gebruik browser devtools
```

**Preventie**:

- Optimaliseer statische assets
- Gebruik CDN voor productie
- Implementeer caching

### 6.2 Langzame Backend Reactie

**Symptom**: `Backend health check > 500ms`

**Oplossing**:

```bash
# Controleer backend logs
docker logs backend

# Controleer database query performance
docker exec backend sqlite3 /app/data/news.db "EXPLAIN QUERY PLAN SELECT * FROM articles;"

# Optimaliseer SQLite
# (zie SQLite optimalisatie best practices)
```

**Preventie**:

- Monitor backend prestaties
- Optimaliseer database queries
- Gebruik connection pooling

## 7. Beveiligingsproblemen

### 7.1 CORS Probleme

**Symptom**: `CORS policy error: No 'Access-Control-Allow-Origin' header`

**Oplossing**:

```bash
# Controleer frontend CORS configuratie
# (als toegevoegd in latere changes)

# Of gebruik proxy server
# (zie proxy configuratie)
```

**Preventie**:

- Configureer CORS correct
- Gebruik environment variabelen voor origins
- Test CORS in CI/CD

### 7.2 Authenticatiesproblemen

**Symptom**: `401 Unauthorized` of `403 Forbidden`

**Oplossing**:

```bash
# Controleer authenticatie configuratie
# (als toegevoegd in latere changes)

# Test authenticatie endpoints
# Gebruik Postman of curl
```

**Preventie**:

- Implementeer sterke authenticatie
- Gebruik HTTPS in productie
- Monitor authenticatie logs

## Foutopsporingswerkstroom

### 1. Identificeer het Probleem

1. **Reproduceer het probleem**: Voer stappen uit om het probleem te reproduceren
2. **Controleer logs**: Bekijk frontend/backend/Docker logs
3. **Test endpoints**: Controleer HTTP endpoints met curl
4. **Controleer status**: Controleer Docker container status

### 2. Analyseer de Oorzaak

1. **Controleer configuratie**: Controleer configuratie bestanden
2. **Controleer dependencies**: Controleer geïnstalleerde packages
3. **Controleer netwerk**: Controleer netwerk connectiviteit
4. **Controleer database**: Controleer database status en integriteit

### 3. Implementeer Oplossing

1. **Start services opnieuw**: Gebruik `docker compose restart`
2. **Herinstalleer dependencies**: Gebruik `npm ci` of `pip install -r`
3. **Herstel data**: Gebruik back-up en restore procedures
4. **Controleer configuratie**: Bewerk configuratie bestanden

### 4. Verifieer Oplossing

1. **Voer tests uit**: Voer relevante tests uit
2. **Controleer logs**: Controleer of logs normale status tonen
3. **Test endpoints**: Controleer of endpoints werken
4. **Monitor prestaties**: Controleer prestatie indicatoren

## Snelstartgids voor Foutopsporing

### Frontend Foutopsporing

```bash
# 1. Controleer frontend status
curl -s http://localhost:3000 | grep "Nieuws Piet"

# 2. Controleer frontend logs
docker logs frontend

# 3. Start frontend opnieuw
docker compose -f compose.yaml -f compose.dev.yaml up -d --build frontend

# 4. Test frontend directly
open http://localhost:3000
```

### Backend Foutopsporing

```bash
# 1. Controleer backend status
curl -s http://localhost:8000/health | jq .

# 2. Controleer backend logs
docker logs backend

# 3. Start backend opnieuw
docker compose up -d --build backend

# 4. Test backend health endpoint
curl -v http://localhost:8000/health
```

### Database Foutopsporing

```bash
# 1. Controleer database status
docker exec backend sqlite3 /app/data/news.db "PRAGMA integrity_check;"

# 2. Controleer database tabellen
docker exec backend sqlite3 /app/data/news.db "SELECT name FROM sqlite_master WHERE type='table';"

# 3. Controleer database grootte
docker exec backend du -h /app/data/news.db
```

## Veelgestelde Vragen

### Wat is het verschil tussen `docker logs` en `docker exec`?

- `docker logs`: Toon container logs
- `docker exec`: Voer commando's in container

### Hoe kan ik frontend logs bekijken?

```bash
docker logs frontend
docker logs -f frontend  # follow logs
```

### Hoe kan ik backend logs bekijken?

```bash
docker logs backend
docker logs -f backend  # follow logs
```

### Wat als Docker Compose faalt?

```bash
# Controleer Docker Compose versie
docker compose version

# Controleer compose.yaml syntaxis
docker compose config

# Start services opnieuw
docker compose up -d
```

## Ondersteuning

### Wanneer moet ik CI/CD raadplegen?

- Wanneer fouten optreden in CI/CD pipelines
- Wanneer reproduceerbare stappen nodig zijn
- Wanneer prestatie problemen optreden

### Wanneer moet ik de repository beheerder raadplegen?

- Wanneer fouten optreden in productie
- Wanneer beveiligingsproblemen optreden
- Wanneer data verlies optreedt

## Referenties

- Docker documentatie: https://docs.docker.com/
- Docker Compose documentatie: https://docs.docker.com/compose/
- Next.js documentatie: https://nextjs.org/docs
- FastAPI documentatie: https://fastapi.tiangolo.com/
- Playwright documentatie: https://playwright.dev/

---

*Troubleshooting documentatie gegenereerd door OpenSpec bootstrap-local-news-dashboard change*