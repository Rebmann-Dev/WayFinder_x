import re
from models.flight_search import FlightSearchRequest


class IntentService:
    AIRPORT_CODE_PATTERN = r"\b[A-Z]{3}\b"
    DATE_PATTERN = r"\b\d{4}-\d{2}-\d{2}\b"

    def extract_flight_request(self, message: str) -> FlightSearchRequest:
        airport_codes = re.findall(self.AIRPORT_CODE_PATTERN, message)
        dates = re.findall(self.DATE_PATTERN, message)

        request = FlightSearchRequest()

        if len(airport_codes) >= 2:
            request.origin = airport_codes[0]
            request.destination = airport_codes[1]

        if len(dates) >= 1:
            request.departure_date = dates[0]

        if len(dates) >= 2:
            request.return_date = dates[1]

        price_match = re.search(r"\$?(\d+(?:\.\d+)?)\s*(max|budget)?", message.lower())
        if price_match and "budget" in message.lower():
            request.max_price = float(price_match.group(1))

        if "nonstop" in message.lower():
            request.max_stops = 0
        elif "1 stop" in message.lower() or "one stop" in message.lower():
            request.max_stops = 1

        return request
