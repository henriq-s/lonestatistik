# =============================================================
#  Lönestatistik – en dashboard för SCB:s lönestatistik
#
#  Läser lokal data (Parquet) som hämtats med uppdatera_data.py.
#  Två vyer:
#    1. Lönespridning – percentiler per yrke, filtrerat på
#       bransch, sektor och kön
#    2. Regioner – medellön per riksområde för ett valt yrke
#
#  Starta appen med:  streamlit run app.py
# =============================================================

import io
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from branscher import bransch_for

DATAMAPP = Path(__file__).parent / "data"

# Färger (validerad palett): en blå sekvens för percentilspannet
FARG_SPANN = "#9ec5f4"     # ljusblå: 10:e–90:e percentilen
FARG_KVARTIL = "#5598e7"   # mellanblå: 25:e–75:e percentilen
FARG_MEDIAN = "#104281"    # mörkblå: medianen
FARG_MEDEL = "#e34948"     # röd: medelvärdet
FARG_STAPEL = "#2a78d6"    # regionvyns staplar


# -------------------------------------------------------------
#  Del 1: Läs in datan (en gång per serverstart)
# -------------------------------------------------------------

@st.cache_data
def las_spridning():
    df = pd.read_parquet(DATAMAPP / "lonespridning.parquet")
    df["Bransch"] = df["SSYK"].map(bransch_for)
    return df


@st.cache_data
def las_region():
    return pd.read_parquet(DATAMAPP / "lonregion.parquet")


@st.cache_data
def las_utveckling():
    return pd.read_parquet(DATAMAPP / "lonutveckling.parquet")


@st.cache_data
def datum_hamtat():
    """När hämtades datan från SCB? Avläses ur datafilernas ändringstid,
    dvs. när uppdatera_data.py senast kördes."""
    filer = list(DATAMAPP.glob("*.parquet"))
    if not filer:
        return None
    senaste = max(fil.stat().st_mtime for fil in filer)
    return datetime.fromtimestamp(senaste).date()


def till_excel(df, bladnamn):
    """Gör om en tabell till en Excel-fil i minnet (för nedladdning).

    Varje kolumn i tabellen blir en egen kolumn i Excel-filen.
    """
    buffert = io.BytesIO()
    with pd.ExcelWriter(buffert, engine="openpyxl") as skrivare:
        df.to_excel(skrivare, index=False, sheet_name=bladnamn)
        # Anpassa kolumnbredderna efter innehållet
        blad = skrivare.sheets[bladnamn]
        for i, kolumn in enumerate(df.columns, start=1):
            langsta = len(kolumn)
            if len(df):
                langsta = max(langsta, int(df[kolumn].astype(str).str.len().max()))
            blad.column_dimensions[blad.cell(1, i).column_letter].width = langsta + 2
    return buffert.getvalue()

EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def visa_tabell(styler, kolumner, textkolumner):
    """Renderar en pandas Styler som vanlig HTML-tabell.

    Streamlits egen st.dataframe ritas på en canvas och stödjer bara ett
    fåtal CSS-egenskaper – bland annat ignoreras kursiv stil. Den här
    varianten stödjer all CSS, till priset av att sortering och sökning
    försvinner (spelar ingen roll för små, färdigsorterade tabeller).
    """
    hoger = [i for i, k in enumerate(kolumner) if k not in textkolumner]
    vanster = [i for i, k in enumerate(kolumner) if k in textkolumner]
    stilar = [
        {"selector": "", "props": [("border-collapse", "collapse"),
                                   ("width", "100%"), ("font-size", "0.875rem")]},
        {"selector": "th, td", "props": [("border", "1px solid rgba(49,51,63,0.12)"),
                                         ("padding", "0.35rem 0.6rem")]},
        {"selector": "th", "props": [("background", "#f0f2f6"),
                                     ("font-weight", "600"), ("color", "#31333F")]},
    ]
    stilar += [{"selector": f"th.col{i}, td.col{i}",
                "props": [("text-align", "right")]} for i in hoger]
    stilar += [{"selector": f"th.col{i}, td.col{i}",
                "props": [("text-align", "left")]} for i in vanster]

    html = (styler.hide(axis="index").set_table_styles(stilar)).to_html()
    st.markdown(html, unsafe_allow_html=True)


def arlig_okning(serie, kolumn="Median"):
    """Räknar årlig procentuell ökning av vald lönekolumn.

    Bara mellan år som ligger direkt efter varandra – saknas ett år
    hoppar vi över det i stället för att räkna en missvisande siffra.
    """
    s = serie.dropna(subset=[kolumn]).sort_values("År").reset_index(drop=True)
    rader = []
    for i in range(1, len(s)):
        if s.loc[i, "År"] - s.loc[i - 1, "År"] == 1:
            okning = (s.loc[i, kolumn] / s.loc[i - 1, kolumn] - 1) * 100
            rader.append({"År": int(s.loc[i, "År"]), "Ökning": okning})
    return pd.DataFrame(rader)


def ackumulerad_okning(yrke_serie, alla_serie, kolumn="Median"):
    """Ackumulerad procentuell ökning för två serier, indexerade till
    SAMMA basår (första året där båda har värden) så jämförelsen blir
    rättvis. Returnerar (yrke_df, alla_df, basår).
    """
    def som_arsserie(serie):
        s = serie.dropna(subset=[kolumn]).sort_values("År")
        return s.set_index("År")[kolumn]

    yrke = som_arsserie(yrke_serie)
    alla = som_arsserie(alla_serie)
    gemensamma = yrke.index.intersection(alla.index)
    if len(gemensamma) == 0:
        return pd.DataFrame(), pd.DataFrame(), None

    basar = int(gemensamma.min())

    def indexera(s):
        s = s[s.index >= basar]
        return pd.DataFrame({"År": s.index.astype(int),
                             "Ökning": (s / s.loc[basar] - 1) * 100})

    return indexera(yrke), indexera(alla), basar


st.set_page_config(page_title="Lönestatistik", page_icon="💰", layout="wide")

if not (DATAMAPP / "lonespridning.parquet").exists():
    st.error("Datafilerna saknas. Kör först:  .venv\\Scripts\\python uppdatera_data.py")
    st.stop()

spridning = las_spridning()
region = las_region()
utveckling = las_utveckling()

st.title("💰 Lönestatistik")
st.caption("Månadslöner per yrke · Källa: Lönestrukturstatistik, hela ekonomin "
           "(AM0110). Statistikansvarig myndighet: Medlingsinstitutet. "
           "Statistiken framställd av SCB och hämtad via SCB:s öppna API.")


# -------------------------------------------------------------
#  Del 2: Gemensamma filter (gäller båda vyerna)
# -------------------------------------------------------------

kol1, kol2, kol3 = st.columns(3)
with kol1:
    vald_sektor = st.selectbox("Sektor", sorted(spridning["Sektor"].unique(),
                                                key=lambda s: s != "samtliga sektorer"))
with kol2:
    valt_kon = st.selectbox("Kön", ["Totalt", "Kvinnor", "Män"])
with kol3:
    valt_ar = st.selectbox("År", sorted(spridning["År"].unique(), reverse=True))

flik_spridning, flik_region, flik_yrke = st.tabs(
    ["📊 Lönespridning", "🗺️ Regioner", "🔍 Yrkesfokus"])

# Sidfoten skapas här (så att den hamnar under flikarna i layouten) men
# fylls direkt – flikinnehållet nedan kan anropa st.stop(), och då hade
# en sidfot som skrivs sist i koden aldrig hunnit ritas ut.
sidfot = st.container()
with sidfot:
    st.divider()
    hamtat = datum_hamtat()
    if hamtat:
        st.caption(
            f"Data hämtad från SCB {hamtat:%Y-%m-%d}. SCB rättar löpande sina "
            "källdata och rättelser meddelas bara i Statistikdatabasen – "
            "siffror som ändrats efter det datumet syns alltså inte här. "
            "Statistiken är öppna data (CC0)."
        )


# -------------------------------------------------------------
#  Del 3: Lönespridningsvyn
# -------------------------------------------------------------

with flik_spridning:
    valda_branscher = st.multiselect(
        "Bransch (tomt = alla)",
        options=sorted(spridning["Bransch"].unique()),
        placeholder="Välj en eller flera branscher",
    )

    urval = spridning[
        (spridning["Sektor"] == vald_sektor)
        & (spridning["Kön"] == valt_kon)
        & (spridning["År"] == valt_ar)
        & (spridning["SSYK"] != "0000")  # raden "Samtliga yrken" hanteras separat
    ]
    if valda_branscher:
        urval = urval[urval["Bransch"].isin(valda_branscher)]

    # Släng yrken som saknar värden helt (döljs av SCB i små grupper)
    urval = urval.dropna(subset=["Median"]).sort_values("Median", ascending=False)

    st.markdown(f"**{len(urval)} yrken** matchar filtren.")

    # --- Diagram: percentilspann för ALLA yrken (scrollbart) ---
    # Sorterat stigande: sista raden (högst median) ritas överst,
    # så förstavyn i den scrollbara behållaren visar toppen.
    sorterat = urval.iloc[::-1]

    # Axelraden och det höga diagrammet är två separata figurer. För att
    # deras ritytor ska hamna exakt över varandra låser vi BÅDA till samma
    # vänstermarginal och samma x-intervall. 440 px rymmer även det längsta
    # yrkesnamnet (uppmätt till 421 px), så inga etiketter klipps.
    MARGIN_V = 440
    x_min = float(sorterat[["P10", "Median"]].min().min())
    x_max = float(sorterat[["P90", "Medel"]].max().max())
    luft = (x_max - x_min) * 0.03
    x_intervall = [x_min - luft, x_max + luft]

    def spann_i_ett_spar(df, fran_kolumn, till_kolumn, farg, bredd):
        """Ritar alla yrkens spann som ETT spår (None bryter linjen mellan
        yrkena) – mycket snabbare än ett spår per yrke."""
        x, y = [], []
        for _, rad in df.iterrows():
            x += [rad[fran_kolumn], rad[till_kolumn], None]
            y += [rad["Yrke"], rad["Yrke"], None]
        return go.Scatter(x=x, y=y, mode="lines",
                          line=dict(color=farg, width=bredd),
                          showlegend=False, hoverinfo="skip")

    fig = go.Figure()
    fig.add_trace(spann_i_ett_spar(sorterat, "P10", "P90", FARG_SPANN, 3))
    fig.add_trace(spann_i_ett_spar(sorterat, "P25", "P75", FARG_KVARTIL, 9))
    # Median och medel som markörer. Hovring sköts av det osynliga spåret
    # nedan, så att alla sex värdena visas samlat i stället för ett i taget.
    fig.add_trace(go.Scatter(
        x=sorterat["Median"], y=sorterat["Yrke"], mode="markers", name="Median",
        marker=dict(color=FARG_MEDIAN, size=11, symbol="line-ns-open",
                    line=dict(width=3)),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=sorterat["Medel"], y=sorterat["Yrke"], mode="markers", name="Medel",
        marker=dict(color=FARG_MEDEL, size=8),
        showlegend=False, hoverinfo="skip",
    ))

    # Osynlig stapel över hela raden = ett stort hovringsmål per yrke.
    # Värdena förformateras här så att dolda värden blir "–" i stället för NaN.
    matt_kolumner = ["P10", "P25", "Median", "Medel", "P75", "P90"]
    hovervarden = sorterat[matt_kolumner].map(
        lambda v: "–" if pd.isna(v) else f"{v:,.0f} kr")
    fig.add_trace(go.Bar(
        y=sorterat["Yrke"], x=[x_intervall[1] - x_intervall[0]] * len(sorterat),
        base=x_intervall[0], orientation="h",
        marker=dict(color="rgba(0,0,0,0)"),
        customdata=hovervarden.values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "10:e percentilen: %{customdata[0]}<br>"
            "25:e percentilen: %{customdata[1]}<br>"
            "Median: %{customdata[2]}<br>"
            "Medel: %{customdata[3]}<br>"
            "75:e percentilen: %{customdata[4]}<br>"
            "90:e percentilen: %{customdata[5]}"
            "<extra></extra>"
        ),
        showlegend=False,
    ))

    hojd = max(400, 32 * len(sorterat) + 40)
    fig.update_layout(
        height=hojd,
        plot_bgcolor="#fcfcfb", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, 'Segoe UI', sans-serif"),
        showlegend=False,          # legenden bor i axelraden ovanför
        hovermode="closest",
        bargap=0,
        # Axeln är dold här (den syns i axelraden), men rutnätet behålls
        # som lodrätt riktmärke hela vägen ner.
        xaxis=dict(range=x_intervall, showticklabels=False, title=None,
                   gridcolor="#e1e0d9", fixedrange=True),
        # Kategorier ritas i den ordning de dyker upp i datan, nerifrån
        # och upp – "sorterat" är stigande, så högst median hamnar överst.
        # Explicit intervall tar bort plotlys automarginal, som annars
        # blir ett stort tomrum i ett så här högt diagram.
        yaxis=dict(color="#52514e", showgrid=False, fixedrange=True,
                   range=[-0.6, len(sorterat) - 0.4]),
        margin=dict(t=10, b=10, l=MARGIN_V, r=0, autoexpand=False),
    )

    # --- Axelraden: egen liten figur som ligger UTANFÖR scrollrutan ---
    fig_axel = go.Figure()
    for farg, bredd, namn in [
        (FARG_SPANN, 3, "10:e–90:e percentilen"),
        (FARG_KVARTIL, 9, "25:e–75:e percentilen"),
    ]:
        fig_axel.add_trace(go.Scatter(
            x=[None], y=[None], mode="lines", name=namn,
            line=dict(color=farg, width=bredd), hoverinfo="skip"))
    fig_axel.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers", name="Median",
        marker=dict(color=FARG_MEDIAN, size=11, symbol="line-ns-open",
                    line=dict(width=3)), hoverinfo="skip"))
    fig_axel.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers", name="Medel",
        marker=dict(color=FARG_MEDEL, size=8), hoverinfo="skip"))
    fig_axel.update_layout(
        height=105,
        plot_bgcolor="#fcfcfb", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, 'Segoe UI', sans-serif"),
        legend=dict(orientation="h", yanchor="top", y=0, x=0, xanchor="left",
                    font=dict(size=12)),
        xaxis=dict(range=x_intervall, side="top", title="Månadslön (kr)",
                   tickformat=",.0f", gridcolor="#e1e0d9", color="#898781",
                   linecolor="#c3c2b7", fixedrange=True),
        yaxis=dict(visible=False, range=[0, 1], fixedrange=True),
        margin=dict(t=58, b=32, l=MARGIN_V, r=0, autoexpand=False),
    )

    # Båda figurerna läggs i likadana behållare, och båda tvingas reservera
    # plats för en scrollbar. Annars blir axelraden ~42 px bredare än det
    # scrollande diagrammet och skalorna skulle töjas olika mycket.
    st.markdown("""
        <style>
        .st-key-axelrad, .st-key-spridningsdiagram { overflow-y: scroll !important; }
        /* Axelraden behåller ramens mått (så ritytorna hamnar lika)
           men ramen görs osynlig, och luften mellan de två minskas. */
        .st-key-axelrad { border-color: transparent !important;
                          margin-bottom: -1rem !important; }
        </style>
    """, unsafe_allow_html=True)

    utan_verktyg = {"displayModeBar": False}
    with st.container(height=125, key="axelrad"):
        st.plotly_chart(fig_axel, width="stretch", config=utan_verktyg)
    # Fast höjd på behållaren gör diagrammet scrollbart
    with st.container(height=min(700, hojd + 20), key="spridningsdiagram"):
        st.plotly_chart(fig, width="stretch", config=utan_verktyg)
    st.caption("Skalan överst står kvar när du scrollar. "
               "Håll muspekaren över en rad för att se alla värden.")

    # --- Tabellen: alla yrken som matchar filtren ---
    kolumner = ["SSYK", "Yrke", "Bransch", "P10", "P25", "Median", "Medel", "P75", "P90"]
    st.dataframe(
        urval[kolumner],
        width="stretch",
        height=500,
        hide_index=True,
        column_config={
            "SSYK": st.column_config.TextColumn("SSYK", width="small"),
            **{k: st.column_config.NumberColumn(k, format="localized")
               for k in ["P10", "P25", "Median", "Medel", "P75", "P90"]},
        },
    )
    st.caption("Belopp i kr/månad. Tomma celler = SCB redovisar inte värdet "
               "(för få anställda i gruppen). Klicka på en kolumnrubrik för att sortera.")

    st.download_button(
        "📥 Ladda ner tabellen som Excel",
        data=till_excel(urval[kolumner], "Lönespridning"),
        file_name=f"lonespridning_{valt_ar}.xlsx",
        mime=EXCEL_MIME,
    )


# -------------------------------------------------------------
#  Del 4: Regionvyn
# -------------------------------------------------------------

with flik_region:
    # "Samtliga yrken" (0000) sorteras först och blir standardval.
    # 0001/0002 är restposter (övriga/okända yrken) – de tas bort.
    yrkesval = region[["SSYK", "Yrke"]].drop_duplicates().sort_values("SSYK")
    yrkesval = yrkesval[~yrkesval["SSYK"].isin(["0001", "0002"])]
    etiketter = yrkesval["SSYK"] + "  " + yrkesval["Yrke"]

    valt_yrke = st.selectbox("Yrke (skriv för att söka)", etiketter)
    vald_ssyk = valt_yrke.split()[0]

    r_urval = region[
        (region["SSYK"] == vald_ssyk)
        & (region["Sektor"] == vald_sektor)
        & (region["Kön"] == valt_kon)
        & (region["År"] == valt_ar)
        & (region["Region"] != "Riket")
    ].dropna(subset=["Medellön"]).sort_values("Medellön", ascending=True)

    riket = region[
        (region["SSYK"] == vald_ssyk)
        & (region["Sektor"] == vald_sektor)
        & (region["Kön"] == valt_kon)
        & (region["År"] == valt_ar)
        & (region["Region"] == "Riket")
    ]["Medellön"].squeeze()

    if r_urval.empty:
        st.info("SCB redovisar ingen regional data för det här urvalet "
                "(för få anställda). Prova ett annat filter.")
    else:
        fig2 = go.Figure(go.Bar(
            x=r_urval["Medellön"], y=r_urval["Region"], orientation="h",
            marker=dict(color=FARG_STAPEL),
            hovertemplate="%{x:,.0f} kr<extra>%{y}</extra>",
        ))
        if pd.notna(riket):
            fig2.add_vline(x=riket, line_dash="dot", line_color="#52514e",
                           annotation_text=f"Riket: {riket:,.0f} kr",
                           annotation_position="top")
        fig2.update_layout(
            height=420,
            plot_bgcolor="#fcfcfb", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="system-ui, 'Segoe UI', sans-serif"),
            xaxis=dict(title="Medellön (kr/månad)", gridcolor="#e1e0d9",
                       tickformat=",.0f", color="#898781"),
            yaxis=dict(color="#52514e", showgrid=False),
            margin=dict(t=40, l=10),
        )
        st.plotly_chart(fig2, width="stretch")

        st.dataframe(
            r_urval[["Region", "Medellön", "Antal anställda"]]
            .sort_values("Medellön", ascending=False),
            width="stretch", hide_index=True,
            column_config={
                "Medellön": st.column_config.NumberColumn(format="localized"),
                "Antal anställda": st.column_config.NumberColumn(format="localized"),
            },
        )
        st.caption("Regionerna är SCB:s åtta riksområden (NUTS 2). "
                   "Percentiler finns tyvärr inte på regional nivå.")

        st.download_button(
            "📥 Ladda ner tabellen som Excel",
            data=till_excel(
                r_urval[["Region", "Medellön", "Antal anställda"]]
                .sort_values("Medellön", ascending=False),
                "Lön per region",
            ),
            file_name=f"lonregion_{vald_ssyk}_{valt_ar}.xlsx",
            mime=EXCEL_MIME,
        )


# -------------------------------------------------------------
#  Del 5: Yrkesfokus – allt om ett enskilt yrke
# -------------------------------------------------------------

with flik_yrke:
    fokus_val = region[["SSYK", "Yrke"]].drop_duplicates().sort_values("SSYK")
    fokus_val = fokus_val[~fokus_val["SSYK"].isin(["0000", "0001", "0002"])]
    fokus_etiketter = (fokus_val["SSYK"] + "  " + fokus_val["Yrke"]).tolist()

    fokus_yrke = st.selectbox("Yrke", fokus_etiketter, index=None,
                              placeholder="Välj ett yrke", key="fokus_yrke")
    if fokus_yrke is None:
        st.info("Välj ett yrke i listan här ovanför.")
        st.stop()
    fokus_ssyk = fokus_yrke.split()[0]
    fokus_namn = fokus_yrke[len(fokus_ssyk):].strip()

    # --- Linjediagram: medianlönens utveckling 2018–2025 ---
    yrke_serie = utveckling[
        (utveckling["SSYK"] == fokus_ssyk)
        & (utveckling["Sektor"] == vald_sektor)
        & (utveckling["Kön"] == valt_kon)
    ].sort_values("År")
    alla_serie = utveckling[
        (utveckling["SSYK"] == "0000")
        & (utveckling["Sektor"] == vald_sektor)
        & (utveckling["Kön"] == valt_kon)
    ].sort_values("År")

    if yrke_serie["Median"].isna().all():
        st.info("SCB redovisar ingen löneutveckling för det här urvalet "
                "(för få anställda). Prova ett annat filter.")
    else:
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=yrke_serie["År"], y=yrke_serie["Median"],
            name=fokus_namn, mode="lines+markers",
            line=dict(color=FARG_STAPEL, width=2), marker=dict(size=8),
            hovertemplate="%{y:,.0f} kr<extra>" + fokus_namn + "</extra>",
        ))
        fig3.add_trace(go.Scatter(
            x=alla_serie["År"], y=alla_serie["Median"],
            name="Hela arbetsmarknaden (samtliga yrken)", mode="lines+markers",
            line=dict(color="#898781", width=2, dash="dot"), marker=dict(size=8),
            hovertemplate="%{y:,.0f} kr<extra>Hela arbetsmarknaden</extra>",
        ))
        fig3.update_layout(
            title=dict(text=f"Medianlönens utveckling 2018–2025 · {vald_sektor}",
                       font=dict(size=13), x=0),
            height=420, hovermode="x unified",
            plot_bgcolor="#fcfcfb", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="system-ui, 'Segoe UI', sans-serif"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            xaxis=dict(tickmode="linear", dtick=1, showgrid=False,
                       range=[2017.6, 2025.4],
                       linecolor="#c3c2b7", color="#898781"),
            yaxis=dict(title="Medianlön (kr/månad)", gridcolor="#e1e0d9",
                       tickformat=",.0f", color="#898781"),
            margin=dict(t=70),
        )
        st.plotly_chart(fig3, width="stretch")
        st.caption("Tidsserien bygger på två SCB-tabeller (2018–2022 respektive "
                   "2023–2025); SCB har justerat insamlingsmetoden mellan dem, så "
                   "jämförelser tvärs över 2022/2023 bör tolkas med lite försiktighet.")

        # --- Diagram 2: ackumulerad procentuell ökning (indexerat) ---
        yrke_ack, alla_ack, basar = ackumulerad_okning(yrke_serie, alla_serie)
        if not yrke_ack.empty:
            figa = go.Figure()
            figa.add_hline(y=0, line_color="#c3c2b7", line_width=1)
            figa.add_trace(go.Scatter(
                x=yrke_ack["År"], y=yrke_ack["Ökning"],
                name=fokus_namn, mode="lines+markers",
                line=dict(color=FARG_STAPEL, width=2), marker=dict(size=8),
                hovertemplate="+%{y:.1f} % sedan " + str(basar)
                              + "<extra>" + fokus_namn + "</extra>",
            ))
            figa.add_trace(go.Scatter(
                x=alla_ack["År"], y=alla_ack["Ökning"],
                name="Hela arbetsmarknaden (samtliga yrken)", mode="lines+markers",
                line=dict(color="#898781", width=2, dash="dot"), marker=dict(size=8),
                hovertemplate="+%{y:.1f} % sedan " + str(basar)
                              + "<extra>Hela arbetsmarknaden</extra>",
            ))
            figa.update_layout(
                title=dict(text=f"Ackumulerad procentuell ökning sedan {basar}",
                           font=dict(size=13), x=0),
                height=330, hovermode="x unified",
                plot_bgcolor="#fcfcfb", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="system-ui, 'Segoe UI', sans-serif"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                xaxis=dict(tickmode="linear", dtick=1, showgrid=False,
                           range=[2017.6, 2025.4],
                           linecolor="#c3c2b7", color="#898781"),
                yaxis=dict(title=f"Ökning sedan {basar}", gridcolor="#e1e0d9",
                           ticksuffix=" %", tickformat=".1f", color="#898781"),
                margin=dict(t=70),
            )
            st.plotly_chart(figa, width="stretch")

        # --- Diagram 3: årlig procentuell ökning (grupperade staplar) ---
        yrke_okning = arlig_okning(yrke_serie)
        alla_okning = arlig_okning(alla_serie)
        if not yrke_okning.empty:
            figp = go.Figure()
            figp.add_trace(go.Bar(
                x=yrke_okning["År"], y=yrke_okning["Ökning"],
                name=fokus_namn,
                marker=dict(color=FARG_STAPEL, cornerradius=3),
                hovertemplate="%{y:.1f} %<extra>" + fokus_namn + "</extra>",
            ))
            figp.add_trace(go.Bar(
                x=alla_okning["År"], y=alla_okning["Ökning"],
                name="Hela arbetsmarknaden (samtliga yrken)",
                marker=dict(color="#898781", cornerradius=3),
                hovertemplate="%{y:.1f} %<extra>Hela arbetsmarknaden</extra>",
            ))
            figp.add_hline(y=0, line_color="#c3c2b7", line_width=1)
            figp.update_layout(
                title=dict(text="Årlig procentuell ökning av medianlönen",
                           font=dict(size=13), x=0),
                height=330, hovermode="x unified",
                barmode="group", bargap=0.3, bargroupgap=0.08,
                plot_bgcolor="#fcfcfb", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="system-ui, 'Segoe UI', sans-serif"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                xaxis=dict(tickmode="linear", dtick=1, showgrid=False,
                           range=[2017.6, 2025.4],
                           linecolor="#c3c2b7", color="#898781"),
                yaxis=dict(title="Ökning mot föregående år", gridcolor="#e1e0d9",
                           ticksuffix=" %", tickformat=".1f", color="#898781"),
                margin=dict(t=70),
            )
            st.plotly_chart(figp, width="stretch")
            st.caption("Siffran för 2023 avser ökningen 2022→2023, som spänner över "
                       "bytet av SCB-tabell – tolka den med extra försiktighet.")

    # --- Lönespridning för valt yrke och år (+ hela arbetsmarknaden som referens) ---
    st.subheader(f"Lönespridning {valt_ar}")
    kolumner = ["SSYK", "Yrke", "Bransch", "P10", "P25", "Median", "Medel", "P75", "P90"]

    def spridningsrad(ssyk):
        return spridning[
            (spridning["SSYK"] == ssyk)
            & (spridning["Sektor"] == vald_sektor)
            & (spridning["Kön"] == valt_kon)
            & (spridning["År"] == valt_ar)
        ]

    fokus_spridning = spridningsrad(fokus_ssyk)
    marknad_rad = spridningsrad("0000").copy()
    marknad_rad["Bransch"] = "–"  # branschgruppering saknar mening för totalen

    tabell_spr = pd.concat([fokus_spridning, marknad_rad])[kolumner]

    matt_kol = ["P10", "P25", "Median", "Medel", "P75", "P90"]
    visa_tabell(
        tabell_spr.style
        .apply(lambda rad: ["font-style: italic" if rad["SSYK"] == "0000" else ""
                            for _ in rad], axis=1)
        .format({k: "{:,.0f}" for k in matt_kol}, na_rep="–"),
        kolumner=kolumner,
        textkolumner=["SSYK", "Yrke", "Bransch"],
    )
    st.caption("Den kursiva raden visar hela arbetsmarknaden (samtliga yrken) "
               "som jämförelse.")

    # --- Lön per region för valt yrke, inklusive raden Riket ---
    st.subheader(f"Lön per region {valt_ar}")
    fokus_region = region[
        (region["SSYK"] == fokus_ssyk)
        & (region["Sektor"] == vald_sektor)
        & (region["Kön"] == valt_kon)
        & (region["År"] == valt_ar)
    ].dropna(subset=["Medellön"]).sort_values("Medellön", ascending=False)

    if fokus_region.empty:
        st.info("Ingen regional data för det här urvalet.")
    else:
        def markera_riket(rad):
            # Riket-raden särskiljs med kursiv stil
            if rad["Region"] == "Riket":
                return ["font-style: italic"] * len(rad)
            return [""] * len(rad)

        regionkolumner = ["Region", "Medellön", "Antal anställda"]
        visa_tabell(
            fokus_region[regionkolumner]
            .style.apply(markera_riket, axis=1)
            .format({"Medellön": "{:,.0f}", "Antal anställda": "{:,.0f}"},
                    na_rep="–"),
            kolumner=regionkolumner,
            textkolumner=["Region"],
        )
