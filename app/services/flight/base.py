from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class FlightProvider(ABC):
    """Abstract interface for flight search backends.

    Implementations must return a dict with at least:
      - success: bool
      - error: str (when success is False)
      - flights: list (when success is True)
      - origin, destination, departure_date: echoed back for summarization
    """

    @abstractmethod
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
        raise NotImplementedError
