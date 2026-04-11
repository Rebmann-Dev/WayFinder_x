from typing import List

import streamlit as st

import logging

from models.chat import ChatMessage
from prompts.system_prompts import build_system_prompt

_WELCOME_MESSAGE = (
    "Hi. I'm WayFinder, your travel planning assistant. Where would you like to go?"
)

log = logging.getLogger("wayfinder.agent")


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
        ):
            st.session_state.pop(key, None)

    @classmethod
    def get_latest_user_message(cls) -> str:
        for message in reversed(st.session_state[cls.SESSION_KEY]):
            if message.role == "user":
                return message.content
        return ""

    @classmethod
    def trim_llm_thread_for_context(cls, max_messages: int = 20) -> None:
        """
        Remove old tool result messages from the middle of the thread when it
        grows too large, preserving the system prompt, recent user/assistant
        turns, and any tool messages from the last 2 exchanges.
        """
        thread = st.session_state.get(cls.LLM_KEY, [])
        if len(thread) <= max_messages:
            return

        system = [m for m in thread if m.get("role") == "system"]
        rest = [m for m in thread if m.get("role") != "system"]

        # Drop old tool messages first — they're the bulkiest and least needed
        trimmed = [m for m in rest if m.get("role") != "tool"]

        # If still too long, keep only the most recent turns
        if len(system) + len(trimmed) > max_messages:
            trimmed = trimmed[-(max_messages - len(system)) :]

        st.session_state[cls.LLM_KEY] = system + trimmed
        log.info(
            "LLM thread trimmed to %d messages", len(st.session_state[cls.LLM_KEY])
        )

    @classmethod
    def get_clean_llm_messages(cls) -> list:
        """
        Returns the LLM thread with only valid roles for model input:
        system, user, assistant, and tool. Strips any duplicate assistant
        turns or leftover nudge messages from previous agent runs.
        """
        cls.initialize()
        thread = st.session_state.get(cls.LLM_KEY, [])
        cleaned = []
        for m in thread:
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
            # Only keep valid roles
            if role in ("system", "user", "assistant", "tool"):
                cleaned.append(m)

        return cleaned
