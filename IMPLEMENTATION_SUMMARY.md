# Bootstrap Local News Dashboard - Implementatie Samenvatting

## Overzicht

Dit document biedt een overzicht van de implementatie van OpenSpec change `bootstrap-local-news-dashboard`. Het dekt alle taken in secties 7-10 (inclusief) en de uitgevoerde verificatie. Alle aantallen hieronder zijn geteld uit `openspec/changes/bootstrap-local-news-dashboard/tasks.md`; alle meetresultaten zijn op **2026-09-28** feitelijk uitgevoerd en worden bovendien afgedwongen door de tests in `backend/tests/`.

## Implementatiestatus

### Telling van de checkboxen (werkelijk geteld)

- **Alle checkboxen**: 154 totaal — 154 `[x]`, 0 `[ ]`
- **Aggregaat-parents**: 10 (9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6)
- **Leaf-taken** (154 min 10 aggregaat-parents): 144 totaal — **144 voltooid**, **0 open**
- Open leaf-taken: **geen**

### Status per sectie

| Sectie | Checkboxen | Voltooid | Status |
| --- | --- | --- | --- |
| 1. Repository Structuur Setup | 5 | 5 | voltooid |
| 2. Docker Compose Configuratie | 9 | 9 | voltooid |
| 3. Next.js PWA Skelet | 7 | 7 | voltooid |
| 4. FastAPI Health Endpoint | 19 | 19 | voltooid |
| 5. SQLite Database Configuratie | 6 | 6 | voltooid |
| 6. Lokale Documentatie | 9 | 9 | voltooid |
| 7. Healthcheck Tests | 7 | 7 | voltooid (7.2, 7.3 met echte Compose-/Next.js-meting) |
| 8. Integratietests | 8 | 8 | voltooid (8.1-8.8, zie meetresultaten hieronder) |
| 9. Exacte Verificatie Taken | 43 | 43 | voltooid (9.1 en 9.4 met runtime-uitvoering) |
| 10. Discrete Verified Tasks | 41 | 41 | voltooid (10.1-10.6 inclusief parents) |
| **Totaal** | **154** | **154** | — |

Leaf-basis (zonder de 10 aggregaat-parents): secties 1-6 = 55/55, sectie 7 = 7/7, sectie 8 = 8/8, sectie 9 = 39/39, sectie 10 = 35/35 → **144/144 voltooid, 0 open**.

## Meetresultaten integratietests (sectie 8)

Alle onderstaande waarden komen uit feitelijke uitvoering; ze worden gecontroleerd door `backend/tests/test_integration.py` (11 tests, allemaal groen).

### 8.1 Test complete applicatie startup met `docker compose up -d --build` (clean-checkout)

- Schone checkout: **76** getrackte bestanden gekopieerd naar een tijdelijke map, met eigen projectnaam (`cleantest<pid><random>`, bijvoorbeeld `cleantest450524233c3cba`), eigen poorten (13000/18000 via `free_port`), eigen volume en eigen netwerk — de echte stack en de echte volume blijven buiten beeld.
- Startopdracht: `docker compose up -d --build` → **rc 0**.
- Readiness: frontend en backend beiden HTTP 200 na **4 pogingen**; de opbouw tot ready duurde 11,4 s.
- `docker compose ps --format json`: backend `running` met healthstatus `healthy`, frontend `running`.
- Afbraak van de eigen context: `docker compose down -v --remove-orphans` → rc 0, `containers_after` = `{}`, eigen image-tags verwijderd, werkmap verwijderd.
- Echte volume `nieuws_piet_sqlite_data`: `CreatedAt` vóór = na = `2026-09-27T23:56:52+02:00` (ongewijzigd).

### 8.2 Verifieer dat frontend en backend toegankelijk zijn

- Frontend `http://127.0.0.1:3000/` → **HTTP 200** met marker `Nieuws Piet`.
- Backend `http://127.0.0.1:8000/health` → **HTTP 200**.

### 8.3 Test health endpoint integratie met Docker Compose

- `GET /health` → **HTTP 200**, JSON body `{"status": "healthy", "components": {"backend": "healthy", "sqlite": "healthy"}}` (**status: healthy**).
- Docker-healthcheck van de backendcontainer meldt `healthy` (interval 10s, timeout 5s, retries 5, start_period 15s), gemeten via `docker compose ps --format json`.

### 8.4 Verifieer mobiele responsiviteit van Next.js applicatie bij 360px

- Puppeteer/Chromium-meting bij viewport **360x800**: `scrollWidth` 360 == `clientWidth` 360, `noHorizontalScroll: true`, lege lijst met overstromende elementen.

### 8.5 Test applicatie functionaliteit met lege staat

- Zichtbaar: `Nog geen nieuws beschikbaar`, `<nav>`, `<main>`, `<h1>Nieuws Piet</h1>`, `rel="manifest"`.
- `consoleErrors: []` (geen consolefouten bij het laden), `blocked: []` (geen niet-localhost verkeer), bewuste controle `fetch('https://example.invalid/nieuws')` → `blocked`.

### 8.6 Documenteer succesvolle integratietest resultaten

- Dit hoofdstuk plus de sectie "Controles" hieronder: de meetresultaten van 8.1-8.5 en 8.7-8.8.

### 8.7 Implementeer reproduceerbare mobiele acceptatie bij 360x800 met Playwright

- `npm run test:e2e` → **rc 0** in 9,7 s met **1 passed (2.6s)**.
- Readiness was geslaagd vóór de e2e-run (0,1 s), viewport **360x800** staat vóór `page.goto`, lokale Chromium in `~/.cache/ms-playwright/chromium-1243` (geen cloud browser), `@playwright/test` vastgepind op `1.63.0`.

### 8.8 Voer de frontend/backend readiness loop uit en laat die slagen vóór `npm run test:e2e`

- `scripts/readiness-loop.sh` → **Readiness geslaagd na 1 pogingen** (rc 0; feitelijke backend-body in een tijdelijk bestand, geen pad-interpolatie in de broncode).
- Op de volgorde start → readiness → e2e (zoals `scripts/run-mobile-e2e.sh` en `frontend/package.json` die afdwingen).

## Meetresultaten sectie 9

### 9.1.7 - 9.1.10 Data-safe rollback met feitelijke uitvoering

Uitgevoerd in een wegwerp-context (eigen projectnaam `rollback<pid><random>` — bijvoorbeeld `rollback450524bb9939a1`, eigen volume `nieuws_piet_sqlite_data_rollback...`, eigen netwerk, eigen backup-directory via `NIEUWS_PIET_DB_BACKUP_DIR`); alle 6 tests groen in 93,3 s (inclusief de twee markerproeven hieronder).

- **Backup**: `scripts/db-rollback.sh backup` → rc 0, `news.db.<UTC>.bak` aangemaakt buiten het volume.
- **Corruptie**: de database in het eigen volume is feitelijk overschreven met `corrupt-<epoch>` (via `alpine:3.20`), zodat preserve echt iets moest herstellen.
- **Preserve (9.1.7)**: rc 0 met `==> Non-destructive down`, `==> ... restore vóór backend-start`, `==> Feitelijk restore naar /app/data/news.db`, `OK: preserve-pad voltooid (volume ... behouden)`; volume-`CreatedAt` na preserve exact gelijk aan de startwaarde (volume behouden).
- **Refusie**: `scripts/db-rollback.sh reset` → **exit 2**, tekst `GEWEIGERD`, geen `==> Opt-in: docker compose down -v`, stack bleef `running` en het volume ongewijzigd.
- **Destructief pad (9.1.7/9.1.8)**: `reset --allow-volume-removal` → rc 0; volgorde in de uitvoer backup → integriteitsvalidatie → `==> Opt-in: docker compose down -v` → `==> Feitelijk restore naar /app/data/news.db` → verificatie; de `CreatedAt` van het volume **wijzigde** (volume opnieuw aangemaakt); nieuwe backup aanwezig.
- **9.1.8**: `docker compose up -d --build` na restore → rc 0, `/health` daarna **status: healthy**; `docker compose exec -i backend python` geeft `integrity_check: ok`, `tables: > 0`, `marker: nieuws-piet`.
- **9.1.9**: `curl`/HTTP op `/health` → **HTTP 200** met JSON `status: healthy` en `components: {backend: healthy, sqlite: healthy}`.
- **9.1.10**: volgorde in de uitvoer: backup → integriteitsvalidatie → `down -v` → restore → verificatie, en **geen enkele stap** met restore vóór `down -v`. Opruiming van de eigen context: `down -v` rc 0, geen resterende containers of images; de echte volume `nieuws_piet_sqlite_data` is vóór en na identiek.

### 9.4.1 - 9.4.12 Mobile exact verificatie

13 tests in `backend/tests/test_mobile_runtime.py`, allemaal groen (38,9 s): lockfile-pin `@playwright/test` 1.63.0, `npm run test:e2e`, readiness vóór de e2e, lokale Chromium (geen cloud browser), viewport 360x800 vóór navigatie, marker `Nieuws Piet`, zichtbare `nav` en `main`, tekst `Nog geen nieuws beschikbaar`, `scrollWidth <= clientWidth`, auto-retry-readiness zonder vaste slaaptijd met netwerkisolatie (alleen localhost) en een expliciete ban op accounts/API-keys/SaaS/cloud-browser/betaalde diensten/externe API's.

## Herstelronde: review-blokkades en medium-punten

Alle vier de review-blokkades zijn opgelost en met eigen tests afgedwongen; de
medium-punten zijn eveneens verwerkt. Elke claim hieronder is in deze ronde
feitelijk uitgevoerd.

### Blokkade 1 — expliciete markercontrole in *beide* restoreverificatiepaden

- `scripts/db-rollback.sh`: `verify_data` én `verify_full` toetsen nu naast
  `PRAGMA integrity_check` en de aanwezigheid van tabellen ook expliciet
  `bootstrap_marker.initialized == 'nieuws-piet'` (met `try/except sqlite3.Error`),
  printen `integrity_check: ... | tables: ... | marker: ...` en sluiten alleen af
  met exit 0 wanneer alle drie kloppen.
- `test_9_1_7_restore_weigert_ontbrekende_of_verkeerde_marker`: de backup wordt
  feitelijk beschadigd (rij verwijderd resp. waarde `fout`); `restore` geeft rc ≠ 0
  en **geen** `OK: backup teruggezet`, met `marker: geen marker` respectievelijk
  `marker: fout` in de uitvoer; daarna herstel met de goede backup → rc 0 en
  `marker: nieuws-piet`.
- `test_9_1_10_preserve_verificatie_weigert_marker_afwijking`: de backend schrijft
  de marker bij elke startup opnieuw, dus de live database wordt **ná** de start
  beschadigd; integriteit blijft `ok` (dus `/health` blijft 200 healthy) maar de
  marker niet. `verify_full` — de exacte functiebron uit `db-rollback.sh` — geeft
  daarna rc ≠ 0 met `integrity_check: ok | ... | marker: fout` respectievelijk
  `marker: geen marker`.

### Blokkade 2 — 9.4.4 voert feitelijk `npm ci` uit

- `runtime_env.npm_ci_isolated()` kopieert alléén `package.json` +
  `package-lock.json` naar een verse tijdelijke werkmap, draait daar
  `npm ci --no-audit --no-fund`, controleert dat de pin, de lockfile-versie en de
  geïnstalleerde versie identiek zijn (`X.Y.Z`), draait `npx playwright install chromium`
  en probeert `chromium.executablePath()`; de werkmap wordt in een `finally`
  altijd verwijderd.
- `test_9_4_4_runtime_npm_ci_en_lokale_browser` → **1 passed in 19,9 s**
  (los gedraaid; meting in deze omgeving: `npm ci` ≈ 7,6 s, `playwright install
  chromium` ≈ 1,6 s, beide rc 0, verse `node_modules` aanwezig).

### Blokkade 3 — cleanup-registratie direct ná een geslaagd `up`

- `ensure_stack_up()` registreert de afbouw **direct ná** `docker compose up -d --build`,
  vóór readiness en health; een fout vóór die registratie ruimt eigen restanten
  zelf op, een fout daarna breekt de eigen context af met `stop_stack(...)` en
  gooit daarna door. `stop_stack()` controleert containers, gepubliceerde poorten,
  volumestatus en (op verzoek) het netwerk en geeft `{ok, problems, ...}`;
  `cleanup_all()` meldt elke afwijking in plaats van die te verbergen.
- `test_startup_faal_ruimt_eigen_context_op` → **1 passed in 12,2 s** (los
  gedraaid): de readiness-probe ziet dat de afbouw al geregistreerd is, de
  verwachte `AssertionError: ... niet ready` volgt, en daarna zijn er geen
  containers, geen eigen volume, geen eigen netwerk, zijn de eigen poorten vrij en
  zijn de eigen images verwijderd; de hoofdstack (naam/state/health) en de echte
  volume `CreatedAt` zijn ongewijzigd.
- Volledige suite-draai: **geen enkele** `[runtime_env] cleanup ... meldt een
  probleem`-melding.

### Blokkade 4 — strikte volume-identificator-validatie

- `validate_volume_name()` in `scripts/db-rollback.sh`, aangeroepen **vóór** het
  `case "${MODE}"`-blok: `^[A-Za-z0-9][A-Za-z0-9_.-]*$` — paden, slashes,
  backslashes, kolonnen, witruimte en leidende tekens worden geweigerd nog vóór
  de eerste docker-opdracht. Dezelfde regel geldt Python-zijde via
  `validate_docker_name()` voor project-, volume- en netwerknamen.
- `test_9_1_volumenaam_weigert_pad_slash_en_witruimte`: 12 ongeldige namen →
  rc 1 met `FOUT: ... geen geldige Docker named-volume-naam` en géén dispatch
  (geen `Gebruik:`-uitvoer); lege waarde valt terug op de named volume;
  geldige naam + `--help` → rc 0.
- `test_9_1_resource_identificatoren_gestrenge_validatie`: dezelfde lijst wordt
  via `validate_docker_name()` als `AssertionError` afgewezen, geldige namen
  komen ongewijzigd terug. Beide tests → **2 passed in 0,53 s**.

### Medium-punten

- **Unieke suffixes**: `unique_slug()` = prefix + `os.getpid()` + `secrets.token_hex(4)`
  (geen seconde-timestamp) voor clean-checkout-, rollback- en isolatie-contexten.
- **Geen misleidende voltooiing bij skips**: `conftest.py` registreert elke
  overgeslagen test in `runtime_env.skipped_tests`; het alfabetisch laatste
  bestand `backend/tests/test_zz_lokale_suite_volledig.py` eist een lege lijst en
  meldt precies wat er overslaat. Geverifieerd met een tijdelijke overslaande
  test → de guard faalde met `...::test_tmp_skip_probe: Skipped: probeerskip`.
- **Bestandsaantallen**: werkboom **80** bestanden (76 getrackt + 4 nieuwe);
  `git status` toont **14** regels (10 gewijzigd + 4 nieuw), niet 13.
- **Poortvrijheid**: `port_free()` zet `SO_REUSEADDR`, zodat een rustende
  TIME_WAIT-verbinding niet als "bezet" wordt gemeld (actieve luisteraars wel);
  `wait_ports_free()` vangt het naijlen van `docker compose down` op.

## Gemaakt Documentatie

### 1. README.md
- **Locatie**: `/home/peter/git/de-nieuws-piet/README.md`
- **Inhoud**: Project overzicht, installatie, ontwikkeling, gebruik, tests, bijdragen, licentie
- **Status**: ✅ Volledig

### 2. Docker Compose Documentatie
- **Locatie**: `/home/peter/git/de-nieuws-piet/docs/docker-compose.md`
- **Inhoud**: Docker Compose configuratie, installatie, startup, readiness verificatie, data-safe rollback, troubleshooting
- **Status**: ✅ Volledig

### 3. Ontwikkelingsopstelling Documentatie
- **Locatie**: `/home/peter/git/de-nieuws-piet/docs/development-setup.md`
- **Inhoud**: Lokale ontwikkelomgeving setup, vereisten, installatie, frontend/setup, backend/setup, Docker Compose, synchronisatie, foutopsporing
- **Status**: ✅ Volledig

### 4. Troubleshooting Documentatie
- **Locatie**: `/home/peter/git/de-nieuws-piet/docs/troubleshooting.md`
- **Inhoud**: Docker problemen, frontend problemen, backend problemen, database problemen, test problemen, prestatie problemen, beveiligingsproblemen
- **Status**: ✅ Volledig

### 5. API Documentatie - Health Endpoint
- **Locatie**: `/home/peter/git/de-nieuws-piet/docs/api-health-endpoint.md`
- **Inhoud**: API overzicht, response formats, request details, test scenarios, test scripts, client bibliotheken, error handling, monitoring, security, performance, integratie
- **Status**: ✅ Volledig

### 6. Mobiele Playwright Acceptatie Documentatie
- **Locatie**: `/home/peter/git/de-nieuws-piet/docs/mobile-playwright-acceptance.md`
- **Inhoud**: Mobiele acceptatie testing, vereisten, installatie, setup, test implementatie, test uitvoering, foutopsporing, prestatie optimalisatie, beveiliging, rapportage, automatisering, snelstartgids
- **Status**: ✅ Volledig

### 7. Data-Safe Rollback en Restore Documentatie
- **Locatie**: `/home/peter/git/de-nieuws-piet/docs/data-safe-rollback-restore.md`
- **Inhoud**: Data-safe rollback/restore procedures, vereisten, installatie, backup/restore overzicht, preserve pad, destructive pad, shell commando referentie, foutopsporing, automatisering, snelstartgids
- **Status**: ✅ Volledig

### 8. Failure Testing Documentatie
- **Locatie**: `/home/peter/git/de-nieuws-piet/docs/failure-testing.md`
- **Inhoud**: Failure testing, vereisten, installatie, overzicht, test scenario's, test implementatie, test fixtures, test utilities, test uitvoering, foutopsporing, prestatie optimalisatie, beveiliging, snelstartgids
- **Status**: ✅ Volledig

### 9. Discrete Verified Tasks Documentatie
- **Locatie**: `/home/peter/git/de-nieuws-piet/docs/discrete-verified-tasks.md`
- **Inhoud**: Discrete verified tasks, vereisten, implementatie, verificatie, snelstartgids
- **Status**: ✅ Volledig

## Verificatie

### 1. OpenSpec Status

```bash
openspec status --change "bootstrap-local-news-dashboard" --json
```

**Resultaat** (relevant): de vier planning-artifacts (`proposal`, `specs`, `design`, `tasks`) staan op status `done`; `isPlanningComplete: true`.

### 2. OpenSpec Instructions

```bash
openspec instructions apply --change "bootstrap-local-news-dashboard" --json
```

**Resultaat** (relevant):

```json
"progress": { "total": 154, "complete": 154, "remaining": 0 }
```

- Progress: 154/154 checkboxen voltooid, 0 resterend.

### 3. Git Status

```bash
git status --short
```

**Resultaat**: 14 regels in `git status --short` (10 gewijzigde + 4 nieuwe bestanden), **niet gecommit** (deze ronde is uitgevoerd als backup-codebouwer: wijzigen en verifiëren, geen commit/push).

| Type | Bestanden |
| --- | --- |
| gewijzigd | `IMPLEMENTATION_SUMMARY.md`, `backend/tests/conftest.py`, `backend/tests/test_discrete_verified_tasks.py`, `backend/tests/test_exact_verification.py`, `backend/tests/test_healthcheck.py`, `backend/tests/test_integration.py`, `frontend/playwright.config.js`, `openspec/changes/bootstrap-local-news-dashboard/tasks.md`, `scripts/db-rollback.sh`, `scripts/readiness-loop.sh` |
| nieuw | `backend/tests/runtime_env.py`, `backend/tests/test_mobile_runtime.py`, `backend/tests/test_rollback_runtime.py`, `backend/tests/test_zz_lokale_suite_volledig.py` |

### 4. Git Diff

```bash
git diff --check
git diff --cached --check
```

**Resultaat**: beide exit 0 (geen whitespace-fouten). `bash -n scripts/*.sh` → exit 0; `python3 -m py_compile backend/tests/*.py` → exit 0.

## Controles

### 1. Backend tests (volledige suite)

```bash
cd backend && python3 -m pytest
```

**Resultaat**: `159 passed` (totaal 159 tests, 0 overgeslagen; uitvoeringstijd 199,99 s ≈ 3 min 20 s; geen `[runtime_env] cleanup ... meldt een probleem`-meldingen; alle eigen containers/netwerken/poorten na afloop opgeruimd).

| Bestand | Tests | Resultaat |
| --- | --- | --- |
| `tests/test_db.py` | 15 | passed |
| `tests/test_discrete_verified_tasks.py` | 36 | passed |
| `tests/test_exact_verification.py` | 42 | passed (0 skipped; incl. 2 volumenaam-validatietests) |
| `tests/test_health.py` | 21 | passed |
| `tests/test_healthcheck.py` | 14 | passed (7.2/7.3 met echte Compose- en Next.js-meting) |
| `tests/test_integration.py` | 11 | passed (8.1-8.8 + opruimgarantie bij gefaalde start) |
| `tests/test_mobile_runtime.py` | 13 | passed (9.4.1-9.4.12, 9.4.4 met feitelijk `npm ci`) |
| `tests/test_rollback_runtime.py` | 6 | passed (9.1.7-9.1.10 + 2 markerproeven) |
| `tests/test_zz_lokale_suite_volledig.py` | 1 | passed (guard: 0 overgeslagen tests) |
| **Totaal** | **159** | **passed, 0 skipped** |

- [x] Backend health/healthcheck/db-tests (36 + 21 + 15 = 72 geslaagd)
- [x] Discrete verified tasks tests (36/36 geslaagd)
- [x] Exacte verificatietests sectie 9 (42/42 geslaagd, 0 overgeslagen)
- [x] Integratietests met Docker (11/11 geslaagd, inclusief clean-checkout start)
- [x] Mobiele Playwright-verificatie (13/13 geslaagd, `npm run test:e2e` → `1 passed`)
- [x] Feitelijk restore + opt-in `down -v` (6/6 geslaagd, eigen wegwerp-context)
- [x] Review-blokkade 1: markercontrole in `verify_data` én `verify_full` + 2 afwijzende tests
- [x] Review-blokkade 2: `npm ci` in een verse tempkopie (`test_9_4_4_runtime_npm_ci_en_lokale_browser`)
- [x] Review-blokkade 3: cleanup direct ná `up` + `test_startup_faal_ruimt_eigen_context_op`
- [x] Review-blokkade 4: strikte volumenaam-validatie + 2 afwijzende tests
- [x] Medium: unieke PID/random-slug, skip-guard (0 overgeslagen), correcte bestandsaantallen

### 2. Scripts en Playwright-configuratie

- [x] `bash -n scripts/readiness-loop.sh scripts/run-mobile-e2e.sh scripts/db-rollback.sh` → exit 0
- [x] Geen `webServer` in `frontend/playwright.config.js`
- [x] `cd frontend && npx playwright test --list` → 1 test in 1 file (chromium)
- [x] `npm run test:e2e` uitgevoerd → `1 passed (2.6s)`, rc 0

### 3. Resterende verificatie

- [x] **Docker**: sectie 8 integratietests, 7.2/7.3 Compose/Next.js-tests en de readiness loop uitgevoerd
- [x] **e2e**: sectie 9.4 mobiele Playwright-verificatie (`npm run test:e2e`) uitgevoerd
- [x] **restore**: sectie 9.1.7-9.1.10 feitelijk restore, integriteit, `/health` en opt-in `down -v` uitgevoerd
- [x] **volledige suite**: 159/159 passed, 0 overgeslagen, geen cleanup-meldingen; restcontrole na afloop (containers/volumes/netwerken/poorten/workmaps) schoon
- [x] **sectie 10**: volledig `[x]`

## Restrisico

1. **Runtime-tests hebben Docker, node/npm en lokale Chromium nodig.** Zonder daemon, zonder npm of zonder `~/.cache/ms-playwright` draaien ze niet volledig; de rollback-tests slaan bovendien over wanneer 127.0.0.1:3000/8000 al bezet zijn door een vóór deze sessie draaiende stack (die wordt bewust nooit gestopt). Dat kan nooit onopgemerkt blijven: elke skip wordt in `runtime_env.skipped_tests` geregistreerd en `test_zz_lokale_suite_volledig.py` (alfabetisch laatst) laat de suite dan **falen** met de precieze reden in plaats van als voltooid door te gaan.
2. **Geen commit/push.** Deze ronde is uitgevoerd door de backup-codebouwer: bestanden zijn gewijzigd en geverifieerd, maar niet gecommit; zie de tabel bij Git Status (14 regels: 10 gewijzigd + 4 nieuw).
3. **Statische tests blijven statisch.** `test_exact_verification.py` (42 tests) en `test_discrete_verified_tasks.py` (36 tests) controleren tekst, regex en structuur; het runtime-gedrag wordt door de runtime-bestanden hierboven afgedwongen. De volumenaam-validatie en de `verify_full`-markerproef zijn dubbelen: ze draaien én statisch (functiebron) én feitelijk (uitvoering van het script).
4. **Meetresultaten zijn machineafhankelijk** (tijden, pogingenaantallen, `CreatedAt`); de assertions richten zich op rc/tekst/status, niet op de exacte waarden.

## Conclusie

De implementatie van OpenSpec change `bootstrap-local-news-dashboard` is **voltooid**: 154 van de 154 checkboxen (144 van de 144 leaf-taken) zijn afgevinkt en de vier review-blokkades zijn in deze herstelronde opgelost én met eigen tests afgedwongen. De verplichte lokale suite draait **159/159 tests groen, 0 overgeslagen**, in 199,99 s, zonder cleanup-meldingen en met alle eigen containers, netwerken, poorten, werkmaps en images achteraf opgeruimd (alleen de echte volume `nieuws_piet_sqlite_data` en de eigen project-images blijven staan, zoals bedoeld).

Volgende stappen:

1. De 14 gewijzigde/nieuwe bestanden beoordelen en committen (door de primaire gebruiker/orchestrator; deze ronde committe niet).
2. `openspec status`/`openspec archive` uitvoeren wanneer de change formeel afgerond moet worden.
3. Optioneel: de env-overrides `NIEUWS_PIET_DB_VOLUME`/`NIEUWS_PIET_DB_BACKUP_DIR` expliciet in `docs/data-safe-rollback-restore.md` documenteren.

De gemaakte documentatie biedt een complete referentie voor het opzetten, ontwikkelen en testen van Nieuws Piet. Alle documentatie volgt de OpenSpec conventies en biedt praktische gidsen voor ontwikkelaars.

---

*Implementatie samenvatting gegenereerd door OpenSpec bootstrap-local-news-dashboard change*
