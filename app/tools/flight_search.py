from models.flight_search import FlightSearchRequest
from services.flight_api import FlightAPIService


class FlightSearchTool:
    def __init__(self) -> None:
        self.api_service = FlightAPIService()

    def run(self, request: FlightSearchRequest):
        if not request.is_ready():
            missing = []
            if not request.origin:
                missing.append("origin")
            if not request.destination:
                missing.append("destination")
            if not request.departure_date:
                missing.append("departure date")

            return {
                "success": False,
                "missing_fields": missing,
                "data": {
                    "success": False,
                    "error": (
                        "I need "
                        + ", ".join(missing)
                        + ". Use 3-letter airport codes (e.g. SEA, JFK) and a date as YYYY-MM-DD."
                    ),
                    "flights": [],
                },
            }

        flights = self.api_service.search_flights(
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
