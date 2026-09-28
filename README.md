# Nieuws Piet - Lokale Persoonlijke Nieuwswebsite

## Overzicht

Nieuws Piet is een lokale, mobiele persoonlijke nieuwswebsite die dagelijks betrouwbare nieuws verzamelt, dedupliceert, rangschikt en in het Nederlands samenvat. De website is primair voor één gebruiker en is toegankelijk via browser en mobiel, zonder publieke hosting.

## Onderwerpen

1. AI
2. Kubernetes en cloud native
3. Linux en open source
4. T Cloud Public en Open Telekom Cloud
5. Digitale soevereiniteit en Europese cloud
6. Oekraïne
7. Iran en Midden-Oosten
8. Geopolitiek
9. Crypto, met extra prioriteit voor Ethereum

## Productprincipes

- **Lokaal-first**: standaard alleen bereikbaar op LAN; optioneel veilig via Tailscale.
- **Brongebonden**: elk item bevat bron, datum en directe link.
- **Geen willekeurige content-scraping in de eerste versie; voorkeur voor RSS en officiële publicaties.
- **Mobiel eerst, maar volwaardig op desktop.
- **Geen automatische claims zonder bron; samenvattingen noemen onzekerheid waar nodig.
- **Persoonlijke ranking verbetert alleen door expliciete feedback zoals Meer, Minder, Belangrijk en Niet relevant.

## Voorgestelde architectuur

- **Frontend**: Next.js PWA met responsive kaarten, leesstatus en instellingen.
- **Backend**: Python/FastAPI voor feed-ophaling, deduplicatie, ranking en API.
- **Database**: SQLite voor artikelen, bronnen, onderwerpen, feedback en jobstatus.
- **Runtime**: Docker Compose op een lokale server.
- **Scheduler**: dagelijkse import- en samenvattingsjob; later optionele Telegram-melding bij topnieuws.
- **LLM-laag**: samenvatten en prioriteren op basis van bronmetadata en onderwerpregels, met altijd een bronlink naast de samenvatting.

## Bronstrategie

Start met officiële en hoogwaardige bronnen per domein:

- Kubernetes Blog, CNCF, Linux Foundation en relevante releaseblogs.
- Deutsche Telekom, T Cloud Public, Open Telekom Cloud en EU/ENISA/BSI-publicaties.
- Ethereum Foundation en geselecteerde betrouwbare Ethereum/cryptobronnen.
- Reuters, AP, BBC, Al Jazeera en andere geselecteerde kwaliteitsbronnen voor geopolitiek.

Een broncatalogus blijft bewerkbaar in de website. Elke bron krijgt een betrouwbaarheidsscore, onderwerpen en een actieve/inactieve status.

## Dagelijkse nieuwsverwerking

1. Haal nieuwe feed-items op.
2. Normaliseer URL, titel, datum, bron en onderwerp.
3. Dedupliqueer berichten over hetzelfde feit.
4. Classificeer en rangschik op onderwerp, actualiteit, bronkwaliteit en expliciete gebruikersfeedback.
5. Maak korte Nederlandse samenvatting met relevantie voor Peter.
6. Toon per rubriek de belangrijkste items; bewaar volledige bronlink.

## MVP-schermen

- **Vandaag**: topnieuws, maximaal vijf prioritaire dossiers.
- **Rubrieken**: per onderwerp recente en belangrijkste items.
- **Artikelkaart**: titel, bron, datum, samenvatting, relevantie, labels en link.
- **Instellingen**: bronnen, onderwerpen, gewichten en notificatievoorkeuren.
- **Feedback**: Meer zoals dit, Minder zoals dit, Belangrijk, Niet relevant, Gelezen.

## Niet-functionele eisen

- Goede werking op mobiel vanaf 360 px breedte.
- Eerste scherm binnen circa twee seconden op het lokale netwerk.
- Dagelijkse job is idempotent: opnieuw draaien levert geen duplicaten op.
- Back-up van SQLite en configuratie.
- Geen openbare toegang zonder expliciete keuze.
- Bron-URL en publicatiedatum worden per kaart bewaard.

## OpenSpec-aanpak

OpenSpec wordt de bron van waarheid voor gedrag en wijzigingen. Iedere zelfstandige feature krijgt een eigen change-map onder `openspec/changes/<change-naam>/` met `proposal.md`, `design.md`, `tasks.md` en delta-specs. De vaste flow is: explore -> propose -> review -> apply -> test -> archive.

## Startstructuur

```
openspec/
  specs/
    news-ingestion/spec.md
    ranking-and-feedback/spec.md
    dashboard/spec.md
    notifications/spec.md
    privacy-and-access/spec.md
  changes/
  config.yaml
```

## Eerste OpenSpec-changes

1. **bootstrap-local-news-dashboard**
   - Doel: repository, Docker Compose, FastAPI, Next.js, SQLite, healthcheck en lokale toegang.
   - Acceptatie: één commando start frontend, API en database; mobiele startpagina toont een lege toestand.

2. **add-source-catalog-and-ingestion**
   - Doel: broncatalogus, RSS-ophaling, URL-normalisatie, opslag en idempotente scheduler.
   - Acceptatie: minimaal tien geconfigureerde bronnen, dubbele items worden niet opnieuw opgeslagen.

3. **add-topic-classification-and-ranking**
   - Doel: onderwerpen, gewichten en basisrangschikking voor AI, Kubernetes, Linux, T Cloud/soevereiniteit, geopolitiek en Ethereum.
   - Acceptatie: elk geïmporteerd item heeft één of meer onderwerpen en een uitlegbare score.

4. **add-daily-briefing-ui**
   - Doel: mobiele Vandaag-pagina, rubrieken, bronlinks en leesstatus.
   - Acceptatie: pagina werkt op mobiel en desktop en toont topitems per rubriek.

5. **add-feedback-learning**
   - Doel: feedbackknoppen en transparante voorkeursscores.
   - Acceptatie: feedback verandert toekomstige ranking aantoonbaar; gebruiker kan voorkeuren terugdraaien.

6. **add-summary-and-deduplication**
   - Doel: brongebonden Nederlandse samenvattingen en clustering rond dezelfde gebeurtenis.
   - Acceptatie: iedere samenvatting toont bronlinks; verwante artikelen worden als dossier samengevoegd.

7. **add-notification-policy**
   - Doel: optionele Telegram-alerts voor alleen hoog-prioritair nieuws.
   - Acceptatie: geen notificatie zonder ingestelde drempel; notificatie bevat bronlink en reden van prioriteit.

## Werkwijze per change

- `/opsx:explore`: verken alternatieven en risico's zonder code te wijzigen.
- `/opsx:propose <change>`: schrijf doel, scope, niet-doelen, acceptatiecriteria en rollback.
- Review: akkoord op voorstel voordat de implementatie start.
- `/opsx:apply`: implementeer kleine, toetsbare taken uit tasks.md.
- Test: unit-, integratie- en mobiele browserchecks; controleer idempotentie en bronattributie.
- `/opsx:archive`: neem goedgekeurde delta-specs op in openspec/specs zodat de actuele werking altijd vastligt.

## Eerste beslissingen voor de bouw

- Begin met RSS en officiële bronnen; voeg betaalde bronnen of API's pas later toe.
- Begin met één dagelijkse update; voeg meerdere updates per dag pas toe als de bronkwaliteit goed is.
- Gebruik feedback als expliciete voorkeur, niet als ondoorzichtige persoonlijke profilering.
- Houd samenvatting, bron en ranking afzonderlijk traceerbaar.

## MVP-acceptatie

De eerste versie is gereed wanneer de website lokaal draait, dagelijks nieuws uit de gekozen rubrieken ophaalt, geen duplicaten toont, op mobiel goed werkt, bronlinks weergeeft en expliciete feedback gebruikt om de volgende ranking te verbeteren.

## Volgende concrete stap

Maak de repository en voer OpenSpec-change `bootstrap-local-news-dashboard` uit. Daarna stellen we de eerste broncatalogus samen en bouwen we de importpipeline voordat we een LLM-samenvattingslaag toevoegen.

## Uitbreiding onderwerpen en broncatalogus

### AI-trends en AI-tools

Voeg een aparte rubriek toe voor AI-trends en AI-tools. Volg onder meer modelreleases, agent-frameworks, open-weight modellen, inference/hardware, AI-security, AI-governance, developer tools en praktische enterprise-adoptie. Rangschik technische ontwikkelingen en concrete productlanceringen hoger dan algemene marketingaankondigingen.

### Azure

Voeg Azure en Microsoft-cloud toe als zelfstandig onderwerp. Focus op Azure Kubernetes Service, Azure Arc, Azure AI Foundry, sovereign-cloud-ontwikkelingen, identity/security, landing zones, netwerk en Europese datalocatie/compliance. Neem officiële Azure-updates, Microsoft Security en relevante release notes op als voorkeursbronnen.

### AWS

Voeg AWS toe als zelfstandig onderwerp. Focus op EKS, Bedrock, IAM/security, networking, European Sovereign Cloud, data-residency, Kubernetes/platformontwikkelingen en relevante release notes. Neem AWS What's New, AWS Security Blog, EKS-release notes en AWS Architecture Blog op als voorkeursbronnen.

## Aanpassing aan classificatie en ranking

- Nieuwe hoofdonderwerpen: AI-trends & tools, Azure en AWS.
- Geef Azure/AWS-artikelen over Kubernetes, AI-platformen, security en sovereign-cloud een extra kruislabel met de bestaande onderwerpen.
- Gebruik onderscheid tussen productreleases, technische referentiearchitectuur, security/compliance, prijs/contractnieuws en marketing. Marketing krijgt standaard een lagere score.
- Voeg per bron een veld toe voor cloud: azure, aws, t-cloud, otc, multi-cloud of sovereign-cloud.

## OpenSpec-uitbreiding

8. **add-ai-tools-and-hyperscaler-coverage**
   - Doel: broncatalogus, classificatie en dashboardonderwerpen uitbreiden met AI-trends/tools, Azure en AWS.
   - Acceptatie: items uit de nieuwe bronnen krijgen één of meer correcte onderwerpen; Kubernetes-, security- en sovereign-cloud-items tonen kruislabels; marketingitems worden lager gerangschikt dan technische of security-relevante updates.

## Installatie

### Vereisten

- Docker en Docker Compose (v2 plugin, commando `docker compose`)
- Node.js >= 20
- Python >= 3.10

### Setup

1. Clone de repository
2. Voer `docker compose up -d --build` uit om de `frontend` en `backend` services te starten
3. Voer de frontend/backend readiness loop uit (max 30 attempts, `sleep 1`, `curl --max-time 5`)
4. Open de applicatie op `http://localhost:3000`

### Ontwikkeling

1. Maak wijzigingen aan frontend code in `frontend/` directory
2. Maak wijzigingen aan backend code in `backend/` directory
3. Voer `docker compose up -d --build` uit om wijzigingen toe te passen
4. Voer de readiness loop opnieuw uit en controleer daarna `npm run test:e2e` voor mobiele acceptatie
5. Gebruik health endpoint op `http://localhost:8000/health` (nooit als frontend controle) om systeemstatus te verifiëren

## Gebruik

De applicatie is toegankelijk op:
- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/health`

## Tests

### Backend Tests

Voer backend health tests uit:
```bash
cd backend
python -m pytest tests/ -v
```

### Frontend Tests

Voer frontend e2e tests uit:
```bash
cd frontend
npm run test:e2e
```

### Integratietests

Voer complete applicatie startup test uit:
```bash
docker compose up -d --build
# Wacht op readiness
./scripts/readiness-loop.sh
```

## Documentatie

- **Docker Compose acceptatie**: Zie sectie 6.2 in de documentatie.
- **Health endpoint API**: Zie sectie 6.5 in de documentatie.
- **Mobiele responsiviteit**: Zie sectie 6.9 in de documentatie.
- **Data-safe rollback/restore**: Zie sectie 6.7 in de documentatie.
- **Failure testing**: Zie sectie 6.8 in de documentatie.

## Bijdragen

Bijdragen zijn welkom! Lees het CONTRIBUTING.md bestand voor meer informatie over hoe u kunt bijdragen aan dit project.

## Licentie

Dit project is gelicentieerd onder de MIT-licentie. Zie de LICENSE-bestand voor meer details.

## Contact

Voor vragen of problemen, neem contact op met de projectbeheerder.

---

*Documentatie gegenereerd door OpenSpec bootstrap-local-news-dashboard change*