# OpenSpec-roadmap — De Nieuws Piet

Deze roadmap bouwt het lokale nieuwsdashboard in kleine, afzonderlijk accepteerbare changes. De huidige bootstrap blijft de technische basis. Nieuwe change-directories ontstaan pas just-in-time tijdens `propose`; deze roadmap is de planning en niet een verzameling vooraf goedgekeurde specs.

De praktische uitvoering staat in [`applying-openspec-changes.md`](applying-openspec-changes.md).

## Uitgangspunten

- één change levert één zelfstandig resultaat;
- eerst deterministische functionaliteit, daarna pas LLM-samenvattingen;
- RSS en officiële bronnen vóór scraping of betaalde API's;
- bron-URL, publicatiedatum en herkomst blijven altijd zichtbaar;
- externe accounts, kosten, publieke toegang en notificaties vereisen apart akkoord;
- observeerbaar gedrag staat in specs; exacte code en scripts horen in implementatie en tests;
- na iedere change: valideren, toepassen, testen, menselijk accepteren en archiveren.

## Commandonotatie

De aanwezige OpenCode-commando's gebruiken:

```text
/opsx-explore
/opsx-propose
/opsx-apply
/opsx-update
/opsx-sync
/opsx-archive
```

Gebruik lokale autocomplete als bron van waarheid. `/opsx-propose` maakt de planning-artifacts; er is geen standaardcommando `/opsx-compose`.

---

## Change 1 — `bootstrap-local-news-dashboard`

**Status:** geïmplementeerd en uitgebreid getest; nog niet gearchiveerd naar `openspec/specs/`.

**Resultaat:** lokale Next.js-frontend, FastAPI-backend, SQLite, Docker Compose, healthchecks en mobiele lege toestand.

**Eerstvolgende gate:** menselijke acceptatie, OpenSpec-validatie en archive. Herschrijf deze historische change niet om de toekomstige architectuur passend te maken.

```text
/opsx-archive bootstrap-local-news-dashboard
```

Voer vóór archive de repositorychecks uit die in de apply-handleiding staan.

---

## Change 2 — `add-source-catalog`

**Doel:** een lokale catalogus voor nieuwsbronnen toevoegen zonder al berichten op te halen.

**In scope:**

- SQLite-model en migratie/init voor bronnen;
- naam, feed-URL, website-URL, type, taal, betrouwbaarheid en actief/inactief;
- onderwerpen en cloudlabel (`azure`, `aws`, `t-cloud`, `otc`, `multi-cloud`, `sovereign-cloud`);
- lokale API voor lezen, toevoegen en wijzigen;
- een kleine initiële set officiële bronnen;
- validatie van dubbele en ongeldige URL's.

**Niet in scope:** RSS ophalen, scraping, planning, ranking, samenvatting of notificaties.

**Menselijke gate:** velden, initiële bronnen en betekenis van betrouwbaarheid goedkeuren.

### Explore

```text
/opsx-explore Onderzoek een minimale lokale broncatalogus voor De Nieuws Piet. Bekijk het bestaande FastAPI/SQLite-bootstrapmodel en ontwerp bronvelden, unieke URL-regels, actief/inactief, onderwerpen, betrouwbaarheid, taal en cloudlabels. Gebruik alleen lokale opslag. Geen RSS-ophaling, scraping, ranking, LLM, scheduler of notificaties. Schrijf nog geen productiecode.
```

### Propose

```text
/opsx-propose add-source-catalog - Voeg een lokale, bewerkbare broncatalogus toe aan FastAPI en SQLite. Ondersteun naam, feed-URL, website-URL, type, taal, betrouwbaarheid, actief/inactief, onderwerpen en cloudlabel. Weiger ongeldige of dubbele feed-URL's en lever een kleine beoordeelde set officiële startbronnen. Geen feed-ophaling, scraping, ranking, LLM, scheduler of notificaties.
```

### Apply

```text
/opsx-apply add-source-catalog
```

**Acceptatie:** catalogusitems kunnen lokaal worden gelezen en gewijzigd; duplicaten en ongeldige URL's worden afgewezen; herstart behoudt de data; er vindt geen netwerkfetch plaats.

---

## Change 3 — `add-idempotent-rss-ingestion`

**Doel:** actieve RSS/Atom-bronnen handmatig en idempotent kunnen ophalen en opslaan.

**In scope:**

- alleen actieve catalogusbronnen ophalen;
- timeouts, begrensde retries en foutstatus per bron;
- GUID, canonical URL, titel, publicatiedatum, bronnaam en originele link normaliseren;
- exacte idempotentie op stabiele bronidentiteit;
- handmatig CLI-commando en API-status;
- fixtures en lokale contracttests zonder live internet.

**Niet in scope:** willekeurige scraping, scheduler, onderwerpclassificatie, ranking, clustering, samenvatting of UI-kaarten.

**Menselijke gate:** netwerkbeleid, timeouts, bewaartermijn en eerste live dry-run goedkeuren.

### Explore

```text
/opsx-explore Onderzoek hoe De Nieuws Piet actieve RSS en Atom feeds veilig, begrensd en idempotent kan importeren. Ontwerp stabiele itemidentiteit, URL-normalisatie, datumafhandeling, timeouts, beperkte retries, bronfouten en synthetische fixtures. Begin met een handmatig commando. Geen scraping, scheduler, ranking, LLM, clustering of notificaties.
```

### Propose

```text
/opsx-propose add-idempotent-rss-ingestion - Voeg een handmatige RSS/Atom-import toe voor actieve catalogusbronnen. Normaliseer GUID of canonical URL, titel, publicatiedatum, bron en originele link; sla hetzelfde bronitem maximaal één keer op. Begrens timeouts en retries, registreer fouten per bron en test met lokale fixtures. Geen scraping, scheduler, classificatie, ranking, LLM of notificaties.
```

### Apply

```text
/opsx-apply add-idempotent-rss-ingestion
```

**Acceptatie:** twee identieke imports maken geen duplicaten; een defecte bron blokkeert andere bronnen niet; ieder opgeslagen item heeft bronlink en publicatiedatum; fixturetests gebruiken geen extern netwerk.

---

## Change 4 — `add-explainable-topic-ranking`

**Doel:** artikelen deterministisch classificeren en uitlegbaar rangschikken zonder LLM.

**In scope:**

- onderwerpen voor AI/tools, Kubernetes, Linux, T Cloud/OTC, digitale soevereiniteit, Azure, AWS, Oekraïne, Iran/Midden-Oosten, geopolitiek en Ethereum;
- meerdere labels per artikel;
- vaste gewichten voor actualiteit, bronkwaliteit, onderwerp en contenttype;
- marketing standaard lager waarderen dan technische, security- of compliance-inhoud;
- score-uitleg opslaan en via API teruggeven;
- herberekening met dezelfde input geeft hetzelfde resultaat.

**Niet in scope:** persoonlijke feedback, LLM-classificatie, clustering, samenvattingen of notificaties.

**Menselijke gate:** onderwerpen, basisgewichten en marketingregel goedkeuren.

### Explore

```text
/opsx-explore Onderzoek een deterministische en uitlegbare onderwerpclassificatie en ranking voor De Nieuws Piet. Gebruik bronmetadata, titel en vaste regels voor AI/tools, Kubernetes, Linux, T Cloud/OTC, digitale soevereiniteit, Azure, AWS, geopolitiek en Ethereum. Ontwerp meerdere labels, scorecomponenten en marketing-deprioritering. Geen LLM, persoonlijke feedback, clustering of notificaties.
```

### Propose

```text
/opsx-propose add-explainable-topic-ranking - Voeg deterministische onderwerpclassificatie en basisranking toe. Ondersteun meerdere labels, vaste gewichten voor actualiteit, bronkwaliteit, onderwerp en contenttype, kruislabels voor cloud/Kubernetes/security/soevereiniteit en een zichtbare score-uitleg. Marketing scoort standaard lager. Dezelfde input levert dezelfde score. Geen LLM, feedback, clustering, samenvatting of notificaties.
```

### Apply

```text
/opsx-apply add-explainable-topic-ranking
```

**Acceptatie:** ieder geschikt item heeft labels en een reproduceerbare score-uitleg; dezelfde dataset levert dezelfde volgorde; grensgevallen zijn met fixtures getest.

---

## Change 5 — `add-daily-briefing-ui`

**Doel:** geïmporteerde en gerangschikte artikelen bruikbaar tonen op mobiel en desktop.

**In scope:**

- Vandaag-pagina met maximaal vijf prioritaire dossiers/items;
- rubrieken per onderwerp;
- kaart met titel, bron, publicatiedatum, score-uitleg en directe bronlink;
- lege, laad- en fouttoestand;
- gelezen/ongelezen status;
- mobiele acceptatie vanaf 360 px en desktopweergave.

**Niet in scope:** feedbackleren, LLM-samenvattingen, gebeurtenisclustering, instellingen voor alle gewichten of notificaties.

**Menselijke gate:** kaartinhoud, aantal topitems en mobiele UX goedkeuren.

### Explore

```text
/opsx-explore Onderzoek de minimale Vandaag- en rubrieken-UI voor de bestaande geïmporteerde en gerangschikte artikelen. Ontwerp brongebonden kaarten, directe links, publicatiedatum, score-uitleg, gelezenstatus en lege/laad/fouttoestanden voor 360px en desktop. Geen feedbackleren, LLM-samenvattingen, clustering of notificaties.
```

### Propose

```text
/opsx-propose add-daily-briefing-ui - Voeg een mobiele Vandaag-pagina en rubrieken toe voor geïmporteerde artikelen. Toon maximaal vijf prioritaire items, titel, bron, publicatiedatum, directe bronlink, labels en score-uitleg. Ondersteun gelezen/ongelezen en duidelijke lege, laad- en fouttoestanden. Test vanaf 360px en desktop. Geen feedbackleren, LLM, clustering of notificaties.
```

### Apply

```text
/opsx-apply add-daily-briefing-ui
```

**Acceptatie:** actuele items staan in stabiele volgorde; bronlinks werken; gelezenstatus blijft bewaard; mobiele en desktopacceptatie zijn groen.

---

## Change 6 — `add-explicit-feedback-preferences`

**Doel:** transparante persoonlijke voorkeuren laten beïnvloeden wat later hoger of lager staat.

**In scope:**

- `Meer`, `Minder`, `Belangrijk` en `Niet relevant`;
- feedback lokaal opslaan met onderwerp en broncontext;
- uitlegbare invloed op toekomstige scores;
- iedere keuze terugdraaien;
- begrenzing zodat feedback nieuws niet onvindbaar maakt.

**Niet in scope:** impliciete tracking, gedragsprofilering, embeddingprofielen, LLM-personalisatie of notificaties.

**Menselijke gate:** sterkte, grenzen en betekenis van iedere feedbackactie goedkeuren.

### Explore

```text
/opsx-explore Onderzoek transparante, uitsluitend expliciete feedback voor De Nieuws Piet. Modelleer Meer, Minder, Belangrijk en Niet relevant, lokale opslag, omkeerbaarheid, begrensde score-invloed en zichtbare uitleg. Voorkom impliciete tracking en filterbubbels. Geen LLM-profiel, embeddings of notificaties.
```

### Propose

```text
/opsx-propose add-explicit-feedback-preferences - Voeg lokale, omkeerbare feedbackacties Meer, Minder, Belangrijk en Niet relevant toe. Laat feedback toekomstige ranking begrensd en uitlegbaar beïnvloeden op basis van bron en onderwerp. Sla geen impliciet gedrag op en voorkom dat één actie een onderwerp permanent onzichtbaar maakt. Geen LLM-personalisatie, embeddings of notificaties.
```

### Apply

```text
/opsx-apply add-explicit-feedback-preferences
```

**Acceptatie:** feedback verandert een volgende ranking aantoonbaar; undo herstelt het oude resultaat; score-uitleg toont de feedbackcomponent; alleen expliciete acties worden opgeslagen.

---

## Change 7 — `add-event-deduplication`

**Doel:** meerdere artikelen over dezelfde gebeurtenis als één lokaal dossier tonen zonder bronverlies.

**In scope:**

- deterministische kandidaatselectie op genormaliseerde URL, titel, entiteiten en tijdvenster;
- conservatieve drempel: twijfel blijft afzonderlijk;
- één dossier met alle originele bronlinks;
- handmatig losmaken of samenvoegen;
- herhaalde verwerking is idempotent.

**Niet in scope:** LLM-clustering, samenvattingen, automatische waarheidsclaims of notificaties.

**Menselijke gate:** clusteringdrempel en correctiemechanisme goedkeuren.

### Explore

```text
/opsx-explore Onderzoek conservatieve, deterministische gebeurtenisdeduplicatie voor De Nieuws Piet. Vergelijk canonical URL, genormaliseerde titel, herkenbare entiteiten en een tijdvenster. Ontwerp dossiers die alle originele bronnen behouden, bij twijfel niet samenvoegen en handmatig corrigeerbaar zijn. Geen LLM, samenvatting of notificaties.
```

### Propose

```text
/opsx-propose add-event-deduplication - Voeg conservatieve deterministische clustering toe voor artikelen over dezelfde gebeurtenis. Gebruik canonical URL, titelkenmerken, entiteiten en tijdvenster; twijfelgevallen blijven apart. Bewaar alle bronlinks, maak handmatig losmaken/samenvoegen mogelijk en houd herhaalde verwerking idempotent. Geen LLM, samenvatting of notificaties.
```

### Apply

```text
/opsx-apply add-event-deduplication
```

**Acceptatie:** bekende duplicaatfixtures vormen één dossier met alle bronnen; niet-gerelateerde grensgevallen blijven apart; correcties blijven na herberekening behouden.

---

## Change 8 — `add-grounded-dutch-summaries`

**Doel:** korte Nederlandse samenvattingen maken die controleerbaar aan de opgeslagen bronnen zijn gekoppeld.

**In scope:**

- eerst keuze tussen lokaal model en externe provider;
- minimaal benodigde artikeltekst en metadata;
- samenvatting met expliciete bronverwijzingen en onzekerheid;
- prompt- en modelversie vastleggen;
- budget, timeouts, retries en fallback naar titel/metadata;
- geen samenvatting publiceren wanneer grounding faalt.

**Niet in scope:** autonome websearch, onbegrensde scraping, rankingbeslissingen door het model of notificaties.

**Menselijke gate:** provider, privacy, kosten, brongebruik en kwaliteitsevaluatie expliciet goedkeuren.

### Explore

```text
/opsx-explore Onderzoek brongebonden Nederlandse samenvattingen voor De Nieuws Piet. Vergelijk lokaal model en externe provider op privacy, hardware, kwaliteit en kosten. Ontwerp minimale input, bronverwijzingen, onzekerheid, prompt/modelversie, budget, timeouts, fallback en evaluatiefixtures. Het model bepaalt niet de ranking en voert geen websearch uit. Schrijf nog geen productiecode en maak geen betaalde accounts.
```

### Propose

```text
/opsx-propose add-grounded-dutch-summaries - Voeg na expliciete providerkeuze korte Nederlandse samenvattingen toe die uitsluitend op opgeslagen broninhoud zijn gebaseerd. Bewaar prompt- en modelversie, toon bronlinks en onzekerheid, begrens kosten/timeouts/retries en val veilig terug op bronmetadata wanneer grounding of provider faalt. Het model bepaalt geen ranking en doet geen autonome websearch.
```

### Apply

```text
/opsx-apply add-grounded-dutch-summaries
```

**Acceptatie:** evaluatiefixtures tonen correcte bronverwijzingen; ongegronde claims worden geweigerd; provideruitval laat de rest van het dashboard werken; werkelijke kosten en datastroom zijn zichtbaar.

---

## Change 9 — `add-daily-news-job`

**Doel:** de bewezen stappen dagelijks lokaal en idempotent uitvoeren.

**In scope:**

- vaste lokale job voor ingestie, classificatie, ranking, clustering en optionele samenvatting;
- timezone en starttijd expliciet configureren;
- dubbele ticks en herstart veilig afhandelen;
- status per stap en privacyarme foutdiagnostiek;
- handmatige dry-run, replay en kill switch.

**Niet in scope:** publieke scheduler, Telegram of andere notificaties, nieuwe businesslogica.

**Menselijke gate:** tijdstip, resourcegebruik, samenvattingskosten en eerste automatische run goedkeuren.

### Explore

```text
/opsx-explore Onderzoek een lokale dagelijkse job voor de bestaande De Nieuws Piet-pipeline. Modelleer timezone, dubbele ticks, procesonderbreking, partial failure, idempotente replay, stapstatus, privacyarme logging, dry-run en kill switch. Voeg geen nieuwe rankingregels, publieke scheduler of notificaties toe.
```

### Propose

```text
/opsx-propose add-daily-news-job - Voeg één lokale dagelijkse job toe die de bestaande ingestie-, classificatie-, ranking-, clustering- en goedgekeurde samenvattingsstappen idempotent uitvoert. Configureer timezone en tijdstip expliciet, voorkom dubbele runs, registreer stapstatus zonder artikelinhoud in logs en ondersteun dry-run, replay en kill switch. Geen publieke scheduler of notificaties.
```

### Apply

```text
/opsx-apply add-daily-news-job
```

**Acceptatie:** een herhaalde run maakt geen duplicaten; hervatten na een fout is veilig; dry-run schrijft niets; de kill switch voorkomt nieuwe automatische runs.

---

## Change 10 — `add-telegram-notification-policy`

**Doel:** optionele Telegram-meldingen sturen voor alleen uitzonderlijk relevant nieuws.

**In scope:**

- expliciete relevantiedrempel en maximaal aantal meldingen;
- bronlink en reden van prioriteit in ieder bericht;
- deduplicatie per dossier;
- stille uren, handmatige test en kill switch;
- alleen lokale pipeline-output gebruiken.

**Niet in scope:** algemene dagelijkse spam, inkomende Telegram-commando's, vrije agentbeslissingen of autonome websearch.

**Menselijke gate:** chatdoel, drempel, stille uren en eerste echte verzending afzonderlijk goedkeuren.

### Explore

```text
/opsx-explore Onderzoek een sobere outbound-only Telegram-notificatie voor De Nieuws Piet. Ontwerp relevantiedrempel, reden van prioriteit, bronlink, dossierdeduplicatie, rate limit, stille uren, handmatige dry-run en kill switch. Geen inkomende commando's, vrije agentbeslissingen of autonome websearch.
```

### Propose

```text
/opsx-propose add-telegram-notification-policy - Voeg optionele outbound-only Telegram-meldingen toe voor nieuws boven een expliciet goedgekeurde relevantiedrempel. Neem bronlink en reden van prioriteit op, dedupliceer per dossier, begrens volume, respecteer stille uren en bied dry-run en kill switch. Geen inkomende commando's, algemene briefing-spam of vrije agentbeslissingen.
```

### Apply

```text
/opsx-apply add-telegram-notification-policy
```

**Acceptatie:** alleen items boven de drempel worden eenmaal gemeld; stille uren en limieten werken; ieder bericht bevat bron en reden; uitschakelen stopt nieuwe meldingen direct.

---

## Vaste volgorde

```text
bootstrap sluiten
  → broncatalogus
  → RSS-ingestie
  → uitlegbare classificatie/ranking
  → dashboard-UI
  → expliciete feedback
  → gebeurtenisdeduplicatie
  → brongebonden samenvattingen
  → dagelijkse job
  → optionele Telegram-meldingen
```

Als een eerdere change laat zien dat de architectuur anders moet, stop dan. Werk eerst roadmap en actieve artifacts bij, valideer opnieuw en hervat pas na menselijke review.
