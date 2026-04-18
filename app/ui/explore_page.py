"""Explore page -- tabbed layout with map, hikes, wildlife, food, history + data sections."""

import datetime
import json
import logging
from pathlib import Path
from ui.safety_display import render_safety_panel
import streamlit as st

log = logging.getLogger("wayfinder.explore")

_COUNTRIES_DIR = Path(__file__).resolve().parent.parent / "data" / "countries"

_CONTINENT_FOLDERS = [
    "south_america",
    "central_america",
    "north_america",
    "europe",
    "asia",
    "africa",
    "oceania",
    "southeast_asia",
]

# ── Static lookup tables ──────────────────────────────────────────────────────

_COUNTRY_CODE_MAP: dict[str, str] = {
    "Ecuador":   "EC", "Peru":      "PE", "Argentina": "AR",
    "Bolivia":   "BO", "Brazil":    "BR", "Chile":     "CL",
    "Colombia":  "CO", "Guyana":    "GY", "Paraguay":  "PY",
    "Suriname":  "SR", "Uruguay":   "UY", "Venezuela": "VE",
    "Costa Rica":    "CR", "Panama":        "PA", "Guatemala":  "GT",
    "Belize":        "BZ", "Honduras":      "HN", "Nicaragua":  "NI",
    "El Salvador":   "SV",
    "Mexico":    "MX", "United States": "US", "Canada": "CA",
}

_FLAGS: dict[str, str] = {
    "EC": "🇪🇨", "PE": "🇵🇪", "AR": "🇦🇷", "BO": "🇧🇴",
    "BR": "🇧🇷", "CL": "🇨🇱", "CO": "🇨🇴", "GY": "🇬🇾",
    "PY": "🇵🇾", "SR": "🇸🇷", "UY": "🇺🇾", "VE": "🇻🇪",
    "CR": "🇨🇷", "PA": "🇵🇦", "GT": "🇬🇹", "BZ": "🇧🇿",
    "HN": "🇭🇳", "NI": "🇳🇮", "SV": "🇸🇻",
    "MX": "🇲🇽", "US": "🇺🇸", "CA": "🇨🇦",
}

_COUNTRY_CENTROIDS: dict[str, tuple[float, float]] = {
    "EC": (-1.8, -78.2),  "PE": (-9.2, -75.0),  "AR": (-38.4, -63.6),
    "BO": (-16.3, -63.6), "BR": (-14.2, -51.9),  "CL": (-35.7, -71.5),
    "CO": (4.6, -74.3),   "GY": (4.9, -58.9),    "PY": (-23.4, -58.4),
    "SR": (3.9, -56.0),   "UY": (-32.5, -55.8),  "VE": (8.0, -66.6),
    "CR": (9.7, -83.8),   "PA": (8.5, -80.8),    "GT": (15.8, -90.2),
    "BZ": (17.2, -88.5),  "HN": (15.2, -86.2),   "NI": (12.9, -85.2),
    "SV": (13.8, -88.9),
    "MX": (23.6, -102.6), "US": (37.1, -95.7),   "CA": (56.1, -106.3),
}

country_centers: dict[str, tuple[list[float], int]] = {
    "Ecuador":   ([-1.5, -78.0],  7),  "Peru":      ([-9.2, -75.0],  6),
    "Argentina": ([-38.4, -63.6], 5),  "Bolivia":   ([-16.3, -63.6], 6),
    "Brazil":    ([-14.2, -51.9], 5),  "Chile":     ([-35.7, -71.5], 5),
    "Colombia":  ([4.6, -74.3],   6),  "Guyana":    ([4.9, -58.9],   7),
    "Paraguay":  ([-23.4, -58.4], 6),  "Suriname":  ([3.9, -56.0],   7),
    "Uruguay":   ([-32.5, -55.8], 7),  "Venezuela": ([8.0, -66.6],   6),
    "Costa Rica":  ([9.7, -83.8],  8), "Panama":    ([8.5, -80.8],   8),
    "Guatemala":   ([15.8, -90.2], 7), "Belize":    ([17.2, -88.5],  8),
    "Honduras":    ([15.2, -86.2], 7), "Nicaragua": ([12.9, -85.2],  7),
    "El Salvador": ([13.8, -88.9], 8),
}

@st.cache_data(ttl=600)
def _discover_countries() -> dict:
    """
    Scan all continent folders and build a registry from JSON identity fields.
    Returns dict keyed by display name (e.g. 'Costa Rica') with:
        {
            'file_stem': 'costarica',
            'continent': 'central_america',
            'flag': '🇨🇷',
            'centroid': (9.7489, -83.7534),
            'iso2': 'CR',
        }
    """
    registry = {}
    for continent in _CONTINENT_FOLDERS:
        folder = _COUNTRIES_DIR / continent
        if not folder.is_dir():
            continue
        for json_file in sorted(folder.glob("*.json")):
            if json_file.stem.startswith("."):
                continue
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            identity = data.get("identity", {})
            name = identity.get("name")
            if not name:
                continue
            # centroid: prefer identity fields, fall back to None
            lat = identity.get("latitude") or identity.get("lat")
            lon = identity.get("longitude") or identity.get("lon")
            registry[name] = {
                "file_stem": json_file.stem,
                "continent": continent,
                "flag": identity.get("flag_emoji", ""),
                "centroid": (float(lat), float(lon)) if lat and lon else None,
                "iso2": (identity.get("code") or "").upper(),
            }
    return registry
# ── Derived lookups (built from registry at import time) ─────────────────────
_COUNTRY_CENTER_FALLBACKS = {
    "Mexico":      (23.634, -102.553, 5),
    "Belize":      (17.189, -88.497,  7),
    "Costa Rica":  (9.748,  -83.753,  7),
    "El Salvador": (13.794, -88.896,  8),
    "Guatemala":   (15.783, -90.230,  7),
    "Honduras":    (15.200, -86.242,  7),
    "Nicaragua":   (12.865, -85.207,  7),
    "Panama":      (8.538,  -80.782,  7),
}

def _build_derived_maps():
    registry = _discover_countries()
    country_centers = {}
    centroids = {}
    code_map = {}
    for name, entry in registry.items():
        c = entry.get("centroid")
        iso2 = entry.get("iso2", "")
        if c:
            country_centers[name] = (list(c), 6)
            centroids[iso2] = c
        elif name in _COUNTRY_CENTER_FALLBACKS:
            lat, lon, zoom = _COUNTRY_CENTER_FALLBACKS[name]
            country_centers[name] = ([lat, lon], zoom)
            centroids[iso2] = (lat, lon)
        if iso2:
            code_map[iso2] = name
    return country_centers, centroids, code_map

country_centers, _COUNTRY_CENTROIDS, _COUNTRY_CODE_MAP = _build_derived_maps()

# City → country mapping for auto-detection from destination_city
_CITY_COUNTRY_MAP = {
    "quito": "Ecuador", "guayaquil": "Ecuador", "cuenca": "Ecuador", "manta": "Ecuador", "esmeraldas": "Ecuador",
    "lima": "Peru", "cusco": "Peru", "arequipa": "Peru", "trujillo": "Peru", "iquitos": "Peru", "mancora": "Peru",
    "buenos aires": "Argentina", "mendoza": "Argentina", "córdoba": "Argentina", "cordoba": "Argentina",
    "bariloche": "Argentina", "ushuaia": "Argentina", "el calafate": "Argentina", "salta": "Argentina",
    "la paz": "Bolivia", "sucre": "Bolivia", "cochabamba": "Bolivia", "santa cruz": "Bolivia", "uyuni": "Bolivia",
    "rio de janeiro": "Brazil", "são paulo": "Brazil", "sao paulo": "Brazil", "brasília": "Brazil",
    "brasilia": "Brazil", "salvador": "Brazil", "fortaleza": "Brazil", "recife": "Brazil",
    "santiago": "Chile", "valparaíso": "Chile", "valparaiso": "Chile", "punta arenas": "Chile",
    "puerto natales": "Chile", "san pedro de atacama": "Chile", "pichilemu": "Chile",
    "bogotá": "Colombia", "bogota": "Colombia", "medellín": "Colombia", "medellin": "Colombia",
    "cartagena": "Colombia", "cali": "Colombia", "santa marta": "Colombia",
    "georgetown": "Guyana",
    "asunción": "Paraguay", "asuncion": "Paraguay", "ciudad del este": "Paraguay",
    "paramaribo": "Suriname",
    "montevideo": "Uruguay", "punta del este": "Uruguay", "colonia del sacramento": "Uruguay",
    "caracas": "Venezuela", "mérida": "Venezuela", "merida": "Venezuela", "maracaibo": "Venezuela",
        # Costa Rica
    "san josé": "Costa Rica", "san jose": "Costa Rica", "la fortuna": "Costa Rica",
    "tamarindo": "Costa Rica", "manuel antonio": "Costa Rica", "monteverde": "Costa Rica",
    "jacó": "Costa Rica", "jaco": "Costa Rica", "puerto viejo": "Costa Rica",
    # Panama
    "panama city": "Panama", "ciudad de panamá": "Panama", "bocas del toro": "Panama",
    "boquete": "Panama", "colón": "Panama", "colon": "Panama",
    # Guatemala
    "guatemala city": "Guatemala", "antigua": "Guatemala", "flores": "Guatemala",
    "quetzaltenango": "Guatemala", "xela": "Guatemala",
    # Belize
    "belize city": "Belize", "san ignacio": "Belize", "placencia": "Belize",
    "ambergris caye": "Belize", "caye caulker": "Belize",
    # Honduras
    "tegucigalpa": "Honduras", "san pedro sula": "Honduras", "roatán": "Honduras",
    "roatan": "Honduras", "copán": "Honduras", "copan": "Honduras",
    # Nicaragua
    "managua": "Nicaragua", "granada": "Nicaragua", "león": "Nicaragua",
    "leon": "Nicaragua", "san juan del sur": "Nicaragua",
    # El Salvador
    "san salvador": "El Salvador", "santa ana": "El Salvador", "suchitoto": "El Salvador",
    "el tunco": "El Salvador",

    # Mexico
    "mexico city": "Mexico", "cdmx": "Mexico", "cancún": "Mexico", "cancun": "Mexico",
    "oaxaca": "Mexico", "guadalajara": "Mexico", "playa del carmen": "Mexico",
    "tulum": "Mexico", "san cristóbal de las casas": "Mexico", "puerto escondido": "Mexico",
    "cabo san lucas": "Mexico", "san miguel de allende": "Mexico", "mérida": "Mexico",
    "monterrey": "Mexico", "puebla": "Mexico", "mazatlán": "Mexico", "mazatlan": "Mexico",
    "puerto vallarta": "Mexico", "palenque": "Mexico", "chihuahua": "Mexico",

    # Costa Rica
    "san josé": "Costa Rica", "san jose": "Costa Rica", "liberia": "Costa Rica",
    "tamarindo": "Costa Rica", "manuel antonio": "Costa Rica", "la fortuna": "Costa Rica",
    "monteverde": "Costa Rica", "jacó": "Costa Rica", "jaco": "Costa Rica",
    "puerto viejo": "Costa Rica", "nosara": "Costa Rica", "santa teresa": "Costa Rica",

    # Guatemala
    "guatemala city": "Guatemala", "antigua": "Guatemala", "flores": "Guatemala",
    "quetzaltenango": "Guatemala", "xela": "Guatemala", "panajachel": "Guatemala",
    "semuc champey": "Guatemala", "lanquín": "Guatemala",

    # Belize
    "belize city": "Belize", "san ignacio": "Belize", "placencia": "Belize",
    "caye caulker": "Belize", "ambergris caye": "Belize", "dangriga": "Belize",

    # Honduras
    "tegucigalpa": "Honduras", "san pedro sula": "Honduras", "roatán": "Honduras",
    "roatan": "Honduras", "copán": "Honduras", "copan": "Honduras", "la ceiba": "Honduras",

    # Nicaragua
    "managua": "Nicaragua", "granada": "Nicaragua", "león": "Nicaragua", "leon": "Nicaragua",
    "san juan del sur": "Nicaragua", "ometepe": "Nicaragua", "matagalpa": "Nicaragua",

    # El Salvador
    "san salvador": "El Salvador", "santa ana": "El Salvador", "el tunco": "El Salvador",
    "suchitoto": "El Salvador", "la libertad": "El Salvador",

    # Panama
    "panama city": "Panama", "bocas del toro": "Panama", "boquete": "Panama",
    "santa catalina": "Panama", "colón": "Panama", "colon": "Panama", "el valle": "Panama",
}


# ── Profile loader ────────────────────────────────────────────────────────────


@st.cache_data(ttl=300)
def _load_profile(country_name: str) -> dict | None:
    """Load and normalize a country profile from JSON.

    Returns a flat dict that all render tabs use, or None if no JSON found.
    """
    data = _load_country_json(country_name)
    if not data:
        return None

    # ── Hikes: combine day hikes + multi-day treks ──────────────────────
    # Fallback: new countries use outdoors.hikes (split by duration_days)
    day_hikes = _get(data, "outdoors.top_day_hikes") or []
    multi_treks = _get(data, "outdoors.multi_day_treks") or []
    if not day_hikes and not multi_treks:
        raw_hikes = _get(data, "outdoors.hikes") or []
        for h in (raw_hikes if isinstance(raw_hikes, list) else []):
            if isinstance(h, dict) and h.get("duration_days", 1) <= 1:
                day_hikes.append(h)
            elif isinstance(h, dict):
                multi_treks.append(h)
    hikes = list(day_hikes if isinstance(day_hikes, list) else []) + \
            list(multi_treks if isinstance(multi_treks, list) else [])

    # ── Food: normalize string and dict formats ─────────────────────────
    def _normalize_food_items(items):
        result = []
        for item in (items if isinstance(items, list) else []):
            if isinstance(item, dict):
                result.append({
                    "name": item.get("name", ""),
                    "emoji": item.get("emoji", ""),
                    "description": item.get("description", ""),
                })
            elif isinstance(item, str):
                if " \u2014 " in item:
                    name, desc = item.split(" \u2014 ", 1)
                    result.append({"name": name.strip(), "emoji": "", "description": desc.strip()})
                elif " -- " in item:
                    name, desc = item.split(" -- ", 1)
                    result.append({"name": name.strip(), "emoji": "", "description": desc.strip()})
                elif " - " in item:
                    name, desc = item.split(" - ", 1)
                    result.append({"name": name.strip(), "emoji": "", "description": desc.strip()})
                else:
                    result.append({"name": item, "emoji": "", "description": ""})
        return result

    # Fallback: new countries use food.dishes
    dishes = _normalize_food_items(
        _get(data, "food.signature_dishes") or _get(data, "food.dishes")
    )
    drinks = _normalize_food_items(_get(data, "food.must_try_drinks"))
    street_food = _get(data, "food.street_food_safety") or ""
    vegetarian = _get(data, "food.vegetarian_friendliness") or ""

    regional_specs = _get(data, "food.regional_specialties") or []
    regional_parts = []
    for r in (regional_specs if isinstance(regional_specs, list) else []):
        if isinstance(r, dict):
            regional_parts.append(
                f"{r.get('region', '')}: {r.get('specialty', r.get('description', ''))}"
            )
        elif isinstance(r, str):
            regional_parts.append(r)
    regional = "; ".join(regional_parts)

    # ── History / Culture ───────────────────────────────────────────────
    culture = _get(data, "culture") or {}
    history = []

    def _items_to_lines(items):
        out = []
        for item in (items if isinstance(items, list) else []):
            if isinstance(item, dict):
                parts = [str(v) for v in item.values() if isinstance(v, str)]
                out.append(" \u2014 ".join(parts))
            elif isinstance(item, str):
                out.append(item)
        return out

    customs = culture.get("local_customs")
    if customs:
        history.append(("Culture & Customs", "\n".join(_items_to_lines(customs))))

    holidays = culture.get("important_holidays")
    if holidays:
        history.append(("Important Holidays", "\n".join(_items_to_lines(holidays))))

    norms = culture.get("social_norms")
    if norms:
        history.append(("Social Norms", "\n".join(_items_to_lines(norms))))

    greeting = culture.get("greeting_style")
    if greeting:
        history.append(("Greetings", str(greeting)))

    dress = culture.get("dress_expectations")
    if dress:
        history.append(("Dress Code", str(dress)))

    # ── Wildlife ────────────────────────────────────────────────────────
    wildlife_zones = _get(data, "outdoors.wildlife_zones") or []
    wildlife_plain = _get(data, "outdoors.wildlife") or []
    wildlife = list(wildlife_zones if isinstance(wildlife_zones, list) else []) + \
               [{"name": w} if isinstance(w, str) else w
                for w in (wildlife_plain if isinstance(wildlife_plain, list) else [])]

    return {
        "hikes": hikes,
        "dishes": dishes,
        "drinks": drinks,
        "street_food": street_food,
        "vegetarian": vegetarian,
        "regional": regional,
        "history": history,
        "wildlife": wildlife,
        "surf_spots": _get(data, "outdoors.surf_spots") or [],
        "national_parks": (
            _get(data, "outdoors.top_national_parks")
            or _get(data, "outdoors.national_parks")
            or []
        ),
        "history_entries": _get(data, "history") or [],
        "danger_zones": _get(data, "outdoors.danger_zones") or [],
        "identity": _get(data, "identity") or {},
        "budget": _get(data, "budget") or {},
        "weather": _get(data, "weather_and_seasonality") or {},
        "transport": _get(data, "transport") or {},
        "laws": _get(data, "laws") or _get(data, "laws_and_rules") or {},
        "safety": _get(data, "safety") or {},
        "_raw": data,
    }


# ── Map marker data ─────────────────────────────────────────────────────────

HIKE_MARKERS = {
    "Ecuador": [
        ("Rucu Pichincha", -0.168, -78.553),
        ("Pasochoa Wildlife Refuge", -0.467, -78.483),
        ("Mindo Cloud Forest Trails", -0.047, -78.774),
        ("El Cajas National Park Circuit", -2.782, -79.188),
        ("Sierra Negra Volcano — Galapagos", -0.827, -91.106),
        ("Tungurahua Volcano Viewpoint", -1.467, -78.443),
        ("Quilotoa Loop", -0.862, -78.899),
        ("Cotopaxi Volcano Trek", -0.680, -78.436),
        ("Chimborazo", -1.469, -78.817),
        ("Illiniza Norte", -0.659, -78.713),
        ("Antisana", -0.481, -78.143),
        ("Podocarpus National Park Trek", -4.115, -79.188),
    ],
    "Peru": [
        ("Rainbow Mountain (Vinicunca)", -13.735, -71.334),
        ("Colca Canyon Trek", -15.640, -71.989),
        ("Machu Picchu from Aguas Calientes", -13.163, -72.545),
        ("Gocta Waterfall Hike", -6.022, -77.898),
        ("Pastoruri Glacier Trek", -10.001, -77.190),
        ("Inca Trail to Machu Picchu", -13.300, -72.400),
        ("Salkantay Trek", -13.339, -72.582),
        ("Huayhuash Circuit", -10.349, -76.889),
        ("Santa Cruz Trek", -9.041, -77.612),
        ("Ausangate Circuit", -13.789, -71.224),
        ("Choquequirao Trek", -13.524, -72.847),
        ("Lares Trek", -13.028, -72.109),
    ],
    "Argentina": [
        ("Fitz Roy Trek", -49.272, -72.932),
        ("Laguna Torre Trek", -49.306, -72.937),
        ("Glaciar Perito Moreno Walk", -50.497, -73.118),
        ("Quebrada de Humahuaca Circuit", -23.207, -65.349),
        ("Valle de la Luna Circuit", -30.099, -67.890),
        ("Aconcagua Normal Route", -32.654, -70.011),
        ("Lanin Volcano Ascent", -39.638, -71.503),
    ],
    "Bolivia": [
        ("Death Road Descent", -16.289, -67.795),
        ("Huayna Potosi Summit", -16.264, -68.160),
        ("Choro Trek", -16.353, -67.847),
        ("Takesi Trek", -16.554, -67.874),
        ("Laguna Colorada / Salar de Uyuni", -22.162, -67.558),
        ("Illimani Summit Trek", -16.638, -67.775),
    ],
    "Brazil": [
        ("Pedra do Telegrafo", -23.054, -43.567),
        ("Trilha da Praia do Rosa", -28.126, -48.646),
        ("Chapada dos Veadeiros — Canion dos Couros", -14.141, -47.684),
        ("Chapada Diamantina — Vale do Pati", -12.526, -41.463),
        ("Trilha do Ouro (Gold Trail)", -23.218, -44.716),
    ],
    "Chile": [
        ("Valle de la Luna", -22.908, -68.317),
        ("Volcan Villarrica Ascent", -39.422, -71.952),
        ("El Tatio Geyser Field", -22.332, -68.013),
        ("Torres del Paine W Trek", -51.032, -73.005),
        ("Torres del Paine O Circuit", -51.100, -73.100),
        ("Carretera Austral — Cochrane", -47.244, -72.574),
        ("Parque Patagonia — Aviles Valley", -47.220, -72.600),
    ],
    "Colombia": [
        ("Valle de Cocora Wax Palm Circuit", 4.638, -75.495),
        ("Serrania de la Macarena — Cano Cristales", 2.200, -73.923),
        ("Ciudad Perdida (Lost City) Trek", 11.040, -73.926),
        ("PNN El Cocuy Glacier Trek", 6.400, -72.400),
        ("Tayrona National Park — Pueblito Trek", 11.330, -73.918),
        ("Nevado del Tolima Summit", 4.659, -75.384),
    ],
    "Guyana": [
        ("Turtle Mountain, Iwokrama", 4.681, -58.731),
        ("Iwokrama Canopy Walkway Trail", 4.681, -58.731),
        ("Shell Beach Conservation Trail", 7.600, -59.800),
        ("Kaieteur Falls Trek", 5.174, -59.483),
        ("Mount Roraima Trek", 5.143, -60.762),
    ],
    "Paraguay": [
        ("Cerro Cora National Park Trails", -22.640, -56.019),
        ("Ybycui National Park Waterfall Trails", -26.097, -57.050),
        ("Jesuit Mission Circuit Walk", -27.300, -55.800),
        ("Medanos del Chaco Dune Walk", -21.800, -62.100),
        ("Chaco Wildlife Drive", -21.199, -61.616),
    ],
    "Suriname": [
        ("Brownsberg Nature Park Trails", 4.946, -55.189),
        ("Peperpot Nature Park Walk", 5.866, -55.069),
        ("Raleighvallen Nature Reserve Trails", 4.700, -56.233),
        ("Julianatop Summit Trek", 3.893, -56.468),
    ],
    "Uruguay": [
        ("Cabo Polonio Sand Dune Trek", -34.401, -53.785),
        ("Quebrada de los Cuervos Circuit", -33.093, -54.464),
        ("Santa Teresa National Park Coastal Walk", -33.970, -53.550),
        ("Cerro Catedral Summit Walk", -34.090, -55.530),
    ],
    "Venezuela": [
        ("Avila / Warairarepano National Park", 10.543, -66.879),
        ("Roraima Tepui Trek", 5.143, -60.762),
        ("Angel Falls Trekking Route", 5.968, -62.534),
        ("Los Nevados Trek, Merida", 8.530, -71.050),
    ],
    "Costa Rica": [
    ("Cerro Chato (Arenal)", 10.463, -84.703),
    ("Manuel Antonio Park Trails", 9.390, -84.136),
    ("Monteverde Cloud Forest Hanging Bridges", 10.300, -84.812),
    ("Rincón de la Vieja Geothermal Trail", 10.831, -85.324),
    ("Corcovado — San Pedrillo to Sirena", 8.574, -83.706),
    ("Poás Volcano Crater", 10.200, -84.231),
    ("Cerro Chirripó Summit", 9.485, -83.489),
    ("Corcovado Multi-Day Traverse", 8.540, -83.580),
    ("Río Celeste and Tenorio Volcano Trail", 10.719, -85.017),
    ],
    "Panama": [
        ("Pipeline Road (Camino del Oleoducto) — Soberanía NP", 9.131, -79.714),
        ("Volcán Barú Summit", 8.808, -82.543),
        ("Quetzal Trail (Sendero Los Quetzales)", 8.836, -82.496),
        ("Isla Bastimentos — Red Frog Beach and Nivida Cave", 9.295, -82.157),
        ("Boquete Waterfall Circuit", 8.778, -82.443),
        ("Camino de Cruces Historic Trail", 9.050, -79.630),
        ("Darién Gap Expedition (La Palma / Emberá communities)", 7.930, -77.730),
        ("Coiba Island Diving and Exploration", 7.455, -81.738),
        ("Guna Yala Island Hopping", 9.555, -78.983),
    ],
    "Guatemala": [
        ("Volcán Acatenango Overnight (summit hike)", 14.501, -90.876),
        ("Volcán Pacaya Active Lava Fields", 14.381, -90.601),
        ("Volcán San Pedro (Lake Atitlán)", 14.650, -91.268),
        ("Indian Nose (Nariz del Indio) Sunrise Hike", 14.741, -91.246),
        ("Tikal Temple Circuit and Jungle Hike", 17.222, -89.624),
        ("Semuc Champey Pools and Caves", 15.533, -89.960),
        ("Chichicastenango Market Walk", 14.947, -91.112),
        ("Río Dulce to Livingston Boat Journey", 15.831, -88.757),
        ("El Mirador Jungle Trek", 17.757, -89.921),
        ("Quetzaltenango to Lake Atitlán Hike (Xela-Atitlán)", 14.833, -91.518),
        ("Cuchumatanes Highlands Trek", 15.417, -91.500),
    ],
    "Belize": [
        ("ATM Cave (Actun Tunichil Muknal)", 17.183, -88.933),
        ("Caracol Maya Ruins", 16.756, -89.119),
        ("Xunantunich Maya Ruins", 17.091, -89.136),
        ("Cockscomb Basin Jaguar Preserve Hike", 16.760, -88.530),
        ("Inland Blue Hole and St. Herman's Cave", 17.165, -88.680),
        ("Cave Tubing (Nohoch Che'en / Caves Branch)", 17.212, -88.665),
        ("Great Blue Hole Dive / Snorkel", 17.316, -87.535),
        ("Crooked Tree Wildlife Sanctuary Boat Tour", 17.736, -88.532),
        ("Toledo Maya Village Experience", 16.100, -88.900),
        ("Lamanai Archaeological Reserve and River Journey", 17.765, -88.657),
    ],
    "Honduras": [
        ("Copán Archaeological Site Trails", 14.839, -89.141),
        ("Pico Bonito Lower Trails", 15.641, -86.921),
        ("Celaque National Park — Las Minas Summit", 14.549, -88.659),
        ("Lago de Yojoa Birding Walk", 14.894, -87.979),
        ("Macaw Mountain Bird Park Trails (Copán)", 14.845, -89.152),
        ("Cuero y Salado Manatee Boat Tour", 15.820, -86.990),
        ("Río Plátano Biosphere Reserve Expedition", 15.600, -84.900),
        ("Celaque Cloud Forest Multi-Day", 14.530, -88.670),
    ],
    "Nicaragua": [
        ("Masaya Volcano — Lava Lake Viewpoint", 11.984, -86.161),
        ("Cerro Negro Volcano Boarding", 12.506, -86.702),
        ("Mombacho Volcano Cloud Forest", 11.828, -85.966),
        ("Concepción Volcano (Isla de Ometepe)", 11.538, -85.622),
        ("Maderas Volcano (Isla de Ometepe)", 11.453, -85.553),
        ("Las Isletas Kayaking (Granada)", 11.900, -85.930),
        ("Bosawás Biosphere Reserve Expedition", 13.700, -85.100),
        ("Río San Juan Jungle Route", 11.100, -84.600),
    ],
    "El Salvador": [
        ("Santa Ana Volcano (Ilamatepec) Summit", 13.853, -89.630),
        ("Izalco Volcano Hike", 13.814, -89.634),
        ("El Imposible National Park Trails", 13.830, -89.970),
        ("Ruta de las Flores Waterfall Walk", 13.877, -89.680),
        ("Montecristo Cloud Forest", 14.414, -89.374),
        ("Lago de Coatepeque Kayak Circuit", 13.866, -89.547),
        ("Tazumal and Joya de Cerén Archaeological Walks", 13.982, -89.676),
        ("Ruta de las Flores Hiking Circuit", 13.870, -89.690),
        ("Northern Mountains (Morazán) Circuit", 13.767, -88.100),
    ],
    "Mexico": [
    ("Iztaccíhuatl (Izta) via Paso de Cortés", 19.179, -98.642),
    ("Monte Albán", 17.043, -96.768),
    ("Hierve el Agua", 16.865, -96.275),
    ("Nevado de Toluca (Xinantécatl)", 19.108, -99.758),
    ("Cañón del Sumidero", 16.851, -93.075),
    ("Palenque Ruins and Jungle Trails", 17.484, -92.046),
    ("Chichen Itza and Cenote Circuit", 20.683, -88.569),
    ("Copper Canyon Rim to Rim (El Chepe + hiking)", 27.317, -107.683),
    ("Volcán Pico de Orizaba (Citlaltépetl) Summit", 19.030, -97.268),
    ("Calakmul Biosphere Trek", 18.113, -89.805),
    ("Sierra Norte of Oaxaca (Pueblos Mancomunados)", 17.217, -96.417),
    ("Malinche National Park Summit", 19.229, -98.034),
],

}

SURF_MARKERS = {
    "Ecuador": [
        ("Montanita", -1.812, -80.757),
        ("Ayampe", -1.674, -80.756),
        ("Canoa", -0.478, -80.469),
        ("Mompiche", 0.483, -80.037),
        ("Salinas", -2.214, -80.957),
        ("Puerto Cayo", -1.362, -80.742),
        ("Los Frailes", -1.522, -80.742),
        ("Atacames", 0.872, -79.848),
        ("Tortuga Bay", -0.765, -90.298),
    ],
    "Peru": [
        ("Mancora", -4.103, -81.047),
        ("Puerto Chicama", -7.704, -79.456),
        ("Huanchaco", -8.082, -79.122),
        ("Punta Hermosa", -12.332, -76.834),
        ("Lobitos", -4.446, -81.271),
    ],
    "Argentina": [
        ("Mar del Plata — La Popular", -38.005, -57.544),
        ("Miramar", -38.268, -57.835),
        ("Necochea", -38.555, -58.739),
        ("Monte Hermoso", -38.992, -61.294),
    ],
    "Brazil": [
        ("Fernando de Noronha — Cacimba do Padre", -3.851, -32.423),
        ("Florianopolis — Praia Mole", -27.610, -48.432),
        ("Itacare, Bahia", -14.278, -38.998),
        ("Jericoacoara, Ceara", -2.797, -40.512),
        ("Saquarema", -22.929, -42.508),
        ("Ubatuba", -23.434, -45.071),
    ],
    "Chile": [
        ("Punta de Lobos, Pichilemu", -34.430, -71.999),
        ("Pichilemu — Infiernillo", -34.387, -71.996),
        ("Matanzas", -33.964, -71.877),
        ("El Gringo, Iquique", -20.213, -70.151),
        ("Arica — La Lisera", -18.506, -70.335),
        ("Easter Island — Hanga Oa", -27.148, -109.432),
    ],
    "Colombia": [
        ("Playa El Almejal, El Valle", 6.194, -77.346),
        ("Playa Terco, Nuqui", 5.711, -77.271),
        ("Punta Huina, Nuqui", 5.738, -77.296),
        ("Juanchaco, Valle del Cauca", 3.884, -77.352),
        ("Capurgana", 8.631, -77.344),
    ],
    "Uruguay": [
        ("Playa Brava, Punta del Este", -34.963, -54.934),
        ("La Barra", -34.928, -54.878),
        ("La Paloma", -34.659, -54.162),
        ("La Pedrera", -34.592, -54.129),
        ("Cabo Polonio", -34.401, -53.785),
        ("Punta del Diablo", -34.008, -53.546),
    ],
    "Venezuela": [
        ("Choroni (Puerto Colombia)", 10.497, -67.598),
        ("El Yaque, Isla Margarita", 10.945, -63.850),
        ("Los Roques", 11.850, -66.850),
    ],
    "Suriname": [
        ("Galibi Beach", 5.849, -57.065),
    ],
    "Costa Rica": [
    ("Playa Tamarindo", 10.299, -85.837),
    ("Playa Santa Teresa", 9.647, -85.167),
    ("Playa Dominical", 9.252, -83.855),
    ("Pavones", 8.428, -83.148),
    ("Salsa Brava (Puerto Viejo)", 9.659, -82.752),
    ("Witch's Rock (Roca Bruja)", 10.916, -85.748),
    ("Playa Jacó", 9.616, -84.627),
    ],
    "El Salvador": [
        ("Punta Roca", 13.495, -89.290),
        ("El Tunco", 13.498, -89.374),
        ("El Zonte (Bitcoin Beach)", 13.493, -89.432),
        ("Las Flores", 13.286, -88.224),
        ("El Cuco", 13.192, -88.238),
        ("El Sunzal", 13.501, -89.397),
    ],
    "Guatemala": [
        ("El Paredón", 13.927, -91.191),
        ("Sipacate", 13.930, -91.148),
    ],
    "Nicaragua": [
        ("Playa Maderas", 11.388, -85.871),
        ("Popoyo", 11.320, -86.010),
        ("Playa Gigante", 11.363, -85.994),
        ("San Juan del Sur — Main Beach", 11.254, -85.872),
        ("Playa Colorado (Rancho Santana area)", 11.332, -86.003),
    ],
    "Panama": [
        ("Santa Catalina", 7.867, -81.259),
        ("Playa Venao", 7.530, -80.189),
        ("Silverbacks (Isla Bastimentos)", 9.302, -82.133),
        ("Bluff Beach (Isla Colón)", 9.368, -82.262),
    ],
    "Mexico": [
    ("Puerto Escondido (Zicatela Beach)", 15.857, -97.062),
    ("La Punta (Puerto Escondido)", 15.862, -97.073),
    ("Sayulita", 20.868, -105.438),
    ("Punta de Mita", 20.773, -105.531),
    ("Troncones", 17.961, -101.868),
    ("Barra de la Cruz", 15.720, -96.031),
    ("Mazunte / Punta Cometa", 15.666, -96.572),
    ("Zipolite", 15.672, -96.527),
    ("Todos Santos", 23.447, -110.228),
    ("Los Cerritos (Todos Santos area)", 23.376, -110.204),
    ("Petacalco / Nexpa", 17.963, -101.869),
    ("La Ticla", 18.255, -103.204),
    ("Pascuales", 18.910, -103.849),
],
}

PARK_MARKERS = {
    "Ecuador": [
        ("Galapagos", -0.6, -90.3),
        ("Cotopaxi", -0.68, -78.44),
        ("El Cajas", -2.78, -79.17),
        ("Machalilla", -1.55, -80.75),
        ("Yasuni", -1.0, -76.0),
        ("Podocarpus", -4.1, -79.2),
    ],
    "Peru": [
        ("Manu", -11.8, -71.5),
        ("Huascaran", -9.1, -77.6),
        ("Paracas", -13.8, -76.25),
        ("Tambopata", -12.9, -69.3),
        ("Machu Picchu", -13.16, -72.55),
    ],
    "Argentina": [
        ("Los Glaciares NP", -50.041, -73.073),
        ("Iguazu NP", -25.686, -54.444),
        ("Nahuel Huapi NP", -41.059, -71.530),
        ("Talampaya NP", -29.745, -67.920),
        ("Tierra del Fuego NP", -54.829, -68.521),
    ],
    "Bolivia": [
        ("Salar de Uyuni", -20.266, -67.609),
        ("Madidi NP", -13.500, -68.800),
        ("Eduardo Avaroa Reserve", -22.162, -67.558),
        ("Sajama NP", -18.106, -68.887),
    ],
    "Brazil": [
        ("Iguacu NP", -25.695, -54.437),
        ("Chapada Diamantina NP", -12.526, -41.463),
        ("Lencois Maranhenses NP", -2.484, -43.129),
        ("Jau NP", -1.960, -61.672),
        ("Chapada dos Veadeiros NP", -14.141, -47.684),
    ],
    "Chile": [
        ("Torres del Paine NP", -51.032, -73.005),
        ("Lauca NP", -18.199, -69.382),
        ("Rapa Nui NP (Easter Island)", -27.113, -109.349),
        ("Los Flamencos Reserve", -23.233, -68.017),
        ("Patagonia NP", -47.156, -72.704),
    ],
    "Colombia": [
        ("Tayrona NNP", 11.330, -73.918),
        ("Los Flamencos Sanctuary", 11.400, -73.100),
        ("Amacayacu NNP", -3.667, -70.233),
        ("PNN El Cocuy", 6.400, -72.400),
        ("Serrania de la Macarena", 2.200, -73.923),
    ],
    "Guyana": [
        ("Kaieteur NP", 5.174, -59.483),
        ("Iwokrama Forest", 4.681, -58.731),
        ("Kanuku Mountains", 3.300, -59.500),
        ("Shell Beach", 7.600, -59.800),
    ],
    "Paraguay": [
        ("Cerro Cora NP", -22.640, -56.019),
        ("Ybycui NP", -26.097, -57.050),
        ("Teniente Enciso NP", -21.199, -61.616),
        ("Lago Ypacarai", -25.330, -57.333),
    ],
    "Suriname": [
        ("Central Suriname Nature Reserve", 4.000, -56.500),
        ("Brownsberg Nature Park", 4.946, -55.189),
        ("Galibi Nature Reserve", 5.844, -57.067),
        ("Bigi Pan Nature Reserve", 5.800, -57.100),
    ],
    "Uruguay": [
        ("Cabo Polonio NP", -34.401, -53.785),
        ("Santa Teresa NP", -33.970, -53.550),
        ("Esteros de Farrapos", -32.750, -58.100),
        ("San Miguel NP", -33.630, -53.410),
    ],
    "Venezuela": [
        ("Canaima NP", 6.230, -62.850),
        ("Los Roques Archipelago NP", 11.850, -66.850),
        ("Medanos de Coro NP", 11.540, -69.960),
        ("Sierra Nevada de Merida NP", 8.530, -71.050),
    ],
    "Costa Rica": [
    ("Corcovado NP", 8.540, -83.580),
    ("Manuel Antonio NP", 9.390, -84.136),
    ("Tortuguero NP", 10.560, -83.504),
    ("Arenal Volcano NP", 10.463, -84.703),
    ("Monteverde Cloud Forest Reserve", 10.300, -84.812),
    ("Rincón de la Vieja NP", 10.831, -85.324),
    ("Chirripó NP", 9.485, -83.489),
    ],
    "Panama": [
        ("Soberanía NP", 9.131, -79.714),
        ("Coiba NP", 7.455, -81.738),
        ("Darién NP", 7.930, -77.730),
        ("La Amistad NP", 8.900, -82.800),
        ("Boquete / Volcán Barú NP", 8.808, -82.543),
    ],
    "Guatemala": [
        ("Tikal NP", 17.222, -89.624),
        ("Semuc Champey NM", 15.533, -89.960),
        ("Volcán Acatenango", 14.501, -90.876),
        ("Sierra de las Minas BR", 15.150, -89.850),
        ("Laguna del Tigre NP", 17.500, -90.900),
    ],
    "Belize": [
        ("Cockscomb Basin Wildlife Sanctuary", 16.760, -88.530),
        ("Blue Hole NM", 17.316, -87.535),
        ("Caracol Archaeological Reserve", 16.756, -89.119),
        ("Lamanai Archaeological Reserve", 17.765, -88.657),
        ("Crooked Tree Wildlife Sanctuary", 17.736, -88.532),
    ],
    "Honduras": [
        ("Copán Archaeological Site", 14.839, -89.141),
        ("Pico Bonito NP", 15.641, -86.921),
        ("Celaque NP", 14.549, -88.659),
        ("Río Plátano BR", 15.600, -84.900),
        ("Cusuco NP", 15.483, -88.249),
    ],
    "Nicaragua": [
        ("Masaya Volcano NP", 11.984, -86.161),
        ("Mombacho Volcano NR", 11.828, -85.966),
        ("Isla de Ometepe BR", 11.495, -85.590),
        ("Bosawás BR", 13.700, -85.100),
        ("Indio Maíz BR", 11.050, -84.200),
    ],
    "El Salvador": [
        ("El Imposible NP", 13.830, -89.970),
        ("Montecristo NP", 14.414, -89.374),
        ("Walter Thilo Deininger NP", 13.550, -89.380),
        ("Cerro Verde NP", 13.866, -89.629),
        ("El Jocotal Lagoon NR", 13.390, -88.300),
    ],
    "Mexico": [
    ("Iztaccíhuatl–Popocatépetl NP", 19.179, -98.642),
    ("Copper Canyon (Barrancas del Cobre)", 27.317, -107.683),
    ("Calakmul BR", 18.113, -89.805),
    ("Palenque NP", 17.484, -92.046),
    ("Sumidero Canyon NP", 16.851, -93.075),
    ("Nevado de Toluca NP", 19.108, -99.758),
    ("Sian Ka'an BR", 19.800, -87.650),
],
}

DANGER_MARKERS = {
    "Ecuador": [
        ("La Perla district, Guayaquil", -2.18, -79.9),
        ("Centro Historico at night, Quito", -0.22, -78.51),
    ],
    "Peru": [
        ("Centro de Lima at night", -12.05, -77.03),
        ("Callao port area", -12.06, -77.15),
    ],
    "Argentina": [
        ("Patagonia weather — El Chalten", -49.331, -72.887),
        ("Aconcagua altitude zone", -32.654, -70.011),
    ],
    "Bolivia": [
        ("Yungas Road (Death Road)", -16.289, -67.795),
        ("Chapare Region", -16.500, -65.500),
        ("High Altitude — La Paz", -16.5, -68.15),
    ],
    "Brazil": [
        ("Favelas — Rio de Janeiro", -22.906, -43.173),
        ("Northeast rip currents — Recife", -8.119, -34.903),
        ("Amazon border zone", -3.0, -60.0),
    ],
    "Chile": [
        ("Patagonia extreme weather — Punta Arenas", -53.163, -70.917),
        ("Atacama altitude — San Pedro", -22.909, -68.200),
        ("Araucania conflict zone — Temuco", -38.735, -72.590),
    ],
    "Colombia": [
        ("Arauca Dept — Do Not Travel", 7.090, -70.760),
        ("Cauca Dept rural areas", 2.450, -76.600),
        ("Norte de Santander border", 7.893, -72.506),
        ("Darien Gap", 8.000, -77.100),
    ],
    "Guyana": [
        ("Albouystown / Tiger Bay, Georgetown", 6.803, -58.157),
        ("Gold Mining Roads — Interior", 5.000, -59.500),
    ],
    "Paraguay": [
        ("Northeast Border — Amambay", -22.557, -55.726),
        ("Deep Chaco — wet season", -21.0, -61.0),
    ],
    "Suriname": [
        ("Interior rivers without guide", 4.000, -56.000),
        ("Gold Mining Areas", 4.946, -55.189),
    ],
    "Uruguay": [
        ("Cabo Polonio surf — large swell", -34.401, -53.785),
    ],
    "Venezuela": [
        ("Colombia border zone — Tachira", 7.766, -72.226),
        ("Amazonas State", 3.500, -65.500),
        ("Maiquetia Airport route", 10.601, -66.991),
        ("Caracas city center", 10.480, -66.903),
    ],
    "Costa Rica": [
    ("Rip currents — Playa Dominical", 9.252, -83.855),
    ("Crocodile zone — Tárcoles River mouth", 9.690, -84.628),
    ],
    "Panama": [
        ("Darién Gap — No Travel Zone", 8.000, -77.500),
        ("Colón city center", 9.359, -79.900),
    ],
    "Guatemala": [
        ("Zone 18, Guatemala City", 14.669, -90.497),
        ("El Petén border zone — Mexico", 17.500, -90.200),
        ("Acatenango summit — altitude sickness zone", 14.501, -90.876),
    ],
    "Belize": [
        ("South Side Belize City", 17.247, -88.765),
        ("Southern Highway at night", 16.500, -88.500),
    ],
    "Honduras": [
        ("San Pedro Sula city center", 15.504, -88.025),
        ("Tegucigalpa — Kennedy/Villa Nueva", 14.093, -87.206),
        ("Caribbean coast at night — La Ceiba", 15.758, -86.793),
    ],
    "Nicaragua": [
        ("Managua city center at night", 12.136, -86.313),
        ("Northern border zone — Honduras", 13.500, -86.500),
    ],
    "El Salvador": [
        ("San Salvador — Soyapango district", 13.701, -89.144),
        ("La Libertad port area at night", 13.486, -89.320),
    ],
    "Mexico": [
    ("Sinaloa / Culiacán — cartel activity", 24.809, -107.394),
    ("Guerrero State — Acapulco", 16.853, -99.823),
    ("Tamaulipas border — Nuevo Laredo", 27.476, -99.512),
    ("Colima State", 19.245, -103.725),
    ("Tepito district — Mexico City", 19.445, -99.128),
],

}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_country_json(country_name: str) -> dict | None:
    """Load country JSON by display name using the discovered registry."""
    registry = _discover_countries()
    entry = registry.get(country_name)
    if not entry:
        return None
    path = _COUNTRIES_DIR / entry["continent"] / f"{entry['file_stem']}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.error("Failed to load country JSON %s: %s", path, e)
        return None
    
def _get_hike_markers(country_name: str) -> list[tuple]:
    data = _load_country_json(country_name)
    markers = []
    if data:
        for section in ["top_day_hikes", "multi_day_treks"]:
            for h in (data.get("outdoors", {}).get(section) or []):
                if isinstance(h, dict) and h.get("lat") and h.get("lon"):
                    markers.append((h["name"], float(h["lat"]), float(h["lon"])))
    if not markers:
        markers = HIKE_MARKERS.get(country_name, [])
    return markers


def _get_surf_markers(country_name: str) -> list[tuple]:
    data = _load_country_json(country_name)
    markers = []
    if data:
        for s in (data.get("outdoors", {}).get("surf_spots") or []):
            if isinstance(s, dict) and s.get("lat") and s.get("lon"):
                markers.append((s["name"], float(s["lat"]), float(s["lon"])))
    if not markers:
        markers = SURF_MARKERS.get(country_name, [])
    return markers


def _get_park_markers(country_name: str) -> list[tuple]:
    data = _load_country_json(country_name)
    markers = []
    if data:
        outdoors = data.get("outdoors", {})
        parks = outdoors.get("top_national_parks") or outdoors.get("national_parks") or []
        for p in parks:
            if isinstance(p, dict) and p.get("lat") and p.get("lon"):
                markers.append((p["name"], float(p["lat"]), float(p["lon"])))
    if not markers:
        markers = PARK_MARKERS.get(country_name, [])
    return markers


def _get_danger_markers(country_name: str) -> list[tuple]:
    data = _load_country_json(country_name)
    markers = []
    if data:
        for d in (data.get("safety", {}).get("danger_zones") or []):
            if isinstance(d, dict) and d.get("lat") and d.get("lon"):
                markers.append((d["name"], float(d["lat"]), float(d["lon"])))
    if not markers:
        markers = DANGER_MARKERS.get(country_name, [])
    return markers

def _get(data, dotpath, default=None):
    """Resolve a dot-separated path into nested dicts."""
    if data is None:
        return default
    node = data
    for part in dotpath.split("."):
        if not isinstance(node, dict):
            return default
        node = node.get(part)
        if node is None:
            return default
    return node


def _no_data():
    st.caption("More data coming soon")


def _detect_country() -> str:
    """Detect country from session state. Falls back to first available country."""
    registry = _discover_countries()
    valid_countries = set(registry.keys())
    name_lower_map = {k.lower(): k for k in registry}
    iso2_map = {v["iso2"]: k for k, v in registry.items() if v["iso2"]}

    explore_country = st.session_state.get("explore_country", "")
    if explore_country in valid_countries:
        return explore_country

    sel = st.session_state.get("selected_location")
    if isinstance(sel, dict) and sel.get("country"):
        cl = sel["country"].lower()
        for name_lower, name in name_lower_map.items():
            if name_lower in cl:
                return name

    dest = st.session_state.get("destination_airport", {})
    if isinstance(dest, dict):
        cc = (dest.get("country_code") or dest.get("country") or "").upper().strip()
        if cc in iso2_map:
            return iso2_map[cc]
        matched = name_lower_map.get(cc.lower())
        if matched:
            return matched

    dest_city = st.session_state.get("destination_city", "")
    if dest_city:
        city_lower = dest_city.lower().strip()
        matched = _CITY_COUNTRY_MAP.get(city_lower)
        if matched and matched in valid_countries:
            return matched
        for city_key, country_name in _CITY_COUNTRY_MAP.items():
            if city_key in city_lower and country_name in valid_countries:
                return country_name

    return "Ecuador"


def _detect_country_from_coords(lat, lon):
    """Detect which country a lat/lon falls in using centroids (closest match)."""
    if not _COUNTRY_CENTROIDS:
        return None
    best_code = None
    best_dist = float("inf")
    for code, (clat, clon) in _COUNTRY_CENTROIDS.items():
        dist = (lat - clat) ** 2 + (lon - clon) ** 2
        if dist < best_dist:
            best_dist = dist
            best_code = code
    return best_code


# ── Tab renderers ────────────────────────────────────────────────────────────


def _render_map_tab(active_country: str, data: dict | None) -> None:
    """Render the Map tab with Leaflet map, controls, and safety scoring."""
    try:
        import folium
        from streamlit_folium import st_folium
    except ImportError:
        st.warning("Install `folium` and `streamlit-folium` to see the interactive map.")
        return

    registry = _discover_countries()
    entry = registry.get(active_country, {})
    centroid = entry.get("centroid")
    if centroid:
        center, zoom = list(centroid), 6
    else:
        center, zoom = [-15.0, -60.0], 3
    center, zoom = country_centers.get(active_country, ([-1.5, -78.0], 7))

    # Map controls row 1
    ctrl_c1, ctrl_c2, ctrl_c3 = st.columns([2, 2, 3])
    with ctrl_c1:
        show_wildlife = st.checkbox(
            "Show wildlife zones",
            value=st.session_state.get("map_show_wildlife", False),
            key="map_show_wildlife",
        )
    with ctrl_c2:
        show_hikes = st.checkbox(
            "Show hike markers",
            value=st.session_state.get("map_show_hikes", True),
            key="map_show_hikes",
        )
    with ctrl_c3:
        wildlife_risk_filter = st.slider(
            "Min wildlife risk to show", 1, 5,
            st.session_state.get("wildlife_risk_filter", 3),
            key="wildlife_risk_filter",
        )

    # Map controls row 2 -- Fix 3: surf, parks, danger toggles
    ctrl_d1, ctrl_d2, ctrl_d3 = st.columns(3)
    with ctrl_d1:
        show_surf = st.checkbox("\U0001f3c4 Show surf spots", value=True, key="map_show_surf")
    with ctrl_d2:
        show_parks = st.checkbox("\U0001f33f Show national parks", value=True, key="map_show_parks")
    with ctrl_d3:
        show_danger = st.checkbox("\u26a0\ufe0f Show dangerous areas", value=False, key="map_show_danger")

    ##### added below this 4/14 -- trying to combat the lat lon out of bounds & location picker reverting to SA country (snapping back)
    
    m = folium.Map(
    location=[-15, -60], # starts on SA which is are intial target
    zoom_start=3,
    tiles=None,
    min_zoom=2,
    max_bounds=True,
    min_lat=-85,
    max_lat=85,
    min_lon=-180,
    max_lon=180,
    )

    folium.TileLayer(
        "OpenStreetMap",
        no_wrap=True,
    ).add_to(m)

  

    #### to here 4/14

    sel = st.session_state.get("selected_location")
    if sel and isinstance(sel, dict) and sel.get("lat"):
        folium.Marker(
            [sel["lat"], sel["lon"]],
            popup=sel.get("city", "Destination"),
            tooltip="Your destination",
            icon=folium.Icon(color="red", icon="map-marker"),
        ).add_to(m)

    # Wildlife zones
    if show_wildlife and active_country in ("Ecuador", "Peru"):
        _wt = []
        _threat_centers = {}
        try:
            if active_country == "Ecuador":
                from models.safety.submodels.ecuador_safety import _WILDLIFE_THREATS as _wt
                _threat_centers = {
                    "amazon": (-1.0, -76.5), "coastal_lowland": (-1.5, -80.5),
                    "cloud_forest": (-0.5, -78.5), "andes": (-1.5, -78.5),
                    "galapagos": (-0.6, -90.5), "rural": (-2.0, -79.0), "urban": (-0.2, -78.5),
                }
            else:
                from models.safety.submodels.peru_safety import _WILDLIFE_THREATS_PERU as _wt
                _threat_centers = {
                    "amazon": (-5.0, -74.0), "coastal_lowland": (-10.0, -77.0),
                    "cloud_forest": (-10.0, -74.0), "andes": (-13.0, -72.0),
                    "rural": (-8.0, -75.0), "urban": (-12.0, -77.0),
                }
        except ImportError:
            st.caption("Wildlife data not available.")

        risk_colors = {5: "#cc0000", 4: "#ff6600", 3: "#ffaa00", 2: "#88cc00", 1: "#00aa44"}
        shown_threats = set()
        for threat in _wt:
            if not isinstance(threat, dict):
                continue
            if threat.get("risk", 0) < wildlife_risk_filter:
                continue
            habitats = threat.get("habitats", [])
            for hab in habitats:
                if hab in _threat_centers:
                    clat, clon = _threat_centers[hab]
                    key = (threat["name"], hab)
                    if key in shown_threats:
                        continue
                    shown_threats.add(key)
                    color = risk_colors.get(threat["risk"], "#888888")
                    folium.Circle(
                        location=[clat, clon],
                        radius=80000,
                        color=color,
                        fill=True,
                        fill_opacity=0.15,
                        opacity=0.5,
                        tooltip=f"{threat['name']} (risk {threat['risk']}/5)",
                        popup=folium.Popup(
                            f"<b>{threat['name']}</b><br>Risk: {threat['risk']}/5<br>"
                            f"Type: {threat.get('type', '')}<br>{threat.get('notes', '')[:120]}",
                            max_width=250,
                        ),
                    ).add_to(m)
                    break

    # Hike markers — use HIKE_MARKERS lookup (lat/lon hardcoded per hike)
    if show_hikes:
        hike_pins = _get_hike_markers(active_country)
        # Build a quick name→detail lookup from profile for popup enrichment
        profile = _load_profile(active_country)
        hike_detail = {}
        if profile:
            for hike in profile.get("hikes", []):
                if isinstance(hike, dict):
                    hike_detail[hike.get("name", "")] = hike
        for hike_name, hlat, hlon in hike_pins:
            detail = hike_detail.get(hike_name, {})
            diff = detail.get("difficulty", "")
            dur = detail.get("duration", "")
            desc = detail.get("description", "")[:100]
            popup_html = f"<b>\U0001f3d4 {hike_name}</b>"
            if diff or dur:
                popup_html += f"<br>{diff}{' — ' + dur if dur else ''}"
            if desc:
                popup_html += f"<br>{desc}..."
            folium.Marker(
                [hlat, hlon],
                popup=folium.Popup(popup_html, max_width=220),
                tooltip=f"\U0001f3d4 {hike_name}",
                icon=folium.Icon(color="orange", icon="map-marker", prefix="glyphicon"),
            ).add_to(m)

    # Surf spot markers — use hardcoded for Ecuador/Peru, JSON for others
    if show_surf:
        surf_hardcoded = _get_surf_markers(active_country)
        if surf_hardcoded:
            # Build name→detail lookup from JSON profile
            surf_detail = {}
            profile = _load_profile(active_country)
            if profile:
                for spot in profile.get("surf_spots", []):
                    if isinstance(spot, dict):
                        surf_detail[spot.get("name", "")] = spot
            for spot_name, slat, slon in surf_hardcoded:
                detail = surf_detail.get(spot_name, {})
                wave = detail.get("break_type") or detail.get("wave_type", "")
                difficulty = detail.get("difficulty", "")
                best = detail.get("best_months", "")
                desc = (detail.get("description", "") or "")[:120]
                popup_html = f"<b>\U0001f3c4 {spot_name}</b>"
                if wave:
                    popup_html += f"<br><i>Break:</i> {wave}"
                if difficulty:
                    popup_html += f"<br><i>Difficulty:</i> {difficulty}"
                if best:
                    if isinstance(best, list):
                        best = ", ".join(best)
                    popup_html += f"<br><i>Best months:</i> {best}"
                if desc:
                    popup_html += f"<br>{desc}{'...' if len(detail.get('description',''))>120 else ''}"
                folium.Marker([slat, slon],
                    popup=folium.Popup(popup_html, max_width=260),
                    tooltip=f"\U0001f3c4 {spot_name}",
                    icon=folium.Icon(color="blue", icon="tint", prefix="glyphicon"),
                ).add_to(m)

    # National park markers — use hardcoded for Ecuador/Peru, JSON for others
    if show_parks:
        parks_hardcoded = _get_park_markers(active_country)
        if parks_hardcoded:
            # Build name→detail lookup from JSON profile
            park_detail = {}
            profile = _load_profile(active_country)
            if profile:
                for park in profile.get("national_parks", []):
                    if isinstance(park, dict):
                        park_detail[park.get("name", "")] = park
            for park_name, plat, plon in parks_hardcoded:
                detail = park_detail.get(park_name, {})
                region = detail.get("region", "")
                area = detail.get("area_km2", "")
                desc = (detail.get("description", "") or "")[:120]
                best = detail.get("best_months", "")
                highlights = detail.get("highlights", [])
                popup_html = f"<b>\U0001f33f {park_name}</b><br><i>National Park</i>"
                if region:
                    popup_html += f"<br><i>Region:</i> {region}"
                if area:
                    popup_html += f"<br><i>Area:</i> {area:,} km\u00b2" if isinstance(area, (int, float)) else f"<br><i>Area:</i> {area} km\u00b2"
                if best:
                    if isinstance(best, list):
                        best = ", ".join(best)
                    popup_html += f"<br><i>Best months:</i> {best}"
                if highlights:
                    hl = highlights[:3] if isinstance(highlights, list) else []
                    if hl:
                        popup_html += f"<br><i>Highlights:</i> {', '.join(str(h) for h in hl)}"
                if desc:
                    popup_html += f"<br>{desc}{'...' if len(detail.get('description',''))>120 else ''}"
                folium.Marker([plat, plon],
                    popup=folium.Popup(popup_html, max_width=280),
                    tooltip=f"\U0001f33f {park_name}",
                    icon=folium.Icon(color="green", icon="tree-conifer", prefix="glyphicon"),
                ).add_to(m)

    # Fix 3: Dangerous area markers
    if show_danger:
            for danger_name, dlat, dlon in _get_danger_markers(active_country):
                folium.Marker(
                    [dlat, dlon],
                    popup=folium.Popup(f"<b>\u26a0\ufe0f {danger_name}</b><br>Exercise caution", max_width=200),
                    tooltip=f"\u26a0\ufe0f {danger_name}",
                    icon=folium.Icon(color="red", icon="warning-sign", prefix="glyphicon"),
                ).add_to(m)

    map_data = st_folium(m, use_container_width=True, height=900, key="explore_main_map")

    # Capture map click and reverse-geocode
    clicked = map_data.get("last_clicked") if map_data else None
    if clicked and clicked.get("lat") is not None and clicked.get("lng") is not None:
        c_lat, c_lng = clicked["lat"], clicked["lng"]
        c_lng = ((c_lng + 180) % 360) - 180                          ###### added above this 4/14 -- trying to combat the lat lon out of bounds & location picker reverting to SA country (snapping back)

        if (c_lat != st.session_state.get("explore_click_lat")
                or c_lng != st.session_state.get("explore_click_lon")):
            st.session_state["explore_click_lat"] = c_lat
            st.session_state["explore_click_lon"] = c_lng
            try:
                import requests as _req
                rg = _req.get(
                    "https://nominatim.openstreetmap.org/reverse",
                    params={"lat": c_lat, "lon": c_lng, "format": "json"},
                    headers={"User-Agent": "WayFinder/1.0"},
                    timeout=3,
                )
                if rg.ok and rg.json().get("display_name"):
                    parts = rg.json()["display_name"].split(",")
                    st.session_state["explore_click_name"] = parts[0].strip()
                else:
                    st.session_state["explore_click_name"] = f"{c_lat:.4f}, {c_lng:.4f}"
            except Exception:
                st.session_state["explore_click_name"] = f"{c_lat:.4f}, {c_lng:.4f}"

            # Fix 2: detect country from click coordinates and switch if different Fix 3: adding toggle can come off when we find new solution or have every single country maped with code
            if st.session_state.get("explore_auto_country_snap", False):
                detected_cc = _detect_country_from_coords(c_lat, c_lng)
                if detected_cc:
                    cc_to_country = {v: k for k, v in _COUNTRY_CODE_MAP.items()}
                    detected_name = cc_to_country.get(detected_cc)
                    if detected_name and detected_name != st.session_state.get("explore_country"):
                        st.session_state["explore_country"] = detected_name

            st.rerun()

    # Safety scoring section
    st.divider()
    st.markdown("### Safety Score")
    score_col1, score_col2 = st.columns([3, 1])
    with score_col1:
        explore_dest = st.text_input(
            "Score a location",
            placeholder="e.g. Quito, Cusco, Iquitos...",
            key="explore_score_input",
            value=st.session_state.get("explore_click_name", ""),
            label_visibility="collapsed",
        )
    with score_col2:
        score_btn = st.button("Run Score", use_container_width=True, key="explore_run_score")

    click_lat = st.session_state.get("explore_click_lat")
    click_lon = st.session_state.get("explore_click_lon")
    click_name = st.session_state.get("explore_click_name", "")
    if click_lat is not None:
        st.info(
            f"**Selected from map:** {click_name}  \n"
            f"Lat: `{click_lat:.5f}` - Lon: `{click_lon:.5f}`"
        )

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    sel_month = st.selectbox(
        "Travel month (for weather assessment)",
        options=list(range(1, 13)),
        format_func=lambda x: month_names[x - 1],
        index=datetime.date.today().month - 1,
        key="explore_travel_month",
    )

    if score_btn:
        _run_safety_score(explore_dest, active_country, sel_month)

    explore_result = st.session_state.get("explore_safety_result")
    if explore_result and isinstance(explore_result, dict) and explore_result.get("success"):
        render_safety_panel(explore_result, label=st.session_state.get("explore_scored_location", ""))
    elif explore_result and isinstance(explore_result, dict):
        st.error(f"Scoring failed: {explore_result.get('error')}")


def _run_safety_score(explore_dest: str, active_country: str, sel_month: int) -> None:
    """Run safety scoring for the given destination."""
    try:
        import requests as _req
    except ImportError:
        st.error("requests library not available")
        return

    lat = lon = country = None
    location_name = explore_dest

    if explore_dest:
        try:
            geo_r = _req.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": explore_dest, "format": "json", "limit": 1},
                headers={"User-Agent": "WayFinder/1.0"},
                timeout=5,
            )
            if geo_r.ok and geo_r.json():
                geo = geo_r.json()[0]
                lat = float(geo["lat"])
                lon = float(geo["lon"])
                country = geo.get("display_name", "").split(",")[-1].strip()
            else:
                st.warning(f"Could not find '{explore_dest}'.")
        except Exception as e:
            st.error(f"Geocoding failed: {e}")
    elif st.session_state.get("explore_click_lat") is not None:
        lat = st.session_state["explore_click_lat"]
        lon = st.session_state["explore_click_lon"]
        location_name = st.session_state.get("explore_click_name", f"{lat:.4f}, {lon:.4f}")
        country = active_country

    if lat is not None and lon is not None:
        try:
            from services.safety_service import SafetyService
            from models.safety.schemas import SafetyRequest

            @st.cache_resource
            def _get_safety():
                return SafetyService()

            _ss = _get_safety()
            req = SafetyRequest(
                latitude=lat,
                longitude=lon,
                country=country,
                location_name=location_name,
                travel_month=sel_month,
            )
            result = _ss.assess_request(req, include_details=True)
            st.session_state["explore_safety_result"] = result
            st.session_state["explore_scored_location"] = location_name
            st.rerun()
        except Exception as e:
            st.error(f"Scoring failed: {e}")

'''
def _render_safety_results_panel(result: dict, label: str = "") -> None:
    """Render safety scoring outputs as a tabbed panel (Fix 1: restored sub-tabs)."""
    score = result.get("safety_score")
    band = result.get("risk_band", "---")
    model_version = result.get("model_version", "---")

    if label:
        st.markdown(f"**{label}**")

    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric("Safety Score", f"{score:.1f}/100" if score is not None else "---")
    m_col2.metric("Risk Band", f"{band}")
    m_col3.metric("Model", model_version)

    details = result.get("details", {})
    weather = result.get("weather_risk", {})
    ecuador = result.get("ecuador_risk", {})
    peru_r = result.get("peru_risk", {})
    lgbt = result.get("lgbt_safety") or (result.get("details", {}) or {}).get("lgbt_safety", {})

    tab_labels = ["Score Details"]
    if isinstance(weather, dict) and weather and not weather.get("error"):
        tab_labels.append("Weather")
    if isinstance(ecuador, dict) and ecuador.get("applicable"):
        tab_labels.append("Ecuador")
    if isinstance(peru_r, dict) and peru_r.get("applicable"):
        tab_labels.append("Peru")
    if isinstance(lgbt, dict) and "lgbt_safety_score" in lgbt:
        tab_labels.append("LGBT")

    tabs = st.tabs(tab_labels)
    tab_idx = 0

    # ── Score Details tab ────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            st.markdown("**Model breakdown**")
            if isinstance(details, dict):
                mlp = details.get("mlp_score_v6")
                rf = details.get("rf_score_v6")
                v9b = details.get("v9b_score")
                if mlp is not None:
                    st.metric("MLP v6", f"{mlp:.1f}")
                if rf is not None:
                    st.metric("Random Forest v6", f"{rf:.1f}")
                if v9b is not None:
                    st.metric("v9b MLP", f"{v9b:.1f}")
        with d_col2:
            st.markdown("**Location**")
            r_lat = result.get("latitude")
            r_lon = result.get("longitude")
            r_country = result.get("country", "---")
            if r_lat and r_lon:
                st.caption(f"{r_lat:.4f}, {r_lon:.4f}")
            st.caption(f"{r_country}")
            if isinstance(details, dict):
                feat_count = details.get("feature_count")
                if feat_count:
                    st.caption(f"Features used: {feat_count}")

    # ── Weather tab (Fix 1) ──────────────────────────────────────────
    if isinstance(weather, dict) and weather and not weather.get("error") and tab_idx <= len(tabs) - 1:
        with tabs[tab_idx]:
            tab_idx += 1
            st.markdown("### Weather Risk")
            w_score = weather.get("weather_risk_score", "---")
            w_label = weather.get("weather_risk_label", "---")
            st.markdown(f"## {w_score}/5 -- {w_label}")
            assessment = weather.get("travel_month_assessment", "")
            if assessment:
                st.info(assessment)
            active_risks = weather.get("active_risks") or weather.get("risks", [])
            if active_risks:
                st.markdown("**Active risks this month:**")
                for risk in active_risks:
                    if isinstance(risk, dict):
                        risk_name = risk.get("name") or risk.get("risk", "Unknown")
                        severity = risk.get("severity", 0)
                        dots = "\U0001f534" * severity if severity else ""
                        desc = risk.get("description") or risk.get("notes", "")
                        with st.expander(f"{dots} {risk_name}"):
                            if desc:
                                st.write(desc)
                    elif isinstance(risk, str):
                        with st.expander(f"\U0001f534 {risk}"):
                            st.write(risk)

    # ── Ecuador tab (Fix 1) ──────────────────────────────────────────
    if isinstance(ecuador, dict) and ecuador.get("applicable") and tab_idx <= len(tabs) - 1:
        with tabs[tab_idx]:
            tab_idx += 1
            e_col1, e_col2, e_col3 = st.columns(3)
            e_col1.metric("Overall Risk", f"{ecuador.get('overall_risk', '---')}/5")
            e_col2.metric("Crime Risk", f"{ecuador.get('crime_risk', '---')}/5")
            e_col3.metric("Wildlife Risk", f"{ecuador.get('wildlife_risk', '---')}/5")
            province = ecuador.get("province") or ecuador.get("region", "")
            homicide_rate = ecuador.get("homicide_rate")
            if province or homicide_rate:
                parts = []
                if province:
                    parts.append(f"Province: {province}")
                if homicide_rate is not None:
                    parts.append(f"Homicide rate: {homicide_rate}/100k")
                st.markdown(" \u00b7 ".join(parts))
            note = ecuador.get("note") or ecuador.get("summary", "")
            if note:
                if ecuador.get("overall_risk", 0) >= 4:
                    st.warning(note)
                else:
                    st.info(note)

    # ── Peru tab (Fix 1) ─────────────────────────────────────────────
    if isinstance(peru_r, dict) and peru_r.get("applicable") and tab_idx <= len(tabs) - 1:
        with tabs[tab_idx]:
            tab_idx += 1
            p_col1, p_col2, p_col3 = st.columns(3)
            p_col1.metric("Overall Risk", f"{peru_r.get('overall_risk', '---')}/5")
            p_col2.metric("Crime Risk", f"{peru_r.get('crime_risk', '---')}/5")
            p_col3.metric("Wildlife Risk", f"{peru_r.get('wildlife_risk', '---')}/5")
            province = peru_r.get("province") or peru_r.get("region", "")
            homicide_rate = peru_r.get("homicide_rate")
            if province or homicide_rate:
                parts = []
                if province:
                    parts.append(f"Province: {province}")
                if homicide_rate is not None:
                    parts.append(f"Homicide rate: {homicide_rate}/100k")
                st.markdown(" \u00b7 ".join(parts))
            note = peru_r.get("note") or peru_r.get("summary", "")
            if note:
                if peru_r.get("overall_risk", 0) >= 4:
                    st.warning(note)
                else:
                    st.info(note)

    # ── LGBT tab (Fix 1) ─────────────────────────────────────────────
    if isinstance(lgbt, dict) and "lgbt_safety_score" in lgbt and tab_idx <= len(tabs) - 1:
        with tabs[tab_idx]:
            tab_idx += 1
            labels_map = {
                1: "Criminalized",
                2: "Hostile",
                3: "Neutral",
                4: "Accepting",
                5: "Very Safe",
            }
            score_l = lgbt.get("lgbt_safety_score")
            legal_idx = lgbt.get("lgbt_legal_index")
            l_col1, l_col2 = st.columns(2)
            l_col1.metric("LGBT Safety Score", f"{score_l}/5" if score_l else "---")
            if legal_idx is not None:
                l_col2.metric("Legal Index", f"{legal_idx:.1f}/100")
            verdict_label = labels_map.get(score_l, "---")
            if score_l == 5:
                st.markdown(f"**Very Safe -- full legal equality**")
            elif score_l:
                st.markdown(f"**{verdict_label}**")
            confidence = lgbt.get("confidence") or "high"
            st.markdown(f"Data confidence: {confidence}")
            st.caption("Source: ILGA World, Rainbow Map, and WayFinder LGBT classifier (1 = Criminalized \u2192 5 = Very Safe)")
'''

def _render_hikes_tab(active_country: str) -> None:
    """Render the Hikes tab with hike info cards loaded from JSON."""
    profile = _load_profile(active_country)
    hikes = profile["hikes"] if profile else []
    if not hikes:
        st.info(f"Hike data for {active_country} coming soon.")
        return

    hike_names = [h["name"] for h in hikes if isinstance(h, dict) and "name" in h]
    chosen = st.selectbox("Choose a hike:", ["-- Select a hike --"] + hike_names, key="hike_selector")

    if chosen != "-- Select a hike --":
        idx = hike_names.index(chosen)
        hike = hikes[idx]
        st.session_state["selected_hike_idx"] = idx

        st.markdown(f"### {hike['name']}")
        area = hike.get("province") or hike.get("region", "---")
        difficulty = hike.get("difficulty", "")
        duration = hike.get("duration", "")
        st.caption(f"{area} - {difficulty} - {duration}")
        if hike.get("elevation_m"):
            st.caption(f"Max elevation: {hike['elevation_m']:,}m")
        st.markdown(hike.get("description", ""))
        if hike.get("notes"):
            st.markdown("**Notes:**")
            st.caption(hike["notes"])
        if hike.get("tips"):
            st.markdown("**Tips:**")
            st.caption(hike["tips"])
        if hike.get("wildlife"):
            if isinstance(hike["wildlife"], list):
                st.markdown("**Wildlife you may see:**")
                st.caption(", ".join(str(w) for w in hike["wildlife"]))
        best = hike.get("best_months")
        if best:
            if isinstance(best, list):
                best = ", ".join(str(m) for m in best)
            st.caption(f"Best months: {best}")


def _render_wildlife_tab(active_country: str) -> None:
    """Render the Wildlife tab -- JSON wildlife zones first, then safety-model threats."""
    # Show wildlife zones from JSON profile
    profile = _load_profile(active_country)
    all_wildlife = profile["wildlife"] if profile else []
    if all_wildlife:
        st.markdown(f"## {active_country} -- Wildlife & Nature Zones")
        for item in all_wildlife:
            if isinstance(item, str):
                st.markdown(f"- {item}")
                continue
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("zone_name", "Unknown")
            st.markdown(f"**{name}**")
            c1, c2 = st.columns(2)
            if item.get("region"):
                c1.caption(f"Region: {item['region']}")
            species = item.get("key_species") or item.get("species", [])
            if species:
                if isinstance(species, list):
                    c2.caption(f"Key species: {', '.join(str(s) for s in species)}")
                else:
                    c2.caption(f"Key species: {species}")
            best = item.get("best_months")
            if best:
                if isinstance(best, list):
                    best = ", ".join(str(m) for m in best)
                st.caption(f"Best months: {best}")
            if item.get("description"):
                st.caption(item["description"])
            st.divider()

    # Supplementary: safety-model wildlife threats for Ecuador/Peru
    threats_list = []
    try:
        if active_country == "Peru":
            from models.safety.submodels.peru_safety import _WILDLIFE_THREATS_PERU as threats_list
        elif active_country == "Ecuador":
            from models.safety.submodels.ecuador_safety import _WILDLIFE_THREATS as threats_list
    except ImportError:
        pass

    if not threats_list and not all_wildlife:
        st.info(f"Wildlife information for {active_country} coming soon.")
        return
    if not threats_list:
        return

    by_type = {}
    for t in threats_list:
        if not isinstance(t, dict):
            continue
        ttype = t.get("type", "other")
        by_type.setdefault(ttype, []).append(t)

    type_labels = {
        "venomous snake": "Venomous Snakes",
        "large predator": "Large Predators",
        "disease vector": "Disease Vectors",
        "venomous spider": "Venomous Spiders",
        "venomous insect": "Venomous Insects",
        "parasitic insect": "Parasitic Insects",
        "parasitic fish": "Parasitic Fish",
        "electric fish": "Electric Fish",
        "rabies vector": "Rabies Vectors",
        "geological": "Geological Hazards",
        "environmental": "Environmental Hazards",
        "weather": "Weather Hazards",
        "wildlife encounter": "Wildlife Encounters",
    }

    for ttype, threats in sorted(by_type.items()):
        label = type_labels.get(ttype, ttype.title())
        with st.expander(label, expanded=False):
            for threat in sorted(threats, key=lambda x: -x.get("risk", 0)):
                risk_val = threat.get("risk", 0)
                st.markdown(f"**{threat.get('name', 'Unknown')}** ({risk_val}/5)")
                habitats = threat.get("habitats", [])
                if isinstance(habitats, list):
                    st.caption(f"Habitats: {', '.join(habitats)} | Max altitude: {threat.get('altitude_max_m', 'N/A')}m")
                else:
                    st.caption(f"Habitats: {habitats}")
                notes = threat.get("notes", "")
                if notes:
                    st.caption(notes)
                st.divider()


def _render_food_tab(active_country: str) -> None:
    """Render the Food tab -- all data loaded uniformly from JSON via _load_profile."""
    profile = _load_profile(active_country)
    if not profile or (not profile["dishes"] and not profile["drinks"]):
        st.info(f"Food information for {active_country} coming soon.")
        return

    st.markdown(f"## {active_country} -- Food & Cuisine")

    # Signature dishes
    if profile["dishes"]:
        st.markdown("### Signature Dishes")
        for dish in profile["dishes"]:
            emoji = dish.get("emoji", "")
            name = dish.get("name", "")
            desc = dish.get("description", "")
            with st.expander(f"{emoji} {name}".strip()):
                st.write(desc) if desc else st.caption("No description available.")

    st.divider()

    # Drinks grid
    if profile["drinks"]:
        st.markdown("### Drinks")
        drinks = profile["drinks"]
        cols = st.columns(min(len(drinks), 3))
        for i, drink in enumerate(drinks):
            with cols[i % len(cols)]:
                emoji = drink.get("emoji", "")
                name = drink.get("name", "")
                desc = drink.get("description", "")
                st.markdown(f"**{emoji} {name}**".strip())
                if desc:
                    st.caption(desc)

    st.divider()

    # Street food safety
    if profile["street_food"]:
        st.markdown("### Street Food Safety")
        st.info(profile["street_food"])

    # Vegetarian notes
    if profile["vegetarian"]:
        st.markdown("### Vegetarian Notes")
        st.caption(profile["vegetarian"])

    # Regional cuisine
    if profile["regional"]:
        st.markdown("### Regional Cuisine")
        st.caption(profile["regional"])


def _render_history_tab(active_country: str) -> None:
    """Render the History/Culture tab -- structured history entries + culture data from JSON."""
    profile = _load_profile(active_country)
    if not profile:
        st.info(f"Culture & history information for {active_country} coming soon.")
        return

    st.markdown(f"## {active_country} \u2014 History & Culture")

    # ── Structured history entries (new format: list of {title, content}) ──
    history_entries = profile.get("history_entries", [])
    if history_entries:
        st.markdown("### History")
        for entry in history_entries:
            if isinstance(entry, dict):
                title = entry.get("title", "")
                content = entry.get("content", "")
                with st.expander(title, expanded=False):
                    st.markdown(content)
            elif isinstance(entry, (list, tuple)) and len(entry) == 2:
                # legacy (title, content) tuple format
                with st.expander(entry[0], expanded=False):
                    st.markdown(entry[1])
        st.divider()

    # ── Culture data from culture key ──────────────────────────────────
    timeline = profile.get("history", [])
    culture_sections = [t for t in timeline if t[0] not in (e.get("title", "") for e in history_entries if isinstance(e, dict))]
    if culture_sections:
        st.markdown("### Culture")
        for title, content in culture_sections:
            with st.expander(title, expanded=True):
                for line in content.split("\n"):
                    if line.strip():
                        st.markdown(f"- {line}")
    elif not history_entries:
        st.info(f"Culture & history information for {active_country} coming soon.")


def _render_surf_tab(data: dict | None) -> None:
    """Render the Surf tab from country JSON outdoors.surf_spots."""
    spots = _get(data, "outdoors.surf_spots", [])
    if not spots:
        _no_data()
        return
    for spot in spots:
        if isinstance(spot, dict):
            name = spot.get("name", "Unknown")
            st.markdown(f"**{name}**")
            c1, c2, c3 = st.columns(3)
            if spot.get("region"):
                c1.caption(f"Region: {spot['region']}")
            bt = spot.get("break_type") or spot.get("wave_type")
            if bt:
                c2.caption(f"Break type: {bt}")
            if spot.get("difficulty"):
                c3.caption(f"Difficulty: {spot['difficulty']}")

            c4, c5 = st.columns(2)
            if spot.get("wave_direction"):
                c4.caption(f"Wave direction: {spot['wave_direction']}")
            wave_size = spot.get("typical_wave_size")
            if isinstance(wave_size, dict):
                peak = wave_size.get("peak_season", "")
                off = wave_size.get("off_season", "")
                c5.caption(f"Wave size: peak {peak}, off {off}")
            elif wave_size:
                c5.caption(f"Wave size: {wave_size}")

            best = spot.get("best_months")
            if best:
                if isinstance(best, list):
                    best = ", ".join(str(m) for m in best)
                st.caption(f"Best months: {best}")
            if spot.get("description"):
                st.caption(spot["description"])
            if spot.get("notes"):
                st.caption(f"Notes: {spot['notes']}")
            st.divider()
        else:
            st.markdown(f"- {spot}")


def _render_parks_tab(data: dict | None) -> None:
    """Render the Parks tab from country JSON outdoors.top_national_parks."""
    parks = _get(data, "outdoors.top_national_parks", [])
    if not parks:
        _no_data()
        return
    for park in parks:
        if isinstance(park, dict):
            name = park.get("name", "Unknown")
            desc = park.get("description", "")
            region = park.get("region", "")
            st.markdown(f"**{name}**")
            if region:
                st.caption(f"Region: {region}")
            if desc:
                st.caption(desc)
            best = park.get("best_months")
            if best:
                if isinstance(best, list):
                    best = ", ".join(str(m) for m in best)
                st.caption(f"Best months: {best}")
        elif isinstance(park, str):
            parts = park.split(" -- ", 1)
            if len(parts) == 2:
                st.markdown(f"**{parts[0].strip()}**")
                st.caption(parts[1].strip())
            else:
                st.markdown(f"- {park}")
        st.divider()


def _render_budget_tab(data: dict | None) -> None:
    """Render the Budget tab from country JSON budget section."""
    budget = _get(data, "budget")
    if not budget or not isinstance(budget, dict):
        _no_data()
        return

    currency = budget.get("currency") or _get(data, "language_and_money.currency", "---")
    st.markdown(f"**Currency:** {currency}")
    st.divider()

    tier_keys = [
        ("daily_budget_backpacker", "Backpacker"),
        ("daily_budget_midrange", "Midrange"),
        ("daily_budget_comfort", "Comfort"),
    ]
    has_tiers = any(budget.get(k) for k, _ in tier_keys)
    if has_tiers:
        st.markdown("**Daily Budget Tiers**")
        cols = st.columns(3)
        for i, (key, label) in enumerate(tier_keys):
            val = budget.get(key)
            if val:
                cols[i].metric(label, str(val))
        st.divider()

    tiers = budget.get("daily_budget_tiers") or budget.get("daily_budget")
    if tiers and not has_tiers:
        st.markdown("**Daily Budget Tiers**")
        if isinstance(tiers, dict):
            for tier, amount in tiers.items():
                st.caption(f"**{tier}**: {amount}")
        elif isinstance(tiers, list):
            for t in tiers:
                if isinstance(t, dict):
                    st.caption(f"**{t.get('tier', '')}**: {t.get('amount', t.get('range', ''))}")
                else:
                    st.caption(str(t))
        st.divider()

    cost_keys = [
        ("hostel_avg", "Hostel avg"),
        ("hotel_avg", "Hotel avg"),
        ("meal_avg", "Meal avg"),
        ("coffee_avg", "Coffee avg"),
        ("beer_avg", "Beer avg"),
        ("local_transport_avg", "Local transport avg"),
        ("sim_card_avg", "SIM card avg"),
        ("surfboard_rental_avg", "Surfboard rental avg"),
        ("coworking_day_pass_avg", "Coworking day pass avg"),
    ]
    st.markdown("**Average Costs**")
    for key, label in cost_keys:
        val = budget.get(key)
        if val:
            st.caption(f"{label}: {val}")

    vfm = budget.get("value_for_money")
    if vfm:
        st.divider()
        st.markdown(f"**Value for Money:** {vfm}")


def _render_travel_info_tab(data: dict | None) -> None:
    """Render the Travel Info tab -- visa, health, safety advisory."""
    # Visa
    st.markdown("### Visa & Entry")
    visa_section = _get(data, "entry_and_border.visa_requirements")
    if isinstance(visa_section, dict):
        for k, v in visa_section.items():
            st.caption(f"**{k.replace('_', ' ').title()}**: {v}")
    elif isinstance(visa_section, list):
        st.markdown("**Visa:** " + "; ".join(str(v) for v in visa_section))
    elif visa_section:
        st.markdown(f"**Visa:** {visa_section}")
    else:
        visa_oa = _get(data, "entry_and_border.visa_on_arrival")
        if visa_oa:
            st.markdown(f"**Visa on arrival:** {visa_oa}")

    passport = _get(data, "entry_and_border.passport_validity_rule")
    if passport:
        st.caption(f"Passport: {passport}")
    onward = _get(data, "entry_and_border.proof_of_onward_travel_required")
    if onward is not None:
        st.caption(f"Proof of onward travel required: {'Yes' if onward else 'No'}")

    st.divider()

    # Health
    st.markdown("### Health")
    health = _get(data, "health")
    if isinstance(health, dict):
        rec = health.get("recommended_vaccines") or health.get("vaccinations", [])
        if rec:
            if isinstance(rec, list):
                vax_names = []
                for v in rec:
                    if isinstance(v, dict):
                        vax_names.append(v.get("name", str(v)))
                    else:
                        vax_names.append(str(v))
                st.markdown("**Recommended vaccines:** " + ", ".join(vax_names))
            else:
                st.markdown(f"**Recommended vaccines:** {rec}")

        malaria = health.get("malaria_risk") or health.get("malaria")
        if malaria:
            st.caption(f"Malaria risk: {malaria}")

        altitude = health.get("altitude_sickness_risk") or health.get("altitude_sickness")
        if altitude:
            st.caption(f"Altitude sickness: {altitude}")

        water = health.get("tap_water_safe")
        if water is not None:
            st.caption(f"Tap water safe: {'Yes' if water else 'No'}")
        elif health.get("food_water_safety"):
            st.caption(f"Food/water safety: {health['food_water_safety']}")

    st.divider()

    # Safety advisory
    st.markdown("### Safety Advisory")
    safety = _get(data, "safety")
    if isinstance(safety, dict):
        level = safety.get("travel_advisory_level_us")
        label_text = safety.get("travel_advisory_level_label", "")
        if level:
            st.metric("US Travel Advisory Level", f"{level}/4 -- {label_text}")

        crime = safety.get("crime_risk")
        if crime:
            st.caption(f"Crime risk: {crime}")

        solo = safety.get("solo_female_travel_notes")
        if solo:
            st.caption(f"Solo female travel: {solo}")

        lgbtq = safety.get("lgbtq_notes")
        if lgbtq:
            st.caption(f"LGBTQ+ notes: {lgbtq}")

        emergency = safety.get("emergency_numbers")
        if isinstance(emergency, dict):
            parts = [f"{k}: {v}" for k, v in emergency.items()]
            st.markdown("**Emergency Numbers:** " + " | ".join(parts))
        elif emergency:
            st.markdown(f"**Emergency Numbers:** {emergency}")

        embassy = safety.get("embassy_contact_info")
        if isinstance(embassy, dict):
            for k, v in embassy.items():
                st.caption(f"**{k.replace('_', ' ').title()}**: {v}")


# ── Main entry point ─────────────────────────────────────────────────────────


def render_explore_page() -> None:
    """Main explore page entry point -- called from chat_page when in explore mode."""
    ##### added auto_snap this 4/14 -- trying to combat the lat lon out of bounds & location picker reverting to SA country (snapping back)
    auto_snap = st.toggle(
        "***** Auto-switch country from map click - Dev function with out toggle or every single country code mapped it will snap back to SA where we have jsons for every country ***** ",
        value=st.session_state.get("explore_auto_country_snap", False),
        key="explore_auto_country_snap",
    )
    registry = _discover_countries()
    all_countries = sorted(registry.keys())

    default_country = _detect_country()  # auto-detect from chat/session
    # Only use auto-detect as default if user hasn't manually selected
    if "explore_country_manual" not in st.session_state:
        st.session_state["explore_country_manual"] = default_country

    selected = st.selectbox(
        "🌍 Country",
        options=all_countries,
        index=all_countries.index(st.session_state["explore_country_manual"])
            if st.session_state["explore_country_manual"] in all_countries else 0,
        key="explore_country_manual",
        label_visibility="collapsed",
    )
    active_country = selected
    st.session_state["explore_country"] = active_country

        
    data = _load_country_json(active_country)      # pass the display name directly
    cc = _COUNTRY_CODE_MAP.get(active_country, active_country[:2].upper())

    flag = _FLAGS.get(cc, "\U0001f30d")
    if data:
        flag = _get(data, "identity.flag_emoji") or flag
        st.markdown(f"# {flag} Explore: {active_country}")

    # Tab navigation
    tab_map, tab_hikes, tab_wildlife, tab_food, tab_history, \
        tab_surf, tab_parks, tab_budget, tab_travel = st.tabs([
            "Map",
            "Hikes",
            "Wildlife",
            "Food",
            "History",
            "Surf",
            "Parks",
            "Budget",
            "Travel Info",
        ])

    with tab_map:
        _render_map_tab(active_country, data)

    with tab_hikes:
        st.markdown(f"### {active_country} Hikes")
        st.caption("Select a hike to see details and view it on the map.")
        _render_hikes_tab(active_country)

    with tab_wildlife:
        st.markdown(f"### {active_country} Wildlife Threats")
        _render_wildlife_tab(active_country)

    with tab_food:
        _render_food_tab(active_country)

    with tab_history:
        _render_history_tab(active_country)

    with tab_surf:
        st.markdown(f"### {active_country} -- Surf Spots")
        _render_surf_tab(data)

    with tab_parks:
        st.markdown(f"### {active_country} -- National Parks & Preserves")
        _render_parks_tab(data)

    with tab_budget:
        st.markdown(f"### {active_country} -- Budget & Costs")
        _render_budget_tab(data)

    with tab_travel:
        st.markdown(f"### {active_country} -- Travel Info")
        _render_travel_info_tab(data)
