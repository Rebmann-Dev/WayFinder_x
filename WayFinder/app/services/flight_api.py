import logging
import os
from typing import Any, Dict, List
from urllib.parse import urlunparse, urlencode

import requests

log = logging.getLogger("wayfinder.flight_api")

API_BASE_URL = os.getenv(
    "API_BASE_URL", "localhost:8080"
)  # replace with your real endpoint
API_BASE_SCHEME = os.getenv("API_BASE_SCHEME", "http")  # default to http if not set


class FlightAPIService:
    def __init__(self, base_url: str = API_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        trip_type: str = "oneway",
        return_date: str | None = None,
        max_stops: int = -1,
        max_price: int = 0,
        adults: int = 1,
        children: int = 0,
    ) -> List[Dict[str, Any]]:
        stops = "any"
        if max_stops == 0:
            stops = "nonstop"
        elif max_stops == 1:
            stops = "max1"
        elif max_stops == 2:
            stops = "max2"

        if max_price is None:
            max_price = ""

        query = {
            "date": departure_date,
            "tripType": trip_type,
            "stops": stops,
            "maxPrice": max_price,
            "adults": adults,
            "children": children,
        }

        q = urlencode(query)

        url = urlunparse(
            (
                API_BASE_SCHEME,
                self.base_url,
                f"/flights/{origin}/{destination}",
                "",
                q,
                "",
            )
        )

        try:
            response = requests.get(
                url,
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                },
            )
        except requests.RequestException as exc:
            log.error("Flight API request failed url=%s error=%s", url, exc)
            return {
                "success": False,
                "error": (
                    "Flight search is temporarily unavailable because the flight API "
                    f"request failed: {exc}"
                ),
            }

        log.info(
            "Flight API response status=%s url=%s bytes=%d",
            response.status_code,
            url,
            len(response.content),
        )
        if response.status_code != 200:
            log.warning(
                "Flight API non-200 status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            return {
                "success": False,
                "error": f"API request failed with status code {response.status_code}: {response.text}",
            }

        try:
            data = response.json()
        except ValueError as exc:
            log.error(
                "Flight API invalid JSON url=%s body=%s", url, response.text[:500]
            )
            return {
                "success": False,
                "error": f"Flight API returned invalid JSON: {exc}",
            }

        flights = data.get("flights", [])
        log.info(
            "Flight API parsed current_price=%s flights=%d keys=%s",
            data.get("current_price"),
            len(flights) if isinstance(flights, list) else -1,
            sorted(data.keys()) if isinstance(data, dict) else [],
        )

        return {
            "flights": flights if isinstance(flights, list) else [],
            "success": True,
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
        }
