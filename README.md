# DULA ZPL Proxy

Deze service vangt Zebra ZPL-printjobs op die naar de DULA-printer worden gestuurd, past de labelinhoud aan voor het DPD-formaat en stuurt de aangepaste printjob vervolgens door naar de echte printer.

Het project is bedoeld voor een specifieke DULA 222-omgeving waarin de labels door de printer niet goed uitlijnen met de juiste tekstposities en lettergroottes. In plaats van de originele ZPL direct door te sturen, wordt de stream onderweg gerewrite.

## Wat doet het?

De proxy:

- luistert op `0.0.0.0:9100`
- ontvangt raw ZPL-data van een client/toepassing
- past font- en positiecorrecties toe op de labelcode
- behoudt `^FWR`-secties intact en corrigeert alleen de normale `^FWN`-velden
- past specifieke DPD-veldverplaatsingen toe, zoals contactpersoon, consignmentnummer en datumregel
- stuurt de aangepaste ZPL door naar de configured doelprinter (standaard ingesteld via de variabelen `PRINTER_IP` en `PRINTER_PORT` in `zpl-proxy.py`)

## Configuratie

De printerinstellingen zijn niet hardcoded voor een specifieke omgeving. Open `zpl-proxy.py` en pas deze waarden aan als dat nodig is:

```python
PRINTER_IP = "192.168.1.50"
PRINTER_PORT = 9100
```

De proxy luistert zelf standaard op `0.0.0.0:9100`, maar de echte printer waarop de aangepaste ZPL wordt afgeleverd kan per installatie verschillen.

## Aanpassingen die worden gedaan

- Zebra Font 0 wordt in normale tekstblokken aangepast naar een aangepaste hoogte/breedte
- specifieke `^FOx,y`-coordinaten worden herschikt om de printuitlijning te verbeteren
- extra ruimte wordt gemaakt voor de datumregel onder de DPD-header

## Gebruik

Start de proxy:

```bash
python3 zpl-proxy.py
```

### Testmodus

Zonder iets naar de printer te sturen, toont de proxy de aangepaste ZPL en slaat deze op:

```bash
python3 zpl-proxy.py --test
```

Dit schrijft:

- `/tmp/dula-test-original.zpl`
- `/tmp/dula-test-output.zpl`

### Debugmodus

Bewaar originele en aangepaste printjobs met tijdstempel:

```bash
python3 zpl-proxy.py --debug
```

Daarna worden bestanden zoals deze gemaakt:

- `/tmp/dula-original-20250101-123456-123456.zpl`
- `/tmp/dula-modified-20250101-123456-123456.zpl`

## Opmerking

Dit is een gespecialiseerde proxy voor een specifieke printer- en labelconfiguratie. De ZPL-regels zijn hardcoded voor de DULA/DPD-labeluitlijning en zijn niet algemeen te gebruiken voor andere printers of labelsets.
