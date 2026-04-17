from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import FlightProvider


class DisabledFlightProvider(FlightProvider):
    """Flight provider used when flight search is turned off.

    Returns a clear, user-friendly error message without calling any API.
    """

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        trip_type: str = "oneway",
        return_date: Optional[str] = None,
        max_stops: int = -1,
        max_price: Optional[int] = 0,
        adults: int = 1,
        children: int = 0,
    ) -> Dict[str, Any]:
        return {
            "success": False,
            "error": (
                "Flight search is currently disabled in this environment. "
                "Enable it by setting flight_scraper_mode to 'stub' or 'live'."
            ),
            "flights": [],
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
        }
