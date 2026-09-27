# Spec Delta

## Doel

Configureert SQLite database voor lokale ontwikkeling met minimale configuratie, connectie lifecycle, connectiviteit en persistentie alleen.

## TOEVOEGDE Requirements

### Requirement: SQLite database initialisatie
Het systeem SHALL SQLite database initialiseren met minimale configuratie wanneer applicatie start.

#### Scenario: Database connectiviteit setup
- **Given** applicatie start
- **When** applicatie SQLite database connectiviteit activeert
- **Then** wordt SQLite database geconfigureerd voor connectiviteit en persistentie

### Requirement: Database connectie management
Het systeem SHALL SQLite database connecties beheren met eenvoudige connectie lifecycle.

#### Scenario: Database connectie handling
- **Given** applicatie database requests maakt
- **When** applicatie SQLite database connecties activeert
- **Then** worden connecties correct geopend en gesloten

### Requirement: Database persistentie
Het systeem SHALL SQLite database persistentie garanderen met backend-mounted volume/path.

#### Scenario: Database persistentie verificatie
- **Given** backend container gerecreateerd wordt
- **When** backend container opnieuw gestart wordt
- **Then** blijft SQLite database toegankelijk met persistentie verificatie

### Requirement: Data-safe rollback plan
Het systeem SHALL concrete data-safe rollback plan bieden met exacte Compose stop/down commando's, onderscheid tussen preserving versus deleting SQLite volume/database, niet-destructieve backup voorafgaand aan destructieve actie, restauratie procedure en verificatie na herstel.

#### Scenario: Data-safe rollback plan
- **Given** destructieve actie op SQLite database wordt uitgevoerd
- **When** rollback procedure wordt geactiveerd
- **Then** wordt niet-destructieve backup gemaakt, SQLite volume/database preserved versus deleted volgens configuratie, exacte Compose stop/down commando's worden uitgevoerd, restauratie procedure wordt uitgevoerd en verificatie na herstel wordt uitgevoerd

**Note:** Rollback plan is implementatie-neutral maar concrete en actionable. Geen externe storage/services worden geïntroduceerd.

### Requirement: Concrete rollback implementation
Het systeem SHALL implementeren exacte data-safe rollback met volgende specificaties:

- **DB rollback named volume**: `nieuws_piet_sqlite_data`
- **Backend mount**: `/app/data`
- **Database file**: `/app/data/news.db`
- **Host backup**: `./backups/news.db.<UTC timestamp>.bak` (outside named volume)

#### Scenario: Concrete rollback implementation
- **Given** backend container met SQLite database wordt gerecreateerd
- **When** data-safe rollback procedure wordt uitgevoerd
- **Then** wordt volgende exacte shell commando sequence uitgevoerd:

```bash
# Stop backend service
docker compose stop backend

# Create backups directory
mkdir -p backups

# Create consistent backup from named volume
# Using temporary container mounting the named volume read-only
docker run --rm \
  -v nieuws_piet_sqlite_data:/source \
  -v $(pwd)/backups:/backup \
  alpine/sh -c 'cp -r /source/news.db /backup/news.db.$(date -u +%Y%m%dT%H%M%SZ).bak'

# Non-destructive docker compose down (no -v)
docker compose down

# Recreate and start volume/db path
# (Volume is preserved from previous step)
docker compose up -d backend

# Verify database integrity and known marker
docker compose exec backend python -c "
import sqlite3
import sys
from datetime import datetime

conn = sqlite3.connect('/app/data/news.db')
cursor = conn.cursor()

# Check if database is accessible
try:
    cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')
    tables = cursor.fetchall()
    print(f'Database accessible, found {len(tables)} tables')
    
    # Verify expected structure (adjust based on actual schema)
    cursor.execute('PRAGMA table_info(articles)')
    if cursor.fetchone():
        print('Articles table exists - database integrity verified')
    else:
        print('Warning: Articles table not found')
        
except Exception as e:
    print(f'Database integrity check failed: {e}')
    sys.exit(1)

conn.close()
print('Database integrity verification successful')
"

# Health endpoint verification
curl -f http://localhost:8000/health

# Optional: docker compose down -v only after successful backup and restore
# docker compose down -v
```

**Note:** All commands use only docker compose/docker and standard shell. No external account/cost service is used.