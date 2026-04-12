from __future__ import annotations

from typing import Any

from agents.utils.grounding import (
    airport_codes_from_tool_results,
    user_explicit_iata_codes,
)


def strict_date_clarification(args: dict[str, Any]) -> str | None:
    """
    Returns a clarification prompt if required date fields are missing,
    or None if all necessary dates are present.
    """
    departure_date = str(args.get("departure_date", "")).strip()
    return_date = str(args.get("return_date", "")).strip()
    trip_type = str(args.get("trip_type", "oneway") or "oneway").strip().lower()

    requested_dates = [d for d in [departure_date] if d]
    if trip_type == "roundtrip" and return_date:
        requested_dates.append(return_date)

    if not requested_dates:
        return "What date would you like to fly? Please use YYYY-MM-DD."

    return None


def strict_airport_clarification(
    args: dict[str, Any],
    messages: list[dict[str, Any]],
) -> str | None:
    """
    Returns a clarification prompt if origin or destination codes are
    missing or ungrounded, or None if both are resolved.
    """
    origin = str(args.get("origin", "")).strip().upper()
    destination = str(args.get("destination", "")).strip().upper()

    grounded_codes = user_explicit_iata_codes(
        messages
    ) | airport_codes_from_tool_results(messages)

    origin_grounded = len(origin) == 3 and origin in grounded_codes
    destination_grounded = len(destination) == 3 and destination in grounded_codes

    if len(origin) != 3 and len(destination) != 3:
        return (
            "Please tell me both the departure and destination airports. "
            "You can use city names or 3-letter airport codes."
        )
    if len(origin) != 3 or not origin_grounded:
        return (
            "What is your departure airport? Please provide the city or the "
            "3-letter origin airport code."
        )
    if len(destination) != 3 or not destination_grounded:
        return (
            "What is your destination airport? Please provide the city or the "
            "3-letter destination airport code."
        )
    if origin == destination and len(grounded_codes) < 2:
        return (
            "I only have one airport so far. What is your departure airport? "
            "Please provide the city or the 3-letter origin airport code."
        )

    return None
