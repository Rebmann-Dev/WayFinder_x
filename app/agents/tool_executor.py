import json
from typing import Any

from services.airport_search_service import search_airports
from services.flight_api import FlightAPIService


class ToolExecutor:
    def __init__(self) -> None:
        self._flights = FlightAPIService()

    def run(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "search_airports":
            q = str(arguments.get("query", "")).strip()
            limit = int(arguments.get("limit", 12) or 12)
            rows = search_airports(q, limit=limit)
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
                return json.dumps(
                    {
                        "success": False,
                        "error": "origin and destination must be 3-letter IATA codes.",
                    }
                )
            if not departure_date:
                return json.dumps(
                    {"success": False, "error": "departure_date (YYYY-MM-DD) is required."}
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
                payload = {
                    "success": True,
                    "origin": raw.get("origin"),
                    "destination": raw.get("destination"),
                    "departure_date": raw.get("departure_date"),
                    "flights": ranked,
                    "total_returned": len(ranked),
                    "note": (
                        "These are the top results ranked by the API. "
                        "Present ALL of them to the user. Do NOT invent extra flights."
                    ),
                }
                return json.dumps(payload)

            return json.dumps({"success": False, "error": "Unexpected API response shape."})

        return json.dumps({"error": f"Unknown tool: {name}"})
