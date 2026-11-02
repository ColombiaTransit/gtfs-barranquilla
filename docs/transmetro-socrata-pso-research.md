# Transmetro: aanvullende bronnen en PSO-onderzoek (2026-11-02)

Deze onderzoeksnotitie is **aanvullend op de bestaande werkende KML/Playwright-pipeline**. Vervang bestaande KML-haltes, shapes of frequentieconfiguraties niet automatisch met onderstaande bronnen.

## Socrata: paraderos per route

- Dataset: [Paraderos del Sistema, hxy3-94yh](https://www.datos.gov.co/resource/hxy3-94yh.json?$limit=5000).
- Lokaal onderzochte download: **928** route-halteregels; **42** letterlijke routelabels; **610** unieke haltenamen; **682** unieke exacte coördinatenparen.
- Velden: `nombre_ruta`, `nombre_parada`, `secuencia_parada`, `coordenada_y` (lat), `coordenada_x` (lon), `geocoded_column` (GeoJSON Point).
- Voor alle 42 routelabels is de `secuencia_parada` compleet en zonder dubbelen binnen het patroon.
- **Let op:** 682 exacte coördinatenparen zijn niet noodzakelijk 682 fysieke haltes; meerdere perrons, rijrichtingen en kleine coördinaatverschillen blijven apart totdat matching is gecontroleerd.
- De routevarianten `A5-3 Don Bosco` (29 halteregels) en `A5-3 Contingencia` (14) gebruiken voorlopig dezelfde dienstregelingreferentie `A5-3`, maar blijven **verschillende patronen**. Dit impliceert niet dat beide tegelijkertijd rijden.
- Gebruik `scripts/fetch_socrata_paraderos.py` voor een reproduceerbare snapshot en CSV met route-haltevolgorde. Vergelijk met KML `COD_PARADA`; overschrijf KML-identiteiten niet op basis van gelijkende namen.

## Dienstregeling: tijdlagen gescheiden houden

De bestaande `config/*_frequencies.yml` bevatten reeds **gedetailleerde tijdvakken** uit de officiële PDF's van januari 2024. Deze niet vervangen door grovere daggemiddelden. Het betreft historische referentiewaarden; publiceer niet als geverifieerde actuele 2026-frequenties.

Nieuwere operationele vensters (te vergelijken met de live routepagina's):
- [Werkdagen, augustus 2025](https://apiwebtm.com/uploads/HORARIO_DIAS_HABILES_9d41cf8642.pdf).
- [Zaterdag, oktober 2026](https://apiwebtm.com/uploads/HORARIO_SABADOS_ab6f770aca.pdf).
- [Zondag/feestdagen, oktober 2026](https://apiwebtm.com/uploads/HORARIOS_DOMINGOS_Y_FESTIVOS_6ccaa04dc0.pdf).

Uit de onderzochte zaterdagtabel: A5-3 04:50–22:07; A9-4 17:00–21:30; U30 05:30–16:49; A8-3 05:30–18:27; R10 05:00–09:01; S10 05:37–09:38. Zondag/feestdag: A5-3 05:30–21:05; A9-4 06:00–20:30; U30, A8-3, R10, S10, R40 en S40 geen dienst volgens de onderzochte tabel. **Controleer de exacte PDF-versie en de betekenis van laatste vertrek vóór productiewijzigingen.**

## Historische PSO-gegevens / ontbrekende patronen

- [AMB Informe 1, reestructuración (2014)](https://www.ambq.gov.co/wp-content/uploads/2016/circulares-y-resoluciones-transporte/Informe%201%20Reestructuracio%CC%81n%20AMBQ.pdf): tabellen 11–13 met programmering, intervallen en omlooptijden; **niet** als actuele 2026-dienstregeling gebruiken.
- Historische indicaties: B10 06:00–08:23 ~5,5 min en S20 17:02–19:30 ~5,5 min (2014); B10/S20 ~8 min spits en A3-5 ~15 min (2019). Niet toevoegen aan huidige `frequencies.txt` zonder bevestiging.
- A3-40 is historisch beschreven als spitsversterking van A3-4; behoud afzonderlijk patroon.
- Voor A3-40, A3-5, A5-6, B10, Gran Malecón en S20 is in de onderzochte **recente PDF-selectie** geen passend bevestigd dienstvenster gevonden. Dat betekent niet dat de routes vandaag niet bestaan. De repository heeft mogelijk al andere live-bronnen.
- **PSO 2025:** AMB Resolución Metropolitana 096-2026 verwijst naar **FCP No. 143-001-25082025**, Plan de Servicios Operacionales Transmetro. De volledige PSO en bijlagen zijn nog niet beschikbaar; een informatieverzoek aan AMB/Transmetro is op 2026-11-02 verzonden. Gevraagde bijlagen: interval per tijdvak, despacho, ciclos, routevarianten en wijzigingen 2025–2026.

## GraphHopper / GTFS

De bestaande pipeline heeft al **echte KML-shapes**. GraphHopper is primair bedoeld om **rijtijden tussen opeenvolgende haltes** te berekenen en optioneel ontbrekende geometrie te reconstrueren; de bestaande shapes niet onnodig vervangen. Maak een configureerbare GraphHopper-adapter met busprofiel, halteertijd, busbanen en kalibratie tegen officiële omlooptijden. De huidige `travel_time.py` is een schatting.

Voorgestelde verwerking: Socrata-snapshot -> kwaliteitsrapport/matching met KML -> dienstvensters met geldigheidsdatum en bron -> historische frequenties apart -> GraphHopper-rijtijden -> GTFS-validator. Maak ontbrekende gegevens expliciet; vul ze niet stilzwijgend met actuele claims. De bestaande fallback van 9999 seconden moet als placeholder herkenbaar blijven.

## Nog te verifiëren

1. Publicatiedatum en actuele status van de Socrata-dataset.
2. Welke van de 42 patronen actief, tijdelijk of vervallen zijn; met name Gran Malecón, A5-6, A3-40 en A5-3 Contingencia.
3. Verschillen tussen Socrata-volgorde en bestaande KML-stops/shapes.
4. Frequenties na januari 2024, inclusief exacte tijdvakgrenzen.
5. Volledige PSO FCP 143-001-25082025 en eventuele wijzigingen in 2026.
