import json
import logging
import re
from datetime import date, timedelta
from typing import Any

from services.airport_search_service import search_airports
from services.flight_api import FlightAPIService

log = logging.getLogger("wayfinder.tools")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ToolExecutor:
    def __init__(self) -> None:
        self._flights = FlightAPIService()

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
                dep_date = raw.get("departure_date", departure_date)
                payload = {
                    "success": True,
                    "origin": raw.get("origin"),
                    "destination": raw.get("destination"),
                    "departure_date": dep_date,
                    "flights": ranked,
                    "total_returned": len(ranked),
                    "instruction": (
                        f"Present ALL {len(ranked)} flights below to the user as a numbered list. "
                        f"Include the departure date ({dep_date}) in your response header. "
                        "For each flight show: airline, departure time, arrival time, duration, stops, and price. "
                        "Do NOT skip any. Do NOT add flights not in this list."
                    ),
                }
                log.info("TOOL RESULT search_flights  %s→%s date=%s flights=%d", origin, destination, dep_date, len(ranked))
                return json.dumps(payload)

            log.error("TOOL RESULT search_flights  unexpected shape: %s", str(raw)[:200])
            return json.dumps({"success": False, "error": "Unexpected API response shape."})

        log.warning("TOOL CALL  unknown tool: %s", name)
        return json.dumps({"error": f"Unknown tool: {name}"})
