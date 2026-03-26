from __future__ import annotations

import json
import logging
import re
from collections.abc import Generator
from typing import Any

from agents.tool_call_parser import normalize_arguments, parse_tool_calls
from agents.tool_definitions import TOOLS
from agents.tool_executor import ToolExecutor
from core.config import settings
from services.model_service import ModelService

log = logging.getLogger("wayfinder.agent")

_TOOL_STRIP = re.compile(r"<tool_call>[\s\S]*?</tool_call>", re.IGNORECASE)
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_IATA_RE = re.compile(r"\b[A-Z]{3}\b")
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
        dates.update(_DATE_RE.findall(content))
    return dates


def _explicit_iata_codes_in_text(text: str) -> list[str]:
    return _IATA_RE.findall(text)


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
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        matches = _DATE_RE.findall(str(message.get("content", "")))
        if matches:
            return matches[-1]
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


def _normalize_place_hint(value: str) -> str:
    cleaned = re.sub(_DATE_RE, "", value)
    cleaned = re.sub(r"\b(it is|it's|i am|i'm|going to|traveling to)\b", "", cleaned, flags=re.IGNORECASE)
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
        departure_time = str(flight.get("departure_time", "")).strip() or "Unknown departure"
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

        origin_result = self._executor.run("search_airports", {"query": origin_hints[0]})
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
            messages.append({"role": "tool", "name": "search_airports", "content": result_str})

    def run(
        self,
        messages: list[dict[str, Any]],
    ) -> Generator[AgentStreamEvent, None, None]:
        """
        Mutates ``messages`` in place (same list as session llm thread).
        Final user-visible text is emitted as an event with kind ``done``.

        Intermediate tool-call steps are **not** streamed to the UI — only a
        status caption is shown so the user sees progress without raw XML.
        The final non-tool-call generation is streamed token-by-token.
        """
        log.info("AGENT START  steps=%d", settings.agent_max_steps)
        yield AgentStreamEvent("status", "Thinking…")

        for step in range(settings.agent_max_steps):
            is_last_possible = step == settings.agent_max_steps - 1

            direct_call = self._maybe_direct_user_search(messages)
            if direct_call is not None:
                name, args = direct_call
                log.info(
                    "AGENT DIRECT  %s args=%s",
                    name,
                    json.dumps(args, default=str),
                )
                yield AgentStreamEvent("status", f"Running `{name}`…")
                result_str = self._executor.run(name, args)
                messages.append({"role": "tool", "name": name, "content": result_str})
                final_text = self._maybe_finish_from_tool_result(name, result_str)
                if final_text is not None:
                    yield AgentStreamEvent("done", final_text)
                    messages.append({"role": "assistant", "content": final_text})
                    return
                if not is_last_possible:
                    yield AgentStreamEvent("status", "Processing results…")
                    continue

            route_hint_call = self._maybe_resolve_route_hint_search(messages)
            if route_hint_call is not None:
                name, args = route_hint_call
                log.info(
                    "AGENT RESOLVED  %s args=%s",
                    name,
                    json.dumps(args, default=str),
                )
                yield AgentStreamEvent("status", f"Running `{name}`…")
                result_str = self._executor.run(name, args)
                messages.append({"role": "tool", "name": name, "content": result_str})
                final_text = self._maybe_finish_from_tool_result(name, result_str)
                if final_text is not None:
                    yield AgentStreamEvent("done", final_text)
                    messages.append({"role": "assistant", "content": final_text})
                    return
                if not is_last_possible:
                    yield AgentStreamEvent("status", "Processing results…")
                    continue

            resumed_call = self._maybe_resume_grounded_search(messages)
            if resumed_call is not None:
                name, args = resumed_call
                log.info(
                    "AGENT RESUME  %s args=%s",
                    name,
                    json.dumps(args, default=str),
                )
                yield AgentStreamEvent("status", f"Running `{name}`…")
                result_str = self._executor.run(name, args)
                messages.append({"role": "tool", "name": name, "content": result_str})
                final_text = self._maybe_finish_from_tool_result(name, result_str)
                if final_text is not None:
                    yield AgentStreamEvent("done", final_text)
                    messages.append({"role": "assistant", "content": final_text})
                    return
                if not is_last_possible:
                    yield AgentStreamEvent("status", "Processing results…")
                    continue

            full_text = ""
            stream_to_ui = False

            for token in self._model.stream_agent_turn(messages, tools=TOOLS):
                full_text += token

                if not stream_to_ui and not _has_tool_call_tag(full_text):
                    yield AgentStreamEvent("token", token)
                elif not stream_to_ui and _has_tool_call_tag(full_text):
                    stream_to_ui = False

            log.info("AGENT STEP %d  generated %d chars  has_tool_call=%s", step + 1, len(full_text), _has_tool_call_tag(full_text))
            messages.append({"role": "assistant", "content": full_text})

            calls = parse_tool_calls(full_text)
            if not calls:
                visible = _strip_tool_blocks(full_text) or full_text.strip()
                log.info("AGENT DONE   final reply %d chars", len(visible))
                yield AgentStreamEvent("done", visible)
                return

            yield AgentStreamEvent(
                "status",
                f"Searching ({len(calls)} tool call{'s' if len(calls) > 1 else ''})…",
            )

            explicit_dates = _user_explicit_dates(messages)
            for call in calls:
                name = str(call.get("name", "")).strip()
                args = normalize_arguments(call.get("arguments", {}))

                if name == "search_flights":
                    self._maybe_ground_route_codes(args, messages)
                    airport_clarification = _strict_airport_clarification(
                        args,
                        messages,
                    )
                    if airport_clarification is not None:
                        log.info(
                            "AGENT BLOCKED search_flights  ungrounded route origin=%s destination=%s",
                            str(args.get("origin", "")).strip().upper(),
                            str(args.get("destination", "")).strip().upper(),
                        )
                        messages.pop()
                        yield AgentStreamEvent("done", airport_clarification)
                        messages.append(
                            {"role": "assistant", "content": airport_clarification}
                        )
                        return

                    clarification = _strict_date_clarification(args)
                    requested_dates = [
                        str(args.get("departure_date", "")).strip(),
                    ]
                    return_date = str(args.get("return_date", "")).strip()
                    trip_type = str(args.get("trip_type", "oneway") or "oneway").strip().lower()
                    if trip_type == "roundtrip" and return_date:
                        requested_dates.append(return_date)

                    if clarification is None:
                        missing_explicit_dates = [
                            d for d in requested_dates if d and d not in explicit_dates
                        ]
                        if missing_explicit_dates:
                            clarification = (
                                "Please give me the exact travel date in YYYY-MM-DD format. "
                                "I can't use relative dates like 'tomorrow' or 'next Friday'."
                            )

                    if clarification is not None:
                        log.info(
                            "AGENT BLOCKED search_flights  explicit_dates=%s requested=%s",
                            sorted(explicit_dates),
                            requested_dates,
                        )
                        messages.pop()
                        yield AgentStreamEvent("done", clarification)
                        messages.append({"role": "assistant", "content": clarification})
                        return

                yield AgentStreamEvent("status", f"Running `{name}`…")
                result_str = self._executor.run(name, args)
                messages.append(
                    {"role": "tool", "name": name, "content": result_str}
                )
                final_text = self._maybe_finish_from_tool_result(name, result_str)
                if final_text is not None:
                    yield AgentStreamEvent("done", final_text)
                    messages.append({"role": "assistant", "content": final_text})
                    return

            if not is_last_possible:
                yield AgentStreamEvent("status", "Processing results…")

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
