import json
from typing import List

import streamlit as st

import logging

from models.chat import ChatMessage
from prompts.system_prompts import build_system_prompt

_WELCOME_MESSAGE = (
    "Hi. I'm WayFinder, your travel planning assistant. Where would you like to go?"
)

log = logging.getLogger("wayfinder.agent")


def _compact_old_tool_content(name: str, content: str) -> str:
    """
    Reduce old tool-result payloads to their essential fields so that
    previous exchanges don't bloat the prompt or confuse the model.

    The `instruction` key is always stripped — it is a per-response
    directive that is meaningless (and harmful) in conversation history.
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content

    data.pop("instruction", None)

    if name == "search_flights":
        flights = data.get("flights", [])
        data = {
            "success": data.get("success"),
            "origin": data.get("origin"),
            "destination": data.get("destination"),
            "departure_date": data.get("departure_date"),
            "total_returned": data.get("total_returned", len(flights)),
        }
    elif name == "search_airports":
        data = {"matches": data.get("matches", [])[:3], "count": data.get("count")}
    elif name == "get_safety_assessment":
        # Keep score/band; drop verbose feature details
        data.pop("details", None)

    return json.dumps(data)


class MemoryService:
    SESSION_KEY = "messages"
    LLM_KEY = "llm_messages"

    @classmethod
    def initialize(cls) -> None:
        system_prompt = build_system_prompt()

        if cls.SESSION_KEY not in st.session_state:
            st.session_state[cls.SESSION_KEY] = [
                ChatMessage(
                    role="system",
                    content=system_prompt,
                ),
                ChatMessage(
                    role="assistant",
                    content=_WELCOME_MESSAGE,
                ),
            ]
        elif st.session_state[cls.SESSION_KEY]:
            first_message = st.session_state[cls.SESSION_KEY][0]
            if (
                first_message.role == "system"
                and first_message.content != system_prompt
            ):
                st.session_state[cls.SESSION_KEY][0] = ChatMessage(
                    role="system",
                    content=system_prompt,
                )

        if cls.LLM_KEY not in st.session_state:
            cls._reset_llm_thread()
        elif st.session_state[cls.LLM_KEY]:
            first_llm_message = st.session_state[cls.LLM_KEY][0]
            if (
                first_llm_message.get("role") == "system"
                and first_llm_message.get("content") != system_prompt
            ):
                st.session_state[cls.LLM_KEY][0] = {
                    "role": "system",
                    "content": system_prompt,
                }

    @classmethod
    def _reset_llm_thread(cls) -> None:
        st.session_state[cls.LLM_KEY] = [
            {"role": "system", "content": build_system_prompt()},
        ]

    @classmethod
    def append_llm_user(cls, content: str) -> None:
        cls.initialize()
        st.session_state[cls.LLM_KEY].append({"role": "user", "content": content})

    @classmethod
    def get_llm_messages(cls) -> list:
        cls.initialize()
        return st.session_state[cls.LLM_KEY]

    @classmethod
    def get_messages(cls) -> List[ChatMessage]:
        return st.session_state[cls.SESSION_KEY]

    @classmethod
    def add_message(cls, role: str, content: str) -> None:
        st.session_state[cls.SESSION_KEY].append(
            ChatMessage(role=role, content=content)
        )

    @classmethod
    def get_model_messages(cls, max_history: int = 8) -> list[dict[str, str]]:
        messages = st.session_state[cls.SESSION_KEY]

        system_message = messages[0]
        recent_messages = messages[1:][-max_history:]

        return [system_message.to_dict()] + [msg.to_dict() for msg in recent_messages]

    @classmethod
    def get_display_messages(cls) -> List[ChatMessage]:
        return [
            msg for msg in st.session_state[cls.SESSION_KEY] if msg.role != "system"
        ]

    @classmethod
    def clear(cls) -> None:
        st.session_state[cls.SESSION_KEY] = [
            ChatMessage(role="system", content=build_system_prompt()),
            ChatMessage(role="assistant", content=_WELCOME_MESSAGE),
        ]
        cls._reset_llm_thread()

        # Clear sidebar-provided travel context so the next conversation
        # starts fresh without stale origin/destination state
        for key in (
            "departure_city_raw",
            "departure_city_resolved",
            "departure_city_candidates",
            "departure_date",
            "_date_from_chat",
            "_destination_from_chat",
        ):
            st.session_state.pop(key, None)

    @classmethod
    def get_latest_user_message(cls) -> str:
        for message in reversed(st.session_state[cls.SESSION_KEY]):
            if message.role == "user":
                return message.content
        return ""

    @classmethod
    def trim_llm_thread_for_context(
        cls,
        model_service=None,
        tools=None,
        target_tokens: int | None = None,
    ) -> None:
        """
        Token-aware pre-agent trim. If ``model_service`` is provided, uses
        its tokenizer to count tokens and delegates to
        ``_trim_thread_to_fit`` for the actual pruning. Otherwise no-ops —
        the in-agent trim will catch any overflow just-in-time.
        """
        if model_service is None:
            return

        thread = st.session_state.get(cls.LLM_KEY, [])
        if not thread:
            return

        if target_tokens is None:
            max_in = getattr(model_service, "MAX_INPUT_TOKENS", 4096)
            target_tokens = int(max_in * 0.85)

        # Local import to avoid a circular dependency at module load
        from agents.local_tool_agent import _trim_thread_to_fit

        before = len(thread)
        _trim_thread_to_fit(
            thread,
            count_tokens=model_service.count_tokens,
            tools=tools,
            target_tokens=target_tokens,
        )
        if len(thread) != before:
            st.session_state[cls.LLM_KEY] = thread
            log.info(
                "LLM thread trimmed to %d messages (was %d)",
                len(thread),
                before,
            )

    @classmethod
    def get_clean_llm_messages(cls) -> list:
        """
        Returns the LLM thread with only valid roles for model input.

        - Strips nudge/context injection messages from previous agent runs.
        - Compacts tool results from *previous* exchanges: strips the
          `instruction` directive field and reduces large payloads (flight
          lists, airport lists) to a short summary. This prevents old tool
          blobs from confusing the model when the topic changes.
        - Tool results that belong to the *current* exchange (after the last
          user message) are left untouched so the model can use them fully.
        """
        cls.initialize()
        thread = st.session_state.get(cls.LLM_KEY, [])

        # Index of the last user message separates previous from current exchange
        last_user_idx = max(
            (i for i, m in enumerate(thread) if m.get("role") == "user"),
            default=len(thread),
        )

        cleaned = []
        for i, m in enumerate(thread):
            role = m.get("role", "")
            content = m.get("content", "")

            # Strip nudge messages injected by the narration guard
            if role == "user" and content.startswith(
                "Please call the appropriate tool now"
            ):
                continue
            # Strip context injections from previous agent runs
            if role == "user" and content.startswith("[context:"):
                continue

            # Drop orphan tool messages — a tool result without an
            # immediately preceding assistant(<tool_call>) turn breaks
            # Qwen's chat template and causes the next generation to
            # hallucinate. This can happen when prior short-circuit runs
            # persisted raw tool results without a wrapping assistant
            # turn.
            if role == "tool":
                prev = cleaned[-1] if cleaned else None
                prev_is_tool_call = (
                    prev is not None
                    and prev.get("role") == "assistant"
                    and "<tool_call>" in str(prev.get("content", "")).lower()
                )
                if not prev_is_tool_call:
                    continue

            # Compact tool results from previous exchanges
            if role == "tool" and i < last_user_idx:
                name = m.get("name", "")
                compacted = _compact_old_tool_content(name, content)
                cleaned.append({**m, "content": compacted})
                continue

            if role in ("system", "user", "assistant", "tool"):
                cleaned.append(m)

        return cleaned
