from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import FlightProvider


class StubFlightProvider(FlightProvider):
    """Returns deterministic mock flights for development/testing."""

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
        flights: List[Dict[str, Any]] = [
            {
                "is_top": True,
                "airline": {"name": "WayFinder Air"},
                "departure": f"{departure_date} 08:00",
                "arrival": f"{departure_date} 14:30",
                "arrival_time_ahead": None,
                "duration": "6h 30m",
                "stops": 0,
                "legs": [],
                "delay": "on time",
                "price": "$520",
                "emissions": {"co2_kg": 420},
            },
            {
                "is_top": False,
                "airline": {"name": "Mock Airlines"},
                "departure": f"{departure_date} 10:15",
                "arrival": f"{departure_date} 17:45",
                "arrival_time_ahead": None,
                "duration": "7h 30m",
                "stops": 1,
                "legs": [
                    {
                        "is_layover": True,
                        "arrival_airport": {"code": "PTY"},
                        "layover_duration": "1h 10m",
                    }
                ],
                "delay": "on time",
                "price": "$480",
                "emissions": {"co2_kg": 460},
            },
        ]

        return {
            "success": True,
            "flights": flights,
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
        }
