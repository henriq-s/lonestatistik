# 💰 Lönestatistik

En dashboard som visualiserar svensk lönestatistik på ett mer utforskningsbart
sätt än de officiella tabellerna. Byggd med Streamlit och data från SCB:s öppna
API.

## Vad appen visar

**📊 Lönespridning** – alla ~390 yrken sorterade efter medianlön, med hela
löneintervallet (10:e–90:e percentilen) utritat per yrke. Filtrerbart på bransch,
sektor, kön och år. Skalan följer med när man scrollar.

**🗺️ Regioner** – medellön per riksområde för ett valt yrke, med riksgenomsnittet
som referenslinje.

**🔍 Yrkesfokus** – allt om ett enskilt yrke: medianlönens utveckling 2018–2025
jämfört med hela arbetsmarknaden, ackumulerad och årlig procentuell ökning, samt
lönespridning och regional fördelning.

Tabellerna kan laddas ner som Excel-filer.

## Kom igång

Kräver Python 3.12 eller senare.

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\streamlit run app.py
```

Appen läser färdig data från mappen `data/` och anropar alltså inte SCB:s API
när den körs.

## Uppdatera datan

SCB släpper ny lönestrukturstatistik en gång per år, normalt i maj/juni. För att
hämta hem den:

```bash
.venv\Scripts\python uppdatera_data.py
```

Skriptet hämtar tre tabeller från SCB och sparar dem som Parquet-filer i `data/`.
Det tar någon minut eftersom det pausar mellan anropen för att hålla sig inom
SCB:s gräns på 30 anrop per 10 sekunder.

**Starta om appen efteråt** – annars ligger den gamla datan kvar i minnescachen.

> ⚠️ Skriptet använder PxWebApi version 1, som SCB stänger av vid årsskiftet
> 2026/2027. Det behöver migreras till version 2 innan dess.

## Filer

| Fil | Innehåll |
|---|---|
| `app.py` | Själva dashboarden |
| `uppdatera_data.py` | Hämtar data från SCB:s API |
| `branscher.py` | Grupperar SSYK-yrkeskoder i branscher – enkel att redigera |
| `data/` | Nedladdad statistik i Parquet-format |

## Data och källa

Statistiken är **Lönestrukturstatistik, hela ekonomin (AM0110)**.
Statistikansvarig myndighet är **Medlingsinstitutet**; statistiken framställs av
**SCB** och hämtas via SCB:s öppna API.

SCB:s öppna data är licensierad under
[CC0](https://creativecommons.org/publicdomain/zero/1.0/deed.sv), vilket innebär
att den får användas och spridas fritt.

Ett par saker som är värda att veta när man tolkar siffrorna:

- **Medianen är oftast mer rättvisande än medelvärdet.** Ett fåtal höga löner
  drar upp snittet, och när sammansättningen i ett yrke ändras kan medelvärdet
  röra sig utan att någons lön gjort det.
- **Tomma värden** betyder att SCB inte redovisar siffran, för att gruppen är
  för liten.
- **Tidsserien bygger på två SCB-tabeller** (2018–2022 respektive 2023–2025) med
  ett metodbyte i skarven, så jämförelser tvärs över 2022/2023 bör tolkas med
  viss försiktighet.
- **Percentiler saknas regionalt** – SCB redovisar bara medellön per riksområde,
  eftersom grupperna annars blir för små för tillförlitliga spridningsmått.

## Verktyg

Python, [Streamlit](https://streamlit.io), [pandas](https://pandas.pydata.org),
[Plotly](https://plotly.com/python/) och [pyarrow](https://arrow.apache.org) –
allt fritt och öppen källkod.
