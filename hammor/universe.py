"""The universe of stocks Hammor Co. covers on ADX (Abu Dhabi) and DFM (Dubai).

Each entry carries a *business-activity* classification, which is the first
stage of the AAOIFI Standard 21 screen:

  ok           Core business is permissible. Financial-ratio screens still apply.
  islamic_fin  Islamic bank / takaful / Islamic finance house. Supervised by its
               own Sharia board; AAOIFI debt/cash ratios are not meaningful for it.
  review       Mixed or diversified activities (conglomerates, hotels, retail
               that may sell prohibited goods). Ratios are applied, but the stock
               is NOT recommended until a Sharia scholar or the company's
               Sharia board confirms compliance.
  excluded     Core business is impermissible (conventional banking, conventional
               insurance, interest-based finance, alcohol, tobacco, gambling...).

Symbols are Yahoo Finance symbols: ".AD" = ADX, ".AE" = DFM.
The classifications are a starting point prepared by the research desk.
Review them yourself, and edit this list to add or remove companies.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Company:
    symbol: str
    name: str
    exchange: str  # "ADX" or "DFM"
    sector: str
    activity: str  # ok | islamic_fin | review | excluded
    note: str = ""


_ADX = [
    # Islamic financials
    ("ADIB.AD", "Abu Dhabi Islamic Bank", "Islamic Banking", "islamic_fin"),
    ("SIB.AD", "Sharjah Islamic Bank", "Islamic Banking", "islamic_fin"),
    # Energy & utilities
    ("ADNOCGAS.AD", "ADNOC Gas", "Energy", "ok"),
    ("ADNOCDRILL.AD", "ADNOC Drilling", "Energy", "ok"),
    ("ADNOCDIST.AD", "ADNOC Distribution", "Energy", "ok"),
    ("ADNOCLS.AD", "ADNOC Logistics & Services", "Energy", "ok"),
    ("DANA.AD", "Dana Gas", "Energy", "ok"),
    ("TAQA.AD", "Abu Dhabi National Energy (TAQA)", "Utilities", "ok"),
    # Materials & industrials
    ("BOROUGE.AD", "Borouge", "Materials", "ok"),
    ("FERTIGLB.AD", "Fertiglobe", "Materials", "ok"),
    ("EMSTEEL.AD", "Emirates Steel Arkan", "Materials", "ok"),
    ("RAKCEC.AD", "RAK Ceramics", "Materials", "ok"),
    ("ADPORTS.AD", "AD Ports Group", "Industrials", "ok"),
    ("NMDC.AD", "NMDC Group", "Industrials", "ok"),
    # Real estate
    ("ALDAR.AD", "Aldar Properties", "Real Estate", "ok"),
    ("MODON.AD", "Modon Holding", "Real Estate", "ok"),
    ("RAKPROP.AD", "RAK Properties", "Real Estate", "ok"),
    ("ESHRAQ.AD", "Eshraq Investments", "Real Estate", "ok"),
    # Telecom & technology
    ("EAND.AD", "e& (Emirates Telecommunications)", "Telecom", "ok"),
    ("PRESIGHT.AD", "Presight AI", "Technology", "ok"),
    ("SPACE42.AD", "Space42", "Technology", "ok"),
    # Consumer, healthcare, education
    ("AGTHIA.AD", "Agthia Group", "Consumer Staples", "ok"),
    ("AMR.AD", "Americana Restaurants", "Consumer Discretionary", "ok"),
    ("LULU.AD", "Lulu Retail", "Consumer Staples", "review",
     "Hypermarket chain; confirm share of prohibited goods sold"),
    ("PUREHEALTH.AD", "PureHealth", "Healthcare", "ok"),
    ("BURJEEL.AD", "Burjeel Holdings", "Healthcare", "ok"),
    ("ALEFEDT.AD", "Alef Education", "Education", "ok"),
    # Diversified holdings (need Sharia board confirmation)
    ("IHC.AD", "International Holding Company", "Diversified", "review",
     "Conglomerate with financial-services exposure"),
    ("ALPHADHABI.AD", "Alpha Dhabi Holding", "Diversified", "review",
     "Conglomerate; includes hospitality"),
    ("MULTIPLY.AD", "Multiply Group", "Diversified", "review",
     "Investment holding"),
    ("GHITHA.AD", "Ghitha Holding", "Consumer Staples", "review",
     "Food holding; review subsidiaries"),
    ("QHOLDING.AD", "Q Holding", "Diversified", "review", "Investment holding"),
    ("2POINTZERO.AD", "2PointZero", "Diversified", "review", "Investment holding"),
    # Excluded: conventional finance / hospitality with alcohol
    ("FAB.AD", "First Abu Dhabi Bank", "Banking", "excluded",
     "Conventional (interest-based) bank"),
    ("ADCB.AD", "Abu Dhabi Commercial Bank", "Banking", "excluded",
     "Conventional (interest-based) bank"),
    ("RAKBANK.AD", "RAKBANK", "Banking", "excluded",
     "Conventional (interest-based) bank"),
    ("ADNIC.AD", "Abu Dhabi National Insurance", "Insurance", "excluded",
     "Conventional insurance"),
    ("ADNH.AD", "Abu Dhabi National Hotels", "Hospitality", "excluded",
     "Hotels with material alcohol revenue"),
]

_DFM = [
    # Islamic financials
    ("DIB.AE", "Dubai Islamic Bank", "Islamic Banking", "islamic_fin"),
    ("AJMANBANK.AE", "Ajman Bank", "Islamic Banking", "islamic_fin"),
    ("AMLAK.AE", "Amlak Finance", "Islamic Finance", "islamic_fin"),
    ("GFH.AE", "GFH Financial Group", "Islamic Finance", "islamic_fin"),
    # Utilities & infrastructure
    ("DEWA.AE", "Dubai Electricity & Water Authority", "Utilities", "ok"),
    ("EMPOWER.AE", "Emirates Central Cooling (Empower)", "Utilities", "ok"),
    ("TABREED.AE", "National Central Cooling (Tabreed)", "Utilities", "ok"),
    ("SALIK.AE", "Salik", "Infrastructure", "ok"),
    ("PARKIN.AE", "Parkin", "Infrastructure", "ok"),
    # Real estate
    ("EMAAR.AE", "Emaar Properties", "Real Estate", "ok",
     "Hospitality arm: verify non-compliant income stays under 5%"),
    ("EMAARDEV.AE", "Emaar Development", "Real Estate", "ok"),
    ("DEYAAR.AE", "Deyaar Development", "Real Estate", "ok"),
    ("UPP.AE", "Union Properties", "Real Estate", "ok"),
    ("TECOM.AE", "TECOM Group", "Real Estate", "ok"),
    # Transport, telecom, exchange
    ("AIRARABIA.AE", "Air Arabia", "Transport", "ok"),
    ("ARMX.AE", "Aramex", "Transport", "ok"),
    ("DTC.AE", "Dubai Taxi Company", "Transport", "ok"),
    ("DU.AE", "Emirates Integrated Telecom (du)", "Telecom", "ok"),
    ("DFM.AE", "Dubai Financial Market", "Capital Markets", "ok"),
    # Consumer, education, healthcare
    ("TAALEEM.AE", "Taaleem Holdings", "Education", "ok"),
    ("AMANAT.AE", "Amanat Holdings", "Healthcare & Education", "ok"),
    ("SPINNEYS.AE", "Spinneys 1961", "Consumer Staples", "review",
     "Supermarkets; confirm share of prohibited goods sold"),
    # Diversified / mixed
    ("DIC.AE", "Dubai Investments", "Diversified", "review",
     "Diversified holding with financial investments"),
    ("ALANSARI.AE", "Al Ansari Financial Services", "Financial Services", "review",
     "Exchange house; review interest-bearing activities"),
    # Excluded
    ("EMIRATESNBD.AE", "Emirates NBD", "Banking", "excluded",
     "Conventional (interest-based) bank"),
    ("MASQ.AE", "Mashreq Bank", "Banking", "excluded",
     "Conventional (interest-based) bank"),
    ("CBD.AE", "Commercial Bank of Dubai", "Banking", "excluded",
     "Conventional (interest-based) bank"),
    ("SHUAA.AE", "SHUAA Capital", "Financial Services", "excluded",
     "Conventional investment bank"),
]


def _build(rows, exchange):
    out = []
    for row in rows:
        symbol, name, sector, activity, *rest = row
        out.append(Company(symbol, name, exchange, sector, activity, rest[0] if rest else ""))
    return out


UNIVERSE: list[Company] = _build(_ADX, "ADX") + _build(_DFM, "DFM")
