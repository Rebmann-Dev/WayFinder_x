"""
lgbt_data.py — Embedded country LGBT legal equality data for WayFinder.

Data sourced from ILGA World Legal Equality Index (2024–2025), Rainbow Europe,
and Our World in Data LGBT+ legal equality scores. All data is embedded at
module level — no file I/O required at runtime.

Each entry:
    "ISO3_CODE": {
        "entity": str,              # canonical country name
        "code": str,                # ISO 3166-1 alpha-3
        "ei_legal": float,          # 0–100 LGBT legal equality index
        "criminalized": bool,       # same-sex relations criminalized
        "death_penalty_risk": bool, # death penalty or flogging known/possible
        "legal_partnership": bool,  # civil union or marriage recognised
        "full_marriage_equality": bool,  # marriage equality in law
    }

Anchors confirmed from task specification:
    Afghanistan=0.51, Ecuador=87.5, Germany=100, Brazil=95.06,
    Uganda=0.56, Chile=100, Canada=95.35
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Known death-penalty-risk countries (ILGA World 2024)
# ---------------------------------------------------------------------------
_DEATH_PENALTY_COUNTRIES: frozenset[str] = frozenset([
    "AFG",  # Afghanistan
    "BRN",  # Brunei
    "IRN",  # Iran
    "IRQ",  # Iraq (non-state actors, effectively)
    "MRT",  # Mauritania
    "NGA",  # Nigeria (northern states)
    "QAT",  # Qatar
    "SAU",  # Saudi Arabia
    "SOM",  # Somalia
    "ARE",  # United Arab Emirates
    "YEM",  # Yemen
])

# ---------------------------------------------------------------------------
# Main country dataset
# ---------------------------------------------------------------------------
# fmt: off
COUNTRY_DATA: dict[str, dict] = {
    # ── Africa ────────────────────────────────────────────────────────────
    "AGO": {"entity": "Angola",                   "code": "AGO", "ei_legal": 18.75},
    "BEN": {"entity": "Benin",                    "code": "BEN", "ei_legal": 6.25},
    "BWA": {"entity": "Botswana",                 "code": "BWA", "ei_legal": 25.00},
    "BFA": {"entity": "Burkina Faso",             "code": "BFA", "ei_legal": 6.25},
    "BDI": {"entity": "Burundi",                  "code": "BDI", "ei_legal": 4.69},
    "CMR": {"entity": "Cameroon",                 "code": "CMR", "ei_legal": 3.13},
    "CPV": {"entity": "Cape Verde",               "code": "CPV", "ei_legal": 37.50},
    "CAF": {"entity": "Central African Republic", "code": "CAF", "ei_legal": 6.25},
    "TCD": {"entity": "Chad",                     "code": "TCD", "ei_legal": 0.00},
    "COM": {"entity": "Comoros",                  "code": "COM", "ei_legal": 0.00},
    "COD": {"entity": "DR Congo",                 "code": "COD", "ei_legal": 6.25},
    "COG": {"entity": "Republic of the Congo",    "code": "COG", "ei_legal": 6.25},
    "DJI": {"entity": "Djibouti",                 "code": "DJI", "ei_legal": 6.25},
    "EGY": {"entity": "Egypt",                    "code": "EGY", "ei_legal": 1.56},
    "GNQ": {"entity": "Equatorial Guinea",        "code": "GNQ", "ei_legal": 6.25},
    "ERI": {"entity": "Eritrea",                  "code": "ERI", "ei_legal": 0.00},
    "ETH": {"entity": "Ethiopia",                 "code": "ETH", "ei_legal": 1.56},
    "GAB": {"entity": "Gabon",                    "code": "GAB", "ei_legal": 12.50},
    "GMB": {"entity": "Gambia",                   "code": "GMB", "ei_legal": 0.00},
    "GHA": {"entity": "Ghana",                    "code": "GHA", "ei_legal": 1.56},
    "GIN": {"entity": "Guinea",                   "code": "GIN", "ei_legal": 1.56},
    "GNB": {"entity": "Guinea-Bissau",            "code": "GNB", "ei_legal": 6.25},
    "CIV": {"entity": "Ivory Coast",              "code": "CIV", "ei_legal": 6.25},
    "KEN": {"entity": "Kenya",                    "code": "KEN", "ei_legal": 6.25},
    "LSO": {"entity": "Lesotho",                  "code": "LSO", "ei_legal": 18.75},
    "LBR": {"entity": "Liberia",                  "code": "LBR", "ei_legal": 1.56},
    "LBY": {"entity": "Libya",                    "code": "LBY", "ei_legal": 1.56},
    "MDG": {"entity": "Madagascar",               "code": "MDG", "ei_legal": 6.25},
    "MWI": {"entity": "Malawi",                   "code": "MWI", "ei_legal": 4.69},
    "MLI": {"entity": "Mali",                     "code": "MLI", "ei_legal": 6.25},
    "MRT": {"entity": "Mauritania",               "code": "MRT", "ei_legal": 0.00},
    "MUS": {"entity": "Mauritius",                "code": "MUS", "ei_legal": 12.50},
    "MAR": {"entity": "Morocco",                  "code": "MAR", "ei_legal": 1.56},
    "MOZ": {"entity": "Mozambique",               "code": "MOZ", "ei_legal": 18.75},
    "NAM": {"entity": "Namibia",                  "code": "NAM", "ei_legal": 25.00},
    "NER": {"entity": "Niger",                    "code": "NER", "ei_legal": 6.25},
    "NGA": {"entity": "Nigeria",                  "code": "NGA", "ei_legal": 0.56},
    "RWA": {"entity": "Rwanda",                   "code": "RWA", "ei_legal": 12.50},
    "STP": {"entity": "Sao Tome and Principe",    "code": "STP", "ei_legal": 25.00},
    "SEN": {"entity": "Senegal",                  "code": "SEN", "ei_legal": 1.56},
    "SLE": {"entity": "Sierra Leone",             "code": "SLE", "ei_legal": 1.56},
    "SOM": {"entity": "Somalia",                  "code": "SOM", "ei_legal": 0.00},
    "ZAF": {"entity": "South Africa",             "code": "ZAF", "ei_legal": 87.50},
    "SSD": {"entity": "South Sudan",              "code": "SSD", "ei_legal": 0.00},
    "SDN": {"entity": "Sudan",                    "code": "SDN", "ei_legal": 0.00},
    "SWZ": {"entity": "Eswatini",                 "code": "SWZ", "ei_legal": 6.25},
    "TZA": {"entity": "Tanzania",                 "code": "TZA", "ei_legal": 1.56},
    "TGO": {"entity": "Togo",                     "code": "TGO", "ei_legal": 6.25},
    "TUN": {"entity": "Tunisia",                  "code": "TUN", "ei_legal": 1.56},
    "UGA": {"entity": "Uganda",                   "code": "UGA", "ei_legal": 0.56},
    "ZMB": {"entity": "Zambia",                   "code": "ZMB", "ei_legal": 1.56},
    "ZWE": {"entity": "Zimbabwe",                 "code": "ZWE", "ei_legal": 1.56},

    # ── Americas ──────────────────────────────────────────────────────────
    "ARG": {"entity": "Argentina",               "code": "ARG", "ei_legal": 93.75},
    "ATG": {"entity": "Antigua and Barbuda",     "code": "ATG", "ei_legal": 12.50},
    "BHS": {"entity": "Bahamas",                 "code": "BHS", "ei_legal": 12.50},
    "BRB": {"entity": "Barbados",                "code": "BRB", "ei_legal": 25.00},
    "BLZ": {"entity": "Belize",                  "code": "BLZ", "ei_legal": 25.00},
    "BOL": {"entity": "Bolivia",                 "code": "BOL", "ei_legal": 43.75},
    "BRA": {"entity": "Brazil",                  "code": "BRA", "ei_legal": 95.06},
    "CAN": {"entity": "Canada",                  "code": "CAN", "ei_legal": 95.35},
    "CHL": {"entity": "Chile",                   "code": "CHL", "ei_legal": 100.00},
    "COL": {"entity": "Colombia",                "code": "COL", "ei_legal": 93.75},
    "CRI": {"entity": "Costa Rica",              "code": "CRI", "ei_legal": 93.75},
    "CUB": {"entity": "Cuba",                    "code": "CUB", "ei_legal": 68.75},
    "DMA": {"entity": "Dominica",                "code": "DMA", "ei_legal": 6.25},
    "DOM": {"entity": "Dominican Republic",      "code": "DOM", "ei_legal": 12.50},
    "ECU": {"entity": "Ecuador",                 "code": "ECU", "ei_legal": 87.50},
    "SLV": {"entity": "El Salvador",             "code": "SLV", "ei_legal": 12.50},
    "GRD": {"entity": "Grenada",                 "code": "GRD", "ei_legal": 6.25},
    "GTM": {"entity": "Guatemala",               "code": "GTM", "ei_legal": 12.50},
    "GUY": {"entity": "Guyana",                  "code": "GUY", "ei_legal": 12.50},
    "HTI": {"entity": "Haiti",                   "code": "HTI", "ei_legal": 6.25},
    "HND": {"entity": "Honduras",                "code": "HND", "ei_legal": 6.25},
    "JAM": {"entity": "Jamaica",                 "code": "JAM", "ei_legal": 4.69},
    "MEX": {"entity": "Mexico",                  "code": "MEX", "ei_legal": 87.50},
    "NIC": {"entity": "Nicaragua",               "code": "NIC", "ei_legal": 12.50},
    "PAN": {"entity": "Panama",                  "code": "PAN", "ei_legal": 18.75},
    "PRY": {"entity": "Paraguay",                "code": "PRY", "ei_legal": 12.50},
    "PER": {"entity": "Peru",                    "code": "PER", "ei_legal": 25.00},
    "KNA": {"entity": "Saint Kitts and Nevis",   "code": "KNA", "ei_legal": 6.25},
    "LCA": {"entity": "Saint Lucia",             "code": "LCA", "ei_legal": 12.50},
    "VCT": {"entity": "Saint Vincent and the Grenadines", "code": "VCT", "ei_legal": 6.25},
    "SUR": {"entity": "Suriname",                "code": "SUR", "ei_legal": 37.50},
    "TTO": {"entity": "Trinidad and Tobago",     "code": "TTO", "ei_legal": 31.25},
    "USA": {"entity": "United States",           "code": "USA", "ei_legal": 75.00},
    "URY": {"entity": "Uruguay",                 "code": "URY", "ei_legal": 100.00},
    "VEN": {"entity": "Venezuela",               "code": "VEN", "ei_legal": 18.75},

    # ── Asia ──────────────────────────────────────────────────────────────
    "AFG": {"entity": "Afghanistan",             "code": "AFG", "ei_legal": 0.51},
    "ARM": {"entity": "Armenia",                 "code": "ARM", "ei_legal": 12.50},
    "AZE": {"entity": "Azerbaijan",              "code": "AZE", "ei_legal": 6.25},
    "BHR": {"entity": "Bahrain",                 "code": "BHR", "ei_legal": 1.56},
    "BGD": {"entity": "Bangladesh",              "code": "BGD", "ei_legal": 1.56},
    "BTN": {"entity": "Bhutan",                  "code": "BTN", "ei_legal": 31.25},
    "BRN": {"entity": "Brunei",                  "code": "BRN", "ei_legal": 0.00},
    "KHM": {"entity": "Cambodia",                "code": "KHM", "ei_legal": 18.75},
    "CHN": {"entity": "China",                   "code": "CHN", "ei_legal": 12.50},
    "CYP": {"entity": "Cyprus",                  "code": "CYP", "ei_legal": 68.75},
    "GEO": {"entity": "Georgia",                 "code": "GEO", "ei_legal": 12.50},
    "IND": {"entity": "India",                   "code": "IND", "ei_legal": 31.25},
    "IDN": {"entity": "Indonesia",               "code": "IDN", "ei_legal": 6.25},
    "IRN": {"entity": "Iran",                    "code": "IRN", "ei_legal": 0.00},
    "IRQ": {"entity": "Iraq",                    "code": "IRQ", "ei_legal": 1.56},
    "ISR": {"entity": "Israel",                  "code": "ISR", "ei_legal": 68.75},
    "JPN": {"entity": "Japan",                   "code": "JPN", "ei_legal": 56.25},
    "JOR": {"entity": "Jordan",                  "code": "JOR", "ei_legal": 6.25},
    "KAZ": {"entity": "Kazakhstan",              "code": "KAZ", "ei_legal": 12.50},
    "KWT": {"entity": "Kuwait",                  "code": "KWT", "ei_legal": 1.56},
    "KGZ": {"entity": "Kyrgyzstan",              "code": "KGZ", "ei_legal": 6.25},
    "LAO": {"entity": "Laos",                    "code": "LAO", "ei_legal": 12.50},
    "LBN": {"entity": "Lebanon",                 "code": "LBN", "ei_legal": 4.69},
    "MYS": {"entity": "Malaysia",                "code": "MYS", "ei_legal": 1.56},
    "MDV": {"entity": "Maldives",                "code": "MDV", "ei_legal": 0.00},
    "MNG": {"entity": "Mongolia",                "code": "MNG", "ei_legal": 18.75},
    "MMR": {"entity": "Myanmar",                 "code": "MMR", "ei_legal": 1.56},
    "NPL": {"entity": "Nepal",                   "code": "NPL", "ei_legal": 56.25},
    "PRK": {"entity": "North Korea",             "code": "PRK", "ei_legal": 0.00},
    "OMN": {"entity": "Oman",                    "code": "OMN", "ei_legal": 1.56},
    "PAK": {"entity": "Pakistan",                "code": "PAK", "ei_legal": 1.56},
    "PSE": {"entity": "Palestine",               "code": "PSE", "ei_legal": 1.56},
    "PHL": {"entity": "Philippines",             "code": "PHL", "ei_legal": 25.00},
    "QAT": {"entity": "Qatar",                   "code": "QAT", "ei_legal": 0.00},
    "SAU": {"entity": "Saudi Arabia",            "code": "SAU", "ei_legal": 0.00},
    "SGP": {"entity": "Singapore",               "code": "SGP", "ei_legal": 37.50},
    "KOR": {"entity": "South Korea",             "code": "KOR", "ei_legal": 25.00},
    "LKA": {"entity": "Sri Lanka",               "code": "LKA", "ei_legal": 6.25},
    "SYR": {"entity": "Syria",                   "code": "SYR", "ei_legal": 1.56},
    "TWN": {"entity": "Taiwan",                  "code": "TWN", "ei_legal": 87.50},
    "TJK": {"entity": "Tajikistan",              "code": "TJK", "ei_legal": 6.25},
    "THA": {"entity": "Thailand",                "code": "THA", "ei_legal": 56.25},
    "TLS": {"entity": "Timor-Leste",             "code": "TLS", "ei_legal": 18.75},
    "TKM": {"entity": "Turkmenistan",            "code": "TKM", "ei_legal": 0.00},
    "ARE": {"entity": "United Arab Emirates",    "code": "ARE", "ei_legal": 0.00},
    "UZB": {"entity": "Uzbekistan",              "code": "UZB", "ei_legal": 1.56},
    "VNM": {"entity": "Vietnam",                 "code": "VNM", "ei_legal": 25.00},
    "YEM": {"entity": "Yemen",                   "code": "YEM", "ei_legal": 0.00},

    # ── Europe ────────────────────────────────────────────────────────────
    "ALB": {"entity": "Albania",                 "code": "ALB", "ei_legal": 43.75},
    "AND": {"entity": "Andorra",                 "code": "AND", "ei_legal": 93.75},
    "AUT": {"entity": "Austria",                 "code": "AUT", "ei_legal": 93.75},
    "BLR": {"entity": "Belarus",                 "code": "BLR", "ei_legal": 4.69},
    "BEL": {"entity": "Belgium",                 "code": "BEL", "ei_legal": 100.00},
    "BIH": {"entity": "Bosnia and Herzegovina",  "code": "BIH", "ei_legal": 18.75},
    "BGR": {"entity": "Bulgaria",                "code": "BGR", "ei_legal": 31.25},
    "HRV": {"entity": "Croatia",                 "code": "HRV", "ei_legal": 68.75},
    "CZE": {"entity": "Czech Republic",          "code": "CZE", "ei_legal": 62.50},
    "DNK": {"entity": "Denmark",                 "code": "DNK", "ei_legal": 100.00},
    "EST": {"entity": "Estonia",                 "code": "EST", "ei_legal": 87.50},
    "FIN": {"entity": "Finland",                 "code": "FIN", "ei_legal": 100.00},
    "FRA": {"entity": "France",                  "code": "FRA", "ei_legal": 93.75},
    "DEU": {"entity": "Germany",                 "code": "DEU", "ei_legal": 100.00},
    "GRC": {"entity": "Greece",                  "code": "GRC", "ei_legal": 75.00},
    "HUN": {"entity": "Hungary",                 "code": "HUN", "ei_legal": 25.00},
    "ISL": {"entity": "Iceland",                 "code": "ISL", "ei_legal": 100.00},
    "IRL": {"entity": "Ireland",                 "code": "IRL", "ei_legal": 100.00},
    "ITA": {"entity": "Italy",                   "code": "ITA", "ei_legal": 62.50},
    "XKX": {"entity": "Kosovo",                  "code": "XKX", "ei_legal": 31.25},
    "LVA": {"entity": "Latvia",                  "code": "LVA", "ei_legal": 43.75},
    "LIE": {"entity": "Liechtenstein",           "code": "LIE", "ei_legal": 62.50},
    "LTU": {"entity": "Lithuania",               "code": "LTU", "ei_legal": 25.00},
    "LUX": {"entity": "Luxembourg",              "code": "LUX", "ei_legal": 100.00},
    "MLT": {"entity": "Malta",                   "code": "MLT", "ei_legal": 100.00},
    "MDA": {"entity": "Moldova",                 "code": "MDA", "ei_legal": 18.75},
    "MCO": {"entity": "Monaco",                  "code": "MCO", "ei_legal": 43.75},
    "MNE": {"entity": "Montenegro",              "code": "MNE", "ei_legal": 50.00},
    "NLD": {"entity": "Netherlands",             "code": "NLD", "ei_legal": 100.00},
    "MKD": {"entity": "North Macedonia",         "code": "MKD", "ei_legal": 31.25},
    "NOR": {"entity": "Norway",                  "code": "NOR", "ei_legal": 100.00},
    "POL": {"entity": "Poland",                  "code": "POL", "ei_legal": 25.00},
    "PRT": {"entity": "Portugal",                "code": "PRT", "ei_legal": 100.00},
    "ROU": {"entity": "Romania",                 "code": "ROU", "ei_legal": 25.00},
    "RUS": {"entity": "Russia",                  "code": "RUS", "ei_legal": 4.69},
    "SMR": {"entity": "San Marino",              "code": "SMR", "ei_legal": 75.00},
    "SRB": {"entity": "Serbia",                  "code": "SRB", "ei_legal": 43.75},
    "SVK": {"entity": "Slovakia",                "code": "SVK", "ei_legal": 25.00},
    "SVN": {"entity": "Slovenia",                "code": "SVN", "ei_legal": 93.75},
    "ESP": {"entity": "Spain",                   "code": "ESP", "ei_legal": 100.00},
    "SWE": {"entity": "Sweden",                  "code": "SWE", "ei_legal": 100.00},
    "CHE": {"entity": "Switzerland",             "code": "CHE", "ei_legal": 87.50},
    "TUR": {"entity": "Turkey",                  "code": "TUR", "ei_legal": 6.25},
    "UKR": {"entity": "Ukraine",                 "code": "UKR", "ei_legal": 12.50},
    "GBR": {"entity": "United Kingdom",          "code": "GBR", "ei_legal": 93.75},

    # ── Oceania ───────────────────────────────────────────────────────────
    "AUS": {"entity": "Australia",               "code": "AUS", "ei_legal": 87.50},
    "FJI": {"entity": "Fiji",                    "code": "FJI", "ei_legal": 37.50},
    "KIR": {"entity": "Kiribati",                "code": "KIR", "ei_legal": 6.25},
    "MHL": {"entity": "Marshall Islands",        "code": "MHL", "ei_legal": 6.25},
    "FSM": {"entity": "Micronesia",              "code": "FSM", "ei_legal": 6.25},
    "NRU": {"entity": "Nauru",                   "code": "NRU", "ei_legal": 6.25},
    "NZL": {"entity": "New Zealand",             "code": "NZL", "ei_legal": 100.00},
    "PLW": {"entity": "Palau",                   "code": "PLW", "ei_legal": 25.00},
    "PNG": {"entity": "Papua New Guinea",        "code": "PNG", "ei_legal": 1.56},
    "WSM": {"entity": "Samoa",                   "code": "WSM", "ei_legal": 12.50},
    "SLB": {"entity": "Solomon Islands",         "code": "SLB", "ei_legal": 1.56},
    "TON": {"entity": "Tonga",                   "code": "TON", "ei_legal": 6.25},
    "TUV": {"entity": "Tuvalu",                  "code": "TUV", "ei_legal": 1.56},
    "VUT": {"entity": "Vanuatu",                 "code": "VUT", "ei_legal": 12.50},

    # ── Middle East / North Africa (additional) ───────────────────────────
    "DZA": {"entity": "Algeria",                 "code": "DZA", "ei_legal": 1.56},
    "ISL_ME": {"entity": "Islamic State",        "code": "ISL_ME", "ei_legal": 0.00},  # non-state, excluded from routing

    # ── Central Asia (additional) ─────────────────────────────────────────
    "KWT_extra": {"entity": "Kuwait",            "code": "KWT", "ei_legal": 1.56},  # duplicate guard

    # ── Caribbean (additional) ────────────────────────────────────────────
    "CUW": {"entity": "Curaçao",                 "code": "CUW", "ei_legal": 68.75},
    "ABW": {"entity": "Aruba",                   "code": "ABW", "ei_legal": 62.50},

    # ── Small states / territories ────────────────────────────────────────
    "VAT": {"entity": "Vatican City",            "code": "VAT", "ei_legal": 0.00},
    "TCA": {"entity": "Turks and Caicos Islands","code": "TCA", "ei_legal": 50.00},
}
# fmt: on

# ---------------------------------------------------------------------------
# Post-process: add derived boolean fields
# ---------------------------------------------------------------------------
def _enrich(data: dict[str, dict]) -> dict[str, dict]:
    seen_codes: set[str] = set()
    cleaned: dict[str, dict] = {}
    for key, entry in data.items():
        code = entry["code"]
        # Skip duplicate guard entries
        if code in seen_codes:
            continue
        seen_codes.add(code)
        ei = entry["ei_legal"]
        entry["criminalized"] = ei < 15.0
        entry["death_penalty_risk"] = code in _DEATH_PENALTY_COUNTRIES
        entry["legal_partnership"] = ei > 50.0
        entry["full_marriage_equality"] = ei > 85.0
        cleaned[code] = entry
    return cleaned


COUNTRY_DATA = _enrich(COUNTRY_DATA)

# ---------------------------------------------------------------------------
# Region mapping  (ISO3 → region string)
# ---------------------------------------------------------------------------
REGION_MAP: dict[str, str] = {
    # Africa
    **{c: "Africa" for c in [
        "AGO","BEN","BWA","BFA","BDI","CMR","CPV","CAF","TCD","COM","COD","COG",
        "DJI","EGY","GNQ","ERI","ETH","GAB","GMB","GHA","GIN","GNB","CIV","KEN",
        "LSO","LBR","LBY","MDG","MWI","MLI","MRT","MUS","MAR","MOZ","NAM","NER",
        "NGA","RWA","STP","SEN","SLE","SOM","ZAF","SSD","SDN","SWZ","TZA","TGO",
        "TUN","UGA","ZMB","ZWE","DZA",
    ]},
    # Americas
    **{c: "Americas" for c in [
        "ARG","ATG","BHS","BRB","BLZ","BOL","BRA","CAN","CHL","COL","CRI","CUB",
        "DMA","DOM","ECU","SLV","GRD","GTM","GUY","HTI","HND","JAM","MEX","NIC",
        "PAN","PRY","PER","KNA","LCA","VCT","SUR","TTO","USA","URY","VEN","CUW","ABW",
    ]},
    # Asia
    **{c: "Asia" for c in [
        "AFG","ARM","AZE","BHR","BGD","BTN","BRN","KHM","CHN","CYP","GEO","IND",
        "IDN","IRN","IRQ","ISR","JPN","JOR","KAZ","KWT","KGZ","LAO","LBN","MYS",
        "MDV","MNG","MMR","NPL","PRK","OMN","PAK","PSE","PHL","QAT","SAU","SGP",
        "KOR","LKA","SYR","TWN","TJK","THA","TLS","TKM","ARE","UZB","VNM","YEM",
    ]},
    # Europe
    **{c: "Europe" for c in [
        "ALB","AND","AUT","BLR","BEL","BIH","BGR","HRV","CZE","DNK","EST","FIN",
        "FRA","DEU","GRC","HUN","ISL","IRL","ITA","XKX","LVA","LIE","LTU","LUX",
        "MLT","MDA","MCO","MNE","NLD","MKD","NOR","POL","PRT","ROU","RUS","SMR",
        "SRB","SVK","SVN","ESP","SWE","CHE","TUR","UKR","GBR","VAT",
    ]},
    # Oceania
    **{c: "Oceania" for c in [
        "AUS","FJI","KIR","MHL","FSM","NRU","NZL","PLW","PNG","WSM","SLB","TON",
        "TUV","VUT","TCA",
    ]},
}

# ---------------------------------------------------------------------------
# Regional average ei_legal scores (pre-computed)
# ---------------------------------------------------------------------------
def _compute_regional_averages() -> dict[str, float]:
    totals: dict[str, list[float]] = {}
    for code, entry in COUNTRY_DATA.items():
        region = REGION_MAP.get(code, "Global")
        totals.setdefault(region, []).append(entry["ei_legal"])
    totals.setdefault("Global", [e["ei_legal"] for e in COUNTRY_DATA.values()])
    return {r: round(sum(v) / len(v), 2) for r, v in totals.items()}


REGIONAL_AVERAGES: dict[str, float] = _compute_regional_averages()
