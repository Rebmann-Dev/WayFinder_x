from services.intent import IntentService
from tools.flight_search import FlightSearchTool

import json


class FlightAgent:
    def __init__(self) -> None:
        self.intent_service = IntentService()
        self.flight_tool = FlightSearchTool()

    def handle(self, user_message: str) -> str:
        request = self.intent_service.extract_flight_request(user_message)
        result = self.flight_tool.run(request)

        if not result["data"]["success"]:
            return f"It seems like there was an error fetching the flight data: {result['data']['error']}."

        data = result["data"]

        if not data["flights"]:
            return "I found no flights matching those filters."

        return summarize_flights_for_chat(data)


def normalize_flight(raw: dict) -> dict:
    return {
        "is_top": raw.get("is_top", False),
        "airline": raw.get("airline", {}),
        "departure_time": raw.get("departure"),
        "arrival_time": raw.get("arrival"),
        "arrival_time_ahead": raw.get("arrival_time_ahead"),
        "duration": raw.get("duration"),
        "stops": raw.get("stops"),
        "legs": raw.get("legs"),
        "delay": raw.get("delay"),
        "price": raw.get("price"),
        "emissions": raw.get("emissions", {}),
        "raw": raw,
    }


def format_flight_for_chat(flight: dict) -> str:
    airline = flight["airline"].get("name", "Unknown airline")
    departure = flight.get("departure_time", "Unknown departure")
    arrival = flight.get("arrival_time", "Unknown arrival")
    duration = flight.get("duration", "Unknown duration")
    stops = flight.get("stops", "Unknown")
    legs = flight.get("legs", "Unknown")
    price = flight.get("price", "Unknown price")

    stop_text = (
        "nonstop"
        if stops == 0
        else f"{stops} stop in {legs[0]['arrival_airport']['code']} for {legs[0]['layover_duration']}"
        if stops == 1
        else f"{stops} stops: "
    )
    if stops > 1:
        for i, leg in enumerate(legs):
            if leg["is_layover"]:
                stop_text += (
                    f"{leg['arrival_airport']['code']} for {leg['layover_duration']}"
                )
            if i <= stops - 2:
                stop_text += ", "

            if i == stops - 2:
                stop_text += "and "

    return f"{airline} | {departure} to {arrival} | {duration} | {stop_text} | {price}"


def summarize_flights_for_chat(data: dict) -> str:
    normalized = [normalize_flight(f) for f in data["flights"]]

    if not normalized:
        return "I couldn’t find any matching flights."

    lines = [
        "Here are a the best flight options for {date} I found that are leaving from {origin} and arriving at {destination}:\n".format(
            date=data["departure_date"],
            origin=data["origin"],
            destination=data["destination"],
        )
    ]

    num = 1
    for flight in normalized:
        if flight["is_top"]:
            prefix = "⭐ " if flight["is_top"] else ""
            lines.append(f"{num}. {prefix}{format_flight_for_chat(flight)}")
            num += 1

    for flight in normalized:
        if num == 15:
            break
        if not flight["is_top"]:
            lines.append(f"{num}. {format_flight_for_chat(flight)}")
            num += 1

    return "\n".join(lines)
