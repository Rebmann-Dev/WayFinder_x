from agents.flight import FlightAgent
from services.model_service import ModelService


class ChatOrchestrator:
    def __init__(self, model_service: ModelService) -> None:
        self.model_service = model_service
        self.flight_agent = FlightAgent()

    def is_flight_request(self, user_message: str) -> bool:
        lowered = user_message.lower()
        keywords = [
            "flight",
            "flights",
            "fly",
            "plane",
            "airfare",
            "ticket",
            "airport",
            "depart",
            "return",
        ]
        return any(word in lowered for word in keywords)

    def handle(self, user_message: str) -> str:
        if self.is_flight_request(user_message):
            return self.flight_agent.handle(user_message)

        return self.model_service.generate_reply_from_text(user_message)
