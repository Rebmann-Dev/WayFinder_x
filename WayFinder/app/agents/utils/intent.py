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

# Strict subset — only these words count as *explicit* flight keywords
# when the message also matches non-flight patterns.
_EXPLICIT_FLIGHT_RE = re.compile(
    r"\b(flight|flights|fly|flying|airfare|ticket|tickets|book|"
    r"depart|departure|arrive|arrival|one[- ]?way|round[- ]?trip)\b",
    re.IGNORECASE,
)

_NON_FLIGHT_RE = re.compile(
    r"\b(tell\s*me\s*about|what\s*is|what's|describe|info|information|"
    r"weather|hotel|hotels|restaurant|things\s*to\s*do|attraction|"
    r"safe|safety|visa|currency|culture|language|timezone|"
    r"history|hike|hiking|wildlife|food|cuisine|nature|"
    r"general|overview|guide|geography|population)\b",
    re.IGNORECASE,
)

_SAFETY_INTENT_RE = re.compile(
    r"\b(safe|safety|dangerous|danger|crime|criminal|risk|risky|secure|security|hazard|hazardous)\b",
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
    travel questions like 'tell me about LA'.

    When non-flight patterns are detected (general info, culture, food,
    etc.), requires explicit flight keywords (flight, fly, book, ticket,
    depart, arrive) — broad words like "travel" or "trip" alone are not
    enough.
    """
    from agents.utils.thread import latest_user_message

    latest = latest_user_message(messages)
    if not latest:
        return False

    # Safety queries are never flight intent — even if "travel" is present
    if _SAFETY_INTENT_RE.search(latest):
        return False

    # If the message matches non-flight patterns (general info questions),
    # require explicit flight keywords — broad words like "travel"/"trip"
    # are not sufficient on their own.
    if _NON_FLIGHT_RE.search(latest):
        return bool(_EXPLICIT_FLIGHT_RE.search(latest))

    return bool(_FLIGHT_INTENT_RE.search(latest))


def is_safety_intent(messages: list[dict[str, Any]]) -> bool:
    """
    Returns True if the most recent real user message is asking about
    safety, crime, or risk for a location.
    """
    from agents.utils.thread import latest_user_message

    latest = latest_user_message(messages)
    if not latest:
        return False
    return bool(_SAFETY_INTENT_RE.search(latest))


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
