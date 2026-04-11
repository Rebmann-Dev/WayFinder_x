from __future__ import annotations

import datetime
import json
import logging
import re
from typing import Any

import dateparser

log = logging.getLogger("wayfinder.agent")

_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

_NL_DATE_RE = re.compile(
    r"""
    (?:
        (?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|
           jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|
           dec(?:ember)?)
        [\s,]+\d{1,2}(?:st|nd|rd|th)?[\s,]+\d{4}
        |
        \d{1,2}(?:st|nd|rd|th)?[\s,]+
        (?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|
           jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|
           dec(?:ember)?)
        [\s,]+\d{4}
        |
        (?:next|this)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)
        |
        in\s+\d+\s+(?:day|week|month)s?
        |
        tomorrow
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_IATA_RE = re.compile(r"\b[A-Z]{3}\b")

_ROUTE_PATTERNS = (
    re.compile(
        r"\bfrom\s+(?P<origin>.+?)\s+to\s+(?P<destination>.+?)(?:$|[,.!?]| on | for )",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bto\s+(?P<destination>.+?)\s+from\s+(?P<origin>.+?)(?:$|[,.!?]| on | for )",
        re.IGNORECASE,
    ),
)

# Module-level IATA cache — populated lazily from the airport CSV
_KNOWN_IATA_CACHE: set[str] = set()


def _is_valid_iata(code: str) -> bool:
    """Validates a 3-letter code against the known airport dataset."""
    global _KNOWN_IATA_CACHE
    if not _KNOWN_IATA_CACHE:
        from services.airport_search_service import _load_airports

        _KNOWN_IATA_CACHE = {row.code for row in _load_airports()}
    return code.upper() in _KNOWN_IATA_CACHE


def explicit_iata_codes_in_text(text: str) -> list[str]:
    """
    Extracts 3-letter codes from text, returning only real IATA airport
    codes. Filters out false positives like USA, API, VPN.
    """
    return [code for code in _IATA_RE.findall(text) if _is_valid_iata(code)]


def user_explicit_iata_codes(messages: list[dict[str, Any]]) -> set[str]:
    """Returns all valid IATA codes mentioned in user messages."""
    codes: set[str] = set()
    for message in messages:
        if message.get("role") != "user":
            continue
        codes.update(explicit_iata_codes_in_text(str(message.get("content", ""))))
    return codes


def airport_codes_from_tool_results(messages: list[dict[str, Any]]) -> set[str]:
    """Returns all IATA codes resolved via search_airports tool results."""
    codes: set[str] = set()
    for message in messages:
        if message.get("role") != "tool" or message.get("name") != "search_airports":
            continue
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        for match in payload.get("matches", []):
            if not isinstance(match, dict):
                continue
            code = str(match.get("iata", "")).strip().upper()
            if len(code) == 3:
                codes.add(code)
    return codes


def user_explicit_dates(messages: list[dict[str, Any]]) -> set[str]:
    """Returns all valid ISO dates mentioned in user messages."""
    dates: set[str] = set()
    for message in messages:
        if message.get("role") != "user":
            continue
        for match in _DATE_RE.findall(str(message.get("content", ""))):
            try:
                datetime.date.fromisoformat(match)
                dates.add(match)
            except ValueError:
                pass
    return dates


def latest_explicit_date(messages: list[dict[str, Any]]) -> str | None:
    """
    Extracts a date from the most recent real user message only.
    Handles both ISO format (2026-08-15) and natural language
    ('august 15th 2026', 'next friday', 'tomorrow').
    Does not scan backwards through history to avoid stale dates
    from previous turns bleeding into new searches.
    """
    today = datetime.date.today()

    last_user_content = None
    for m in reversed(messages):
        if m.get("role") == "user" and not m.get("content", "").startswith("[context:"):
            last_user_content = str(m.get("content", ""))
            break

    if not last_user_content:
        return None

    # ISO format first — unambiguous
    for match in reversed(_DATE_RE.findall(last_user_content)):
        try:
            datetime.date.fromisoformat(match)
            return match
        except ValueError:
            continue

    # Natural language — extract phrase first then parse it
    for phrase in _NL_DATE_RE.findall(last_user_content):
        parsed = dateparser.parse(
            phrase,
            settings={
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": datetime.datetime.now(),
                "RETURN_AS_TIMEZONE_AWARE": False,
            },
        )
        log.debug("DATE EXTRACT  phrase=%r parsed=%s", phrase, parsed)
        if parsed and parsed.date() >= today:
            result = parsed.date().strftime("%Y-%m-%d")
            log.debug("DATE EXTRACT  returning=%s", result)
            return result

    return None


def latest_airport_matches(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Returns the airport matches from the most recent search_airports result."""
    for message in reversed(messages):
        if message.get("role") != "tool" or message.get("name") != "search_airports":
            continue
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        matches = payload.get("matches", [])
        if isinstance(matches, list):
            return [m for m in matches if isinstance(m, dict)]
    return []


def matches_from_result(result_str: str) -> list[dict[str, Any]]:
    """Parses airport matches out of a raw search_airports result string."""
    try:
        payload = json.loads(result_str)
    except json.JSONDecodeError:
        return []
    matches = payload.get("matches", [])
    if not isinstance(matches, list):
        return []
    return [m for m in matches if isinstance(m, dict)]


def latest_message_text(messages: list[dict[str, Any]], role: str) -> str:
    """Returns the most recent message content for a given role."""
    for message in reversed(messages):
        if message.get("role") == role:
            return str(message.get("content", "")).strip()
    return ""


def _normalize_place_hint(value: str) -> str:
    cleaned = re.sub(_DATE_RE, "", value)
    cleaned = re.sub(
        r"\b(it is|it's|i am|i'm|going to|traveling to)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip(" ,.!?").strip()


def route_place_hints(messages: list[dict[str, Any]]) -> dict[str, list[str]]:
    """
    Extracts origin and destination place name hints from user messages
    using route pattern matching ('from X to Y').
    """
    hints: dict[str, list[str]] = {"origin": [], "destination": []}
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        for pattern in _ROUTE_PATTERNS:
            match = pattern.search(content)
            if not match:
                continue
            for key in ("origin", "destination"):
                value = _normalize_place_hint(match.group(key))
                if value and value not in hints[key]:
                    hints[key].append(value)
    return hints
