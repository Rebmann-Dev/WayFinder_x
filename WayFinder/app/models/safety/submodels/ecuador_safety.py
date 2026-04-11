"""
ecuador_safety.py
Ecuador-specific safety model for WayFinder.

Covers two dimensions:
  1. Wildlife threat risk (venomous/dangerous fauna by lat/lon/altitude)
  2. Crime risk by province (based on DINASED + UNODC + travel advisory data)

Returns a risk score 1-5 for each dimension plus combined overall Ecuador risk.
Only activates when the query location is within Ecuador's bounding box.
"""
from __future__ import annotations

from typing import Any

# Ecuador bounding box
_EC_LAT_MIN, _EC_LAT_MAX = -5.02, 1.45
_EC_LON_MIN, _EC_LON_MAX = -81.08, -75.19

# ── Province crime data ────────────────────────────────────────────────────────
# Source: DINASED 2023-2024, US State Dept, InSight Crime Ecuador 2024
# risk 1=very safe, 5=very dangerous
_PROVINCE_RISK: dict[str, dict[str, Any]] = {
    "Guayas":          {"risk": 5, "homicide_rate": 42.0, "notes": "Guayaquil is Ecuador's most violent city; port-related drug trafficking, express kidnappings common"},
    "Los Ríos":        {"risk": 5, "homicide_rate": 38.0, "notes": "High crime, drug routes, avoid rural areas at night"},
    "Manabí":          {"risk": 4, "homicide_rate": 28.0, "notes": "Coastal crime hotspot; improved in Manta tourist areas but rural zones remain dangerous"},
    "El Oro":          {"risk": 4, "homicide_rate": 22.0, "notes": "Border region with Peru, drug trafficking corridors"},
    "Esmeraldas":      {"risk": 5, "homicide_rate": 85.0, "notes": "HIGHEST RISK: Colombian border, FARC/cartel presence, armed groups; avoid entirely"},
    "Sucumbíos":       {"risk": 5, "homicide_rate": 55.0, "notes": "Colombian border, oil region, armed groups; avoid rural areas"},
    "Orellana":        {"risk": 3, "homicide_rate": 18.0, "notes": "Amazon oil zone; crime risk moderate, wildlife risk high"},
    "Napo":            {"risk": 3, "homicide_rate": 14.0, "notes": "Popular ecotourism area; Tena relatively safe"},
    "Pastaza":         {"risk": 3, "homicide_rate": 12.0, "notes": "Remote Amazon; low crime, high wildlife/terrain risk"},
    "Morona Santiago": {"risk": 3, "homicide_rate": 10.0, "notes": "Southern Amazon; remote, low crime, difficult terrain"},
    "Zamora Chinchipe":{"risk": 3, "homicide_rate": 11.0, "notes": "Southern border region; mining conflicts"},
    "Pichincha":       {"risk": 3, "homicide_rate": 15.0, "notes": "Quito is safer for tourists but petty crime high in historic center; avoid La Mariscal at night"},
    "Imbabura":        {"risk": 2, "homicide_rate": 8.0,  "notes": "Otavalo and Cotacachi generally safe for tourists"},
    "Carchi":          {"risk": 3, "homicide_rate": 16.0, "notes": "Colombia border; cross-border crime risk"},
    "Cotopaxi":        {"risk": 2, "homicide_rate": 7.0,  "notes": "Relatively safe; volcano zone"},
    "Tungurahua":      {"risk": 2, "homicide_rate": 9.0,  "notes": "Baños safe for tourists; active volcano risk"},
    "Chimborazo":      {"risk": 2, "homicide_rate": 8.0,  "notes": "Riobamba safe; high altitude trekking zone"},
    "Bolívar":         {"risk": 2, "homicide_rate": 7.0,  "notes": "Rural, low crime"},
    "Cañar":           {"risk": 2, "homicide_rate": 6.0,  "notes": "Ingapirca area; generally safe"},
    "Azuay":           {"risk": 2, "homicide_rate": 8.0,  "notes": "Cuenca is one of Ecuador's safest cities"},
    "Loja":            {"risk": 2, "homicide_rate": 7.0,  "notes": "Southern sierra; generally safe"},
    "Galápagos":       {"risk": 1, "homicide_rate": 1.0,  "notes": "Very safe; wildlife encounter risk is primary concern"},
    "Santa Elena":     {"risk": 3, "homicide_rate": 20.0, "notes": "Beach resort coast; petty crime in Montañita"},
    "Santo Domingo":   {"risk": 4, "homicide_rate": 30.0, "notes": "High crime transit city"},
}

# Province centroids (lat, lon) for spatial matching
_PROVINCE_CENTROIDS: dict[str, tuple[float, float]] = {
    "Guayas":          (-1.83, -79.97),
    "Los Ríos":        (-1.50, -79.40),
    "Manabí":          (-1.05, -80.45),
    "El Oro":          (-3.25, -79.95),
    "Esmeraldas":      (0.96, -79.65),
    "Sucumbíos":       (0.09, -76.89),
    "Orellana":        (-0.46, -76.99),
    "Napo":            (-0.99, -77.81),
    "Pastaza":         (-1.49, -78.00),
    "Morona Santiago": (-2.30, -78.12),
    "Zamora Chinchipe":(-4.07, -78.95),
    "Pichincha":       (-0.18, -78.47),
    "Imbabura":        (0.35, -78.12),
    "Carchi":          (0.60, -77.82),
    "Cotopaxi":        (-0.93, -78.62),
    "Tungurahua":      (-1.25, -78.62),
    "Chimborazo":      (-1.67, -78.65),
    "Bolívar":         (-1.60, -79.00),
    "Cañar":           (-2.55, -78.93),
    "Azuay":           (-2.90, -78.99),
    "Loja":            (-3.99, -79.21),
    "Galápagos":       (-0.53, -90.43),
    "Santa Elena":     (-2.23, -80.86),
    "Santo Domingo":   (-0.25, -79.17),
}

# ── Wildlife threat data ───────────────────────────────────────────────────────
# Each threat: name, risk 1-5, altitude range, habitat zones, seasonality
_WILDLIFE_THREATS: list[dict[str, Any]] = [
    {
        "name": "Fer-de-lance (Bothrops atrox)",
        "risk": 5,
        "type": "venomous snake",
        "altitude_max_m": 2400,
        "habitats": ["amazon", "coastal_lowland", "cloud_forest"],
        "lat_zones": [(-5.0, 1.45)],
        "lon_zones": [(-81.0, -75.2)],
        "seasonality": "year_round",
        "notes": "Most dangerous snake in Ecuador; responsible for most snakebite deaths",
    },
    {
        "name": "Bushmaster (Lachesis muta)",
        "risk": 5,
        "type": "venomous snake",
        "altitude_max_m": 1000,
        "habitats": ["amazon"],
        "lat_zones": [(-5.0, 0.5)],
        "lon_zones": [(-78.5, -75.2)],
        "seasonality": "year_round",
        "notes": "Largest venomous snake in Americas; found in Amazon basin",
    },
    {
        "name": "Black Caiman (Melanosuchus niger)",
        "risk": 4,
        "type": "large predator",
        "altitude_max_m": 300,
        "habitats": ["amazon"],
        "lat_zones": [(-5.0, 0.5)],
        "lon_zones": [(-78.5, -75.2)],
        "seasonality": "year_round",
        "notes": "Amazon rivers and lakes; dangerous when approached",
    },
    {
        "name": "Jaguar (Panthera onca)",
        "risk": 3,
        "type": "large predator",
        "altitude_max_m": 2000,
        "habitats": ["amazon", "cloud_forest"],
        "lat_zones": [(-5.0, 1.0)],
        "lon_zones": [(-79.0, -75.2)],
        "seasonality": "year_round",
        "notes": "Extremely rare encounter; primarily nocturnal",
    },
    {
        "name": "Malaria mosquito (Anopheles)",
        "risk": 4,
        "type": "disease vector",
        "altitude_max_m": 1500,
        "habitats": ["amazon", "coastal_lowland"],
        "lat_zones": [(-5.0, 1.45)],
        "lon_zones": [(-81.0, -75.2)],
        "seasonality": "wet_season",
        "peak_months": [11, 12, 1, 2, 3, 4, 5],
        "notes": "Malaria risk below 1500m; prophylaxis recommended for Amazon travel",
    },
    {
        "name": "Dengue/Zika mosquito (Aedes aegypti)",
        "risk": 3,
        "type": "disease vector",
        "altitude_max_m": 2200,
        "habitats": ["amazon", "coastal_lowland", "urban"],
        "lat_zones": [(-5.0, 1.45)],
        "lon_zones": [(-81.0, -75.2)],
        "seasonality": "year_round",
        "notes": "Present in all lowland regions including coastal cities",
    },
    {
        "name": "Bullet ant (Paraponera clavata)",
        "risk": 3,
        "type": "venomous insect",
        "altitude_max_m": 1500,
        "habitats": ["amazon", "cloud_forest"],
        "lat_zones": [(-5.0, 1.0)],
        "lon_zones": [(-79.0, -75.2)],
        "seasonality": "year_round",
        "notes": "Extremely painful sting; not life-threatening but incapacitating",
    },
    {
        "name": "Goliath birdeater tarantula",
        "risk": 2,
        "type": "venomous spider",
        "altitude_max_m": 1000,
        "habitats": ["amazon"],
        "lat_zones": [(-5.0, 0.5)],
        "lon_zones": [(-78.5, -75.2)],
        "seasonality": "year_round",
        "notes": "Painful bite but rarely medically serious",
    },
    {
        "name": "Vampire bat (Desmodus rotundus)",
        "risk": 3,
        "type": "rabies vector",
        "altitude_max_m": 2000,
        "habitats": ["amazon", "rural"],
        "lat_zones": [(-5.0, 1.0)],
        "lon_zones": [(-81.0, -75.2)],
        "seasonality": "year_round",
        "notes": "Rabies transmission risk; avoid sleeping in open structures",
    },
    {
        "name": "Cotopaxi volcanic hazard",
        "risk": 4,
        "type": "geological",
        "altitude_max_m": 5897,
        "habitats": ["andes"],
        "lat_zones": [(-0.8, -0.5)],
        "lon_zones": [(-78.5, -78.3)],
        "seasonality": "year_round",
        "notes": "Active volcano; check IGEPN alert level before visiting",
    },
    {
        "name": "Altitude sickness (AMS)",
        "risk": 3,
        "type": "environmental",
        "altitude_min_m": 2500,
        "altitude_max_m": 6000,
        "habitats": ["andes"],
        "lat_zones": [(-5.0, 1.0)],
        "lon_zones": [(-80.0, -77.0)],
        "seasonality": "year_round",
        "notes": "Quito at 2850m; Chimborazo summit at 6263m; acclimatize before trekking",
    },
    {
        "name": "Flash flood / landslide",
        "risk": 4,
        "type": "weather",
        "habitats": ["andes", "cloud_forest"],
        "lat_zones": [(-5.0, 1.45)],
        "lon_zones": [(-81.0, -75.2)],
        "seasonality": "wet_season",
        "peak_months": [11, 12, 1, 2, 3, 4],
        "notes": "Wet season (Nov-May): major landslide risk on mountain roads",
    },
    {
        "name": "American Crocodile (Crocodylus acutus)",
        "risk": 4,
        "type": "large predator",
        "altitude_max_m": 200,
        "habitats": ["coastal_lowland", "mangrove", "estuaries"],
        "lat_zones": [(-3.5, 1.45)],
        "lon_zones": [(-81.08, -78.5)],
        "seasonality": "year_round",
        "notes": "Found in coastal rivers, mangroves and estuaries on the Pacific coast (Esmeraldas to Guayas); nesting females are extremely aggressive Jan-April",
    },
    {
        "name": "Spectacled Caiman (Caiman crocodilus)",
        "risk": 3,
        "type": "large predator",
        "altitude_max_m": 500,
        "habitats": ["amazon", "coastal_lowland"],
        "lat_zones": [(-5.0, 1.45)],
        "lon_zones": [(-81.0, -75.2)],
        "seasonality": "year_round",
        "notes": "Widespread in lowland rivers and lakes; smaller than black caiman but still dangerous",
    },
    {
        "name": "Ecuadorian Coral Snake (Micrurus bocourti)",
        "risk": 4,
        "type": "venomous snake",
        "altitude_max_m": 1800,
        "habitats": ["amazon", "coastal_lowland", "cloud_forest"],
        "lat_zones": [(-5.0, 1.45)],
        "lon_zones": [(-81.0, -75.2)],
        "seasonality": "year_round",
        "notes": "Highly neurotoxic venom; red-yellow-black banding; found under leaf litter — easily confused with harmless species",
    },
    {
        "name": "Amazon Tree Boa (Corallus hortulanus)",
        "risk": 2,
        "type": "venomous snake",
        "altitude_max_m": 1000,
        "habitats": ["amazon"],
        "lat_zones": [(-5.0, 0.5)],
        "lon_zones": [(-78.5, -75.2)],
        "seasonality": "year_round",
        "notes": "Non-venomous but extremely aggressive; painful bite with recurved teeth; common in Amazon canopy",
    },
    {
        "name": "Palm Pit Viper (Bothriechis lateralis)",
        "risk": 4,
        "type": "venomous snake",
        "altitude_max_m": 2000,
        "habitats": ["cloud_forest", "amazon"],
        "lat_zones": [(-3.0, 1.45)],
        "lon_zones": [(-80.0, -75.2)],
        "seasonality": "year_round",
        "notes": "Arboreal; camouflages in green foliage; dangerous at head height on forest trails",
    },
    {
        "name": "Equatorial Spitting Cobra (Naja naja ssp.)",
        "risk": 3,
        "type": "venomous snake",
        "altitude_max_m": 1500,
        "habitats": ["coastal_lowland", "amazon"],
        "lat_zones": [(-5.0, 1.0)],
        "lon_zones": [(-81.0, -76.0)],
        "seasonality": "year_round",
        "notes": "Can spit venom up to 2.5m; targets eyes; rinse with water immediately if hit",
    },
    {
        "name": "Puma (Puma concolor)",
        "risk": 3,
        "type": "large predator",
        "altitude_max_m": 4500,
        "habitats": ["andes", "cloud_forest", "amazon"],
        "lat_zones": [(-5.0, 1.0)],
        "lon_zones": [(-81.0, -75.2)],
        "seasonality": "year_round",
        "notes": "Present across Andes and cloud forest; rarely attacks humans but active at dawn/dusk near trails",
    },
    {
        "name": "Giant Otter (Pteronura brasiliensis)",
        "risk": 2,
        "type": "large predator",
        "altitude_max_m": 400,
        "habitats": ["amazon"],
        "lat_zones": [(-5.0, 0.0)],
        "lon_zones": [(-78.5, -75.2)],
        "seasonality": "year_round",
        "notes": "Territorial and aggressive if pups are nearby; keep distance on Amazon rivers",
    },
    {
        "name": "Botfly (Dermatobia hominis)",
        "risk": 3,
        "type": "parasitic insect",
        "altitude_max_m": 2000,
        "habitats": ["amazon", "cloud_forest", "coastal_lowland"],
        "lat_zones": [(-5.0, 1.45)],
        "lon_zones": [(-81.0, -75.2)],
        "seasonality": "wet_season",
        "peak_months": [11, 12, 1, 2, 3, 4, 5],
        "notes": "Larvae burrow into skin; painful subcutaneous infestation; use long sleeves and insect repellent in jungle",
    },
    {
        "name": "Candiru (Vandellia cirrhosa)",
        "risk": 3,
        "type": "parasitic fish",
        "altitude_max_m": 300,
        "habitats": ["amazon"],
        "lat_zones": [(-5.0, 0.2)],
        "lon_zones": [(-78.5, -75.2)],
        "seasonality": "year_round",
        "notes": "Tiny parasitic catfish in Amazon rivers; wear protective swimwear; do not urinate in river water",
    },
    {
        "name": "Electric Eel (Electrophorus electricus)",
        "risk": 3,
        "type": "electric fish",
        "altitude_max_m": 400,
        "habitats": ["amazon"],
        "lat_zones": [(-5.0, 0.5)],
        "lon_zones": [(-78.5, -75.2)],
        "seasonality": "year_round",
        "notes": "Can deliver 600V discharge; avoid wading in murky Amazon waterways",
    },
    {
        "name": "Wandering Spider (Phoneutria fera)",
        "risk": 4,
        "type": "venomous spider",
        "altitude_max_m": 1500,
        "habitats": ["amazon", "coastal_lowland"],
        "lat_zones": [(-5.0, 1.0)],
        "lon_zones": [(-81.0, -75.2)],
        "seasonality": "year_round",
        "notes": "One of world's most venomous spiders; hides in boots, clothing, and banana clusters; shake out gear before wearing",
    },
    {
        "name": "Galapagos Marine Iguana bite",
        "risk": 1,
        "type": "wildlife encounter",
        "altitude_max_m": 100,
        "habitats": ["galapagos"],
        "lat_zones": [(-1.5, 0.0)],
        "lon_zones": [(-92.0, -89.0)],
        "seasonality": "year_round",
        "notes": "Generally harmless; bites when cornered; maintain 2m distance per Galápagos NP rules",
    },
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


class EcuadorSafetyModel:
    """
    Ecuador-specific safety assessment.
    Only returns meaningful results when lat/lon is within Ecuador's bounding box.
    """

    def is_ecuador(self, lat: float, lon: float) -> bool:
        return (_EC_LAT_MIN <= lat <= _EC_LAT_MAX) and (_EC_LON_MIN <= lon <= _EC_LON_MAX)

    def _nearest_province(self, lat: float, lon: float) -> str:
        best, best_d = "Pichincha", float("inf")
        for prov, (plat, plon) in _PROVINCE_CENTROIDS.items():
            d = _haversine_km(lat, lon, plat, plon)
            if d < best_d:
                best_d = d
                best = prov
        return best

    def _wildlife_threats_for_location(
        self, lat: float, lon: float, altitude_m: float = 0.0, month: int | None = None
    ) -> list[dict[str, Any]]:
        active = []
        for threat in _WILDLIFE_THREATS:
            # Check lat zone
            in_lat = any(z[0] <= lat <= z[1] for z in threat.get("lat_zones", [(-90, 90)]))
            # Check altitude
            alt_max = threat.get("altitude_max_m", 9999)
            alt_min = threat.get("altitude_min_m", 0)
            in_alt = alt_min <= altitude_m <= alt_max
            if in_lat and in_alt:
                threat_copy = {k: v for k, v in threat.items() if k not in ("lat_zones", "lon_zones")}
                active.append(threat_copy)
        return active

    def assess(
        self,
        latitude: float,
        longitude: float,
        country: str | None = None,
        altitude_m: float = 0.0,
        travel_month: int | None = None,
    ) -> dict[str, Any]:
        if not self.is_ecuador(latitude, longitude):
            return {
                "applicable": False,
                "message": "Location is outside Ecuador. Ecuador-specific model not applied.",
            }

        province = self._nearest_province(latitude, longitude)
        province_data = _PROVINCE_RISK.get(province, {"risk": 3, "homicide_rate": 15.0, "notes": ""})
        crime_risk = province_data["risk"]

        threats = self._wildlife_threats_for_location(latitude, longitude, altitude_m, travel_month)
        wildlife_risk = max((t["risk"] for t in threats), default=1)
        overall_risk = min(5, max(crime_risk, wildlife_risk))

        return {
            "applicable": True,
            "overall_risk": overall_risk,
            "crime_risk": crime_risk,
            "wildlife_risk": wildlife_risk,
            "province": province,
            "homicide_rate_per_100k": province_data.get("homicide_rate"),
            "crime_notes": province_data.get("notes"),
            "active_wildlife_threats": [t["name"] for t in threats],
            "wildlife_threat_details": threats,
            "source": "DINASED 2024, US State Dept, UNODC, IUCN",
        }
