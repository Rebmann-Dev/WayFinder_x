from __future__ import annotations

import re
from collections.abc import Generator
from typing import Any

from agents.tool_call_parser import normalize_arguments, parse_tool_calls
from agents.tool_definitions import TOOLS
from agents.tool_executor import ToolExecutor
from core.config import settings
from services.model_service import ModelService

_TOOL_STRIP = re.compile(r"<tool_call>[\s\S]*?</tool_call>", re.IGNORECASE)


class AgentStreamEvent:
    __slots__ = ("kind", "text")

    def __init__(self, kind: str, text: str = "") -> None:
        self.kind = kind  # "status" | "token" | "done"
        self.text = text


def _strip_tool_blocks(text: str) -> str:
    return _TOOL_STRIP.sub("", text).strip()


def _has_tool_call_tag(text: str) -> bool:
    return "<tool_call>" in text.lower()


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

            messages.append({"role": "assistant", "content": full_text})

            calls = parse_tool_calls(full_text)
            if not calls:
                visible = _strip_tool_blocks(full_text) or full_text.strip()
                yield AgentStreamEvent("done", visible)
                return

            yield AgentStreamEvent(
                "status",
                f"Searching ({len(calls)} tool call{'s' if len(calls) > 1 else ''})…",
            )

            for call in calls:
                name = str(call.get("name", "")).strip()
                args = normalize_arguments(call.get("arguments", {}))
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
