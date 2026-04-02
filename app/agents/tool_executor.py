import json
import logging
import re
from typing import Any

from services.airport_search_service import search_airports
from services.flight_api import FlightAPIService
"""
added below for safety function
"""
from services.safety_service import SafetyService


log = logging.getLogger("wayfinder.tools")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
            log.info("TOOL RESULT search_airports  count=%d top=%s", len(rows), [r["iata"] for r in rows[:5]])
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
                log.warning("TOOL REJECT search_flights  bad codes: origin=%s dest=%s", origin, destination)
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
                log.info("TOOL RESULT search_flights  %s→%s date=%s flights=%d", origin, destination, dep_date, len(compact_ranked))
                return json.dumps(payload)

            log.error("TOOL RESULT search_flights  unexpected shape: %s", str(raw)[:200])
            return json.dumps({"success": False, "error": "Unexpected API response shape."})

            if name == "get_safety_assessment":                        
                latitude = arguments.get("latitude")
                longitude = arguments.get("longitude")
                country = arguments.get("country")
                location_name = arguments.get("location_name")

                result = self._safety.assess_location(
                    latitude=latitude,
                    longitude=longitude,
                    country=str(country).strip() if country else None,
                    location_name=str(location_name).strip() if location_name else None,
                )

                if not result.get("success"):
                    return json.dumps(result)

                result["instruction"] = (
                    "Present the predicted safety score clearly and briefly. "
                    "Explain that this is a model-based travel safety estimate, not an official crime report. "
                    "Mention the risk band and keep the guidance practical."
                )
                return json.dumps(result)

        log.warning("TOOL CALL  unknown tool: %s", name)
        return json.dumps({"error": f"Unknown tool: {name}"})

