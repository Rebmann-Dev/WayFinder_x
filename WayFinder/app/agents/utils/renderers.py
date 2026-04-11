from __future__ import annotations

import datetime
import json
import re
from typing import Any

_TOOL_STRIP = re.compile(r"<tool_call>[\s\S]*?</tool_call>", re.IGNORECASE)


def strip_tool_blocks(text: str) -> str:
    return _TOOL_STRIP.sub("", text).strip()


def has_tool_call_tag(text: str) -> bool:
    return "<tool_call>" in text.lower()


def render_search_flights_result(result_str: str) -> str | None:
    """
    Renders a single search_flights result into a readable string.
    Used for model-driven tool calls — multi-airport results use
    render_multi_airport_results instead.
    """
    try:
        payload = json.loads(result_str)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict) or "success" not in payload:
        return None

    if payload.get("success") is False:
        error = str(payload.get("error", "")).strip()
        return error or "Flight search failed."

    origin = str(payload.get("origin", "")).strip().upper()
    destination = str(payload.get("destination", "")).strip().upper()
    departure_date = str(payload.get("departure_date", "")).strip()
    flights = payload.get("flights", [])

    if payload.get("no_results") or not isinstance(flights, list) or not flights:
        return (
            f"I couldn't find flights from {origin} to {destination} "
            f"on {departure_date}. "
            "Want to try a different date, nearby airport, or route?"
        )

    lines = [f"Flights from {origin} to {destination} on {departure_date}:"]
    for i, flight in enumerate(flights, start=1):
        if not isinstance(flight, dict):
            continue
        airline = str(flight.get("airline", "")).strip() or "Unknown airline"
        dep = str(flight.get("departure_time", "")).strip() or "Unknown departure"
        arr = str(flight.get("arrival_time", "")).strip() or "Unknown arrival"
        duration = str(flight.get("duration", "")).strip() or "Unknown duration"
        stops = str(flight.get("stops", "")).strip() or "Unknown stops"
        price = str(flight.get("price", "")).strip() or "Unknown price"
        lines.append(
            f"{i}. {airline} | {dep} to {arr} | {duration} | {stops} | {price}"
        )

    return "\n".join(lines)


def render_multi_airport_results(results: list[dict[str, Any]]) -> str:
    """
    Renders flight results across multiple destination airports into
    clean markdown grouped by airport, with color-coded stop badges.
    """
    if not results:
        return "No flights found."

    origin = results[0]["origin"]
    departure_date = results[0]["departure_date"]

    try:
        date_display = datetime.date.fromisoformat(departure_date).strftime(
            "%A, %B %d %Y"
        )
    except ValueError:
        date_display = departure_date

    total_flights = sum(len(r["flights"]) for r in results)
    airport_count = len(results)

    lines = [
        f"## ✈️ Flights from {origin} · {date_display}",
        f"*Found **{total_flights} flight{'s' if total_flights != 1 else ''}** "
        f"across **{airport_count} airport{'s' if airport_count != 1 else ''}***",
        "",
    ]

    for result in results:
        destination = result["destination"]
        flights = result["flights"]

        lines += ["---", f"### {origin} → {destination}", ""]

        for i, flight in enumerate(flights, 1):
            airline = flight.get("airline", "Unknown airline")
            departure = flight.get("departure_time", "—")
            arrival = flight.get("arrival_time", "—")
            duration = flight.get("duration", "—")
            stops = flight.get("stops", "—")
            price = flight.get("price", "—")

            stops_badge = (
                "🟢 Nonstop"
                if stops == "nonstop"
                else "🟡 1 stop"
                if stops == "1 stop"
                else f"🔴 {stops}"
            )

            lines += [
                f"**{i}. {airline}**",
                f"&nbsp;&nbsp;🕐 {departure} → {arrival} &nbsp;·&nbsp; "
                f"⏱ {duration} &nbsp;·&nbsp; {stops_badge} &nbsp;·&nbsp; "
                f"💰 **{price}**",
                "",
            ]

    lines += [
        "---",
        "*Prices and availability may vary. "
        "Ask me to filter by stops, price, or airline — "
        "or pick a flight to get more details.*",
    ]

    return "\n".join(lines)
