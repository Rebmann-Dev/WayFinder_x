# app/services/intent.py

import re
from models.flight_search import FlightSearchRequest
from services.airport_search_service import search_airports


class IntentService:
    AIRPORT_CODE_PATTERN = r"\b[A-Z]{3}\b"
    DATE_PATTERN = r"\b\d{4}-\d{2}-\d{2}\b"

    def extract_flight_request(self, message: str) -> FlightSearchRequest:
        lower_msg = message.lower()

        airport_codes = re.findall(self.AIRPORT_CODE_PATTERN, message)
        dates = re.findall(self.DATE_PATTERN, message)

        request = FlightSearchRequest()

        # 1) Exact IATA codes first (existing behavior)
        if len(airport_codes) >= 2:
            request.origin = airport_codes[0]
            request.destination = airport_codes[1]

        # 2) Fallback: city names like "san diego to quito"
        if (not request.origin or not request.destination) and " to " in lower_msg:
            left, right = lower_msg.split(" to ", 1)
            origin_text = left.strip()
            dest_text = right.strip()

            origin_candidates = search_airports(origin_text, limit=3)
            dest_candidates = search_airports(dest_text, limit=3)

            # Only auto-fill when unambiguous
            if len(origin_candidates) == 1:
                request.origin = origin_candidates[0]["iata"]
            if len(dest_candidates) == 1:
                request.destination = dest_candidates[0]["iata"]

        # 3) Dates (existing behavior)
        if len(dates) >= 1:
            request.departure_date = dates[0]

        if len(dates) >= 2:
            request.return_date = dates[1]

        # 4) Budget / max price (existing behavior)
        price_match = re.search(r"\$?(\d+(?:\.\d+)?)\s*(max|budget)?", lower_msg)
        if price_match and "budget" in lower_msg:
            request.max_price = float(price_match.group(1))

        # 5) Max stops (existing behavior)
        if "nonstop" in lower_msg:
            request.max_stops = 0
        elif "1 stop" in lower_msg or "one stop" in lower_msg:
            request.max_stops = 1

        return request
