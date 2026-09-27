# Spec Delta

## Doel

Vestigt de complete lokale ontwikkelomgeving met Docker Compose, Next.js PWA, FastAPI backend en SQLite database voor het persoonlijke nieuwssite-project.

## TOEVOEGDE Requirements

### Requirement: Docker Compose configuratie
Het systeem SHALL een Docker Compose configuratie bevatten die alle applicatieservices met hun afhankelijkheden en netwerken definieert.

#### Scenario: Docker Compose service definitie
- **Given** Docker Compose geïnitialiseerd wordt
- **When** Docker Compose configuratie wordt geladen
- **Then** worden alle vereiste services (frontend, backend) gedefinieerd met juiste poorttoewijzingen en service afhankelijkheden

### Requirement: Docker Compose acceptatie
Het systeem SHALL reproduceerbare Compose acceptatie bieden met exacte `docker compose` commando's, service namen, frontend/backend URLs/ports, readiness conditions en curl/assertie commando's.

#### Scenario: Docker Compose acceptatie
- **Given** Docker Compose startup wordt uitgevoerd
- **When** `docker compose up -d --build` wordt uitgevoerd
- **Then** worden frontend en backend services gestart met exacte service namen, poorttoewijzingen (frontend:3000, backend:8000), readiness conditions en curl/assertie commando's voor verificatie

**Note:** Compose acceptatie is implementatie-neutral maar concrete en actionable. SQLite is backend-volume mounted, niet separate service.

### Requirement: Exact compose command
Het systeem SHALL exacte `docker compose up -d --build` commando implementeren dat EXCLUSIEF frontend en backend services start.

#### Scenario: Exact compose command
- **Given** Docker Compose startup wordt uitgevoerd
- **When** exacte `docker compose up -d --build` commando wordt uitgevoerd
- **Then** worden volgende services gestart:
  - `frontend` service op poort 3000
  - `backend` service op poort 8000
  - SQLite is backend-volume mounted (`nieuws_piet_sqlite_data`), nooit een service

### Requirement: Frontend en backend readiness verificatie
Het systeem SHALL copyable shell loop bieden dat frontend en backend onafhankelijk verifieert met exacte curl commando's en assertions.

#### Scenario: Frontend en backend readiness verificatie
- **Given** Docker Compose startup voltooid is
- **When** readiness verificatie commando wordt uitgevoerd
- **Then** wordt volgende exacte shell loop uitgevoerd:

```bash
#!/bin/bash
# Exacte frontend en backend readiness verificatie

# Max 30 attempts met 1 second sleep
for i in $(seq 1 30); do
    # Frontend verificatie
    FRONTEND_OK=false
    BACKEND_OK=false
    
    # Frontend check
    if curl -f --max-time 5 http://localhost:3000/ > /dev/null 2>&1; then
        if curl -s --max-time 5 http://localhost:3000/ | grep -q "Nieuws Piet"; then
            FRONTEND_OK=true
        fi
    fi
    
    # Backend health check
    if curl -f --max-time 5 http://localhost:8000/health > /dev/null 2>&1; then
        BACKEND_OK=true
    fi
    
    # Beide checks moeten slagen
    if [ "$FRONTEND_OK" = true ] && [ "$BACKEND_OK" = true ]; then
        echo "Both frontend and backend are ready"
        exit 0
    fi
    
    echo "Attempt $i/30: Frontend=$FRONTEND_OK, Backend=$BACKEND_OK"
    sleep 1
done

echo "Error: Frontend or backend not ready after 30 attempts"
exit 1
```

**Note:** Loop verifieert expliciet beide services, slaat op success, exit nonzero na 30 mislukte pogingen. SQLite is nooit een service.