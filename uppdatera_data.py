# =============================================================
#  Hämtar SCB:s lönestatistik och sparar den lokalt som Parquet.
#
#  Körs manuellt en gång om året, när SCB släppt nya siffror
#  (brukar ske i maj/juni):
#
#      .venv\Scripts\python uppdatera_data.py
#
#  Skapar:
#    data/lonespridning.parquet  – percentiler per yrke/sektor/kön
#    data/lonregion.parquet      – medellön per region/yrke/sektor/kön
# =============================================================

import time
from pathlib import Path

import pandas as pd
import requests

BAS = "https://api.scb.se/OV0104/v1/doris/sv/ssd/AM/AM0110/AM0110A"
SPRIDNING_URL = f"{BAS}/LoneSpridSektYrk4AN"
REGION_URL = f"{BAS}/LonYrkeRegion4AN"
UTVECKLING_GAMLA_URL = f"{BAS}/LoneSpridSektorYrk4A"  # spridning 2014–2022
UTVECKLING_NYA_URL = f"{BAS}/LoneSpridSektYrk4AN"     # spridning 2023–2025

DATAMAPP = Path(__file__).parent / "data"

# SCB tillåter max ~10 anrop per 10 sekunder – vi tar det lugnt
PAUS_MELLAN_ANROP = 1.2  # sekunder


def hamta_metadata(url):
    """Hämtar tabellens variabler: {kod: {värdekod: klartext}}."""
    svar = requests.get(url, timeout=30)
    svar.raise_for_status()
    meta = {}
    for v in svar.json()["variables"]:
        meta[v["code"]] = dict(zip(v["values"], v["valueTexts"]))
    return meta


def slå_upp_kod(meta, variabel, söktext):
    """Hittar värdekoden för en klartext. Exakt träff vinner."""
    for kod, text in meta[variabel].items():
        if text.lower() == söktext.lower():
            return kod
    for kod, text in meta[variabel].items():
        if söktext.lower() in text.lower():
            return kod
    raise ValueError(f"Hittade inte '{söktext}' i variabeln {variabel}")


def hamta_omgang(url, filter_kod, filter_varde, mattkoder, ovriga_variabler):
    """Hämtar en omgång data (t.ex. en sektor) med valda mått.

    Variabler som inte nämns i frågan slås ihop av SCB, så vi måste
    uttryckligen be om alla värden för de övriga variablerna.
    """
    fraga = {
        "query": [
            {"code": filter_kod,
             "selection": {"filter": "item", "values": [filter_varde]}},
            {"code": "ContentsCode",
             "selection": {"filter": "item", "values": mattkoder}},
        ] + [
            {"code": variabel,
             "selection": {"filter": "all", "values": ["*"]}}
            for variabel in ovriga_variabler
        ],
        "response": {"format": "json"},
    }
    svar = requests.post(url, json=fraga, timeout=120)
    svar.raise_for_status()
    return svar.json()


def till_tal(varde):
    """SCB skriver '..' när värdet inte redovisas – gör om till None."""
    return None if varde in ("..", ".") else float(varde)


# -------------------------------------------------------------
#  Tabell 1: Lönespridning (percentiler per yrke, sektor, kön)
# -------------------------------------------------------------

def hamta_lonespridning():
    print("Hämtar lönespridningstabellen ...")
    meta = hamta_metadata(SPRIDNING_URL)

    # De sex mått vi vill ha, och vad kolumnerna ska heta hos oss.
    # OBS: SCB returnerar måtten i tabellens egen ordning (inte i den
    # ordning vi beställer), så vi läser ordningen ur svarets "columns".
    matt_till_kolumn = {
        "10:e percentilen": "P10",
        "25:e percentilen": "P25",
        "Medianlön": "Median",
        "Månadslön": "Medel",
        "75:e percentilen": "P75",
        "90:e percentilen": "P90",
    }
    mattkoder = [slå_upp_kod(meta, "ContentsCode", m) for m in matt_till_kolumn]

    rader = []
    for sektorkod, sektornamn in meta["Sektor"].items():
        print(f"  sektor: {sektornamn}")
        svar = hamta_omgang(SPRIDNING_URL, "Sektor", sektorkod, mattkoder,
                            ovriga_variabler=["Yrke2012", "Kon", "Tid"])
        kolumnnamn = [matt_till_kolumn[kolumn["text"]]
                      for kolumn in svar["columns"] if kolumn["type"] == "c"]
        for post in svar["data"]:
            _, yrkeskod, konkod, ar = post["key"]
            rad = {
                "SSYK": yrkeskod,
                "Yrke": meta["Yrke2012"][yrkeskod],
                "Sektor": sektornamn,
                "Kön": meta["Kon"][konkod].capitalize(),
                "År": int(ar),
            }
            for namn, varde in zip(kolumnnamn, post["values"]):
                rad[namn] = till_tal(varde)
            rader.append(rad)
        time.sleep(PAUS_MELLAN_ANROP)

    return pd.DataFrame(rader)


# -------------------------------------------------------------
#  Tabell 2: Medellön per region (riksområde)
# -------------------------------------------------------------

def hamta_lonregion():
    print("Hämtar regiontabellen ...")
    meta = hamta_metadata(REGION_URL)

    matt_till_kolumn = {"Månadslön": "Medellön", "Antal anställda": "Antal anställda"}
    mattkoder = [slå_upp_kod(meta, "ContentsCode", m) for m in matt_till_kolumn]

    rader = []
    for regionkod, regionnamn in meta["Region"].items():
        print(f"  region: {regionnamn}")
        svar = hamta_omgang(REGION_URL, "Region", regionkod, mattkoder,
                            ovriga_variabler=["Sektor", "Yrke2012", "Kon", "Tid"])
        kolumnnamn = [matt_till_kolumn[kolumn["text"]]
                      for kolumn in svar["columns"] if kolumn["type"] == "c"]
        for post in svar["data"]:
            _, sektorkod, yrkeskod, konkod, ar = post["key"]
            rad = {
                "SSYK": yrkeskod,
                "Yrke": meta["Yrke2012"][yrkeskod],
                "Region": regionnamn,
                "Sektor": meta["Sektor"][sektorkod],
                "Kön": meta["Kon"][konkod].capitalize(),
                "År": int(ar),
            }
            for namn, varde in zip(kolumnnamn, post["values"]):
                rad[namn] = till_tal(varde)
            rader.append(rad)
        time.sleep(PAUS_MELLAN_ANROP)

    return pd.DataFrame(rader)


# -------------------------------------------------------------
#  Tabell 3: Löneutvecklingen över tid (2018–2025)
#
#  Tidsserien sys ihop av två SCB-spridningstabeller: den äldre
#  (t.o.m. 2022) och den nyare (fr.o.m. 2023). Vi hämtar både medel-
#  och medianlön per yrke, sektor och kön. Spridningstabellerna saknar
#  åldersdimension – de är redan totaler över alla åldrar.
# -------------------------------------------------------------

def hamta_lonutveckling_del(url, ar_lista):
    """Hämtar medel- och medianlön per yrke/sektor/kön för valda år."""
    meta = hamta_metadata(url)
    matt_till_kolumn = {"Månadslön": "Medellön", "Medianlön": "Median"}
    mattkoder = [slå_upp_kod(meta, "ContentsCode", m) for m in matt_till_kolumn]

    rader = []
    for sektorkod, sektornamn in meta["Sektor"].items():
        print(f"  sektor: {sektornamn} ({ar_lista[0]}–{ar_lista[-1]})")
        fraga = {
            "query": [
                {"code": "Sektor", "selection": {"filter": "item", "values": [sektorkod]}},
                {"code": "Tid", "selection": {"filter": "item", "values": ar_lista}},
                {"code": "ContentsCode", "selection": {"filter": "item", "values": mattkoder}},
                {"code": "Yrke2012", "selection": {"filter": "all", "values": ["*"]}},
                {"code": "Kon", "selection": {"filter": "all", "values": ["*"]}},
            ],
            "response": {"format": "json"},
        }
        svar = requests.post(url, json=fraga, timeout=120)
        svar.raise_for_status()
        svarjson = svar.json()
        # SCB returnerar måtten i tabellens ordning – läs ur svarets columns
        kolumnnamn = [matt_till_kolumn[kolumn["text"]]
                      for kolumn in svarjson["columns"] if kolumn["type"] == "c"]
        for post in svarjson["data"]:
            _, yrkeskod, konkod, ar = post["key"]
            rad = {
                "SSYK": yrkeskod,
                "Yrke": meta["Yrke2012"][yrkeskod],
                "Sektor": sektornamn,
                "Kön": meta["Kon"][konkod].capitalize(),
                "År": int(ar),
            }
            for namn, varde in zip(kolumnnamn, post["values"]):
                rad[namn] = till_tal(varde)
            rader.append(rad)
        time.sleep(PAUS_MELLAN_ANROP)

    return pd.DataFrame(rader)


def hamta_lonutveckling():
    print("Hämtar löneutveckling 2018–2025 ...")
    gamla = hamta_lonutveckling_del(
        UTVECKLING_GAMLA_URL, [str(ar) for ar in range(2018, 2023)])
    nya = hamta_lonutveckling_del(
        UTVECKLING_NYA_URL, [str(ar) for ar in range(2023, 2026)])
    return pd.concat([gamla, nya], ignore_index=True)


# -------------------------------------------------------------
#  Kör allt och spara
# -------------------------------------------------------------

if __name__ == "__main__":
    DATAMAPP.mkdir(exist_ok=True)

    spridning = hamta_lonespridning()
    spridning.to_parquet(DATAMAPP / "lonespridning.parquet", index=False)
    print(f"Sparade {len(spridning):,} rader -> data/lonespridning.parquet")

    region = hamta_lonregion()
    region.to_parquet(DATAMAPP / "lonregion.parquet", index=False)
    print(f"Sparade {len(region):,} rader -> data/lonregion.parquet")

    utveckling = hamta_lonutveckling()
    utveckling.to_parquet(DATAMAPP / "lonutveckling.parquet", index=False)
    print(f"Sparade {len(utveckling):,} rader -> data/lonutveckling.parquet")

    print("Klart!")
