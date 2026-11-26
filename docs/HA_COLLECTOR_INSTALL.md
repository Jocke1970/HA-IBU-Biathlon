# IBU Collector för Home Assistant – första datainsamlingen

**Status: dev / experimentell.** Insamlaren är en separat HA-integration,
inte en HACS-release av dashboardkortet. Ingen laptop behöver köras efter
installation. Inga projektfiler skapas löst i `/config/`.

## Katalogstruktur

```text
/config/
  configuration.yaml                      # befintlig fil: ett include-block
  custom_components/
    ibu_biathlon/                         # integrationskod (HA-standard)
      __init__.py
      collector.py
      manifest.json
  ibu_biathlon/                           # all vår projektdata
    settings.yaml                         # konfiguration, vid behov API-nyckel
    status.json                           # senast körd cykel, upptäckta lopp och fel
    data/
      raw/catalog/<season>/
      raw/competitions/<event_id>/
      raw/pre/<race_id>/
      raw/live/<race_id>/
      raw/post/<race_id>/
      audit/YYYYMMDD.jsonl
```

## Installation från en verifierad GitHub-commit

Välj en **testad commit på dev** och ersätt `COMMIT` med dess SHA.
Kör sedan i **Home Assistant Terminal & SSH**, inte på laptopen:

```bash
mkdir -p /config/custom_components/ibu_biathlon /config/ibu_biathlon
COMMIT="REPLACE_WITH_TESTED_SHA"
BASE="https://raw.githubusercontent.com/Jocke1970/HA-IBU-Biathlon/$COMMIT/custom_components/ibu_biathlon"
for FILE in __init__.py collector.py manifest.json; do
  curl -fL "$BASE/$FILE" -o "/config/custom_components/ibu_biathlon/$FILE" || exit 1
done
cat > /config/ibu_biathlon/settings.yaml <<'YAML'
season: "2627"
min_delay: 1.0
# api_key: "..."     # endast vid misslyckad automatisk nyckelupptäckt
YAML
```

Lägg till denna enda rad i **befintliga** `/config/configuration.yaml`:

```yaml
ibu_biathlon: !include ibu_biathlon/settings.yaml
```

Om `ibu_biathlon:` redan finns, skapa inte en dublett. Kör kontroll av
konfigurationen i HA och **starta om Home Assistant Core**. Den inbyggda
HA-Pythonmiljön behöver inga extra paket.

Kontrollera sedan i HA-terminalen:

```bash
cat /config/ibu_biathlon/status.json
find /config/ibu_biathlon/data -type f | head -20
```

Börja med `status.json`. Om den visar `state: error` och
`last_error: No frontend API key discovered` kan API-åtkomsten behöva
konfigureras med en legitim nyckel i projektets `settings.yaml`.
**Klistra aldrig in nycklar eller kompletta privata råfiler i en chatt
eller GitHub-issue.** Testa åtkomsten enligt leverantörens villkor.

Om `status.json` innehåller `state: running` men
`discovered_races: 0`, kontrollera `events`,
`events_with_competitions` och råfilerna under `data/raw/catalog`.
Det är inte ett bevis för att världscupen är tom; klockformat eller
nycklar i IBU:s svar kan behöva anpassas. Ingen tävling schemaläggs
automatiskt från en okänd/otydlig lokal klocka.

## Schemaläggning och datamängd

- Vid HA-start, därefter en kontrollerad cykel var 60:e sekund.
  Inga överlappande cykler.
- `Seasons`, `Events`, `Cups` var 6:e timme.
- `Competitions` varannan timme för evenemang nära dagens datum.
- Ett brett prov (**Results + samtliga 47 AnalyticResults-kandidater**)
  inom 45 minuter före verifierad schemalagd start och ett prov
  ungefär tre timmar efter start.
- Under tävlingsfönstret: ett begränsat prov av `Results` +
  `RNGT`, `STTM`, `SKIT`, tidigast varje minut per lopp. Kända
  fält kan vara tomma eller inaktuella; IBU:s uppdateringsfrekvens är
  inte verifierad.
- Minst en sekund mellan IBU GET-anrop (standard).
  Vid HTTP 401, 403 eller 429 pausas resten tills HA startas om.
- Varje JSON-svar får **eget tidsstämplat filnamn**, SHA-256 och en
  separat auditpost. Äldre råsvar skrivs inte över av efterföljande
  tävlingsuppdateringar.
- Vid omstart finns råfiler kvar, men schemaläggarens minnestillstånd
  byggs om från API-katalogen. Tillfälliga avbrott kan ge luckor;
  ingen historisk liveinformation fabriceras.

**Observera:** Detta är en första insamlingsbeta, ingen färdig HA
resultat-/sensorintegration. Varken exakt skottid, banposition,
verifierad liveuppdatering eller åtkomstbehörighet kan utlovas innan
ett konkret IBU-svar har undersökts. Rådatamängden kan växa snabbt;
utrymmesgräns/retention måste införas inför långvarig drift.

## Installationens påverkan

Påverkar inte befintlig Lovelace-JS eller CCResult-replay. Koden ligger
under HA-standardkatalogen `custom_components`; **all** övrig data
och konfiguration ligger i `/config/ibu_biathlon/`.
