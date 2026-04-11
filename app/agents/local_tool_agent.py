from __future__ import annotations

import datetime
import json
import logging
import re
from collections.abc import Generator
from typing import Any

import streamlit as st

from agents.utils import (
    airport_codes_from_tool_results,
    has_tool_call_tag,
    is_flight_search_intent,
    is_narration,
    latest_explicit_date,
    ranked_destination_candidates,
    render_multi_airport_results,
    render_search_flights_result,
    route_place_hints,
    searched_since_last_user_message,
    strict_airport_clarification,
    strict_date_clarification,
    strip_tool_blocks,
    user_explicit_dates,
    user_explicit_iata_codes,
)
from agents.tool_call_parser import normalize_arguments, parse_tool_calls
from agents.tool_definitions import TOOLS
from agents.tool_executor import ToolExecutor
from core.config import settings
from services.model_service import ModelService

log = logging.getLogger("wayfinder.agent")

_FLIGHT_HALLUCINATION_RE = re.compile(
    r"(airline|departure time|arrival time|number of stops|price.*\$)",
    re.IGNORECASE,
)


class AgentStreamEvent:
    __slots__ = ("kind", "text")

    def __init__(self, kind: str, text: str = "") -> None:
        self.kind = kind  # "status" | "token" | "done"
        self.text = text


class LocalToolAgent:
    """
    Orchestrates a local Qwen model with tool calling and token streaming.

    On each run():
    - Detects flight intent before doing any pre-resolution work
    - Pre-resolves origin, destination, and date from sidebar session state
    - Short-circuits to search_flights once both airports and a date are grounded
    - Falls back to model generation for non-flight queries and ambiguous cases
    - Guards against narration loops and hallucinated flight results
    """

    def __init__(self, model_service: ModelService) -> None:
        self._model = model_service
        self._executor = ToolExecutor()

    def _ground_route_codes(
        self,
        args: dict[str, Any],
        thread: list[dict[str, Any]],
    ) -> None:
        """
        Resolves any ungrounded IATA codes in args by running search_airports
        on place name hints extracted from user messages.
        """
        hints = route_place_hints(thread)
        grounded = user_explicit_iata_codes(thread) | airport_codes_from_tool_results(
            thread
        )

        queries: list[str] = []
        for key, hint_key in [("origin", "origin"), ("destination", "destination")]:
            code = str(args.get(key, "")).strip().upper()
            if len(code) == 3 and code not in grounded:
                for hint in hints[hint_key]:
                    if hint.upper() != code:
                        queries.append(hint)
                        break

        for query in queries:
            log.info("AGENT AUTO-RESOLVE airport query=%s", query)
            result_str = self._executor.run("search_airports", {"query": query})
            thread.append(
                {"role": "tool", "name": "search_airports", "content": result_str}
            )

    def _pre_resolve_destination(self, thread: list[dict[str, Any]]) -> Generator:
        """Resolves the map-picked destination into the thread."""
        selected = st.session_state.get("selected_location")
        if selected is None:
            return

        location_query = (
            selected.get("city")
            or selected.get("county")
            or selected.get("state_region")
            or selected.get("country")
        )
        if not location_query:
            return

        log.info("AGENT pre-resolving destination=%s", location_query)
        yield AgentStreamEvent("status", f"Resolving destination: {location_query}…")
        result_str = self._executor.run("search_airports", {"query": location_query})
        thread.append(
            {"role": "tool", "name": "search_airports", "content": result_str}
        )

    def _pre_resolve_origin(self, thread: list[dict[str, Any]]) -> Generator:
        """Injects the sidebar-resolved departure airport as a synthetic tool result."""
        departure_resolved = st.session_state.get("departure_city_resolved")
        if not departure_resolved:
            return

        iata = str(departure_resolved.get("iata", "")).strip().upper()
        if len(iata) != 3:
            return

        log.info("AGENT pre-resolving origin=%s", iata)
        yield AgentStreamEvent("status", f"Using departure: {iata}…")
        synthetic = json.dumps({"matches": [departure_resolved], "count": 1})
        thread.append({"role": "tool", "name": "search_airports", "content": synthetic})

    def _pre_inject_date(
        self,
        thread: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> str | None:
        """
        Resolves the departure date from chat or sidebar and injects it
        into the thread. Returns the resolved date string or None.
        """
        latest_chat_date = latest_explicit_date(messages)
        sidebar_date = st.session_state.get("departure_date")

        date_str = None
        if latest_chat_date:
            date_str = latest_chat_date
            log.info("AGENT using chat-provided date=%s", date_str)
            try:
                parsed = datetime.date.fromisoformat(latest_chat_date)
                if parsed != sidebar_date:
                    st.session_state["departure_date"] = parsed
                    st.session_state["_date_from_chat"] = True
            except ValueError:
                pass
        elif sidebar_date:
            date_str = sidebar_date.strftime("%Y-%m-%d")
            log.info("AGENT using sidebar date=%s", date_str)

        if date_str:
            thread.append(
                {"role": "user", "content": f"[context: departure date is {date_str}]"}
            )
        return date_str

    def _run_short_circuit(
        self,
        thread: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        grounded_codes: set[str],
        explicit_dates: set[str],
        date_str: str | None,
    ) -> Generator[AgentStreamEvent, None, None] | None:
        """
        If both airports are grounded and a date exists, searches all
        ranked destination candidates and renders aggregated results.
        Returns a generator if it handled the request, None otherwise.
        """
        origin = st.session_state.get("departure_city_resolved", {}).get("iata")
        if not origin or origin not in grounded_codes:
            origin = next(iter(grounded_codes))

        candidates = ranked_destination_candidates(thread, exclude=origin)
        if not candidates:
            return None

        departure_date_str = date_str or sorted(explicit_dates)[0]

        def _generate():
            all_results: list[dict] = []

            for destination in candidates:
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
                yield AgentStreamEvent("status", f"Searching {origin} → {destination}…")
                result_str = self._executor.run("search_flights", args)
                tool_msg = {
                    "role": "tool",
                    "name": "search_flights",
                    "content": result_str,
                }
                thread.append(tool_msg)
                messages.append(tool_msg)

                try:
                    payload = json.loads(result_str)
                except json.JSONDecodeError:
                    continue

                if payload.get("success") and payload.get("flights"):
                    all_results.append(
                        {
                            "origin": origin,
                            "destination": destination,
                            "departure_date": departure_date_str,
                            "flights": payload["flights"],
                        }
                    )
                    log.info(
                        "AGENT SHORT-CIRCUIT %s→%s returned %d flights",
                        origin,
                        destination,
                        len(payload["flights"]),
                    )
                else:
                    log.info(
                        "AGENT SHORT-CIRCUIT %s→%s no flights", origin, destination
                    )

            if all_results:
                final_text = render_multi_airport_results(all_results)
            else:
                tried = ", ".join(candidates)
                final_text = (
                    f"I couldn't find any flights from **{origin}** to "
                    f"nearby airports ({tried}) on **{departure_date_str}**.\n\n"
                    "Would you like to try different dates or a different destination?"
                )

            yield AgentStreamEvent("done", final_text)
            messages.append({"role": "assistant", "content": final_text})

        return _generate()

    def _check_tool_call_args(
        self,
        calls: list[dict[str, Any]],
        thread: list[dict[str, Any]],
    ) -> str | None:
        """
        Validates tool call arguments before execution.
        Returns a clarification string if something is missing, None if all good.
        """
        explicit_dates_now = user_explicit_dates(thread)

        for call in calls:
            name = str(call.get("name", "")).strip()
            args = normalize_arguments(call.get("arguments", {}))

            if name == "search_flights":
                self._ground_route_codes(args, thread)

                airport_msg = strict_airport_clarification(args, thread)
                if airport_msg:
                    return airport_msg

                date_msg = strict_date_clarification(args)
                if date_msg is None:
                    requested = [str(args.get("departure_date", "")).strip()]
                    if any(d and d not in explicit_dates_now for d in requested):
                        date_msg = (
                            "Please give me the exact travel date in YYYY-MM-DD format."
                        )
                if date_msg:
                    return date_msg

        return None

    def _execute_tool_calls(
        self,
        calls: list[dict[str, Any]],
        thread: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> Generator[AgentStreamEvent, None, None]:
        """
        Executes validated tool calls and yields status/done events.
        Only called after _check_tool_call_args returns None.
        """
        for call in calls:
            name = str(call.get("name", "")).strip()
            args = normalize_arguments(call.get("arguments", {}))

            yield AgentStreamEvent("status", f"Running `{name}`…")
            result_str = self._executor.run(name, args)
            tool_msg = {"role": "tool", "name": name, "content": result_str}
            thread.append(tool_msg)
            messages.append(tool_msg)

            if name == "search_flights":
                final_text = render_search_flights_result(result_str)
                if final_text:
                    yield AgentStreamEvent("done", final_text)
                    messages.append({"role": "assistant", "content": final_text})
                    return

    def run(
        self,
        messages: list[dict[str, Any]],
    ) -> Generator[AgentStreamEvent, None, None]:
        log.info("AGENT START  steps=%d", settings.agent_max_steps)
        yield AgentStreamEvent("status", "Thinking…")

        user_wants_flights = is_flight_search_intent(messages)
        log.info("AGENT flight_intent=%s", user_wants_flights)

        thread: list[dict[str, Any]] = list(messages)
        date_str: str | None = None

        # ── Pre-resolution (flight requests only) ──────────────────────────
        if user_wants_flights:
            yield from self._pre_resolve_destination(thread)
            yield from self._pre_resolve_origin(thread)
            date_str = self._pre_inject_date(thread, messages)
            log.info("AGENT pre-resolution complete  date_str=%s", date_str)
        else:
            log.info("AGENT skipping pre-resolution, not a flight request")

        # ── Agent loop ─────────────────────────────────────────────────────
        for step in range(settings.agent_max_steps):
            is_last_possible = step == settings.agent_max_steps - 1

            grounded_codes = user_explicit_iata_codes(
                thread
            ) | airport_codes_from_tool_results(thread)
            explicit_dates = user_explicit_dates(thread)
            already_searched = searched_since_last_user_message(thread)

            log.info(
                "AGENT STEP %d  grounded=%s  dates=%s  already_searched=%s  "
                "user_wants_flights=%s  is_last=%s",
                step + 1,
                grounded_codes,
                explicit_dates,
                already_searched,
                user_wants_flights,
                is_last_possible,
            )
            log.debug(
                "AGENT STEP %d  roles=%s",
                step + 1,
                [f"{m.get('role')}:{m.get('name', '')}" for m in thread],
            )

            # ── Short-circuit to search_flights ───────────────────────────────
            short_circuit_eligible = (
                user_wants_flights
                and len(grounded_codes) >= 2
                and bool(explicit_dates)
                and not already_searched
            )
            log.info(
                "AGENT STEP %d  short_circuit_eligible=%s  "
                "(grounded=%d dates=%d already_searched=%s)",
                step + 1,
                short_circuit_eligible,
                len(grounded_codes),
                len(explicit_dates),
                already_searched,
            )

            if short_circuit_eligible:
                log.info("AGENT STEP %d  entering short-circuit", step + 1)
                gen = self._run_short_circuit(
                    thread, messages, grounded_codes, explicit_dates, date_str
                )
                if gen is not None:
                    log.info(
                        "AGENT STEP %d  short-circuit generator active, yielding",
                        step + 1,
                    )
                    yield from gen
                    log.info(
                        "AGENT STEP %d  short-circuit complete, returning", step + 1
                    )
                    log.info("AGENT DONE at short-circuit")
                    return
                else:
                    log.info(
                        "AGENT STEP %d  short-circuit returned None (no candidates), "
                        "falling through to model",
                        step + 1,
                    )

            # ── Model generation ───────────────────────────────────────────
            log.info("AGENT STEP %d  starting model generation", step + 1)
            full_text = ""
            yield AgentStreamEvent("status", "Thinking…")

            for token in self._model.stream_agent_turn(thread, tools=TOOLS):
                full_text += token

            log.info(
                "AGENT STEP %d  model generation complete  chars=%d  has_tool_call=%s",
                step + 1,
                len(full_text),
                has_tool_call_tag(full_text),
            )

            calls = parse_tool_calls(full_text)
            visible = strip_tool_blocks(full_text) or full_text.strip()

            log.info(
                "AGENT STEP %d  parsed  calls=%d  visible_chars=%d",
                step + 1,
                len(calls),
                len(visible),
            )

            # ── Narration guard ────────────────────────────────────────────
            if not calls and is_narration(visible) and not is_last_possible:
                log.info(
                    "AGENT STEP %d  narration detected, looping: %r",
                    step + 1,
                    visible[:120],
                )
                yield AgentStreamEvent("status", "Searching…")
                continue

            # ── Hallucination guard ────────────────────────────────────────
            if (
                not calls
                and user_wants_flights
                and not is_last_possible
                and _FLIGHT_HALLUCINATION_RE.search(visible)
                and not any(m.get("name") == "search_flights" for m in thread)
            ):
                log.warning(
                    "AGENT STEP %d  hallucination detected, looping: %r",
                    step + 1,
                    visible[:120],
                )
                yield AgentStreamEvent("status", "Searching…")
                continue

            # ── Tool calls ─────────────────────────────────────────────────
            if calls:
                log.info(
                    "AGENT STEP %d  executing %d tool call(s)", step + 1, len(calls)
                )
                thread.append({"role": "assistant", "content": full_text})
                yield AgentStreamEvent(
                    "status",
                    f"Searching ({len(calls)} tool call{'s' if len(calls) > 1 else ''})…",
                )

                clarification = self._check_tool_call_args(calls, thread)
                if clarification:
                    log.info(
                        "AGENT STEP %d  clarification required: %r",
                        step + 1,
                        clarification[:120],
                    )
                    thread.pop()
                    yield AgentStreamEvent("done", clarification)
                    messages.append({"role": "assistant", "content": clarification})
                    log.info(
                        "AGENT DONE at CLARIFICATION final reply %d chars", len(visible)
                    )
                    return

                got_done = False
                for event in self._execute_tool_calls(calls, thread, messages):
                    yield event
                    if event.kind == "done":
                        got_done = True

                if got_done:
                    log.info(
                        "AGENT STEP %d  tool execution produced final response, returning",
                        step + 1,
                    )
                    log.info(
                        "AGENT DONE tool execution finished. final reply %d chars",
                        len(visible),
                    )
                    return

                log.info(
                    "AGENT STEP %d  tool executed, no final response yet, continuing loop",
                    step + 1,
                )
                continue

            # ── Final response ─────────────────────────────────────────────
            log.info(
                "AGENT STEP %d  no tool calls, no guards triggered — "
                "treating as final response  chars=%d",
                step + 1,
                len(visible),
            )
            thread.append({"role": "assistant", "content": full_text})
            messages.append({"role": "assistant", "content": full_text})
            log.info("AGENT DONE  final reply %d chars", len(visible))
            yield AgentStreamEvent("done", visible)
            return

        # ── Max steps fallback ─────────────────────────────────────────────
        log.warning(
            "AGENT MAX STEPS REACHED  steps=%d  last_grounded=%s  last_dates=%s",
            settings.agent_max_steps,
            grounded_codes,
            explicit_dates,
        )

        fallback = (
            "I hit the maximum number of steps. Could you provide more specific "
            "details — like the 3-letter airport codes and departure date (YYYY-MM-DD)?"
        )
        yield AgentStreamEvent("done", fallback)
        messages.append({"role": "assistant", "content": fallback})

    def run_collect(self, messages: list[dict[str, Any]]) -> str:
        """Convenience method that collects and returns the final response text."""
        last = ""
        for event in self.run(messages):
            if event.kind == "done":
                last = event.text
        return last
