import json
import logging
import re
from typing import Any

import streamlit as st

from services.airport_search_service import search_airports
from services.flight_api import FlightAPIService
from services.safety_service import SafetyService


log = logging.getLogger("wayfinder.tools")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Only city-specific factors. Country-level macros (homicide_rate,
# gdp_per_capita, unemployment) are deliberately excluded because they
# are identical for every city in the same country and give a false
# impression of specificity in the response.
_SAFETY_FACTOR_KEYS = [
    ("neighbourhood_crime", "avg_crime_k5"),
    ("neighbourhood_safety", "avg_safety_k5"),
    ("weighted_crime", "wavg_crime_k5"),
    ("weighted_safety", "wavg_safety_k5"),
    ("nearest_city_crime", "crime_nearest_labeled_city"),
    ("nearest_city_safety", "safety_nearest_labeled_city"),
]


def _safety_factors(result: dict[str, Any]) -> dict[str, float]:
    """Extract raw city-specific factor values from a safety result.

    All returned factors are city-specific: KNN averages over the 5
    nearest labelled cities, distance-weighted versions, and the single
    nearest labelled city. No country-level macro features are included.
    """
    features = result.get("details", {}).get("features", {})
    factors: dict[str, float] = {}
    if not features:
        return factors
    for out_key, src_key in _SAFETY_FACTOR_KEYS:
        val = features.get(src_key)
        if val is not None:
            factors[out_key] = float(val)
    return factors


def _safety_highlights(result: dict[str, Any]) -> list[str]:
    """Human-readable factor labels (used only in the fallback instruction)."""
    factors = _safety_factors(result)
    out: list[str] = []
    if "neighbourhood_crime" in factors:
        out.append(f"neighbourhood crime index {factors['neighbourhood_crime']:.1f}/100")
    if "neighbourhood_safety" in factors:
        out.append(f"neighbourhood safety index {factors['neighbourhood_safety']:.1f}/100")
    if "nearest_city_crime" in factors:
        out.append(f"nearest-city crime index {factors['nearest_city_crime']:.1f}/100")
    if "nearest_city_safety" in factors:
        out.append(f"nearest-city safety index {factors['nearest_city_safety']:.1f}/100")
    return out


def _build_safety_instruction(result: dict[str, Any]) -> str:
    score = result.get("safety_score", "?")
    band = result.get("risk_band", "unknown")
    location = result.get("location_name") or "this location"
    highlights = _safety_highlights(result)

    factor_text = f" Key factors used: {', '.join(highlights)}." if highlights else ""

    return (
        f"Present the safety assessment for {location}. "
        f"State the safety score ({score}/100) and risk band ('{band}'). "
        f"{factor_text} "
        "Explain the risk band in plain language: "
        "'low' (75+) = generally safe for most travelers; "
        "'moderate' (55-74) = exercise normal caution; "
        "'elevated' (35-54) = extra vigilance advised; "
        "'high' (<35) = significant caution required. "
        "Note this is a model-based estimate using geographic and socioeconomic data, not an official government report. "
        "Keep the response practical and useful for a traveler."
    )


def _format_arrival(raw: dict[str, Any]) -> str:
    arrival = str(raw.get("arrival", "")).strip() or "Unknown arrival"
    ahead = str(raw.get("arrival_time_ahead", "")).strip()
    return f"{arrival} {ahead}".strip()


def _format_stops(raw: dict[str, Any]) -> str:
    stops = raw.get("stops")
    if stops == 0:
        return "nonstop"
    if stops == 1:
        return "1 stop"
    if isinstance(stops, int) and stops > 1:
        return f"{stops} stops"
    return "Unknown stops"


def _compact_flight(raw: dict[str, Any]) -> dict[str, str]:
    airline = raw.get("airline", {})
    airline_name = "Unknown airline"
    if isinstance(airline, dict):
        airline_name = str(airline.get("name", "")).strip() or airline_name

    return {
        "airline": airline_name,
        "departure_time": str(raw.get("departure", "")).strip() or "Unknown departure",
        "arrival_time": _format_arrival(raw),
        "duration": str(raw.get("duration", "")).strip() or "Unknown duration",
        "stops": _format_stops(raw),
        "price": str(raw.get("price", "")).strip() or "Unknown price",
    }


class ToolExecutor:
    def __init__(self) -> None:
        self._flights = FlightAPIService()
        self._safety = SafetyService()

    def run(self, name: str, arguments: dict[str, Any]) -> str:
        log.info("TOOL CALL  %-20s args=%s", name, json.dumps(arguments, default=str))

        if name == "search_airports":
            q = str(arguments.get("query", "")).strip()
            limit = int(arguments.get("limit", 12) or 12)
            rows = search_airports(q, limit=limit)
            log.info(
                "TOOL RESULT search_airports  count=%d top=%s",
                len(rows),
                [r["iata"] for r in rows[:5]],
            )
            return json.dumps({"matches": rows, "count": len(rows)})

        if name == "search_flights":
            origin = str(arguments.get("origin", "")).strip().upper()
            destination = str(arguments.get("destination", "")).strip().upper()
            departure_date = str(arguments.get("departure_date", "")).strip()
            trip_type = str(arguments.get("trip_type", "oneway") or "oneway")
            return_date = arguments.get("return_date")
            if return_date is not None:
                return_date = str(return_date).strip() or None
            max_stops = arguments.get("max_stops", -1)
            if max_stops is not None:
                try:
                    max_stops = int(max_stops)
                except (TypeError, ValueError):
                    max_stops = -1
            max_price = arguments.get("max_price", 0)
            try:
                max_price = int(max_price) if max_price is not None else 0
            except (TypeError, ValueError):
                max_price = 0
            adults = int(arguments.get("adults", 1) or 1)
            children = int(arguments.get("children", 0) or 0)

            if len(origin) != 3 or len(destination) != 3:
                log.warning(
                    "TOOL REJECT search_flights  bad codes: origin=%s dest=%s",
                    origin,
                    destination,
                )
                return json.dumps(
                    {
                        "success": False,
                        "error": "origin and destination must be 3-letter IATA codes.",
                    }
                )
            if not departure_date or not _DATE_RE.match(departure_date):
                log.warning("TOOL REJECT search_flights  bad date=%r", departure_date)
                return json.dumps(
                    {
                        "success": False,
                        "error": (
                            "departure_date is required and must be YYYY-MM-DD. "
                            "Ask the user what date they want to fly."
                        ),
                    }
                )

            raw = self._flights.search_flights(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                trip_type=trip_type,
                return_date=return_date,
                max_stops=max_stops,
                max_price=max_price,
                adults=adults,
                children=children,
            )

            if isinstance(raw, dict) and raw.get("success") is False:
                return json.dumps(raw)

            if isinstance(raw, dict) and raw.get("success"):
                all_flights = raw.get("flights") or []
                top = [f for f in all_flights if f.get("is_top")]
                rest = [f for f in all_flights if not f.get("is_top")]
                ranked = (top + rest)[:5]
                compact_ranked = [_compact_flight(f) for f in ranked]
                dep_date = raw.get("departure_date", departure_date)
                if not ranked:
                    payload = {
                        "success": True,
                        "origin": raw.get("origin"),
                        "destination": raw.get("destination"),
                        "departure_date": dep_date,
                        "flights": [],
                        "total_returned": 0,
                        "no_results": True,
                        "instruction": (
                            "Tell the user that no flights were found for this exact route and date. "
                            "Do NOT mention direct flights, nonstop flights, or any other availability details "
                            "that are not in the tool result. Ask whether they want to try a different date, "
                            "nearby airport, or route."
                        ),
                    }
                    log.info(
                        "TOOL RESULT search_flights  %s→%s date=%s flights=0",
                        origin,
                        destination,
                        dep_date,
                    )
                    return json.dumps(payload)

                payload = {
                    "success": True,
                    "origin": raw.get("origin"),
                    "destination": raw.get("destination"),
                    "departure_date": dep_date,
                    "flights": compact_ranked,
                    "total_returned": len(compact_ranked),
                    "instruction": (
                        f"Present ALL {len(compact_ranked)} flights below as a short numbered list. "
                        f"Use a one-line header with the route and departure date ({dep_date}). "
                        "For each flight show only: airline, departure time, arrival time, duration, stops, and price. "
                        "Do not print JSON, raw field names, nested objects, or extra technical details."
                    ),
                }
                log.info(
                    "TOOL RESULT search_flights  %s→%s date=%s flights=%d",
                    origin,
                    destination,
                    dep_date,
                    len(compact_ranked),
                )
                return json.dumps(payload)

            log.error(
                "TOOL RESULT search_flights  unexpected shape: %s", str(raw)[:200]
            )
            return json.dumps(
                {"success": False, "error": "Unexpected API response shape."}
            )

        if name == "get_safety_assessment":
            import streamlit as st

            latitude = arguments.get("latitude")
            longitude = arguments.get("longitude")
            country = arguments.get("country")
            location_name = arguments.get("location_name")

            if location_name:
                location_name = str(location_name).strip()
            if country:
                country = str(country).strip()

            # ── Prefer session-state destination over LLM tool-call arg ───
            session_dest = (
                st.session_state.get("destination_city")
                or st.session_state.get("destination_airport")
                or None
            )
            if not session_dest:
                selected = st.session_state.get("selected_location") or {}
                session_dest = (
                    selected.get("city")
                    or selected.get("county")
                    or selected.get("state_region")
                    or selected.get("country")
                    or None
                )
            if session_dest:
                if isinstance(session_dest, dict):
                    session_location = (
                        session_dest.get("city")
                        or session_dest.get("name")
                        or session_dest.get("iata")
                        or None
                    )
                else:
                    session_location = str(session_dest)
                if session_location:
                    location_name = session_location

            # Auto-geocode from location name if no coords provided
            if latitude is None or longitude is None:
                if not location_name:
                    return json.dumps(
                        {
                            "success": False,
                            "error": (
                                "To run a safety assessment, please select a destination first. "
                                "Use the 📍 Pick a destination button in the sidebar."
                            ),
                        }
                    )
                geocoded = self._safety.geocode_place(location_name)
                if geocoded is None:
                    return json.dumps(
                        {
                            "success": False,
                            "error": f"Could not find coordinates for '{location_name}'. Try a well-known city name.",
                        }
                    )
                latitude, longitude, geocoded_country = geocoded
                log.info(
                    "TOOL GEOCODE  %s -> lat=%.4f lon=%.4f country=%s",
                    location_name,
                    latitude,
                    longitude,
                    geocoded_country,
                )
                if not country:
                    country = geocoded_country or None

            result = self._safety.assess_location(
                latitude=latitude,
                longitude=longitude,
                country=country,
                location_name=location_name,
                include_details=True,
            )

            if not result.get("success"):
                return json.dumps(result)

            log.info(
                "TOOL RESULT get_safety_assessment  %s score=%.1f band=%s",
                location_name or f"({latitude},{longitude})",
                result.get("safety_score", 0),
                result.get("risk_band"),
            )
            result["factors"] = _safety_factors(result)
            result["key_factors"] = _safety_highlights(result)
            result["instruction"] = _build_safety_instruction(result)
            result.pop("details", None)  # Already distilled into factors/instruction
            return json.dumps(result)

        if name == "search_web":
            if not st.session_state.get("tavily_enabled", False):
                return json.dumps({
                    "success": False,
                    "error": "Web search is currently disabled. The user can enable it via ⚙️ Dev Tools in the sidebar.",
                })
            from services.tavily_service import TavilyService
            result = TavilyService().search(
                arguments.get("query", ""),
                arguments.get("country_code"),
            )
            if result is None:
                return json.dumps({"success": False, "error": "No results found."})
            return json.dumps(result, default=str)

        log.warning("TOOL CALL  unknown tool: %s", name)
        return json.dumps({"error": f"Unknown tool: {name}"})
