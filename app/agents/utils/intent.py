from __future__ import annotations

import re
from typing import Any

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

_NON_FLIGHT_RE = re.compile(
    r"\b(tell\s*me\s*about|what\s*is|what's|describe|info|information|"
    r"weather|hotel|hotels|restaurant|things\s*to\s*do|attraction|"
    r"safe|safety|visa|currency|culture|language|timezone)\b",
    re.IGNORECASE,
)

_SAFETY_INTENT_RE = re.compile(
    r"\b(safe|safety|dangerous|danger|crime|criminal|risk|risky|secure|security|hazard|hazardous)\b",
    re.IGNORECASE,
)

_WEB_SEARCH_INTENT_RE = re.compile(
    r"\b(web|search the web|surf|surfing|hike|hiking|trek|trail|food|eat|restaurant|dish|"
    r"wildlife|animals|birds|visa|entry|border|vaccine|medical|budget|cost|price|cheap|expensive|"
    r"lodging|hotel|hostel|weather|climate|rain|season|national park|reserve|nature|"
    r"transport|bus|taxi|culture|etiquette|customs|cenote|cenotes|beach|beaches)\b",
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
    """
    from agents.utils.thread import latest_user_message

    latest = latest_user_message(messages)
    if not latest:
        return False

    # Safety queries are never flight intent — even if "travel" is present
    if _SAFETY_INTENT_RE.search(latest):
        return False

    if _NON_FLIGHT_RE.search(latest) and not _FLIGHT_INTENT_RE.search(latest):
        return False

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


def is_web_search_intent(messages: list[dict[str, Any]]) -> bool:
    """
    Returns True if the user asks for anything related to the web search categories
    (e.g., food, hikes, visas, budget, beaches) so we can bypass the flight short-circuit
    and let the agent answer both.
    """
    from agents.utils.thread import latest_user_message

    latest = latest_user_message(messages)
    if not latest:
        return False
    return bool(_WEB_SEARCH_INTENT_RE.search(latest))


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
