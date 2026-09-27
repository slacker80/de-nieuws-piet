# Proposal

## Waarom

Dit wijzigingsvoorstel vestigt de fundamentele lokale ontwikkelomgeving voor het persoonlijke nieuwssite-project. Het creëert de repository-structuur, Docker Compose-opstelling, Next.js PWA-skelet, FastAPI-healthendpoint, SQLite-configuratie en lokale documentatie die nodig zijn om de applicatie lokaal te draaien zonder externe afhankelijkheden. Dit bootstrap-wijzigingsvoorstel stelt het team in staat om onmiddellijk met ontwikkeling te beginnen met een consistente, reproduceerbare lokale opstelling die overeenkomt met de projectvisie.

## Scope

- Lokale, niet-publieke opstelling met Docker Compose (`frontend` en `backend`), Next.js PWA, FastAPI en SQLite.
- Exacte, uitvoerbare acceptatie: readiness verificatie, health contracten, data-safe rollback/restore en mobiele e2e tests.
- Lokale documentatie van setup, rollback, failure testing en mobiele acceptatie.

## Wat verandert er

- **Repository Structuur**: Creëer monorepo-structuur met duidelijke scheiding van zorgen (frontend, backend, infrastructuur)
- **Docker Compose**: Vestig Compose-configuratie met exact `docker compose up -d --build` (v2 syntax), alleen services `frontend` en `backend`; SQLite is een backend-volume, nooit een service
- **Next.js PWA Skelet**: Creëer basis Next.js Progressive Web App met responsief ontwerp en lege staat bij 360px
- **FastAPI Health Endpoint**: Implementeer health check API-endpoint met exacte JSON bodies en HTTP codes (200/503/500)
- **SQLite Configuratie**: Stel SQLite database configuratie en persistentie in op named volume `nieuws_piet_sqlite_data` met backend mount `/app/data` en database file `/app/data/news.db`
- **Lokale Documentatie**: Creëer uitgebreide lokale ontwikkeldocumentatie
- **Healthcheck Tests**: Implementeer geautomatiseerde healthchecks voor alle componenten
- **Compose Acceptance**: Implementeer reproduceerbare Docker Compose acceptatie met exact `docker compose up -d --build`, service namen, frontend/backend URLs/ports, een readiness loop met exacte HTTP status 200 assertions én body assertions (frontend marker `Nieuws Piet`, backend JSON `status: healthy`) en curl/assertie commando's; frontend smoke gebruikt `http://localhost:3000/` en NOOIT `/health`
- **Data-Safe Rollback**: Implementeer uitvoerbare data-safe rollback/restore met exacte volume identiteit `nieuws_piet_sqlite_data`, host backup `./backups/news.db.<UTC timestamp>.bak` buiten het volume, backup vanaf een read-only mount (`:ro`), `PRAGMA integrity_check` validatie van de backup vóór elke destructieve actie, feitelijk restore voor zowel preserve als destructive pad, en `docker compose down -v` uitsluitend als opt-in
- **Failure Testing**: Implementeer deterministische en test-only failure testing met `APP_ENV=test` guard en `APP_HEALTH_FAULT` whitelist (`sqlite`, `sqlite_timeout`, `backend`, `all`), deterministisch gedrag voor onbekende waarden, app-factory/proces-isolatie met reset cleanup, geen filesystem database mutaties, en budgetten van <=500ms server probe en <=1000ms client assertion
- **Mobile Acceptance**: Implementeer reproduceerbare mobiele acceptatie met lokaal gepinde `@playwright/test` (lockfile), `npm ci` plus lokale browser setup, `npm run test:e2e` na geslaagde readiness, viewport 360x800 vóór navigatie, stabiele UI readiness, localhost `baseURL` met netwerkisolatie en exacte assertions (marker, nav, main, lege staat, geen horizontale scrolling)

## Nieuwe Capabilities

### Nieuwe Capabilities
- `local-development/setup`: Vestigt de complete lokale ontwikkelomgeving met Docker Compose, Next.js PWA, FastAPI backend en SQLite database
- `health-monitoring/health-endpoint`: Biedt health check endpoint voor service statusbewaking
- `database/local-sqlite`: Configureert SQLite database voor lokale ontwikkeling en testing
- `documentation/local-dev`: Creëert uitgebreide lokale ontwikkeldocumentatie

## Niet-doelen

- Geen gebruikersaccounts, authenticatie of accountbeheer
- Geen publieke hosting, HTTPS of externe toegang
- Geen RSS-ingang, LLM-samenvattingen, Telegram-notificaties of externe API-integraties in deze bootstrap
- Geen accounts, API keys, SaaS, browser cloud, betaalde diensten of externe API's in tests
- Geen productiedatabase of orchestratieplatform (Kubernetes/cloud)

## Impact

- **Code**: Nieuwe broncode in `src/` directories voor Next.js frontend en FastAPI backend
- **Configuratie**: Compose bestand, named volume met exacte identiteit, SQLite configuratie en ontwikkelomgeving setup
- **Afhankelijkheden**: Lokale ontwikkelafhankelijkheden voor Node.js, Python en Docker; Playwright browser lokaal geïnstalleerd
- **Testing**: Healthcheck tests, failure testing, readiness verificatie en lokale mobiele e2e tests
- **Documentatie**: Lokale ontwikkeldocumentatie, setupgidsen, rollback-, failure testing- en mobiele testgidsen
- **Compose Acceptance**: Exacte `docker compose up -d --build`, service namen, URLs/ports, readiness conditions en curl/assertie commando's
- **Data-Safe Rollback**: Exacte volume identiteit, read-only backup, integriteitsvalidatie, restore voor preserve én destructive pad en opt-in `docker compose down -v`
- **Failure Testing**: `APP_ENV=test` guard met `APP_HEALTH_FAULT` whitelist, app-factory isolatie, reset cleanup en 500ms/1000ms budgetten

## Risico's

- **Docker/Compose afhankelijkheid**: opstelling vereist Docker met de Compose v2 plugin; gedocumenteerde fallback is handmatige start van frontend en backend.
- **Corrupte backup**: beperkt door `PRAGMA integrity_check` validatie vóór elke destructieve actie en verificatie na herstel.
- **Test-only configuratie in productie**: beperkt door de `APP_ENV=test` guard en deterministische ignore van niet-whitelisted waarden.
- **Playwright installatie**: lokale browser setup kan falen; fallback is handmatige 360px controle in de browser.

## Privacy-impact

Alle data blijft lokaal: SQLite database, backups (`./backups`) en logs staan op de eigen machine. Er worden geen accounts, API keys of externe diensten gebruikt; tests draaien uitsluitend tegen `localhost` en blokkeren niet-localhost verkeer. Er worden geen persoonsgegevens naar externe partijen verstuurd.

## Rollback

Van dit wijzigingsvoorstel zelf geldt: de code is in deze bootstrap-fase nog niet geïmplementeerd (alleen planningsartefacten), dus terugrollen betekent het wijzigingsvoorstel annuleren zonder dat er productiedata is. Voor de opstelling die dit wijzigingsvoorstel vastlegt, geldt de data-safe rollback/restore procedure uit `database/local-sqlite`: standaard `docker compose down` (volume behouden), backup met read-only bron plus integriteitsvalidatie vóór elke destructieve actie, feitelijk restore voor preserve én destructive pad, en `docker compose down -v` uitsluitend als opt-in.

Dit wijzigingsvoorstel vestigt de basis voor alle daaropvolgende features en zorgt voor een consistente lokale ontwikkelervaring voor het team.
