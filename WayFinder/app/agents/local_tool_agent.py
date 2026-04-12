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
    is_safety_intent,
    latest_destination_mention,
    latest_explicit_date,
    ranked_destination_candidates,
    render_multi_airport_results,
    render_safety_result,
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

# Tokens we strip off the tail of airport names when deriving a city
# query for the safety lookup.
_AIRPORT_NAME_DESCRIPTORS = {
    "airport",
    "airfield",
    "airbase",
    "international",
    "intl",
    "intercontinental",
    "regional",
    "municipal",
    "national",
    "metropolitan",
    "terminal",
    "field",
}

# Words to strip when extracting a location from a free-form safety question.
_SAFETY_STRIP_RE = re.compile(
    r"\b(?:safe|safety|dangerous|danger|crime|criminal|risk|risky|"
    r"secure|security|hazard|hazardous|is|it|for|in|of|at|the|a|an|"
    r"how|what|whats|about|country|destination|tell|me|to|would|i|"
    r"travel|travell?ing|visit|visiting|going|place|like|level|rate|"
    r"rating|score|be|currently|right|now|today)\b",
    re.IGNORECASE,
)


def _extract_safety_location(text: str) -> str | None:
    """
    Strips safety keywords and common filler words from a free-form
    question so only the place name remains.
    """
    if not text:
        return None
    cleaned = text.replace("'", "")
    cleaned = re.sub(r"[?!.,:;]+", " ", cleaned)
    cleaned = _SAFETY_STRIP_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _location_query_candidates(mention: str) -> list[str]:
    """
    Expands a user-typed location mention into a priority-ordered list of
    progressively shorter queries for the substring-match geocoder.
    """
    if not mention:
        return []

    seen: set[str] = set()
    out: list[str] = []

    def _add(value: str) -> None:
        value = value.strip(" ,.!?")
        if value and value.lower() not in seen:
            seen.add(value.lower())
            out.append(value)

    _add(mention)
    before_comma = mention.split(",", 1)[0]
    _add(before_comma)

    tokens = [t for t in before_comma.split() if t]
    for length in range(len(tokens) - 1, 0, -1):
        _add(" ".join(tokens[:length]))

    return out


def _city_candidates_from_airport_name(name: str) -> list[str]:
    """
    Derives plausible city-name queries from an airport name by peeling
    descriptor tokens off the end.
    """
    if not name:
        return []
    tokens = [t for t in re.split(r"\s+", name.strip()) if t]
    while tokens and tokens[-1].strip(".,").lower() in _AIRPORT_NAME_DESCRIPTORS:
        tokens.pop()
    if not tokens:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for length in range(len(tokens), 0, -1):
        candidate = " ".join(tokens[:length]).strip()
        key = candidate.lower()
        if candidate and key not in seen:
            seen.add(key)
            out.append(candidate)
    return out


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
    - Handles safety queries via deterministic short-circuit
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

    def _airport_safety_brief(
        self,
        airport: dict[str, str],
        cache: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        """
        Returns a per-airport safety brief ``{score, band, city, country}``
        or None if no query candidate resolves.
        """
        iata = str(airport.get("iata", "")).strip().upper()
        if iata and iata in cache:
            return cache[iata]

        name = str(airport.get("name", "")).strip()
        city = str(airport.get("city", "")).strip()
        country = str(airport.get("country", "")).strip()

        selected = st.session_state.get("selected_location") or {}
        selected_city = str(
            selected.get("city")
            or selected.get("county")
            or selected.get("state_region")
            or ""
        ).strip()

        queries: list[str] = []
        if city:
            queries.append(city)
        for candidate in _city_candidates_from_airport_name(name):
            if candidate and candidate not in queries:
                queries.append(candidate)
        if selected_city and selected_city not in queries:
            queries.append(selected_city)

        geocoded: tuple[float, float, str] | None = None
        matched_query: str | None = None
        for query in queries:
            result = self._executor._safety.geocode_place(query)
            if result is not None:
                geocoded = result
                matched_query = query
                break

        if geocoded is None:
            log.info(
                "AGENT safety-brief  geocode failed for %s (tried %s)",
                iata or name,
                queries,
            )
            if iata:
                cache[iata] = None  # type: ignore[assignment]
            return None

        lat, lon, geocoded_country = geocoded
        assess = self._executor._safety.assess_location(
            latitude=lat,
            longitude=lon,
            country=country or geocoded_country,
            location_name=matched_query,
            include_details=False,
        )
        if not assess.get("success"):
            log.info(
                "AGENT safety-brief  assess failed iata=%s err=%s",
                iata,
                assess.get("error"),
            )
            if iata:
                cache[iata] = None  # type: ignore[assignment]
            return None

        brief = {
            "city": matched_query or city or "this destination",
            "country": country or geocoded_country,
            "score": assess.get("safety_score"),
            "band": str(assess.get("risk_band", "") or "").lower(),
            "lat": lat,
            "lon": lon,
        }
        if iata:
            cache[iata] = brief
        log.info(
            "AGENT safety-brief  %s via %r score=%s band=%s",
            iata,
            matched_query,
            brief["score"],
            brief["band"],
        )
        return brief

    def _update_destination_from_chat(
        self,
        messages: list[dict[str, Any]],
    ) -> bool:
        """
        If the latest user message names a new destination, geocode it and
        replace ``st.session_state['selected_location']`` so the sidebar and
        downstream tools pick up the chat-driven update.
        """
        mention = latest_destination_mention(messages)
        if not mention:
            return False

        current = st.session_state.get("selected_location") or {}
        current_name = (
            current.get("city")
            or current.get("county")
            or current.get("state_region")
            or current.get("country")
            or ""
        )
        if current_name and current_name.strip().lower() == mention.strip().lower():
            return False

        candidates = _location_query_candidates(mention)
        geocoded: tuple[float, float, str] | None = None
        resolved_name: str | None = None
        for candidate in candidates:
            result = self._executor._safety.geocode_place(candidate)
            if result is not None:
                geocoded = result
                resolved_name = candidate
                break

        if geocoded is None or resolved_name is None:
            log.info(
                "AGENT chat-destination  geocode failed for %r (tried %s)",
                mention,
                candidates,
            )
            return False

        lat, lon, country = geocoded
        st.session_state["selected_location"] = {
            "city": resolved_name,
            "country": country,
            "lat": lat,
            "lon": lon,
        }
        st.session_state["safety_result"] = None
        st.session_state["_destination_from_chat"] = True
        log.info(
            "AGENT chat-destination  updated to %s (%.4f, %.4f) country=%s",
            resolved_name,
            lat,
            lon,
            country,
        )
        return True

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

        candidates = _location_query_candidates(location_query)
        yield AgentStreamEvent("status", f"Resolving destination: {location_query}…")
        last_result: str | None = None
        for query in candidates:
            log.info("AGENT pre-resolving destination=%s", query)
            result_str = self._executor.run("search_airports", {"query": query})
            last_result = result_str
            try:
                payload = json.loads(result_str)
            except json.JSONDecodeError:
                payload = {}
            if payload.get("matches"):
                thread.append(
                    {"role": "tool", "name": "search_airports", "content": result_str}
                )
                return
            log.info(
                "AGENT pre-resolving destination=%s no matches, trying next",
                query,
            )

        if last_result is not None:
            thread.append(
                {"role": "tool", "name": "search_airports", "content": last_result}
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

    def _run_safety_short_circuit(
        self,
        messages: list[dict[str, Any]],
    ) -> Generator[AgentStreamEvent, None, None] | None:
        """
        Deterministic safety path: when the user asks about safety, crime,
        or risk, bypass the model and call ``get_safety_assessment``
        ourselves.
        """
        from agents.utils.thread import latest_user_message

        latest = latest_user_message(messages)
        location = _extract_safety_location(latest) if latest else None

        if not location:
            selected = st.session_state.get("selected_location") or {}
            location = (
                selected.get("city")
                or selected.get("county")
                or selected.get("state_region")
                or selected.get("country")
                or None
            )

        if not location:
            return None

        def _generate():
            candidates = _location_query_candidates(location)
            resolved_result: str | None = None
            matched_query: str | None = None
            for query in candidates:
                log.info("AGENT SAFETY SHORT-CIRCUIT  %s", query)
                yield AgentStreamEvent("status", f"Looking up safety data for {query}…")
                result_str = self._executor.run(
                    "get_safety_assessment", {"location_name": query}
                )
                try:
                    payload = json.loads(result_str)
                except json.JSONDecodeError:
                    payload = {}
                if payload.get("success"):
                    resolved_result = result_str
                    matched_query = query
                    break
                log.info(
                    "AGENT SAFETY SHORT-CIRCUIT  %s failed, trying next candidate",
                    query,
                )

            if resolved_result is None:
                final_text = (
                    f"I couldn't find safety data for **{location}**. "
                    "Try a well-known city name."
                )
            else:
                final_text = render_safety_result(resolved_result) or (
                    f"Got safety data for {matched_query} but couldn't render it."
                )

            yield AgentStreamEvent("done", final_text)
            messages.append({"role": "assistant", "content": final_text})

        return _generate()

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
            safety_by_iata: dict[str, dict[str, Any]] = {}

            for candidate in candidates:
                destination = candidate["iata"]
                dest_name = candidate.get("name") or destination
                dest_city = candidate.get("city") or ""
                dest_country = candidate.get("country") or ""

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
                    "status",
                    f"Searching flights {origin} → {destination} ({dest_name})…",
                )
                result_str = self._executor.run("search_flights", args)
                tool_msg = {
                    "role": "tool",
                    "name": "search_flights",
                    "content": result_str,
                }
                thread.append(tool_msg)

                try:
                    payload = json.loads(result_str)
                except json.JSONDecodeError:
                    continue

                if payload.get("success") and payload.get("flights"):
                    safety_info = self._airport_safety_brief(
                        candidate, safety_by_iata
                    )
                    all_results.append(
                        {
                            "origin": origin,
                            "destination": destination,
                            "destination_name": dest_name,
                            "destination_city": dest_city,
                            "destination_country": dest_country,
                            "destination_safety": safety_info,
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
                tried = ", ".join(c["iata"] for c in candidates)
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

            if name == "search_flights":
                yield AgentStreamEvent("status", "Searching for flights…")
            elif name == "search_airports":
                yield AgentStreamEvent("status", "Checking airport information…")
            elif name == "get_safety_assessment":
                location = str(args.get("location_name", "")).strip()
                yield AgentStreamEvent(
                    "status",
                    f"Looking up safety data for {location}…" if location else "Looking up safety data…",
                )
            else:
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

            if name == "get_safety_assessment":
                final_text = render_safety_result(result_str)
                if final_text:
                    yield AgentStreamEvent("done", final_text)
                    messages.append({"role": "assistant", "content": final_text})
                    return

    def run(
        self,
        messages: list[dict[str, Any]],
    ) -> Generator[AgentStreamEvent, None, None]:
        log.info("AGENT START  steps=%d", settings.agent_max_steps)
        yield AgentStreamEvent("status", "Preparing your response…")

        user_wants_flights = is_flight_search_intent(messages)
        user_wants_safety = is_safety_intent(messages)
        log.info(
            "AGENT flight_intent=%s  safety_intent=%s",
            user_wants_flights,
            user_wants_safety,
        )

        thread: list[dict[str, Any]] = list(messages)
        date_str: str | None = None

        # ── Pre-resolution (flight requests only) ──────────────────────────
        if user_wants_flights:
            if self._update_destination_from_chat(messages):
                yield AgentStreamEvent(
                    "status",
                    f"Switching destination to "
                    f"{st.session_state['selected_location']['city']}…",
                )
            yield from self._pre_resolve_destination(thread)
            yield from self._pre_resolve_origin(thread)
            date_str = self._pre_inject_date(thread, messages)
            log.info("AGENT pre-resolution complete  date_str=%s", date_str)
        else:
            log.info("AGENT skipping pre-resolution, not a flight request")

        # ── Safety short-circuit ───────────────────────────────────────────
        if user_wants_safety and not user_wants_flights:
            log.info("AGENT entering safety short-circuit")
            safety_gen = self._run_safety_short_circuit(messages)
            if safety_gen is not None:
                yield from safety_gen
                log.info("AGENT DONE at safety short-circuit")
                return
            log.info(
                "AGENT safety short-circuit skipped (no location), "
                "falling through to model"
            )

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
            _trim_thread_to_fit(
                thread,
                count_tokens=self._model.count_tokens,
                tools=TOOLS,
                target_tokens=int(self._model.MAX_INPUT_TOKENS * 0.85),
            )

            log.info("AGENT STEP %d  starting model generation", step + 1)
            full_text = ""
            yield AgentStreamEvent("status", "Analyzing results…")

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
                yield AgentStreamEvent("status", "Searching for flights…")
                continue

            # ── Tool calls ─────────────────────────────────────────────────
            if calls:
                log.info(
                    "AGENT STEP %d  executing %d tool call(s)", step + 1, len(calls)
                )
                thread.append({"role": "assistant", "content": full_text})
                tool_names = [str(c.get("name", "")).strip() for c in calls]
                if "search_flights" in tool_names:
                    status_msg = "Searching for flights…"
                elif "get_safety_assessment" in tool_names:
                    status_msg = "Looking up safety data…"
                elif "search_airports" in tool_names:
                    status_msg = "Checking airport information…"
                else:
                    status_msg = f"Running {len(calls)} tool call{'s' if len(calls) > 1 else ''}…"
                yield AgentStreamEvent("status", status_msg)

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

                messages.append({"role": "assistant", "content": full_text})

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


def _last_real_user_index(thread: list[dict[str, Any]]) -> int:
    """Index of the most recent user turn that isn't a [context:…] injection."""
    last = -1
    for i, m in enumerate(thread):
        if m.get("role") != "user":
            continue
        if str(m.get("content", "")).startswith("[context:"):
            continue
        last = i
    return last


def _trim_thread_to_fit(
    thread: list[dict[str, Any]],
    *,
    count_tokens,
    tools: list[dict[str, Any]] | None,
    target_tokens: int,
) -> None:
    """
    Trims ``thread`` in place until its tokenized form fits under
    ``target_tokens``. Drops oldest tool results first (bulkiest), then
    oldest pre-current-turn messages. Preserves the system prompt and the
    most recent real user message and everything after it.
    """
    try:
        count = count_tokens(thread, tools)
    except Exception as exc:  # tokenizer errors shouldn't block generation
        log.warning("TRIM  count_tokens failed up front: %s", exc)
        return

    if count <= target_tokens:
        return

    initial = count
    log.info(
        "TRIM  start count=%d target=%d msgs=%d",
        initial,
        target_tokens,
        len(thread),
    )

    # Phase 1 — drop oldest tool results (and their paired assistant
    # tool_call turn if present) until we fit or run out of tool messages.
    while count > target_tokens:
        cutoff = _last_real_user_index(thread)
        tool_idx = next(
            (
                i
                for i, m in enumerate(thread)
                if m.get("role") == "tool" and (cutoff < 0 or i < cutoff)
            ),
            None,
        )
        if tool_idx is None:
            break

        thread.pop(tool_idx)
        # If the immediately preceding assistant turn was the tool_call
        # that produced this result, drop it too — an orphan tool_call
        # with no result confuses the Qwen chat template.
        prev_idx = tool_idx - 1
        if prev_idx >= 0 and thread[prev_idx].get("role") == "assistant":
            prev_content = str(thread[prev_idx].get("content", "")).lower()
            if "<tool_call>" in prev_content:
                thread.pop(prev_idx)

        try:
            count = count_tokens(thread, tools)
        except Exception as exc:
            log.warning("TRIM  count_tokens failed mid-pass: %s", exc)
            return

    # Phase 2 — if still over, drop oldest non-system messages that sit
    # before the latest real user turn, one at a time.
    while count > target_tokens:
        cutoff = _last_real_user_index(thread)
        drop_idx = next(
            (
                i
                for i, m in enumerate(thread)
                if m.get("role") != "system" and (cutoff < 0 or i < cutoff)
            ),
            None,
        )
        if drop_idx is None:
            break

        thread.pop(drop_idx)
        try:
            count = count_tokens(thread, tools)
        except Exception as exc:
            log.warning("TRIM  count_tokens failed mid-pass: %s", exc)
            return

    log.info(
        "TRIM  end count=%d (from %d) msgs=%d",
        count,
        initial,
        len(thread),
    )
