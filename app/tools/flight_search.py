# app/tools/flight_search.py

from models.flight_search import FlightSearchRequest
from services.flight import get_flight_provider


class FlightSearchTool:
    def __init__(self) -> None:
        self.provider = get_flight_provider()

    def run(self, request: FlightSearchRequest):
        # If the request is complete, call the provider directly
        if request.is_ready():
            flights = self.provider.search_flights(
                origin=request.origin,
                destination=request.destination,
                departure_date=request.departure_date,
                return_date=request.return_date,
                max_stops=request.max_stops,
                max_price=request.max_price,
                adults=request.adults,
                children=request.children,
            )
            return {
                "success": True,
                "missing_fields": [],
                "data": flights,
            }

        # Otherwise, build a helpful clarification message
        missing = []
        if not request.origin:
            missing.append("origin airport")
        if not request.destination:
            missing.append("destination airport")
        if not request.departure_date:
            missing.append("departure date (YYYY-MM-DD)")

        msg = (
            "To search flights I need "
            + ", ".join(missing)
            + ". Use 3-letter airport codes (e.g. SAN, UIO) "
            "and a date like 2026-05-10."
        )

        return {
            "success": False,
            "missing_fields": missing,
            "data": {
                "success": False,
                "error": msg,
                "flights": [],
            },
        }