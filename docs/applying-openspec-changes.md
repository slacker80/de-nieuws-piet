# OpenSpec-changes toepassen

Deze handleiding voert één change tegelijk uit. De roadmap met change-ID's, grenzen en copy-pasteprompts staat in [`openspec-roadmap.md`](openspec-roadmap.md).

## Eén-scherm-flow

```text
kies eerstvolgende change
        ↓
/opsx-explore
        ↓
/opsx-propose <change-id>
        ↓
mens reviewt proposal + specs + design + tasks
        ↓
openspec validate <change-id>
        ↓
/opsx-apply <change-id>
        ↓
tests + review + acceptatie
        ↓
/opsx-archive <change-id>
        ↓
commit + push + remote controle
```

Open niet alle changes tegelijk. Een roadmapitem wordt pas een echte map onder `openspec/changes/` wanneer de voorgaande change is geaccepteerd en je `/opsx-propose` voor het volgende item uitvoert.

## 0. Rond de bootstrap af

De branch bevat een geïmplementeerde `bootstrap-local-news-dashboard`, maar `openspec/specs/` bevat nog geen gearchiveerde systeemspecs.

1. Controleer de actuele status:

   ```bash
   git status --short
   openspec status --change bootstrap-local-news-dashboard
   ```

2. Voer de relevante controles uit:

   ```bash
   cd backend
   python3 -m pytest
   cd ..

   bash -n scripts/*.sh
   git diff --check
   ```

3. Voer voor volledige runtimeacceptatie uit wanneer Docker, Node en Chromium beschikbaar zijn:

   ```bash
   ./scripts/compose-acceptance.sh
   cd frontend
   npm ci
   npx playwright install chromium
   npm run test:e2e
   cd ..
   ```

4. Beoordeel menselijk:

   - start de stack met één commando;
   - opent de frontend lokaal;
   - is de lege toestand bruikbaar op 360 px;
   - retourneert `/health` gezond;
   - blijft SQLite bestaan na het opnieuw maken van de backendcontainer;
   - blijft de toepassing niet-publiek.

5. Valideer en archiveer met de lokaal aangeboden OpenSpec-commando's:

   ```text
   /opsx-archive bootstrap-local-news-dashboard
   ```

6. Lees na archive terug dat:

   - de actieve change naar `openspec/changes/archive/` is verplaatst;
   - de resulterende specs onder `openspec/specs/` staan;
   - `openspec validate` slaagt;
   - Git alleen de verwachte archivewijzigingen toont.

Archive is geen opruimactie: voer hem alleen uit nadat jij het gedrag hebt geaccepteerd.

## 1. Kies uitsluitend de eerstvolgende change

De eerstvolgende change na de bootstrap is:

```text
add-source-catalog
```

Ga pas naar `add-idempotent-rss-ingestion` wanneer de catalogus is geaccepteerd en gearchiveerd. De volledige volgorde staat in de roadmap.

## 2. Explore

Kopieer de Explore-prompt uit de roadmap naar OpenCode:

```text
/opsx-explore <onderzoeksvraag uit de roadmap>
```

Explore mag:

- bestaande code en specs lezen;
- risico's en alternatieven vergelijken;
- open vragen formuleren;
- een kleine onderzoeksproef voorstellen.

Explore mag niet:

- productiecode wijzigen;
- scope stil uitbreiden;
- externe accounts of betaalde diensten aanmaken;
- de menselijke ontwerpkeuze zelf goedkeuren.

Leg vóór propose minimaal vast:

- welk gebruikersresultaat de change levert;
- welke functionaliteit bewust buiten scope blijft;
- welke bestaande modules en specs veranderen;
- welke onzekerheden implementatie blokkeren;
- hoe acceptatie observeerbaar wordt.

## 3. Propose

Gebruik daarna exact de Propose-prompt uit de roadmap:

```text
/opsx-propose <change-id> - <afgebakende opdracht>
```

Controleer dat de change deze artifacts bevat:

```text
openspec/changes/<change-id>/
├── proposal.md
├── design.md
├── tasks.md
└── specs/
    └── <capability>/spec.md
```

### Review `proposal.md`

- Is het probleem duidelijker dan de gekozen techniek?
- Levert deze change één zelfstandig resultaat?
- Zijn scope en niet-doelen expliciet?
- Zijn privacy, kosten, externe effecten en rollback benoemd?
- Is succes voor jou waarneembaar?

### Review de specs

- Beschrijven requirements gedrag en garanties, niet complete implementatiecode?
- Heeft ieder requirement normale, negatieve en grensscenario's?
- Zijn idempotentie, lege data en providerfouten behandeld waar relevant?
- Blijven bronlink en publicatiedatum behouden?

### Review `design.md`

- Zijn keuzes en verworpen alternatieven uitgelegd?
- Kloppen database- en API-gevolgen?
- Zijn beveiliging, observability, migratie en rollback proportioneel?
- Staan exacte scripts en bibliotheekkeuzes hier of in code, niet onnodig in de gedragsspec?

### Review `tasks.md`

- Zijn taken klein en in logische volgorde?
- Begint gedrag met tests of fixtures?
- Heeft iedere taak een concrete verificatie?
- Zijn er geen herhaalde checklists die hetzelfde bewijs opnieuw vragen?

## 4. Definition of Ready

Start apply pas wanneer:

- scope en niet-doelen door jou zijn goedgekeurd;
- blokkerende vragen zijn opgelost;
- requirements en scenario's testbaar zijn;
- ontwerp en rollback passen bij het risico;
- taken uitvoerbaar zijn;
- OpenSpec-validatie slaagt;
- eventuele externe accounts, kosten of datastromen apart zijn goedgekeurd.

Voer het validatiecommando uit dat jouw lokale CLI toont, bijvoorbeeld:

```bash
openspec validate <change-id>
```

Controleer bij afwijkende syntax eerst:

```bash
openspec --help
openspec validate --help
```

## 5. Apply

Start een schone OpenCode-sessie en voer uit:

```text
/opsx-apply <change-id>
```

Geef de implementerende agent deze grenzen mee:

- lees eerst alle change-artifacts en bestaande relevante specs;
- implementeer alleen de actieve change;
- werk test-first waar gedrag verandert;
- markeer een taak pas `[x]` na echte verificatie;
- wijzig artifacts eerst als nieuwe informatie de aanpak verandert;
- commit of push niet voordat de lokale review groen is.

Voer niet meerdere roadmapchanges in één apply uit.

## 6. Verifiëren

Gebruik minimaal:

```bash
git diff --check
bash -n scripts/*.sh
cd backend && python3 -m pytest && cd ..
```

Afhankelijk van de change:

```bash
./scripts/compose-acceptance.sh
cd frontend && npm ci && npm run test:e2e && cd ..
```

Controleer daarnaast:

- ieder acceptancecriterium heeft werkelijk bewijs;
- netwerk- en providerfouten zijn getest;
- herhalen maakt geen duplicaten wanneer idempotentie is vereist;
- logs bevatten geen tokens, volledige artikelinhoud of andere onnodige data;
- nieuwe documentlinks bestaan;
- tracked bronbestanden bevatten geen credentials.

## 7. Menselijke acceptatie

Code en tests kunnen groen zijn zonder dat de change geaccepteerd is. Beoordeel zelf het zichtbare resultaat en de gate uit de roadmap.

Gebruik drie aparte statussen:

- **geïmplementeerd en groen:** code en controles slagen;
- **geaccepteerd:** jij hebt gedrag en risico's beoordeeld;
- **formeel gesloten:** gevalideerd, gearchiveerd, teruggelezen en gepusht.

## 8. Archive, commit en remote verificatie

Archiveer pas na acceptatie:

```text
/opsx-archive <change-id>
```

Controleer daarna lokaal:

```bash
openspec validate

git status --short
git diff --check
```

Commit en push vervolgens de verwachte bestanden. Controleer remote:

```bash
git rev-parse HEAD
git rev-parse origin/$(git branch --show-current)
```

Als GitHub Actions bestaat, wacht dan op de run van exact die commit. Een succesvolle push alleen bewijst niet dat CI groen is.

## Wijzigingen tijdens apply

```text
Zelfde probleem en hetzelfde gewenste resultaat?
├─ Ja → /opsx-update <change-id> - <revisie>, opnieuw reviewen en valideren
└─ Nee → stop apply en maak later een afzonderlijke change
```

Neem nieuwe functionaliteit niet stil mee omdat de relevante bestanden toch al openstaan.

## Wanneer OpenSpec bewust klein mag blijven

Voor een kleine UI-tekst, typefout of interne refactor zonder gedragswijziging is een volledige change meestal niet nodig. Gebruik wel een change wanneer ten minste één van deze punten geldt:

- zichtbaar gedrag verandert;
- database- of API-contract verandert;
- privacy, beveiliging of externe netwerktoegang verandert;
- een provider, LLM, scheduler of notificatie wordt toegevoegd;
- meerdere modules moeten hetzelfde nieuwe contract volgen;
- acceptatie vooraf voorkomt kostbaar herstelwerk.
