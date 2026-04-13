from dataclasses import dataclass
from typing import Optional


@dataclass
class FlightSearchRequest:
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    max_stops: Optional[int] = None
    max_price: Optional[float] = None
    adults: int = 1
    children: int = 0

    def is_ready(self) -> bool:
        return all(
            [
                self.origin,
                self.destination,
                self.departure_date,
            ]
        )
