# Spec Delta

## Purpose

Voert handmatig RSS/Atom-import uit voor actieve catalogusbronnen: ophalen met harde begrenzingen, normalisatie van itemidentiteit en metadata, en idempotente, per bron atomaire wegschrijving in de lokale SQLite-database, volledig offline testbaar met synthetische fixtures.

## ADDED Requirements

### Requirement: Scope van de capability
Het systeem SHALL uitsluitend handmatige RSS/Atom-import van items uitvoeren voor bronnen die in de lokale broncatalogus staan, en SHALL dat commando alleen uitvoeren wanneer de gebruiker het expliciet start. Het systeem SHALL GEEN automatische of periodieke ophaling, scheduler, achtergrondtaak, scraping van artikelpagina's, classificatie, rangorde, clustering, LLM-toepassingen of notificaties uitvoeren. Deze change SHALL GEEN HTTP-route voor ingestie, itemlijsten of importstatus toevoegen: de vijf bestaande catalogusroutes en het exacte `/health`-contract blijven de enige API. Opgeslagen worden uitsluitend itemmetadata (identiteit, titel, publicatiedatum, links en bron); artikelinhoud of HTML SHALL niet worden bewaard. Per bron wordt uitsluitend de laatste operationele status bewaard (validators, laatste poging, laatste succes, laatste fout), dus één statusrij per bron; een persistente importgeschiedenis van eerdere runresultaten SHALL niet worden aangelegd.

#### Scenario: Geen automatische ophaling bij start of catalogusoperatie
- **GIVEN** de backend draait met actieve bronnen in de catalogus
- **WHEN** de applicatie start of een catalogusoperatie wordt uitgevoerd
- **THEN** wordt er geen feed opgehaald
- **AND** wordt er geen verbinding met een feedhost geopend

#### Scenario: Geen ingestie- of itemroute
- **GIVEN** de backend draait met de ingestiemodulen beschikbaar
- **WHEN** een niet-gedeclareerde route zoals `GET /api/items` wordt benaderd
- **THEN** wordt HTTP 404 geretourneerd
- **AND** wordt er geen itemdata geretourneerd

#### Scenario: Alleen metadata wordt bewaard
- **GIVEN** een feeditem bevat een uitgebreide HTML-beschrijving
- **WHEN** dat item wordt geïmporteerd
- **THEN** bevat de opgeslagen rij uitsluitend identiteit, titel, publicatiedatum, links en bron
- **AND** is de artikelinhoud niet opgeslagen

### Requirement: Selectie van catalogusbronnen
Het systeem SHALL standaard uitsluitend bronnen selecteren waarvan `is_active` waar is en `type` exact `rss` of `atom` is; de te verwerken bronnen en de bijbehorende `feed_url`-waarden komen uitsluitend uit de lokale catalogus en SHALL niet uit argumenten, configuratiebestanden of het netwerk komen. Een expliciet gevraagde bron die niet in de catalogus bestaat levert de foutcode `unknown_source` op; een expliciet gevraagde inactieve bron levert `source_inactive` op; een bron met een `type` buiten `rss`/`atom` levert `unsupported_type` op. In alle drie de gevallen wordt er géén netwerkverkeer uitgevoerd, wordt er niets geschreven en blijft de bestaande operationele bronstatus ongewijzigd. Een selectie zonder enige te verwerken bron SHALL als succes worden afgesloten. Het importeren van items SHALL nooit bronrecords toevoegen, wijzigen of verwijderen.

#### Scenario: Actieve bron wordt verwerkt
- **GIVEN** de catalogus bevat een actieve bron van `type` `rss`
- **WHEN** het importcommando zonder bronselectie wordt gestart
- **THEN** wordt die bron verwerkt
- **AND** worden zijn items in de itemtabel geschreven

#### Scenario: Inactieve bron blijft buiten de selectie
- **GIVEN** de catalogus bevat een inactieve bron naast actieve bronnen
- **WHEN** het importcommando zonder bronselectie wordt gestart
- **THEN** wordt er geen verkeer naar de `feed_url` van die inactieve bron gestuurd
- **AND** heeft die bron geen items

#### Scenario: Expliciet gevraagde inactieve bron
- **GIVEN** de catalogus bevat een inactieve bron met id 7
- **WHEN** het importcommando die bron expliciet als doel krijgt
- **THEN** wordt de foutcode `source_inactive` gerapporteerd
- **AND** wordt er geen netwerkverkeer uitgevoerd

#### Scenario: Onbekend bron-id
- **GIVEN** geen bronrecord met id 99 bestaat
- **WHEN** het importcommando bron 99 expliciet als doel krijgt
- **THEN** wordt de foutcode `unknown_source` gerapporteerd
- **AND** is de exitcode ongelijk aan 0

#### Scenario: Lege selectie is geen fout
- **GIVEN** de catalogus bevat geen enkele actieve bron
- **WHEN** het importcommando zonder bronselectie wordt gestart
- **THEN** wordt er geen netwerkverkeer uitgevoerd
- **AND** eindigt het commando met exitcode 0

### Requirement: Ophalen met begrenzingen en SSRF-bescherming
Het systeem SHALL het ophalen van een feed begrenzen met de volgende vaste gedragsgrenzen:

- Een verbindingspoging SHALL maximaal 5 seconden mogen duren, een leesoperatie maximaal 10 seconden en de volledige verwerking van één bron maximaal 30 seconden. Het overschrijden van die brondeadline levert `source_timeout` op: de verwerking van die bron SHALL dan onmiddellijk worden gestopt, zonder verdere pogingen en zonder enige schrijfactie aan de item- en aliastabellen.
- Een mislukte TLS-handshake of een mislukte certificaat- of hostnaamvalidatie levert `tls_failure` op; er SHALL niet worden herhaald en er SHALL niets worden geschreven. `connect_timeout` en `read_timeout` blijven de codes voor een uitgevallen verbindings- respectievelijk leesoperatie binnen een poging.
- Er worden maximaal 3 redirects gevolgd; een vierde redirect levert `too_many_redirects` op zonder dat de eindbestemming wordt gelezen.
- Op elke hop, inclusief na elke redirect, SHALL opnieuw worden gecontroleerd dat het scheme `http` of `https` is, dat er geen credentials in de URL staan en dat alle opgeloste adressen publiek zijn; elk niet-publiek adres (privé-, loopback-, link-local-, multicast-, reserved-, unspecified-adres of unieke lokale IPv6-adres) levert `blocked_address` op. Een mislukte DNS-resolutie levert `dns_failure` op.
- Een reactielichaam groter dan 2 MiB levert `body_too_large` op; er wordt niet geparseerd en er wordt niets geschreven.
- Een feed met meer dan 500 items levert `too_many_items` op; er wordt niet stilzwijgend afgekap en er wordt niets geschreven.
- Er wordt maximaal 3 keer geprobeerd dezelfde bron te halen (1 initiële poging + 2 herhalingen), uitsluitend bij transient fouten: verbindings- of leestimeout, verbreekfouten en HTTP 429, 502, 503 en 504. De wachttijden tussen pogingen bedragen 0,5 seconden en daarna 1 seconde. Bij alle andere fouten (overige 4xx/5xx, `parse_error`, `blocked_address`, `too_many_redirects`, `source_timeout`, `tls_failure`, databasefouten) SHALL niet te worden herhaald.
- Wanneer voor een bron een `ETag` of `Last-Modified` bekend is, SHALL het verzoek die validators meesturen; een antwoord met HTTP 304 levert de status `not_modified` op, zonder parsen en zonder schrijfacties aan de item- en aliastabellen; uitsluitend de validators en de operationele bronstatus worden in een afzonderlijke, kleine transactie bijgewerkt.

#### Scenario: Drie redirects worden gevolgd
- **GIVEN** een feed antwoordt met drie opeenvolgende redirects naar publieke adressen
- **WHEN** die bron wordt verwerkt
- **THEN** wordt de uiteindelijke feed gelezen en geïmporteerd
- **AND** is er geen fout geregistreerd

#### Scenario: Vierde redirect wordt geweigerd
- **GIVEN** een feed antwoordt met vier redirects
- **WHEN** die bron wordt verwerkt
- **THEN** wordt de foutcode `too_many_redirects` gerapporteerd
- **AND** wordt de eindbestemming niet gelezen

#### Scenario: Redirect naar een loopbackadres
- **GIVEN** een feed redirect naar `http://127.0.0.1/internal`
- **WHEN** die bron wordt verwerkt
- **THEN** wordt de foutcode `blocked_address` gerapporteerd
- **AND** wordt er geen verzoek naar dat adres gestuurd

#### Scenario: Redirect naar een privénetwerk
- **GIVEN** een feed redirect naar `http://10.0.0.5/feed.xml`
- **WHEN** die bron wordt verwerkt
- **THEN** wordt de foutcode `blocked_address` gerapporteerd

#### Scenario: Te groot reactielichaam
- **GIVEN** een feed antwoordt met een lichaam van meer dan 2 MiB
- **WHEN** die bron wordt verwerkt
- **THEN** wordt de foutcode `body_too_large` gerapporteerd
- **AND** wordt er niets geparseerd of geschreven

#### Scenario: Te veel items
- **GIVEN** een feed bevat 501 items
- **WHEN** die bron wordt verwerkt
- **THEN** wordt de foutcode `too_many_items` gerapporteerd
- **AND** is de itemtabel voor die bron ongewijzigd

#### Scenario: Transiente fout wordt beperkt herhaald
- **GIVEN** de eerste twee pogingen naar een bron falen met HTTP 503 en de derde slaagt
- **WHEN** die bron wordt verwerkt
- **THEN** worden precies drie pogingen gedaan
- **AND** worden er twee wachttijden (0,5 s en 1 s) geregistreerd
- **AND** worden de items van het succesvolle antwoord geschreven

#### Scenario: Niet-transiente fout wordt niet herhaald
- **GIVEN** een feed antwoordt met HTTP 404
- **WHEN** die bron wordt verwerkt
- **THEN** wordt er precies één poging gedaan
- **AND** wordt de foutcode `http_4xx` gerapporteerd

#### Scenario: Bekende validators worden meegestuurd
- **GIVEN** voor een bron een `ETag` bekend is
- **WHEN** die bron opnieuw wordt opgehaald
- **THEN** bevat het verzoek die `ETag`
- **AND** wordt een antwoord met HTTP 304 afgehandeld als `not_modified`

#### Scenario: Onbekende validators leiden geen conditioneel verzoek
- **GIVEN** er is nog nooit een succesvolle ophaling voor een bron geweest
- **WHEN** die bron voor het eerst wordt opgehaald
- **THEN** bevat het verzoek geen `ETag` en geen `Last-Modified`
- **AND** wordt het volledige antwoord verwerkt

#### Scenario: Brondeadline stopt verdere verwerking
- **GIVEN** de verwerking van één bron nadert de grens van 30 seconden
- **WHEN** de volgende poging of leesoperatie het budget zou overschrijden
- **THEN** wordt die bron afgesloten met de foutcode `source_timeout`
- **AND** worden er geen verdere pogingen meer gedaan
- **AND** is de item- en aliastabel voor die bron ongewijzigd

#### Scenario: TLS-validatiefout wordt niet herhaald
- **GIVEN** de feedserver presenteert een ongeldig certificaat
- **WHEN** die bron wordt verwerkt
- **THEN** wordt de foutcode `tls_failure` gerapporteerd
- **AND** wordt er precies één poging gedaan
- **AND** wordt er niets aan items of aliassen geschreven

### Requirement: Normalisatie van itemvelden
Het systeem SHALL elk item normaliseren naar de velden `external_id`, `canonical_url`, `original_url`, `title`, `published_at` en de bron, met de volgende regels:

- `external_id` is de GUID of Atom-id na trimmen; een lege of ontbrekende waarde levert geen `external_id` op.
- `original_url` is de itemlink zoals gepubliceerd, opgelost tegen de `feed_url` van de bron, met verwijderd fragment en behouden query.
- `canonical_url` is de canonieke afgeleide van `original_url` (of van de GUID wanneer die een absolute `http`- of `https`-URL is): trimmen, scheme en host lowercase, IDNA-normalisatie zonder netwerk, standaardpoort verwijderd, leeg pad naar `/`, fragment verwijderd, volgorde en waarden van de query en overige percent-encoding behouden, hoofdletters in het pad behouden en dot-segmenten opgelost. Een niet-http(s)-URL, een URL met credentials of een niet-oplosbare relatieve link levert geen `canonical_url` op; er wordt bij itemlinks nooit geweigerd omwille van een fragment of dot-segment.
- `title` is de titel na trimmen; een lege of ontbrekende titel levert `NULL` op.
- `external_id` en `canonical_url` worden als brongebonden identity-aliassen opgeslagen; die aliassen zijn additief: een gewijzigde waarde voor dezelfde bron voegt een alias toe zonder de eerdere alias te overschrijven of te verwijderen.
- `published_at` wordt opgeslagen als ISO-8601 in UTC met expliciete offset `+00:00` wanneer de bron een timezone-aware datum geeft; een tijdzoneloze of ongeldige datum en een ontbrekende datum levert `NULL` op. De publicatiedatum SHALL NOOIT worden vervangen door de importtijd.
- De bron verwijst met een foreign key naar het bestaande catalogusrecord; importeren SHALL geen bronrecords aanmaken.

#### Scenario: Relatieve link met fragment en query
- **GIVEN** de `feed_url` van de bron is `https://example.com/nieuws/` en een itemlink is `/artikel/1?ref=a#sectie`
- **WHEN** dat item wordt genormaliseerd
- **THEN** is `original_url` gelijk aan `https://example.com/artikel/1?ref=a`
- **AND** is `canonical_url` gelijk aan `https://example.com/artikel/1?ref=a`

#### Scenario: GUID als absolute URL
- **GIVEN** een item heeft geen link maar wel de GUID `https://example.org/Bericht?id=9`
- **WHEN** dat item wordt genormaliseerd
- **THEN** is `external_id` gelijk aan `https://example.org/Bericht?id=9`
- **AND** is `canonical_url` gelijk aan `https://example.org/Bericht?id=9`

#### Scenario: Datum met tijdzone wordt naar UTC omgerekend
- **GIVEN** een item heeft de publicatiedatum `Mon, 29 Sep 2025 16:30:00 +0200`
- **WHEN** dat item wordt genormaliseerd
- **THEN** is `published_at` gelijk aan `2025-09-29T14:30:00+00:00`

#### Scenario: Tijdzoneloze datum wordt NULL
- **GIVEN** een item heeft de publicatiedatum `2025-09-29T16:30:00`
- **WHEN** dat item wordt genormaliseerd
- **THEN** is `published_at` `NULL`
- **AND** is de waarde niet de importtijd

#### Scenario: Ongeldige of ontbrekende datum wordt NULL
- **GIVEN** een item heeft de publicatiedatum `gisteren` of geen datum
- **WHEN** dat item wordt genormaliseerd
- **THEN** is `published_at` `NULL`

#### Scenario: Lege titel wordt NULL
- **GIVEN** een item heeft een titel die uitsluitend uit witruimte bestaat
- **WHEN** dat item wordt genormaliseerd
- **THEN** is `title` `NULL`

#### Scenario: Item wordt aan de juiste catalogusbron gebonden
- **GIVEN** de catalogus bevat bron 4 met een actieve feed
- **WHEN** het importcommando die bron verwerkt
- **THEN** verwijzen alle nieuw geschreven items naar bron 4
- **AND** is het aantal bronrecords na de import ongewijzigd

### Requirement: Itemidentiteit en deduplicatie
Het systeem SHALL de identiteit van een item uitsluitend afleiden uit twee brongebonden identity-aliassen: `external_id` en `canonical_url`. Beide aliassen worden als afzonderlijke rijen in de aliastabel opgeslagen en zijn samen met de bron uniek op databaseniveau (primairsleutel op bron, aliastype en aliaswaarde); een foreign key SHALL bovendien afdwingen dat alias en item altijd tot dezelfde bron behoren. De aliassen zijn additief: een gewijzigde GUID of item-URL van dezelfde bron voegt een alias toe op het bestaande item, waarbij de eerdere alias behouden blijft. Hetzelfde bronitem SHALL per bron maximaal één keer worden opgeslagen, ook wanneer het commando meerdere keren wordt uitgevoerd. Een `contenthash` mag alleen als wijzigingsindicatie worden gebruikt en SHALL NOOIT als primaire identiteit dienen: twee items met gelijke inhoud maar verschillende identiteit worden beide opgeslagen. Wanneer de aliassen van één kandidaat naar twee verschillende bestaande items wijzen, SHALL er een conflict (`identity_conflict`) worden gemeld en SHALL er niet worden gemerged of samengevoegd; beide bestaande items blijven ongewijzigd. Een item dat noch een bruikbaar `external_id` noch een bruikbare `canonical_url` oplevert, SHALL veilig worden overgeslagen: het wordt geteld, maar levert geen fout en geen rij op.

#### Scenario: Herhaalde import levert één rij
- **GIVEN** een item staat al in de itemtabel met dezelfde `external_id`
- **WHEN** hetzelfde feedbestand opnieuw wordt geïmporteerd
- **THEN** bestaat er voor dat bronitem nog steeds precies één rij
- **AND** is het aantal rijen voor die bron ongewijzigd

#### Scenario: Identiteit is gebonden aan de bron
- **GIVEN** bron 1 en bron 2 publiceren beide een item met `external_id` `tag:1`
- **WHEN** beide bronnen worden geïmporteerd
- **THEN** bestaan er twee items
- **AND** heeft elk item zijn eigen `source_id`

#### Scenario: Gelijke inhoud met verschillende identiteit
- **GIVEN** twee items in dezelfde bron hebben identieke titel, datum en linktekst maar verschillende `external_id`
- **WHEN** die bron wordt geïmporteerd
- **THEN** worden beide items opgeslagen
- **AND** worden ze niet als duplicaat herkend op basis van inhoud

#### Scenario: Aliassen van één kandidaat wijzen naar twee bestaande items
- **GIVEN** in een bron bestaan item A met `external_id` X en item B met `canonical_url` Y, en een kandidaat heeft `external_id` X én `canonical_url` Y
- **WHEN** die bron wordt geïmporteerd
- **THEN** wordt de foutcode `identity_conflict` gemeld
- **AND** zijn item A en item B ongewijzigd
- **AND** is er niet gemerged

#### Scenario: Zonder identiteit wordt veilig overgeslagen
- **GIVEN** een item heeft geen GUID, geen Atom-id en geen geldige link
- **WHEN** die bron wordt geïmporteerd
- **THEN** wordt het item overgeslagen en geteld
- **AND** is er geen fout geregistreerd
- **AND** bevat de itemtabel geen rij voor dat item

#### Scenario: Unieke identiteit wordt op databaseniveau afgedwongen
- **GIVEN** twee schrijfacties bieden voor dezelfde bron dezelfde `external_id` aan
- **WHEN** beide schrijfacties worden uitgevoerd
- **THEN** slaagt precies één van beide
- **AND** ontstaat er geen duplicaat

#### Scenario: Gewijzigde GUID wordt als extra alias bewaard
- **GIVEN** een bestaand item heeft de alias `external_id` X en dezelfde `canonical_url`
- **WHEN** die bron opnieuw wordt geïmporteerd met `external_id` Z voor datzelfde item
- **THEN** wijzen X en Z naar hetzelfde item
- **AND** bestaat er voor dat item precies één rij in de itemtabel

#### Scenario: Alias van een andere bron wordt door de database geweigerd
- **GIVEN** er bestaat een item met `source_id` 1
- **WHEN** voor bron 2 een alias met `external_id` X wordt aangemaakt die naar dat item verwijst
- **THEN** weigert de database die schrijfactie
- **AND** is er voor bron 2 geen alias X opgeslagen

### Requirement: Idempotente herhaling
Het systeem SHALL bij een volledig herhaalde import van ongewijzigde feedinhoud dezelfde eindtoestand opleveren zonder enige gewijzigde rij: herkende ongewijzigde items worden als ongewijzigd geteld en niet herschreven. Deze garantie geldt voor de item- en aliastabellen; operationele statusvelden van de bron (validators, laatste poging, laatste succes, laatste fout) SHALL per run mogen veranderen en vallen buiten deze garantie. Wanneer een bestaand item met dezelfde identiteit gewijzigde normaliseerbare velden aanbiedt, SHALL die ene rij binnen dezelfde transactie worden bijgewerkt en SHALL er nooit een tweede rij ontstaan. Items die een feed niet meer bevat, SHALL niet worden verwijderd. Het commando SHALL nooit catalogusdata wijzigen.

#### Scenario: Twee keer importeren zonder feedwijziging
- **GIVEN** een bron is eenmaal succesvol geïmporteerd en de feedinhoud is niet gewijzigd
- **WHEN** het commando opnieuw wordt gestart
- **THEN** worden alle items als ongewijzigd geteld
- **AND** is de inhoud van de item- en aliastabellen byte-voor-byte gelijk gebleven

#### Scenario: Operationele status mag per run veranderen
- **GIVEN** een bron is eenmaal succesvol geïmporteerd en de feedinhoud is niet gewijzigd
- **WHEN** het commando opnieuw wordt gestart en het antwoord is opnieuw 200
- **THEN** zijn item- en aliastabellen byte-voor-byte gelijk gebleven
- **AND** is de laatste poging in de bronstatus bijgewerkt zonder foutcode

#### Scenario: Gewijzigde titel van hetzelfde item
- **GIVEN** een bestaand item heeft `title` `Oud`
- **WHEN** de feed voor dezelfde identiteit `title` `Nieuw` aanbiedt
- **THEN** bestaat er na de import precies één rij voor dat item
- **AND** is die rij bijgewerkt naar `Nieuw`

#### Scenario: Verwijderde items blijven staan
- **GIVEN** een feed bevatte bij de vorige import vijf items en nu nog drie
- **WHEN** die bron opnieuw wordt geïmporteerd
- **THEN** bevat de itemtabel nog steeds vijf items voor die bron
- **AND** zijn de twee ontbrekende items niet verwijderd

### Requirement: Ophalen buiten de transactie, atomair per bron
Het systeem SHALL per bron één atomair transcript gebruiken voor alle schrijfacties aan de item- en aliastabellen van die bron: bij een fout midden in de schrijffase blijft de eindtoestand van die bron in die tabellen exact zoals vóór de start van die bron. De operationele bronstatus volgt die semantiek: na een geslaagde verwerking met HTTP 200 SHALL de successstatus samen met de validators in dezelfde itemtransactie worden geschreven, zodat een terugdraaiende schrijffase ook de successstatus teruggedraait; na status `not_modified` en na een fout SHALL de status in een afzonderlijke, kleine transactie worden vastgelegd, buiten dit atomair transcript. Netwerkverkeer, DNS-resoluties en het parsen SHALL buiten de database-transactie plaatsvinden; tijdens de schrijffase worden geen sockets geopend en geen verzoeken gedaan. Een fout bij één bron SHALL geen invloed hebben op de verwerking of de data van andere bronnen.

#### Scenario: Fout in de schrijffase laat de vorige staat intact
- **GIVEN** een bron is bij een eerdere run succesvol geïmporteerd
- **WHEN** de schrijffase van een nieuwe run geforceerd faalt
- **THEN** is de item- en aliastabel voor die bron identiek aan de situatie vóór de run
- **AND** zijn er geen halfgeschreven items
- **AND** is de successstatus van die run niet vastgelegd

#### Scenario: Fout bij één bron laat andere bronnen doorgaan
- **GIVEN** bron 1 geeft een ophaalfout en bron 2 is bereikbaar
- **WHEN** het importcommando beide bronnen verwerkt
- **THEN** worden de items van bron 2 wel geschreven
- **AND** wordt bron 1 afgesloten met een foutcode

#### Scenario: Geen netwerk tijdens de schrijffase
- **GIVEN** alle feeds van een run zijn opgehaald en geparseerd
- **WHEN** de schrijffase per bron wordt uitgevoerd
- **THEN** worden er in die fase geen sockets geopend
- **AND** worden er in die fase geen transportverzoeken gedaan

### Requirement: Foutcodes en rapportage per bron
Het systeem SHALL per verwerkte bron één resultaatregel rapporteren met het bron-id, de status (`ok`, `not_modified` of `fout`), de tellers (toegevoegd, bijgewerkt, ongewijzigd, overgeslagen, conflicten) en, uitsluitend bij status `fout`, exact één stabiele foutcode uit de gesloten set: `unknown_source`, `source_inactive`, `unsupported_type`, `dns_failure`, `tls_failure`, `blocked_address`, `too_many_redirects`, `connect_timeout`, `read_timeout`, `source_timeout`, `http_4xx`, `http_429`, `http_5xx`, `body_too_large`, `too_many_items`, `parse_error`, `identity_conflict`, `db_unavailable`. De status `not_modified` SHALL niet als foutcode voorkomen: `not_modified` is een status, geen fout, en telt niet mee voor de exitcode. De rapportage en exitcode SHALL deterministisch zijn: bronnen worden op oplopend id verwerkt en gerapporteerd. Foutmeldingen en de uitvoer SHALL GEEN SQL-tekst, GEEN stacktraces, GEEN lokale paden, GEEN credentials en GEEN antwoordlichamen bevatten. Het commando SHALL exitcode 0 teruggeven als elke geselecteerde bron zonder fout en zonder conflict is verwerkt en SHALL een exitcode ongelijk aan 0 teruggeven zodra één bron een fout of conflict heeft of de opdracht zelf niet kon starten. Het rapporteren van resultaten SHALL geschieden in de uitvoer van het commando; een persistente importhistorie van runresultaten SHALL niet worden aangelegd (per bron wordt uitsluitend de laatste operationele status bewaard).

#### Scenario: Alle bronnen slagen
- **GIVEN** drie actieve bronnen leveren alle drie een geldige feed
- **WHEN** het importcommando wordt gestart
- **THEN** worden drie resultaatregels gerapporteerd in oplopende bronvolgorde
- **AND** is de exitcode 0

#### Scenario: Fout bij één bron geeft exitcode ongelijk aan 0
- **GIVEN** één actieve bron is onbereikbaar
- **WHEN** het importcommando wordt gestart
- **THEN** bevat de uitvoer voor die bron één foutcode
- **AND** is de exitcode ongelijk aan 0

#### Scenario: Uitvoer bevat geen interne details
- **GIVEN** een bron faalt met een databasefout
- **WHEN** de uitvoer van het commando wordt gecontroleerd
- **THEN** bevat die uitvoer geen SQL-tekst, geen stacktrace en geen lokaal bestandspad

#### Scenario: Conflict telt mee voor de exitcode
- **GIVEN** één bron levert een identiteitsconflict terwijl de rest correct importeert
- **WHEN** het importcommando wordt gestart
- **THEN** wordt de conflictsteller voor die bron groter dan 0
- **AND** is de exitcode ongelijk aan 0

### Requirement: Per-bron operationele status
Het systeem SHALL per bron uitsluitend de laatste operationele status bewaren: het tijdstip van de laatste poging, het tijdstip van het laatste succes (of `NULL` zolang er nog niet met succes is geïmporteerd), de laatste foutcode (of `NULL` na succes of `not_modified`), een gesaneerd en begrensd foutdetail van hoogstens 200 tekens, het laatst gezien HTTP-status (of `NULL` bij niet-HTTP-fouten) en het aantal opeenvolgende mislukkingen. Een runhistorie SHALL niet worden aangelegd: er bestaat per bron hoogstens één statusrij en eerdere runs zijn niet terug te vinden. Elke ophaalpoging SHALL het tijdstip van de laatste poging vastleggen. Na een geslaagde verwerking met HTTP 200 SHALL de laatste foutcode zijn gewist, SHALL het aantal opeenvolgende mislukkingen op nul staan en SHALL het tijdstip van laatste succes zijn bijgewerkt — alles binnen dezelfde itemtransactie als de items en de aliassen, zodat een terugdraaiende schrijffase ook die successstatus teruggedraait. Na status `not_modified` gelden dezelfde effecten in een afzonderlijke, kleine transactie zonder schrijfacties aan de item- en aliastabellen. Na een ophaal-, parse- of schrijffout SHALL de foutcode, het HTTP-status (indien van toepassing), het foutdetail en de teller worden vastgelegd in een afzonderlijke, kleine transactie, waarbij de item- en aliastabellen onaangeroerd blijven. Selectiefouten zonder bronrecord (`unknown_source`) of vóór het ophalen (`source_inactive`, `unsupported_type`) SHALL de bestaande status niet wijzigen. Wanneer de database zelf niet beschikbaar is, SHALL de statusregistratie worden overgeslagen en SHALL de fout in elk geval in de uitvoer en in de exitcode terugkomen. De operationele statusvelden staan buiten de item-idempotentie: hun wijziging per run maakt een herhaalde import niet niet-idempotent.

#### Scenario: Succes wist een eerdere foutstatus
- **GIVEN** de laatste run van bron 5 eindigde met foutcode `http_5xx` en 3 opeenvolgende mislukkingen
- **WHEN** die bron nu met HTTP 200 wordt geïmporteerd
- **THEN** is de laatste foutcode `NULL`
- **AND** is het aantal opeenvolgende mislukkingen 0
- **AND** is het tijdstip van laatste succes bijgewerkt

#### Scenario: Not modified wist de foutstatus zonder itemtransactie
- **GIVEN** de laatste run van een bron eindigde met een fout
- **WHEN** die bron nu antwoordt met HTTP 304
- **THEN** is de laatste foutcode `NULL` en staat het aantal opeenvolgende mislukkingen op 0
- **AND** zijn de item- en aliastabellen ongewijzigd

#### Scenario: Ophaalfout wordt per bron vastgelegd
- **GIVEN** een actieve bron antwoordt met HTTP 404
- **WHEN** het importcommando die bron verwerkt
- **THEN** is de laatste foutcode `http_4xx` en is het laatst gezien HTTP-status 404
- **AND** is het aantal opeenvolgende mislukkingen ten minste 1
- **AND** is de item- en aliastabel voor die bron ongewijzigd
- **AND** is dezelfde foutcode in de uitvoer gerapporteerd

#### Scenario: Foutdetail is gesaneerd en begrensd
- **GIVEN** een bron faalt met een foutmelding van enkele duizenden tekens
- **WHEN** die fout wordt vastgelegd
- **THEN** is het opgeslagen foutdetail hoogstens 200 tekens
- **AND** bevat het geen SQL-tekst, stacktrace, lokaal pad, credential of antwoordlichaam

#### Scenario: Selectiefout wijzigt de status niet
- **GIVEN** bron 7 heeft een opgeslagen foutstatus uit een eerdere run
- **WHEN** het commando die inactieve bron expliciet als doel krijgt
- **THEN** wordt `source_inactive` gerapporteerd
- **AND** is de opgeslagen status van bron 7 ongewijzigd

#### Scenario: Database-fout garandeert geen persistente status
- **GIVEN** de database is tijdens het vastleggen van de status onbereikbaar
- **WHEN** het commando die situatie verwerkt
- **THEN** is de exitcode ongelijk aan 0 en bevat de uitvoer `db_unavailable`
- **AND** geldt geen eis dat de status in de database is bijgewerkt

#### Scenario: Geen runhistorie
- **GIVEN** dezelfde bron is in vijf eerdere runs verwerkt
- **WHEN** de tabel met bronstatus wordt geteld
- **THEN** bestaat er voor die bron precies één statusrij
- **AND** zijn eerdere runs daar niet uit af te leiden

### Requirement: Handmatig CLI-contract
Het systeem SHALL de import aanbieden als modulecommando `python -m app.rss_ingest` met optionele argumenten voor het databasepad en voor het expliciet selecteren van één bron, en SHALL het resultaat van de uitvoering als exitcode teruggeven (0 = alles zonder fout verwerkt, anders ongelijk aan 0). Zonder argumenten SHALL alle geselecteerde actieve bronnen worden verwerkt. Het commando SHALL de database verplicht op schema-versie 3 aantreffen en SHALL bij een oudere versie afsluiten met exitcode ongelijk aan 0 en een verwijzing naar de migratie-opdracht, zonder iets te schrijven. Het commando SHALL niet automatisch migreren. Een onbekend of ongeldig argument levert exitcode ongelijk aan 0 zonder enige schrijfactie.

#### Scenario: Start zonder argumenten
- **GIVEN** de database staat op schema-versie 3 en er zijn actieve bronnen
- **WHEN** `python -m app.rss_ingest` wordt gestart
- **THEN** worden alle actieve bronnen verwerkt
- **AND** is de exitcode 0 bij foutloze verwerking

#### Scenario: Database op oudere versie
- **GIVEN** de database staat op schema-versie 2
- **WHEN** `python -m app.rss_ingest` wordt gestart
- **THEN** is de exitcode ongelijk aan 0
- **AND** wordt de gebruiker verwezen naar de migratie-opdracht
- **AND** is er geen rij gewijzigd

#### Scenario: Ongeldig argument
- **GIVEN** de database staat op schema-versie 3
- **WHEN** het commando een onbekend argument of een niet-numeriek bron-id krijgt
- **THEN** is de exitcode ongelijk aan 0
- **AND** wordt er geen netwerkverkeer uitgevoerd

### Requirement: Offline teststrategie met synthetische fixtures
Het systeem SHALL de ingestie uitsluitend testen zonder live internet: alle HTTP-gedrag (verzoeken, redirects, statuscodes, headers, lichamen en timeouts) SHALL worden gestuurd via een vervangbare transportlaag, de klok en de wachttijden via vervangbare tijd- en slaapvoorzieningen, en de feeds uitsluitend via synthetische lokale XML-fixtures. De bestaande socket-guard-garantie SHALL voor de volledige ingestiesuite gelden: geen enkele test opent een verbinding naar een externe host. Fixtures SHALL uitsluitend voorbeholen domeinnamen (zoals `example.com` en `example.org`) en verzonnen tekst gebruiken. De testen SHALL de normale, negatieve en grensgevallen dekken, inclusief lege feeds, herhaalde uitvoering, ongeldige datums, identiteitsconflicten, de per-bron statusregistratie en alle begrenzingen.

#### Scenario: Socket-guard rond de ingestiesuite
- **GIVEN** de volledige ingestietestsuite draait onder de bestaande socket-guard
- **WHEN** de suite wordt uitgevoerd
- **THEN** wordt er geen verbinding naar een externe host geopend
- **AND** slaagt de suite volledig

#### Scenario: Fixtures zijn synthetisch
- **GIVEN** alle XML-fixtures van de ingestietests worden ingelezen
- **WHEN** zij worden gecontroleerd op herkomst
- **THEN** gebruiken zij uitsluitend voorbeholen domeinnamen en verzonnen tekst
- **AND** bevatten zij geen overgenomen feedteksten van echte publicaties

#### Scenario: Backoff gebruikt injecteerbare slaap
- **GIVEN** een bron faalt tweemaal transient en slaagt daarna
- **WHEN** die bron in de test wordt verwerkt
- **THEN** wordt de slaapvoorziening exact twee keer aangeroepen met 0,5 seconde en 1 seconde
- **AND** duurt de test geen echte wachttijd

#### Scenario: Lege feed is geen fout
- **GIVEN** een feed bevat een kanaal zonder items
- **WHEN** die bron wordt geïmporteerd
- **THEN** worden er geen items geschreven
- **AND** is de exitcode 0
