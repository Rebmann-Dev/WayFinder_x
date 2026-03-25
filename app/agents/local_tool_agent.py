from __future__ import annotations

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


class LocalToolAgent:
    """Local Qwen + tool calls + token streaming (no remote API)."""

    def __init__(self, model_service: ModelService) -> None:
        self._model = model_service
        self._executor = ToolExecutor()

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
                        yield AgentStreamEvent("done", clarification)
                        messages.append({"role": "assistant", "content": clarification})
                        return

                yield AgentStreamEvent("status", f"Running `{name}`…")
                result_str = self._executor.run(name, args)
                messages.append(
                    {"role": "tool", "name": name, "content": result_str}
                )

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
