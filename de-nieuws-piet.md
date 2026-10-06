Persoonlijke nieuwswebsite — plan en OpenSpec-aanpak

Doel
Een lokale, mobielvriendelijke persoonlijke nieuwswebsite die dagelijks betrouwbaar nieuws verzamelt, dedupliceert, rangschikt en in het Nederlands samenvat. De website is primair voor Peter en is toegankelijk via browser en mobiel, zonder publieke hosting.

Onderwerpen
1. AI
2. Kubernetes en cloud native
3. Linux en open source
4. T Cloud Public en Open Telekom Cloud
5. Digitale soevereiniteit en Europese cloud
6. Belangrijkste nieuws uit Nederland
7. Belangrijkste nieuws uit Europa
8. Nederlandse politiek
9. Oekraïne
10. Iran en Midden-Oosten
11. Geopolitiek
12. Crypto in brede zin, met extra prioriteit voor Ethereum
13. CNCF-projecten, cloud-native-ecosysteem en communitynieuws
14. Agentic AI Foundation (AAIF), aangesloten projecten en ecosysteemnieuws

Productprincipes
- Lokaal-first: standaard alleen bereikbaar op LAN; optioneel veilig via Tailscale.
- Brongebonden: elk item bevat bron, datum en directe link.
- Geen willekeurige content-scraping in de eerste versie; voorkeur voor RSS en officiële publicaties.
- Mobiel eerst, maar volwaardig op desktop.
- Geen automatische claims zonder bron; samenvattingen noemen onzekerheid waar nodig.
- Persoonlijke ranking verbetert alleen door expliciete feedback zoals Meer, Minder, Belangrijk en Niet relevant.

Voorgestelde architectuur
- Frontend: Next.js PWA met responsive kaarten, leesstatus en instellingen.
- Backend: Python/FastAPI voor feed-ophaling, deduplicatie, ranking en API.
- Database: SQLite voor artikelen, bronnen, onderwerpen, feedback en jobstatus.
- Runtime: Docker Compose op een lokale server.
- Scheduler: dagelijkse import- en samenvattingsjob; later optionele Telegram-melding bij topnieuws.
- LLM-laag: samenvatten en prioriteren op basis van bronmetadata en onderwerpregels, met altijd een bronlink naast de samenvatting.

Bronstrategie
Start met officiële en hoogwaardige bronnen per domein:
- Kubernetes Blog, CNCF, Linux Foundation en relevante releaseblogs.
- Deutsche Telekom, T Cloud Public, Open Telekom Cloud en EU/ENISA/BSI-publicaties.
- Ethereum Foundation en geselecteerde betrouwbare Ethereum/cryptobronnen.
- Reuters, AP, BBC, Al Jazeera en andere geselecteerde kwaliteitsbronnen voor geopolitiek.
Een broncatalogus blijft bewerkbaar in de website. Elke bron krijgt een betrouwbaarheidsscore, onderwerpen en een actieve/inactieve status.

Dagelijkse nieuwsverwerking
1. Haal nieuwe feed-items op.
2. Normaliseer URL, titel, datum, bron en onderwerp.
3. Dedupliqueer berichten over hetzelfde feit.
4. Classificeer en rangschik op onderwerp, actualiteit, bronkwaliteit en expliciete gebruikersfeedback.
5. Maak korte Nederlandse samenvatting met relevantie voor Peter.
6. Toon per rubriek de belangrijkste items; bewaar volledige bronlink.

MVP-schermen
- Vandaag: topnieuws, maximaal vijf prioritaire dossiers.
- Rubrieken: per onderwerp recente en belangrijkste items.
- Artikelkaart: titel, bron, datum, samenvatting, relevantie, labels en link.
- Instellingen: bronnen, onderwerpen, gewichten en notificatievoorkeuren.
- Feedback: Meer zoals dit, Minder zoals dit, Belangrijk, Niet relevant, Gelezen.

Niet-functionele eisen
- Goede werking op mobiel vanaf 360 px breedte.
- Eerste scherm binnen circa twee seconden op het lokale netwerk.
- Dagelijkse job is idempotent: opnieuw draaien levert geen duplicaten op.
- Back-up van SQLite en configuratie.
- Geen openbare toegang zonder expliciete keuze.
- Bron-URL en publicatiedatum worden per kaart bewaard.

OpenSpec-aanpak
De actuele changevolgorde, scopes en copy-pasteprompts staan in docs/openspec-roadmap.md. De praktische lifecycle van explore tot archive staat in docs/applying-openspec-changes.md.

De bootstrap wordt eerst menselijk geaccepteerd, gevalideerd en gearchiveerd. Daarna wordt alleen de eerstvolgende change just-in-time geopend:
1. add-source-catalog
2. add-idempotent-rss-ingestion
3. add-explainable-topic-ranking
4. add-daily-briefing-ui
5. add-explicit-feedback-preferences
6. add-event-deduplication
7. add-grounded-dutch-summaries
8. add-daily-news-job
9. add-telegram-notification-policy

Vaste flow: /opsx-explore -> /opsx-propose -> menselijke review -> openspec validate -> /opsx-apply -> test en acceptatie -> /opsx-archive.
Maak niet alle change-directories vooraf aan en voer nooit meerdere roadmapchanges in één apply uit.

Eerste beslissingen voor de bouw
- Begin met RSS en officiële bronnen; voeg betaalde bronnen of API's pas later toe.
- Begin met één dagelijkse update; voeg meerdere updates per dag pas toe als de bronkwaliteit goed is.
- Gebruik feedback als expliciete voorkeur, niet als ondoorzichtige persoonlijke profilering.
- Houd samenvatting, bron en ranking afzonderlijk traceerbaar.

MVP-acceptatie
De eerste versie is gereed wanneer de website lokaal draait, dagelijks nieuws uit de gekozen rubrieken ophaalt, geen duplicaten toont, op mobiel goed werkt, bronlinks weergeeft en expliciete feedback gebruikt om de volgende ranking te verbeteren.

Volgende concrete stap
Maak de repository en voer OpenSpec-change bootstrap-local-news-dashboard uit. Daarna stellen we de eerste broncatalogus samen en bouwen we de importpipeline voordat we een LLM-samenvattingslaag toevoegen.


Uitbreiding onderwerpen en broncatalogus

AI-trends en AI-tools
Voeg een aparte rubriek toe voor AI-trends en AI-tools. Volg onder meer modelreleases, agent-frameworks, open-weight modellen, inference/hardware, AI-security, AI-governance, developer tools en praktische enterprise-adoptie. Rangschik technische ontwikkelingen en concrete productlanceringen hoger dan algemene marketingaankondigingen.

Azure
Voeg Azure en Microsoft-cloud toe als zelfstandig onderwerp. Focus op Azure Kubernetes Service, Azure Arc, Azure AI Foundry, sovereign-cloud-ontwikkelingen, identity/security, landing zones, netwerk en Europese datalocatie/compliance. Neem officiële Azure-updates, Microsoft Security en relevante release notes op als voorkeursbronnen.

AWS
Voeg AWS toe als zelfstandig onderwerp. Focus op EKS, Bedrock, IAM/security, networking, European Sovereign Cloud, data-residency, Kubernetes/platformontwikkelingen en relevante release notes. Neem AWS What's New, AWS Security Blog, EKS-release notes en AWS Architecture Blog op als voorkeursbronnen.

Aanpassing aan classificatie en ranking
- Nieuwe hoofdonderwerpen: AI-trends & tools, Azure en AWS.
- Geef Azure/AWS-artikelen over Kubernetes, AI-platformen, security en digitale soevereiniteit een extra kruislabel met de bestaande onderwerpen.
- Gebruik onderscheid tussen productreleases, technische referentiearchitectuur, security/compliance, prijs/contractnieuws en marketing. Marketing krijgt standaard een lagere score.
- Voeg per bron een veld toe voor cloud: azure, aws, t-cloud, otc, multi-cloud of sovereign-cloud.

Nederland, Europa, politiek en ecosystemen
- Voeg dagelijkse rubrieken toe voor het belangrijkste algemene nieuws uit Nederland en Europa. Selecteer op maatschappelijke impact en relevantie; vermijd een brede stroom van klein of sensationeel nieuws.
- Behandel Nederlandse politiek als zelfstandig onderwerp, met nadruk op kabinet, parlement, verkiezingen, beleid, uitvoering en gevolgen voor burgers en bedrijfsleven.
- Verbreed crypto van een Ethereum-rubriek naar algemeen cryptonieuws, terwijl Ethereum een expliciet hogere prioriteit en een eigen kruislabel behoudt.
- Volg CNCF-nieuws over projecten, releases, governance, security, end-userontwikkelingen en het cloud-native-ecosysteem.
- Volg AAIF-nieuws over aangesloten agentprojecten, standaarden, governance, interoperabiliteit en concrete technische releases; algemene AI-marketing krijgt een lagere score.
- Label nieuws dat tegelijk Nederland, Europa, digitale soevereiniteit, cloud, AI of geopolitiek raakt met alle relevante kruislabels.

OpenSpec-indeling
De bronvelden en startbronnen vallen onder add-source-catalog. De onderwerpen, kruislabels en marketingweging vallen onder add-explainable-topic-ranking; dit omvat ook Nederland, Europa, Nederlandse politiek, brede crypto met Ethereum-prioriteit, CNCF en AAIF. Hiervoor komt geen brede catch-all change.

