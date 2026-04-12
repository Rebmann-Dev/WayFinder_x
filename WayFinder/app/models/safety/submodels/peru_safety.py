"""
peru_safety.py — Peru-specific safety model for WayFinder.
Mirrors the structure of ecuador_safety.py for easy extension to other countries.
"""
from __future__ import annotations
from typing import Any

# Peru bounding box
_PE_LAT_MIN, _PE_LAT_MAX = -18.35, -0.01
_PE_LON_MIN, _PE_LON_MAX = -81.33, -68.65

_REGION_RISK: dict[str, dict[str, Any]] = {
    "Lima":              {"risk": 3, "homicide_rate": 12.0, "notes": "Lima Metropolitana: petty crime high in Miraflores/Barranco at night; avoid Callao port area; tourist zones generally safe"},
    "Callao":            {"risk": 4, "homicide_rate": 35.0, "notes": "Port city adjoining Lima; gang violence, drug trafficking; avoid at night"},
    "Cusco":             {"risk": 2, "homicide_rate": 5.0,  "notes": "Very popular tourist city; petty theft on trains and markets; altitude 3400m"},
    "Puno":              {"risk": 3, "homicide_rate": 8.0,  "notes": "Lake Titicaca; political protests common; altitude 3800m"},
    "Arequipa":          {"risk": 2, "homicide_rate": 6.0,  "notes": "White City; generally safe for tourists; Colca Canyon base"},
    "Loreto":            {"risk": 3, "homicide_rate": 14.0, "notes": "Amazon department; Iquitos accessible by air/river only; drug trafficking in remote areas"},
    "Ucayali":           {"risk": 3, "homicide_rate": 16.0, "notes": "Amazon basin; Pucallpa has crime risk; river travel needs care"},
    "Madre de Dios":     {"risk": 3, "homicide_rate": 12.0, "notes": "Puerto Maldonado gateway to Manu; illegal gold mining regions dangerous; biodiversity hotspot"},
    "Huánuco":           {"risk": 4, "homicide_rate": 22.0, "notes": "VRAE region nearby; coca-growing area; drug-related violence; exercise caution"},
    "Ayacucho":          {"risk": 3, "homicide_rate": 10.0, "notes": "Historic Shining Path stronghold; now generally safe in city; rural VRAEM region still affected"},
    "San Martín":        {"risk": 3, "homicide_rate": 11.0, "notes": "Tarapoto safe for tourists; rural areas have drug trafficking routes"},
    "Amazonas":          {"risk": 2, "homicide_rate": 7.0,  "notes": "Chachapoyas and Kuelap ruins; low crime; remote"},
    "La Libertad":       {"risk": 3, "homicide_rate": 18.0, "notes": "Trujillo has gang crime; Chan Chan ruins; northern coast surfing"},
    "Piura":             {"risk": 3, "homicide_rate": 15.0, "notes": "Northern coast; Máncora beach popular; petty theft at beach"},
    "Tumbes":            {"risk": 3, "homicide_rate": 13.0, "notes": "Border with Ecuador; smuggling routes; mangrove reserves"},
    "Lambayeque":        {"risk": 2, "homicide_rate": 9.0,  "notes": "Chiclayo; Sipán archaeological site; generally safe"},
    "Ancash":            {"risk": 2, "homicide_rate": 6.0,  "notes": "Huaraz; Cordillera Blanca; world-class trekking; altitude risk high"},
    "Junín":             {"risk": 3, "homicide_rate": 13.0, "notes": "Huancayo; Mantaro Valley; some VRAEM influence in south"},
    "Pasco":             {"risk": 3, "homicide_rate": 11.0, "notes": "High altitude mining region; Cerro de Pasco at 4300m"},
    "Huancavelica":      {"risk": 3, "homicide_rate": 9.0,  "notes": "Remote highland; poverty; limited tourist infrastructure"},
    "Apurímac":          {"risk": 3, "homicide_rate": 10.0, "notes": "Abancay; remote Andes; coca region border"},
    "Moquegua":          {"risk": 2, "homicide_rate": 4.0,  "notes": "Safe southern region; copper mining area"},
    "Tacna":             {"risk": 2, "homicide_rate": 5.0,  "notes": "Chilean border; duty-free shopping; generally safe"},
    "Ica":               {"risk": 2, "homicide_rate": 7.0,  "notes": "Nazca Lines, Paracas, Huacachina; wine region; generally safe"},
    "Cajamarca":         {"risk": 2, "homicide_rate": 6.0,  "notes": "Northern sierra; historic Inca site; mining protests occasional"},
}

_REGION_CENTROIDS: dict[str, tuple[float, float]] = {
    "Lima":          (-12.04, -77.03),
    "Callao":        (-12.05, -77.15),
    "Cusco":         (-13.52, -71.97),
    "Puno":          (-15.84, -70.02),
    "Arequipa":      (-16.41, -71.54),
    "Loreto":        (-4.0,   -75.0),
    "Ucayali":       (-8.39,  -74.55),
    "Madre de Dios": (-12.59, -70.05),
    "Huánuco":       (-9.93,  -76.24),
    "Ayacucho":      (-13.16, -74.22),
    "San Martín":    (-6.49,  -76.36),
    "Amazonas":      (-6.23,  -77.87),
    "La Libertad":   (-8.12,  -79.03),
    "Piura":         (-5.19,  -80.63),
    "Tumbes":        (-3.57,  -80.45),
    "Lambayeque":    (-6.77,  -79.84),
    "Ancash":        (-9.53,  -77.53),
    "Junín":         (-11.99, -75.28),
    "Pasco":         (-10.67, -76.25),
    "Huancavelica":  (-12.79, -74.97),
    "Apurímac":      (-14.05, -73.09),
    "Moquegua":      (-17.19, -70.93),
    "Tacna":         (-18.01, -70.25),
    "Ica":           (-14.07, -75.73),
    "Cajamarca":     (-7.16,  -78.51),
}

_WILDLIFE_THREATS_PERU: list[dict[str, Any]] = [
    {
        "name": "Fer-de-lance (Bothrops atrox)",
        "risk": 5,
        "type": "venomous snake",
        "altitude_max_m": 2400,
        "habitats": ["amazon", "coastal_lowland", "cloud_forest"],
        "lat_zones": [(-18.0, -0.01)],
        "lon_zones": [(-81.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Most dangerous snake in Peru; responsible for most snakebite deaths; widespread in Amazon and cloud forest",
    },
    {
        "name": "Bushmaster (Lachesis muta)",
        "risk": 5,
        "type": "venomous snake",
        "altitude_max_m": 1000,
        "habitats": ["amazon"],
        "lat_zones": [(-18.0, -0.01)],
        "lon_zones": [(-78.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Largest venomous snake in Americas; Amazon basin only; attacks when cornered",
    },
    {
        "name": "Peruvian Coral Snake (Micrurus peruvianus)",
        "risk": 4,
        "type": "venomous snake",
        "altitude_max_m": 1800,
        "habitats": ["amazon", "coastal_lowland"],
        "lat_zones": [(-18.0, -0.01)],
        "lon_zones": [(-81.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Highly neurotoxic; red-yellow-black banding; hides in leaf litter and soil",
    },
    {
        "name": "Palm Pit Viper (Bothriechis lateralis)",
        "risk": 4,
        "type": "venomous snake",
        "altitude_max_m": 2000,
        "habitats": ["cloud_forest", "amazon"],
        "lat_zones": [(-14.0, -0.01)],
        "lon_zones": [(-78.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Arboreal; camouflaged in green foliage; bites at head height on forest trails",
    },
    {
        "name": "Black Caiman (Melanosuchus niger)",
        "risk": 4,
        "type": "large predator",
        "altitude_max_m": 300,
        "habitats": ["amazon"],
        "lat_zones": [(-14.0, -0.01)],
        "lon_zones": [(-78.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Amazon rivers and oxbow lakes; dangerous when approached; most aggressive during nesting",
    },
    {
        "name": "Spectacled Caiman (Caiman crocodilus)",
        "risk": 3,
        "type": "large predator",
        "altitude_max_m": 500,
        "habitats": ["amazon", "coastal_lowland"],
        "lat_zones": [(-18.0, -0.01)],
        "lon_zones": [(-81.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Widespread in lowland rivers; smaller than black caiman but still dangerous",
    },
    {
        "name": "Jaguar (Panthera onca)",
        "risk": 3,
        "type": "large predator",
        "altitude_max_m": 2000,
        "habitats": ["amazon", "cloud_forest"],
        "lat_zones": [(-18.0, -0.01)],
        "lon_zones": [(-81.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Primarily Manu and Madre de Dios; extremely rare encounter; nocturnal",
    },
    {
        "name": "Puma (Puma concolor)",
        "risk": 3,
        "type": "large predator",
        "altitude_max_m": 4500,
        "habitats": ["andes", "cloud_forest", "amazon"],
        "lat_zones": [(-18.0, -0.01)],
        "lon_zones": [(-81.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Widespread across Andes and Amazon; dawn/dusk active; rarely attacks humans",
    },
    {
        "name": "Giant Otter (Pteronura brasiliensis)",
        "risk": 2,
        "type": "large predator",
        "altitude_max_m": 400,
        "habitats": ["amazon"],
        "lat_zones": [(-14.0, -0.01)],
        "lon_zones": [(-78.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Territorial; Manu and Madre de Dios rivers; aggressive if pups nearby; keep 10m distance",
    },
    {
        "name": "Malaria mosquito (Anopheles)",
        "risk": 4,
        "type": "disease vector",
        "altitude_max_m": 1500,
        "habitats": ["amazon", "coastal_lowland"],
        "lat_zones": [(-18.0, -0.01)],
        "lon_zones": [(-81.0, -68.65)],
        "seasonality": "wet_season",
        "peak_months": [11, 12, 1, 2, 3, 4, 5],
        "notes": "Malaria risk below 1500m throughout Amazon and northern coast; prophylaxis essential for jungle travel",
    },
    {
        "name": "Dengue/Zika mosquito (Aedes aegypti)",
        "risk": 3,
        "type": "disease vector",
        "altitude_max_m": 2200,
        "habitats": ["amazon", "coastal_lowland", "urban"],
        "lat_zones": [(-18.0, -0.01)],
        "lon_zones": [(-81.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Present in all lowland cities including Lima; use repellent year-round",
    },
    {
        "name": "Wandering Spider (Phoneutria fera)",
        "risk": 4,
        "type": "venomous spider",
        "altitude_max_m": 1500,
        "habitats": ["amazon", "coastal_lowland"],
        "lat_zones": [(-18.0, -0.01)],
        "lon_zones": [(-81.0, -68.65)],
        "seasonality": "year_round",
        "notes": "One of world's most venomous; hides in boots, clothing, banana clusters; shake gear before wearing",
    },
    {
        "name": "Bullet ant (Paraponera clavata)",
        "risk": 3,
        "type": "venomous insect",
        "altitude_max_m": 1500,
        "habitats": ["amazon", "cloud_forest"],
        "lat_zones": [(-14.0, -0.01)],
        "lon_zones": [(-80.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Extremely painful sting rated highest on Schmidt Pain Index; not lethal but incapacitating for 24hrs",
    },
    {
        "name": "Botfly (Dermatobia hominis)",
        "risk": 3,
        "type": "parasitic insect",
        "altitude_max_m": 2000,
        "habitats": ["amazon", "cloud_forest"],
        "lat_zones": [(-14.0, -0.01)],
        "lon_zones": [(-81.0, -68.65)],
        "seasonality": "wet_season",
        "peak_months": [11, 12, 1, 2, 3, 4, 5],
        "notes": "Larvae burrow under skin; painful subcutaneous infestation; wear long sleeves in jungle",
    },
    {
        "name": "Candiru (Vandellia cirrhosa)",
        "risk": 3,
        "type": "parasitic fish",
        "altitude_max_m": 300,
        "habitats": ["amazon"],
        "lat_zones": [(-14.0, -0.01)],
        "lon_zones": [(-78.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Tiny parasitic catfish in Amazon rivers; wear protective swimwear; do not urinate in water",
    },
    {
        "name": "Electric Eel (Electrophorus electricus)",
        "risk": 3,
        "type": "electric fish",
        "altitude_max_m": 400,
        "habitats": ["amazon"],
        "lat_zones": [(-14.0, -0.01)],
        "lon_zones": [(-78.0, -68.65)],
        "seasonality": "year_round",
        "notes": "600V discharge; avoid wading in murky Amazon waterways",
    },
    {
        "name": "Vampire bat (Desmodus rotundus)",
        "risk": 3,
        "type": "rabies vector",
        "altitude_max_m": 2000,
        "habitats": ["amazon", "rural"],
        "lat_zones": [(-18.0, -0.01)],
        "lon_zones": [(-81.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Rabies transmission risk; avoid sleeping in open structures; bites often unfelt during sleep",
    },
    {
        "name": "Altitude sickness (AMS/HACE/HAPE)",
        "risk": 4,
        "type": "environmental",
        "altitude_min_m": 2500,
        "altitude_max_m": 6768,
        "habitats": ["andes"],
        "lat_zones": [(-18.35, -0.01)],
        "lon_zones": [(-81.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Cusco 3400m, Puno 3800m, Cerro de Pasco 4300m; acclimatize 2+ days; descend immediately if HACE/HAPE symptoms appear",
    },
    {
        "name": "Flash flood / huaico",
        "risk": 4,
        "type": "weather",
        "habitats": ["andes", "cloud_forest"],
        "lat_zones": [(-18.35, -0.01)],
        "lon_zones": [(-81.0, -68.65)],
        "seasonality": "wet_season",
        "peak_months": [11, 12, 1, 2, 3, 4],
        "notes": "Huaicos (Andean debris flows) kill dozens yearly Nov-Apr; Inca Trail and mountain roads at risk; check local alerts",
    },
    {
        "name": "Piranha (Pygocentrus nattereri)",
        "risk": 2,
        "type": "predatory fish",
        "altitude_max_m": 300,
        "habitats": ["amazon"],
        "lat_zones": [(-14.0, -0.01)],
        "lon_zones": [(-78.0, -68.65)],
        "seasonality": "dry_season",
        "peak_months": [6, 7, 8, 9, 10],
        "notes": "Attack risk highest in dry season when water recedes and fish concentrate; avoid swimming in murky river shallows",
    },
    {
        "name": "Stingray (Potamotrygon spp.)",
        "risk": 3,
        "type": "venomous fish",
        "altitude_max_m": 300,
        "habitats": ["amazon"],
        "lat_zones": [(-14.0, -0.01)],
        "lon_zones": [(-78.0, -68.65)],
        "seasonality": "year_round",
        "notes": "Freshwater stingrays buried in Amazon riverbeds; shuffle feet when wading; extremely painful sting",
    },
]


def _haversine_km(lat1, lon1, lat2, lon2):
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

class PeruSafetyModel:
    def is_peru(self, lat, lon):
        return (_PE_LAT_MIN <= lat <= _PE_LAT_MAX) and (_PE_LON_MIN <= lon <= _PE_LON_MAX)

    def _nearest_region(self, lat, lon):
        best, best_d = "Lima", float("inf")
        for region, (rlat, rlon) in _REGION_CENTROIDS.items():
            d = _haversine_km(lat, lon, rlat, rlon)
            if d < best_d:
                best_d = d
                best = region
        return best

    def _wildlife_threats_for_location(self, lat, lon, altitude_m=0.0, month=None):
        active = []
        for threat in _WILDLIFE_THREATS_PERU:
            in_lat = any(z[0] <= lat <= z[1] for z in threat.get("lat_zones", [(-90, 90)]))
            alt_max = threat.get("altitude_max_m", 9999)
            alt_min = threat.get("altitude_min_m", 0)
            in_alt = alt_min <= altitude_m <= alt_max
            if in_lat and in_alt:
                threat_copy = {k: v for k, v in threat.items() if k not in ("lat_zones", "lon_zones")}
                active.append(threat_copy)
        return active

    def assess(self, latitude, longitude, country=None, altitude_m=0.0, travel_month=None):
        if not self.is_peru(latitude, longitude):
            return {"applicable": False, "message": "Location is outside Peru."}
        region = self._nearest_region(latitude, longitude)
        region_data = _REGION_RISK.get(region, {"risk": 3, "homicide_rate": 12.0, "notes": ""})
        crime_risk = region_data["risk"]
        threats = self._wildlife_threats_for_location(latitude, longitude, altitude_m, travel_month)
        wildlife_risk = max((t["risk"] for t in threats), default=1)
        overall_risk = min(5, max(crime_risk, wildlife_risk))
        return {
            "applicable": True,
            "overall_risk": overall_risk,
            "crime_risk": crime_risk,
            "wildlife_risk": wildlife_risk,
            "region": region,
            "homicide_rate_per_100k": region_data.get("homicide_rate"),
            "crime_notes": region_data.get("notes"),
            "active_wildlife_threats": [t["name"] for t in threats],
            "wildlife_threat_details": threats,
            "source": "INEI 2024, US State Dept, UNODC, IUCN",
        }
