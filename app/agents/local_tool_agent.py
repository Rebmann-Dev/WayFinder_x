from __future__ import annotations

import json
import logging
import datetime
import dateparser
import re
from collections.abc import Generator
from typing import Any

import streamlit as st

from agents.tool_call_parser import normalize_arguments, parse_tool_calls
from agents.tool_definitions import TOOLS
from agents.tool_executor import ToolExecutor
from core.config import settings
from services.model_service import ModelService
from services.airport_search_service import search_airports as _airport_search

log = logging.getLogger("wayfinder.agent")

_TOOL_STRIP = re.compile(r"<tool_call>[\s\S]*?</tool_call>", re.IGNORECASE)
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NL_DATE_RE = re.compile(
    r"""
    (?:
        # "august 15th 2026" / "aug 15 2026" / "15th august 2026"
        (?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|
           jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|
           dec(?:ember)?)
        [\s,]+\d{1,2}(?:st|nd|rd|th)?[\s,]+\d{4}
        |
        \d{1,2}(?:st|nd|rd|th)?[\s,]+
        (?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|
           jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|
           dec(?:ember)?)
        [\s,]+\d{4}
        |
        # relative: "next friday", "in two weeks", "tomorrow"
        (?:next|this)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)
        |
        in\s+\d+\s+(?:day|week|month)s?
        |
        tomorrow
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
_IATA_RE = re.compile(r"\b[A-Z]{3}\b")
_KNOWN_IATA_CACHE: set[str] = set()
_ROUTE_PATTERNS = (
    re.compile(
        r"\bfrom\s+(?P<origin>.+?)\s+to\s+(?P<destination>.+?)(?:$|[,.!?]| on | for )",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bto\s+(?P<destination>.+?)\s+from\s+(?P<origin>.+?)(?:$|[,.!?]| on | for )",
        re.IGNORECASE,
    ),
)
_FLIGHT_INTENT_RE = re.compile(
    r"""
    \b(
        flight|flights|fly|flying|airfare|ticket|tickets|
        search|find|look\s*up|show\s*me|get\s*me|book|
        depart|departure|leave|leaving|travel|trip
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
_NARRATION_PATTERNS = (
    re.compile(
        r"I (will|am going to|can) (now |)(look up|search|find|check|call|use)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(Let me|I'll) (now |)(look up|search|find|check|call|use)", re.IGNORECASE
    ),
    re.compile(r"I have found .{0,60}(now|next|so)", re.IGNORECASE),
    re.compile(r"Once I have .{0,60}(will|can|I'll)", re.IGNORECASE),
    re.compile(r"Now[,]? I will", re.IGNORECASE),
)


def _latest_user_message(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user" and not m.get("content", "").startswith("[context:"):
            return m.get("content", "").strip()
    return ""


def _is_flight_search_intent(messages: list[dict[str, Any]]) -> bool:
    """
    Returns True only if the most recent user message is asking for
    a flight search. Prevents the short-circuit from firing on general
    travel questions like 'tell me about LA'.
    """
    latest = _latest_user_message(messages)
    if not latest:
        return False

    # Explicit non-flight questions — bail out immediately
    _NON_FLIGHT_RE = re.compile(
        r"\b(tell\s*me\s*about|what\s*is|what's|describe|info|information|"
        r"weather|hotel|hotels|restaurant|things\s*to\s*do|attraction|"
        r"safe|safety|visa|currency|culture|language|timezone)\b",
        re.IGNORECASE,
    )
    if _NON_FLIGHT_RE.search(latest) and not _FLIGHT_INTENT_RE.search(latest):
        return False

    return bool(_FLIGHT_INTENT_RE.search(latest))


def _is_narration(text: str) -> bool:
    """
    Returns True if the model output looks like a chain-of-thought narration
    about what it intends to do rather than a genuine final response.
    """
    stripped = _strip_tool_blocks(text).strip()
    # If the text is very short and matches a narration pattern, it's almost
    # certainly not a real final answer
    if len(stripped) > 400:
        return False
    return any(p.search(stripped) for p in _NARRATION_PATTERNS)


def _is_valid_iata(code: str) -> bool:
    """Check if a 3-letter code is a real airport IATA code."""
    global _KNOWN_IATA_CACHE
    if not _KNOWN_IATA_CACHE:
        # Populate cache from airport search service on first use
        from services.airport_search_service import _load_airports

        _KNOWN_IATA_CACHE = {row.code for row in _load_airports()}
    return code.upper() in _KNOWN_IATA_CACHE


def _searched_since_last_user_message(messages: list[dict[str, Any]]) -> bool:
    """
    Returns True only if search_flights was called after the most recent
    real user message. Allows follow-up searches in the same session.
    """
    last_user_idx = None
    for i, m in enumerate(messages):
        if m.get("role") == "user" and not m.get("content", "").startswith("[context:"):
            last_user_idx = i

    if last_user_idx is None:
        return False

    return any(
        m.get("role") == "tool" and m.get("name") == "search_flights"
        for m in messages[last_user_idx:]
    )


class AgentStreamEvent:
    __slots__ = ("kind", "text")

    def __init__(self, kind: str, text: str = "") -> None:
        self.kind = kind  # "status" | "token" | "done"
        self.text = text


def _strip_tool_blocks(text: str) -> str:
    return _TOOL_STRIP.sub("", text).strip()


def _has_tool_call_tag(text: str) -> bool:
    return "<tool_call>" in text.lower()


def _user_explicit_dates(messages: list[dict[str, Any]]) -> set[str]:
    dates: set[str] = set()
    for message in messages:
        if message.get("role") != "user":
            continue
        content = str(message.get("content", ""))
        for match in _DATE_RE.findall(content):
            # Validate it's a real calendar date, not e.g. "2024-99-01"
            try:
                datetime.date.fromisoformat(match)
                dates.add(match)
            except ValueError:
                pass
    return dates


def _is_valid_iata(code: str) -> bool:
    """Check if a 3-letter code is a real airport IATA code."""
    global _KNOWN_IATA_CACHE
    if not _KNOWN_IATA_CACHE:
        # Populate cache from airport search service on first use
        from services.airport_search_service import _load_airports

        _KNOWN_IATA_CACHE = {row.code for row in _load_airports()}
    return code.upper() in _KNOWN_IATA_CACHE


def _explicit_iata_codes_in_text(text: str) -> list[str]:
    """
    Extract 3-letter codes from text, but only return ones that are
    real IATA airport codes. Filters out words like USA, NYC, API, etc.
    """
    raw_matches = _IATA_RE.findall(text)
    return [code for code in raw_matches if _is_valid_iata(code)]


def _user_explicit_iata_codes(messages: list[dict[str, Any]]) -> set[str]:
    codes: set[str] = set()
    for message in messages:
        if message.get("role") != "user":
            continue
        content = str(message.get("content", ""))
        codes.update(_explicit_iata_codes_in_text(content))
    return codes


def _airport_codes_from_tool_results(messages: list[dict[str, Any]]) -> set[str]:
    codes: set[str] = set()
    for message in messages:
        if message.get("role") != "tool" or message.get("name") != "search_airports":
            continue
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        matches = payload.get("matches", [])
        if not isinstance(matches, list):
            continue
        for match in matches:
            if not isinstance(match, dict):
                continue
            code = str(match.get("iata", "")).strip().upper()
            if len(code) == 3:
                codes.add(code)
    return codes


def _strict_date_clarification(args: dict[str, Any]) -> str | None:
    departure_date = str(args.get("departure_date", "")).strip()
    return_date = str(args.get("return_date", "")).strip()
    trip_type = str(args.get("trip_type", "oneway") or "oneway").strip().lower()

    requested_dates = [d for d in [departure_date] if d]
    if trip_type == "roundtrip" and return_date:
        requested_dates.append(return_date)

    if not requested_dates:
        return "What date would you like to fly? Please use YYYY-MM-DD."

    return None


def _ranked_destination_candidates(
    messages: list[dict[str, Any]],
    exclude: str,
) -> list[str]:
    """
    Returns destination IATA codes in priority order from search_airports
    tool results, excluding the origin. Preserves the order returned by
    the airport search service (international airports ranked higher)
    rather than pulling from the unordered grounded_codes set.
    """
    seen: set[str] = set()
    candidates: list[str] = []

    for m in messages:
        if m.get("role") != "tool" or m.get("name") != "search_airports":
            continue
        content = m.get("content", "")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        matches = payload.get("matches", [])
        if not isinstance(matches, list):
            continue
        for match in matches:
            code = str(match.get("iata", "")).strip().upper()
            if len(code) == 3 and code != exclude and code not in seen:
                seen.add(code)
                candidates.append(code)

    return candidates


def _strict_airport_clarification(
    args: dict[str, Any],
    messages: list[dict[str, Any]],
) -> str | None:
    origin = str(args.get("origin", "")).strip().upper()
    destination = str(args.get("destination", "")).strip().upper()

    explicit_codes = _user_explicit_iata_codes(messages)
    resolved_codes = _airport_codes_from_tool_results(messages)
    grounded_codes = explicit_codes | resolved_codes

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


def _latest_message_text(messages: list[dict[str, Any]], role: str) -> str:
    for message in reversed(messages):
        if message.get("role") == role:
            return str(message.get("content", "")).strip()
    return ""


def _latest_explicit_date(messages: list[dict[str, Any]]) -> str | None:
    today = datetime.date.today()

    # Find only the last real user message
    last_user_content = None
    for m in reversed(messages):
        if m.get("role") == "user" and not m.get("content", "").startswith("[context:"):
            last_user_content = str(m.get("content", ""))
            break

    if not last_user_content:
        return None

    iso_matches = _DATE_RE.findall(last_user_content)
    for match in reversed(iso_matches):
        try:
            datetime.date.fromisoformat(match)
            return match
        except ValueError:
            continue

    # Natural language
    nl_matches = _NL_DATE_RE.findall(last_user_content)
    for phrase in nl_matches:
        parsed = dateparser.parse(
            phrase,
            settings={
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": datetime.datetime.now(),
                "RETURN_AS_TIMEZONE_AWARE": False,
            },
        )
        if parsed and parsed.date() >= today:
            result = parsed.date().strftime("%Y-%m-%d")
            log.debug("DATE EXTRACT  returning=%s", result)
            return result

    return None


def _latest_airport_matches(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for message in reversed(messages):
        if message.get("role") != "tool" or message.get("name") != "search_airports":
            continue
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        matches = payload.get("matches", [])
        if isinstance(matches, list):
            return [m for m in matches if isinstance(m, dict)]
    return []


def _matches_from_result(result_str: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(result_str)
    except json.JSONDecodeError:
        return []
    matches = payload.get("matches", [])
    if not isinstance(matches, list):
        return []
    return [match for match in matches if isinstance(match, dict)]


def _render_multi_airport_results(results: list[dict]) -> str:
    """
    Renders flight results across multiple destination airports into a
    clean, readable markdown string grouped by airport.
    """
    if not results:
        return "No flights found."

    origin = results[0]["origin"]
    departure_date = results[0]["departure_date"]

    # Parse date for a friendlier display format
    try:
        import datetime

        date_obj = datetime.date.fromisoformat(departure_date)
        date_display = date_obj.strftime("%A, %B %d %Y")
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

        lines += [
            f"---",
            f"### {origin} → {destination}",
            "",
        ]

        for i, flight in enumerate(flights, 1):
            airline = flight.get("airline", "Unknown airline")
            departure = flight.get("departure_time", "—")
            arrival = flight.get("arrival_time", "—")
            duration = flight.get("duration", "—")
            stops = flight.get("stops", "—")
            price = flight.get("price", "—")

            # Stops badge
            if stops == "nonstop":
                stops_badge = "🟢 Nonstop"
            elif stops == "1 stop":
                stops_badge = "🟡 1 stop"
            else:
                stops_badge = f"🔴 {stops}"

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


def _normalize_place_hint(value: str) -> str:
    cleaned = re.sub(_DATE_RE, "", value)
    cleaned = re.sub(
        r"\b(it is|it's|i am|i'm|going to|traveling to)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.!?").strip()
    return cleaned


def _route_place_hints(messages: list[dict[str, Any]]) -> dict[str, list[str]]:
    hints: dict[str, list[str]] = {"origin": [], "destination": []}
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        for pattern in _ROUTE_PATTERNS:
            match = pattern.search(content)
            if not match:
                continue
            for key in ("origin", "destination"):
                value = _normalize_place_hint(match.group(key))
                if value and value not in hints[key]:
                    hints[key].append(value)
    return hints


def _render_search_flights_result(result_str: str) -> str | None:
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
            f"I couldn't find flights from {origin} to {destination} on {departure_date}. "
            "Want to try a different date, nearby airport, or route?"
        )

    lines = [f"Flights from {origin} to {destination} on {departure_date}:"]
    for index, flight in enumerate(flights, start=1):
        if not isinstance(flight, dict):
            continue
        airline = str(flight.get("airline", "")).strip() or "Unknown airline"
        departure_time = (
            str(flight.get("departure_time", "")).strip() or "Unknown departure"
        )
        arrival_time = str(flight.get("arrival_time", "")).strip() or "Unknown arrival"
        duration = str(flight.get("duration", "")).strip() or "Unknown duration"
        stops = str(flight.get("stops", "")).strip() or "Unknown stops"
        price = str(flight.get("price", "")).strip() or "Unknown price"
        lines.append(
            f"{index}. {airline} | {departure_time} to {arrival_time} | {duration} | {stops} | {price}"
        )

    return "\n".join(lines)


class LocalToolAgent:
    """Local Qwen + tool calls + token streaming (no remote API)."""

    def __init__(self, model_service: ModelService) -> None:
        self._model = model_service
        self._executor = ToolExecutor()

    def _maybe_resume_grounded_search(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]] | None:
        last_assistant = _latest_message_text(messages, "assistant").lower()
        latest_user = _latest_message_text(messages, "user")
        if not last_assistant or not latest_user:
            return None

        if "what is your departure airport" not in last_assistant:
            return None

        origin_codes = _explicit_iata_codes_in_text(latest_user)
        if not origin_codes:
            return None

        departure_date = _latest_explicit_date(messages)
        if not departure_date:
            return None

        destination_matches = _latest_airport_matches(messages)
        if not destination_matches:
            return None

        destination_code = str(destination_matches[0].get("iata", "")).strip().upper()
        if len(destination_code) != 3:
            return None

        return (
            "search_flights",
            {
                "origin": origin_codes[0],
                "destination": destination_code,
                "departure_date": departure_date,
                "trip_type": "oneway",
            },
        )

    def _maybe_direct_user_search(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]] | None:
        if not messages or messages[-1].get("role") != "user":
            return None

        latest_user = _latest_message_text(messages, "user")
        if not latest_user:
            return None

        explicit_codes = _explicit_iata_codes_in_text(latest_user)
        explicit_dates = _DATE_RE.findall(latest_user)
        if len(explicit_codes) < 2 or not explicit_dates:
            return None

        args: dict[str, Any] = {
            "origin": explicit_codes[0],
            "destination": explicit_codes[1],
            "departure_date": explicit_dates[0],
            "trip_type": "oneway",
        }
        if len(explicit_dates) >= 2:
            args["trip_type"] = "roundtrip"
            args["return_date"] = explicit_dates[1]

        return ("search_flights", args)

    def _maybe_resolve_route_hint_search(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]] | None:
        if not messages or messages[-1].get("role") != "user":
            return None

        latest_user = _latest_message_text(messages, "user")
        if not latest_user:
            return None

        if len(_explicit_iata_codes_in_text(latest_user)) >= 2:
            return None

        hints = _route_place_hints(messages)
        origin_hints = hints.get("origin", [])
        destination_hints = hints.get("destination", [])
        if not origin_hints or not destination_hints:
            return None

        departure_date = _latest_explicit_date(messages)
        if not departure_date:
            return None

        origin_result = self._executor.run(
            "search_airports", {"query": origin_hints[0]}
        )
        messages.append(
            {"role": "tool", "name": "search_airports", "content": origin_result}
        )
        destination_result = self._executor.run(
            "search_airports", {"query": destination_hints[0]}
        )
        messages.append(
            {"role": "tool", "name": "search_airports", "content": destination_result}
        )

        origin_matches = _matches_from_result(origin_result)
        destination_matches = _matches_from_result(destination_result)
        if not origin_matches or not destination_matches:
            return None

        origin_code = str(origin_matches[0].get("iata", "")).strip().upper()
        destination_code = str(destination_matches[0].get("iata", "")).strip().upper()
        if len(origin_code) != 3 or len(destination_code) != 3:
            return None

        args: dict[str, Any] = {
            "origin": origin_code,
            "destination": destination_code,
            "departure_date": departure_date,
            "trip_type": "oneway",
        }

        return ("search_flights", args)

    def _maybe_finish_from_tool_result(
        self,
        name: str,
        result_str: str,
    ) -> str | None:
        # Only used for single model-driven search_flights calls now.
        # Multi-airport results are handled by _render_multi_airport_results.
        if name == "search_flights":
            return _render_search_flights_result(result_str)
        return None

    def _maybe_ground_route_codes(
        self,
        args: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> None:
        hints = _route_place_hints(messages)
        explicit_codes = _user_explicit_iata_codes(messages)
        grounded_codes = explicit_codes | _airport_codes_from_tool_results(messages)

        missing_queries: list[str] = []
        origin = str(args.get("origin", "")).strip().upper()
        destination = str(args.get("destination", "")).strip().upper()

        if len(origin) == 3 and origin not in grounded_codes:
            for hint in hints["origin"]:
                if hint.upper() != origin:
                    missing_queries.append(hint)
                    break

        grounded_codes = explicit_codes | _airport_codes_from_tool_results(messages)
        if len(destination) == 3 and destination not in grounded_codes:
            for hint in hints["destination"]:
                if hint.upper() != destination:
                    missing_queries.append(hint)
                    break

        for query in missing_queries:
            log.info("AGENT AUTO-RESOLVE airport query=%s", query)
            result_str = self._executor.run("search_airports", {"query": query})
            messages.append(
                {"role": "tool", "name": "search_airports", "content": result_str}
            )

    def run(
        self,
        messages: list[dict[str, Any]],
    ) -> Generator[AgentStreamEvent, None, None]:
        log.info("AGENT START  steps=%d", settings.agent_max_steps)
        yield AgentStreamEvent("status", "Thinking…")

        user_wants_flights = _is_flight_search_intent(messages)
        log.info("AGENT flight_intent=%s", user_wants_flights)

        thread: list[dict[str, Any]] = list(messages)

        # ── Pre-resolve destination from map picker ────────────────────────────
        if user_wants_flights:
            selected = st.session_state.get("selected_location")
            if selected is not None:
                location_query = (
                    selected.get("city")
                    or selected.get("county")
                    or selected.get("state_region")
                    or selected.get("country")
                )
                if location_query:
                    log.info("AGENT pre-resolving destination=%s", location_query)
                    yield AgentStreamEvent(
                        "status", f"Resolving destination: {location_query}…"
                    )
                    result_str = self._executor.run(
                        "search_airports", {"query": location_query}
                    )
                    thread.append(
                        {
                            "role": "tool",
                            "name": "search_airports",
                            "content": result_str,
                        }
                    )

            departure_resolved = st.session_state.get("departure_city_resolved")
            if departure_resolved:
                iata = str(departure_resolved.get("iata", "")).strip().upper()
                if len(iata) == 3:
                    log.info("AGENT pre-resolving origin=%s", iata)
                    yield AgentStreamEvent("status", f"Using departure: {iata}…")
                    synthetic = json.dumps(
                        {"matches": [departure_resolved], "count": 1}
                    )
                    thread.append(
                        {
                            "role": "tool",
                            "name": "search_airports",
                            "content": synthetic,
                        }
                    )
            # ── Pre-inject departure date ──────────────────────────────────────────
            latest_chat_date = _latest_explicit_date(messages)
            sidebar_date = st.session_state.get("departure_date")

            date_str = None
            if latest_chat_date:
                # User typed a date in chat — this takes priority
                date_str = latest_chat_date
                log.info("AGENT using chat-provided date=%s", date_str)
                # Store the resolved date back to session state so the sidebar stays
                # in sync with what the user said in chat
                try:
                    parsed_date = datetime.date.fromisoformat(latest_chat_date)
                    if parsed_date != sidebar_date:
                        st.session_state["departure_date"] = parsed_date
                        st.session_state["_date_from_chat"] = True
                        st.session_state["departure_date_picker"] = parsed_date
                except ValueError:
                    pass
            elif sidebar_date:
                # Fall back to sidebar picker
                date_str = sidebar_date.strftime("%Y-%m-%d")
                log.info("AGENT using sidebar date=%s", date_str)

            thread.append(
                {
                    "role": "user",
                    "content": f"[context: departure date is {date_str}]",
                }
            )
        else:
            log.info("AGENT skipping pre-resolution, not a flight request")

        for step in range(settings.agent_max_steps):
            is_last_possible = step == settings.agent_max_steps - 1

            grounded_codes = _user_explicit_iata_codes(
                thread
            ) | _airport_codes_from_tool_results(thread)
            explicit_dates = _user_explicit_dates(thread)

            already_searched = _searched_since_last_user_message(thread)

            # ── Short-circuit to search_flights ───────────────────────────────
            if (
                user_wants_flights
                and len(grounded_codes) >= 2
                and explicit_dates
                and not already_searched
            ):
                origin = st.session_state.get("departure_city_resolved", {}).get("iata")
                if not origin or origin not in grounded_codes:
                    codes = list(grounded_codes)
                    origin = codes[0]

                destination_candidates = _ranked_destination_candidates(
                    thread, exclude=origin
                )

                if destination_candidates:
                    departure_date_str = date_str or sorted(explicit_dates)[0]
                    all_results: list[dict] = []  # collect (airport, flights) tuples

                    for destination in destination_candidates:
                        args = {
                            "origin": origin,
                            "destination": destination,
                            "departure_date": departure_date_str,
                            "trip_type": "oneway",
                        }
                        log.info(
                            "AGENT SHORT-CIRCUIT search_flights  %s→%s date=%s",
                            origin,
                            destination,
                            departure_date_str,
                        )
                        yield AgentStreamEvent(
                            "status", f"Searching {origin} → {destination}…"
                        )
                        result_str = self._executor.run("search_flights", args)
                        thread.append(
                            {
                                "role": "tool",
                                "name": "search_flights",
                                "content": result_str,
                            }
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "name": "search_flights",
                                "content": result_str,
                            }
                        )

                        try:
                            result_payload = json.loads(result_str)
                        except json.JSONDecodeError:
                            continue

                        flights = result_payload.get("flights", [])
                        if result_payload.get("success") and flights:
                            all_results.append(
                                {
                                    "origin": origin,
                                    "destination": destination,
                                    "departure_date": departure_date_str,
                                    "flights": flights,
                                }
                            )
                            log.info(
                                "AGENT SHORT-CIRCUIT %s→%s returned %d flights",
                                origin,
                                destination,
                                len(flights),
                            )
                        else:
                            log.info(
                                "AGENT SHORT-CIRCUIT %s→%s no flights",
                                origin,
                                destination,
                            )

                    if all_results:
                        final_text = _render_multi_airport_results(all_results)
                        yield AgentStreamEvent("done", final_text)
                        messages.append({"role": "assistant", "content": final_text})
                        return
                    else:
                        tried = ", ".join(destination_candidates)
                        fallback = (
                            f"I couldn't find any flights from **{origin}** to "
                            f"nearby airports ({tried}) on **{departure_date_str}**.\n\n"
                            "Would you like to try different dates or a different destination?"
                        )
                        yield AgentStreamEvent("done", fallback)
                        messages.append({"role": "assistant", "content": fallback})
                        return
            # ── Model generation ───────────────────────────────────────────────
            full_text = ""
            yield AgentStreamEvent("status", "Thinking…")

            for token in self._model.stream_agent_turn(thread, tools=TOOLS):
                full_text += token

            log.info(
                "AGENT STEP %d  generated %d chars  has_tool_call=%s",
                step + 1,
                len(full_text),
                _has_tool_call_tag(full_text),
            )

            calls = parse_tool_calls(full_text)
            visible = _strip_tool_blocks(full_text) or full_text.strip()

            # ── Narration guard ────────────────────────────────────────────────
            if not calls and _is_narration(visible) and not is_last_possible:
                log.info(
                    "AGENT STEP %d  narration detected, looping: %r",
                    step + 1,
                    visible[:120],
                )
                yield AgentStreamEvent("status", "Searching…")
                continue

            # ── Hallucination guard ────────────────────────────────────────────
            _FLIGHT_HALLUCINATION = re.compile(
                r"(airline|departure time|arrival time|number of stops|price.*\$)",
                re.IGNORECASE,
            )
            if (
                not calls
                and _FLIGHT_HALLUCINATION.search(visible)
                and not any(m.get("name") == "search_flights" for m in thread)
                and not is_last_possible
                and user_wants_flights
            ):
                log.warning("AGENT STEP %d  hallucination detected, looping", step + 1)
                yield AgentStreamEvent("status", "Searching…")
                continue

            # ── Real tool calls ────────────────────────────────────────────────
            if calls:
                thread.append({"role": "assistant", "content": full_text})
                yield AgentStreamEvent(
                    "status",
                    f"Searching ({len(calls)} tool call{'s' if len(calls) > 1 else ''})…",
                )
                explicit_dates_now = _user_explicit_dates(thread)
                for call in calls:
                    name = str(call.get("name", "")).strip()
                    args = normalize_arguments(call.get("arguments", {}))

                    if name == "search_flights":
                        self._maybe_ground_route_codes(args, thread)
                        airport_clarification = _strict_airport_clarification(
                            args, thread
                        )
                        if airport_clarification is not None:
                            thread.pop()
                            yield AgentStreamEvent("done", airport_clarification)
                            messages.append(
                                {
                                    "role": "assistant",
                                    "content": airport_clarification,
                                }
                            )
                            return

                        clarification = _strict_date_clarification(args)
                        if clarification is None:
                            requested_dates = [
                                str(args.get("departure_date", "")).strip()
                            ]
                            missing = [
                                d
                                for d in requested_dates
                                if d and d not in explicit_dates_now
                            ]
                            if missing:
                                clarification = "Please give me the exact travel date in YYYY-MM-DD format."
                        if clarification is not None:
                            thread.pop()
                            yield AgentStreamEvent("done", clarification)
                            messages.append(
                                {"role": "assistant", "content": clarification}
                            )
                            return

                    yield AgentStreamEvent("status", f"Running `{name}`…")
                    result_str = self._executor.run(name, args)
                    thread.append({"role": "tool", "name": name, "content": result_str})
                    # Write real tool results back to caller's messages
                    messages.append(
                        {"role": "tool", "name": name, "content": result_str}
                    )
                    final_text = self._maybe_finish_from_tool_result(name, result_str)
                    if final_text:
                        yield AgentStreamEvent("done", final_text)
                        messages.append({"role": "assistant", "content": final_text})
                        return
                continue

            # ── Genuine final response ─────────────────────────────────────────
            thread.append({"role": "assistant", "content": full_text})
            messages.append({"role": "assistant", "content": full_text})
            log.info("AGENT DONE   final reply %d chars", len(visible))
            for token in visible:
                yield AgentStreamEvent("token", token)
            yield AgentStreamEvent("done", visible)
            return

        # Max steps fallback
        fallback = (
            "I hit the maximum number of steps. Could you provide more specific "
            "details — like the 3-letter airport codes and departure date (YYYY-MM-DD)?"
        )
        yield AgentStreamEvent("done", fallback)
        messages.append({"role": "assistant", "content": fallback})

    def run_collect(self, messages: list[dict[str, Any]]) -> str:
        last = ""
        for event in self.run(messages):
            if event.kind == "done":
                last = event.text
        return last
