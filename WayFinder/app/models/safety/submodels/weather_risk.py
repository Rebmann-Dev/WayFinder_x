"""
weather_risk.py
WayFinder Travel Safety App — Seasonal Weather Risk Module

Assesses weather-based travel risk for a given location and travel date,
using the Open-Meteo historical climate API with a static-regional fallback.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARCHIVE_API = "https://archive-api.open-meteo.com/v1/archive"
ELEVATION_API = "https://api.open-meteo.com/v1/elevation"
HTTP_TIMEOUT = 5  # seconds

RISK_LABELS = {
    1: "Very Low",
    2: "Low",
    3: "Moderate",
    4: "High",
    5: "Extreme",
}

# Static bounding-box risk zones used as fallback when APIs are unavailable.
# Each entry: (min_lat, max_lat, min_lon, max_lon, risk_type, severity, description, months_active)
STATIC_RISK_ZONES: list[dict[str, Any]] = [
    # Monsoon Asia
    {
        "min_lat": 5, "max_lat": 35, "min_lon": 60, "max_lon": 140,
        "type": "monsoon_flooding",
        "severity": 4,
        "description": "Heavy monsoon rainfall causes widespread flooding and landslides.",
        "months_active": [6, 7, 8, 9],
    },
    # Caribbean / Gulf hurricane belt
    {
        "min_lat": 10, "max_lat": 30, "min_lon": -100, "max_lon": -55,
        "type": "tropical_cyclone",
        "severity": 4,
        "description": "Active Atlantic hurricane season brings destructive winds and storm surge.",
        "months_active": [6, 7, 8, 9, 10, 11],
    },
    # West Africa malaria / disease-vector belt
    {
        "min_lat": -5, "max_lat": 20, "min_lon": -18, "max_lon": 50,
        "type": "disease_vector",
        "severity": 3,
        "description": "High mosquito activity increases risk of malaria and other vector-borne diseases.",
        "months_active": [4, 5, 6, 7, 8, 9, 10],
    },
    # Andean high altitude
    {
        "min_lat": -55, "max_lat": 12, "min_lon": -82, "max_lon": -60,
        "type": "altitude_sickness",
        "severity": 3,
        "description": "High-altitude terrain (Andes) poses altitude sickness and hypothermia risk.",
        "months_active": list(range(1, 13)),
    },
    # Sahara / Arabian extreme heat
    {
        "min_lat": 15, "max_lat": 38, "min_lon": -18, "max_lon": 60,
        "type": "extreme_heat",
        "severity": 4,
        "description": "Extreme temperatures and sandstorms common in Sahara and Arabian Peninsula.",
        "months_active": [4, 5, 6, 7, 8, 9],
    },
    # Himalayan / Tibetan altitude & cold
    {
        "min_lat": 26, "max_lat": 40, "min_lon": 68, "max_lon": 105,
        "type": "altitude_sickness",
        "severity": 5,
        "description": "Very high elevation terrain (Himalayas, Tibet) with extreme cold and altitude risk.",
        "months_active": list(range(1, 13)),
    },
    # Bangladesh / Ganges Delta flood
    {
        "min_lat": 20, "max_lat": 27, "min_lon": 85, "max_lon": 95,
        "type": "flood",
        "severity": 4,
        "description": "Low-lying delta regions subject to severe monsoon flooding.",
        "months_active": [6, 7, 8, 9],
    },
    # Tornado alley USA
    {
        "min_lat": 25, "max_lat": 50, "min_lon": -105, "max_lon": -85,
        "type": "severe_storm",
        "severity": 3,
        "description": "Tornado and severe thunderstorm risk in central North America.",
        "months_active": [3, 4, 5, 6],
    },
]


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _month_name(month: int) -> str:
    return datetime(2000, month, 1).strftime("%B")


def _months_to_names(months: list[int]) -> str:
    return ", ".join(_month_name(m) for m in sorted(set(months)))


def _get_elevation(lat: float, lon: float) -> float | None:
    """Return elevation in metres for a point, or None on failure."""
    try:
        resp = requests.get(
            ELEVATION_API,
            params={"latitude": lat, "longitude": lon},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        elevations = data.get("elevation", [])
        if elevations:
            return float(elevations[0])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Elevation API failed: %s", exc)
    return None


def _fetch_climate_stats(
    lat: float,
    lon: float,
    target_month: int,
) -> dict[str, Any] | None:
    """
    Fetch mean monthly precipitation and temperature for *target_month* using
    five years of historical hourly data from Open-Meteo archive.

    Returns a dict with keys: avg_precip_mm, avg_temp_c, max_temp_c
    or None if the request fails.
    """
    today = date.today()
    # Use last 5 complete instances of that month
    results: list[dict[str, float]] = []

    for years_back in range(1, 6):
        year = today.year - years_back
        # First and last day of the target month in that year
        start = date(year, target_month, 1)
        if target_month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, target_month + 1, 1) - timedelta(days=1)

        try:
            resp = requests.get(
                ARCHIVE_API,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "hourly": "precipitation,temperature_2m",
                    "timezone": "UTC",
                },
                timeout=HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            hourly = data.get("hourly", {})
            precip_values = [v for v in hourly.get("precipitation", []) if v is not None]
            temp_values = [v for v in hourly.get("temperature_2m", []) if v is not None]
            if precip_values and temp_values:
                results.append(
                    {
                        "total_precip": sum(precip_values),
                        "avg_temp": sum(temp_values) / len(temp_values),
                        "max_temp": max(temp_values),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Archive API failed for %s-%02d: %s", year, target_month, exc)

    if not results:
        return None

    avg_precip = sum(r["total_precip"] for r in results) / len(results)
    avg_temp = sum(r["avg_temp"] for r in results) / len(results)
    max_temp = max(r["max_temp"] for r in results)

    return {
        "avg_precip_mm": round(avg_precip, 1),
        "avg_temp_c": round(avg_temp, 1),
        "max_temp_c": round(max_temp, 1),
    }


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------

class WeatherRiskAssessor:
    """
    Assesses seasonal weather risk for a travel location.

    Usage:
        assessor = WeatherRiskAssessor()
        result = assessor.assess(lat=27.98, lon=86.92, travel_date=date(2025, 7, 1))
    """

    def assess(
        self,
        lat: float,
        lon: float,
        travel_date: date | None = None,
        country: str | None = None,
    ) -> dict[str, Any]:
        """
        Assess weather risk for the given coordinates and optional travel date.

        Parameters
        ----------
        lat : float
            Latitude of the destination.
        lon : float
            Longitude of the destination.
        travel_date : date | None
            Intended travel date. If None, uses today's date.
        country : str | None
            ISO-3166 country code (optional, reserved for future enrichment).

        Returns
        -------
        dict with keys:
            weather_risk_score   int 1-5
            weather_risk_label   str
            risks                list[dict]
            travel_month_assessment str
            source               str
        """
        travel_date = travel_date or date.today()
        target_month = travel_date.month

        # --- Attempt live API path ---
        try:
            return self._assess_live(lat, lon, target_month, travel_date)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Live API assessment failed (%s); falling back to static rules.", exc
            )
            return self._assess_static(lat, lon, target_month, travel_date)

    # ------------------------------------------------------------------
    # Live API assessment
    # ------------------------------------------------------------------

    def _assess_live(
        self,
        lat: float,
        lon: float,
        target_month: int,
        travel_date: date,
    ) -> dict[str, Any]:
        climate = _fetch_climate_stats(lat, lon, target_month)
        if climate is None:
            raise RuntimeError("Climate API returned no data.")

        elevation = _get_elevation(lat, lon)  # may be None

        risks: list[dict[str, Any]] = []

        # --- Precipitation / flood risk ---
        precip = climate["avg_precip_mm"]
        if precip >= 300:
            risks.append(
                {
                    "type": "flood_landslide",
                    "severity": 5,
                    "description": (
                        f"Exceptionally high monthly precipitation ({precip} mm) creates "
                        "severe flood and landslide risk."
                    ),
                    "months_active": [target_month],
                }
            )
        elif precip >= 150:
            risks.append(
                {
                    "type": "flood_landslide",
                    "severity": 4,
                    "description": (
                        f"Heavy monthly precipitation ({precip} mm) significantly raises "
                        "flood and landslide risk."
                    ),
                    "months_active": [target_month],
                }
            )
        elif precip >= 80:
            risks.append(
                {
                    "type": "heavy_rain",
                    "severity": 2,
                    "description": (
                        f"Moderate monthly precipitation ({precip} mm) — carry wet-weather gear."
                    ),
                    "months_active": [target_month],
                }
            )

        # --- Extreme heat ---
        max_temp = climate["max_temp_c"]
        avg_temp = climate["avg_temp_c"]
        if max_temp >= 45:
            risks.append(
                {
                    "type": "extreme_heat",
                    "severity": 5,
                    "description": (
                        f"Extreme temperatures reaching {max_temp}°C. Heatstroke risk is "
                        "very high; avoid outdoor activity during midday."
                    ),
                    "months_active": [target_month],
                }
            )
        elif max_temp >= 38:
            risks.append(
                {
                    "type": "heat_stress",
                    "severity": 3,
                    "description": (
                        f"High temperatures (up to {max_temp}°C). Heat exhaustion risk; "
                        "stay hydrated and limit sun exposure."
                    ),
                    "months_active": [target_month],
                }
            )

        # --- Cold / hypothermia ---
        if avg_temp <= -15:
            risks.append(
                {
                    "type": "extreme_cold",
                    "severity": 4,
                    "description": (
                        f"Average temperature {avg_temp}°C. Frostbite and hypothermia risk "
                        "require specialist cold-weather equipment."
                    ),
                    "months_active": [target_month],
                }
            )
        elif avg_temp <= 0:
            risks.append(
                {
                    "type": "cold",
                    "severity": 2,
                    "description": (
                        f"Freezing or near-freezing temperatures (avg {avg_temp}°C). "
                        "Dress in insulating layers."
                    ),
                    "months_active": [target_month],
                }
            )

        # --- Altitude sickness (from elevation API) ---
        if elevation is not None:
            if elevation >= 4500:
                risks.append(
                    {
                        "type": "altitude_sickness",
                        "severity": 5,
                        "description": (
                            f"Elevation of {elevation:.0f} m. Severe altitude sickness (HACE/HAPE) "
                            "is a real danger; acclimatise slowly and carry medication."
                        ),
                        "months_active": list(range(1, 13)),
                    }
                )
            elif elevation >= 2500:
                risks.append(
                    {
                        "type": "altitude_sickness",
                        "severity": 3,
                        "description": (
                            f"Elevation of {elevation:.0f} m. Moderate altitude sickness risk; "
                            "allow 2–3 days for acclimatisation."
                        ),
                        "months_active": list(range(1, 13)),
                    }
                )

        # --- UV / disease-vector risk in tropical zone ---
        if -23 <= lat <= 23:
            # Rainy season proxy: high precipitation
            if precip >= 100:
                risks.append(
                    {
                        "type": "disease_vector",
                        "severity": 3,
                        "description": (
                            "Tropical rainy season raises standing-water mosquito populations, "
                            "increasing risk of malaria, dengue, and Zika."
                        ),
                        "months_active": [target_month],
                    }
                )
            # UV is always elevated near equator
            risks.append(
                {
                    "type": "uv_radiation",
                    "severity": 2,
                    "description": (
                        "Tropical latitude delivers high UV index year-round. "
                        "Use SPF 50+ sunscreen and seek shade midday."
                    ),
                    "months_active": list(range(1, 13)),
                }
            )
            # Equatorial high-altitude is particularly severe
            if elevation is not None and elevation >= 2000:
                # Update UV severity
                for r in risks:
                    if r["type"] == "uv_radiation":
                        r["severity"] = 4
                        r["description"] = (
                            f"Tropical latitude combined with {elevation:.0f} m elevation "
                            "produces extreme UV index. Eye and skin protection is essential."
                        )

        # --- Compute aggregate score ---
        score = self._aggregate_score(risks)
        month_assessment = self._month_narrative(
            target_month, climate, elevation, risks
        )

        return {
            "weather_risk_score": score,
            "weather_risk_label": RISK_LABELS[score],
            "risks": risks,
            "travel_month_assessment": month_assessment,
            "source": "open-meteo",
        }

    # ------------------------------------------------------------------
    # Static fallback assessment
    # ------------------------------------------------------------------

    def _assess_static(
        self,
        lat: float,
        lon: float,
        target_month: int,
        travel_date: date,
    ) -> dict[str, Any]:
        risks: list[dict[str, Any]] = []

        for zone in STATIC_RISK_ZONES:
            if (
                zone["min_lat"] <= lat <= zone["max_lat"]
                and zone["min_lon"] <= lon <= zone["max_lon"]
            ):
                # Only include if the travel month is active (or always active)
                if target_month in zone["months_active"]:
                    risks.append(
                        {
                            "type": zone["type"],
                            "severity": zone["severity"],
                            "description": zone["description"],
                            "months_active": zone["months_active"],
                        }
                    )

        score = self._aggregate_score(risks)
        month_name = _month_name(target_month)

        if risks:
            risk_summary = "; ".join(r["type"].replace("_", " ") for r in risks)
            month_assessment = (
                f"{month_name} is an elevated-risk period at this location. "
                f"Known concerns include: {risk_summary}. "
                "Data is based on regional static rules (live API unavailable)."
            )
        else:
            month_assessment = (
                f"{month_name} shows no major flagged risk at this location "
                "based on regional patterns (live API unavailable)."
            )

        return {
            "weather_risk_score": score,
            "weather_risk_label": RISK_LABELS[score],
            "risks": risks,
            "travel_month_assessment": month_assessment,
            "source": "static-regional",
        }

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_score(risks: list[dict[str, Any]]) -> int:
        """
        Compute an aggregate 1–5 risk score from a list of individual risk dicts.
        Logic: max severity drives the score, with a +1 bump when 3+ risks overlap.
        """
        if not risks:
            return 1
        max_sev = max(r["severity"] for r in risks)
        bump = 1 if len(risks) >= 3 else 0
        return _clamp(max_sev + bump, 1, 5)

    @staticmethod
    def _month_narrative(
        target_month: int,
        climate: dict[str, Any],
        elevation: float | None,
        risks: list[dict[str, Any]],
    ) -> str:
        month_name = _month_name(target_month)
        parts: list[str] = [
            f"In {month_name}, average temperature is {climate['avg_temp_c']}°C "
            f"(high {climate['max_temp_c']}°C) with roughly {climate['avg_precip_mm']} mm "
            "of precipitation."
        ]
        if elevation is not None:
            parts.append(f"The destination sits at approximately {elevation:.0f} m elevation.")
        if risks:
            risk_labels = [r["type"].replace("_", " ") for r in risks]
            parts.append(
                f"Active risks this month: {', '.join(risk_labels)}."
            )
        else:
            parts.append("No major weather risks identified for this month.")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Quick smoke-test (run directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    assessor = WeatherRiskAssessor()

    test_cases = [
        ("Kathmandu, Nepal", 27.7172, 85.3240, date(2025, 7, 15)),
        ("Nairobi, Kenya", -1.2921, 36.8219, date(2025, 4, 1)),
        ("Phoenix, AZ", 33.4484, -112.0740, date(2025, 8, 1)),
        ("Reykjavik, Iceland", 64.1355, -21.8954, date(2025, 1, 10)),
    ]

    for name, lat, lon, tdate in test_cases:
        print(f"\n=== {name} ({tdate}) ===")
        result = assessor.assess(lat=lat, lon=lon, travel_date=tdate)
        print(json.dumps(result, indent=2))
