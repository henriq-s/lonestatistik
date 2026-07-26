# =============================================================
#  Branschgruppering av yrken
#
#  SSYK 2012-koden är hierarkisk: de två första siffrorna anger
#  yrkets huvudgrupp. Här samlar vi huvudgrupperna i begripliga
#  branscher. SCB har ingen egen branschindelning i lönetabellerna,
#  så det här är vår egen gruppering – flytta gärna huvudgrupper
#  mellan branscher om du tycker annorlunda!
# =============================================================

BRANSCHER = {
    "Hälso- och sjukvård & omsorg": ["15", "22", "32", "53"],
    "Utbildning": ["14", "23"],
    "IT": ["25", "35"],
    "Teknik & naturvetenskap": ["21", "31"],
    "Ekonomi & förvaltning": ["24", "33"],
    "Juridik, kultur & socialt arbete": ["26", "34"],
    "Ledning & chefsyrken (övriga)": ["11", "12", "13", "16", "17"],
    "Kontor & administration": ["41", "42", "43", "44"],
    "Service, försäljning & restaurang": ["51", "52", "94", "95"],
    "Säkerhet & bevakning": ["54"],
    "Bygg & hantverk": ["71", "72", "73", "74", "75"],
    "Tillverkning & industri": ["76", "81", "82"],  # 76 = livsmedelshantverk (bagare, slaktare)
    "Transport & maskinförare": ["83"],
    "Lantbruk, skog & fiske": ["61", "62", "92"],
    "Städ & renhållning": ["91", "93", "96"],
    "Försvar & militärt arbete": ["01", "02", "03"],
}

# Undantag för enskilda yrken: en fyrsiffrig SSYK-kod här vinner
# över huvudgruppsregeln ovan.
UNDANTAG = {
    "4117": "Hälso- och sjukvård & omsorg",  # Medicinska sekreterare, vårdadministratörer
}

# Vänd på uppslagningen: {huvudgrupp: bransch}
_HUVUDGRUPP_TILL_BRANSCH = {
    huvudgrupp: bransch
    for bransch, huvudgrupper in BRANSCHER.items()
    for huvudgrupp in huvudgrupper
}


def bransch_for(ssyk_kod):
    """Ger branschen för en fyrsiffrig SSYK-kod, t.ex. '2221' -> vård."""
    kod = str(ssyk_kod)
    if kod in UNDANTAG:
        return UNDANTAG[kod]
    return _HUVUDGRUPP_TILL_BRANSCH.get(kod[:2], "Övrigt")
