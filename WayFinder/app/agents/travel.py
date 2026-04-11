from agents.flight import FlightAgent


class TravelAgent:
    def __init__(self) -> None:
        self.flight_agent = FlightAgent()

    def handle(self, user_message: str) -> str:
        lowered = user_message.lower()

        flight_keywords = [
            "flight",
            "flights",
            "fly",
            "plane",
            "airfare",
            "ticket",
            "airport",
        ]

        if any(keyword in lowered for keyword in flight_keywords):
            return self.flight_agent.handle(user_message)

        return "I can help with travel planning. Right now, flight search works best for flight-related requests."
