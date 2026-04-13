from __future__ import annotations

import json
from typing import Any


def latest_user_message(messages: list[dict[str, Any]]) -> str:
    """
    Returns the content of the most recent real user message,
    excluding context injections added by the agent pre-resolution.
    """
    for m in reversed(messages):
        if m.get("role") == "user" and not m.get("content", "").startswith("[context:"):
            return m.get("content", "").strip()
    return ""


def searched_since_last_user_message(messages: list[dict[str, Any]]) -> bool:
    """
    Returns True only if search_flights was called after the most recent
    real user message. Allows follow-up searches in the same session
    without blocking on previous results.
    """
    last_user_idx = None
    for i, m in enumerate(messages):
        if m.get("role") == "user" and not m.get("content", "").startswith("[context:"):
            last_user_idx = i

    if last_user_idx is None:
        return False

    return any(
        m.get("role") == "tool" and m.get("name") == "search_flights"
        for m in messages[last_user_idx:]
    )


def ranked_destination_candidates(
    messages: list[dict[str, Any]],
    exclude: str,
) -> list[dict[str, str]]:
    """
    Returns destination airport dicts (iata, name, city, country) in
    priority order from search_airports tool results, excluding the origin
    code. Preserves the search service's ranking (international airports
    first) rather than pulling from the unordered grounded_codes set.
    """
    seen: set[str] = set()
    candidates: list[dict[str, str]] = []

    for m in messages:
        if m.get("role") != "tool" or m.get("name") != "search_airports":
            continue
        try:
            payload = json.loads(m.get("content", ""))
        except json.JSONDecodeError:
            continue
        for match in payload.get("matches", []):
            if not isinstance(match, dict):
                continue
            code = str(match.get("iata", "")).strip().upper()
            if len(code) == 3 and code != exclude and code not in seen:
                seen.add(code)
                candidates.append(
                    {
                        "iata": code,
                        "name": str(match.get("name", "")).strip(),
                        "city": str(match.get("city", "")).strip(),
                        "country": str(match.get("country", "")).strip(),
                    }
                )

    return candidates
