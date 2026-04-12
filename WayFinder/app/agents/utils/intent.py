from __future__ import annotations

import re
from typing import Any

_FLIGHT_INTENT_RE = re.compile(
    r"""
    \b(
        flight|flights|fly|flying|airfare|ticket|tickets|
        search\s+flights|find\s+flights|look\s*up\s+flights|
        show\s*me\s+flights|get\s*me\s+flights|book\s+flights|
        depart|departure
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_NON_FLIGHT_RE = re.compile(
    r"\b(tell\s*me\s*about|what\s*is|what's|what\s*are|describe|info|information|"
    r"weather|hotel|hotels|restaurant|things\s*to\s*do|attractions?|"
    r"safe|safety|visa|currency|culture|language|timezone|"
    r"hike|hikes|hiking|wildlife|food|cuisine|tips|history|"
    r"activities|sights?|explore|nightlife)\b",
    re.IGNORECASE,
)

_NARRATION_PATTERNS = (
    re.compile(
        r"I (will|am going to|can) (now |)(look up|search|find|check|call|use)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(Let me|I'll) (now |)(look up|search|find|check|call|use)",
        re.IGNORECASE,
    ),
    re.compile(r"I have found .{0,60}(now|next|so)", re.IGNORECASE),
    re.compile(r"Once I have .{0,60}(will|can|I'll)", re.IGNORECASE),
    re.compile(r"Now[,]? I will", re.IGNORECASE),
)


def is_flight_search_intent(messages: list[dict[str, Any]]) -> bool:
    """
    Returns True only if the most recent real user message is asking
    for a flight search. Prevents pre-resolution firing on general
    travel questions like 'tell me about LA' or 'tell me about hikes'.
    """
    from agents.utils.thread import latest_user_message

    latest = latest_user_message(messages)
    if not latest:
        return False

    has_flight = bool(_FLIGHT_INTENT_RE.search(latest))
    has_non_flight = bool(_NON_FLIGHT_RE.search(latest))

    # If the message contains general/non-flight keywords, only treat
    # as flight intent if there is also an explicit flight keyword
    if has_non_flight:
        return has_flight

    return has_flight


def is_narration(text: str) -> bool:
    """
    Returns True if the model output looks like chain-of-thought narration
    about what it intends to do rather than a genuine final response.
    Only matches short outputs — long responses are never narration.
    """
    from agents.utils.renderers import strip_tool_blocks

    stripped = strip_tool_blocks(text).strip()
    if len(stripped) > 400:
        return False
    return any(p.search(stripped) for p in _NARRATION_PATTERNS)
