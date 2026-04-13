from __future__ import annotations

import datetime
import json
import re
from typing import Any

# Qwen-style XML blocks
_TOOL_STRIP = re.compile(r"<tool_call>[\s\S]*?</tool_call>", re.IGNORECASE)


def strip_tool_blocks(text: str) -> str:
    return _TOOL_STRIP.sub("", text).strip()


def has_tool_call_tag(text: str) -> bool:
    return "<tool_call>" in text.lower()


def render_search_flights_result(result_str: str) -> str | None:
    """
    Renders a single search_flights result into a readable string.
    Used for model-driven tool calls — multi-airport results use
    render_multi_airport_results instead.
    """
    try:
        payload = json.loads(result_str)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict) or "success" not in payload:
        return None

    if payload.get("success") is False:
        error = str(payload.get("error", "")).strip()
        return error or "Flight search failed."

    origin = str(payload.get("origin", "")).strip().upper()
    destination = str(payload.get("destination", "")).strip().upper()
    departure_date = str(payload.get("departure_date", "")).strip()
    flights = payload.get("flights", [])

    if payload.get("no_results") or not isinstance(flights, list) or not flights:
        return (
            f"I couldn't find flights from {origin} to {destination} "
            f"on {departure_date}. "
            "Want to try a different date, nearby airport, or route?"
        )

    lines = [f"Flights from {origin} to {destination} on {departure_date}:"]
    for i, flight in enumerate(flights, start=1):
        if not isinstance(flight, dict):
            continue
        airline = str(flight.get("airline", "")).strip() or "Unknown airline"
        dep = str(flight.get("departure_time", "")).strip() or "Unknown departure"
        arr = str(flight.get("arrival_time", "")).strip() or "Unknown arrival"
        duration = str(flight.get("duration", "")).strip() or "Unknown duration"
        stops = str(flight.get("stops", "")).strip() or "Unknown stops"
        price = str(flight.get("price", "")).strip() or "Unknown price"
        lines.append(
            f"{i}. {airline} | {dep} to {arr} | {duration} | {stops} | {price}"
        )

    return "\n".join(lines)


_BAND_META = {
    "low": {
        "emoji": "🟢",
        "label": "Low Risk",
        "lead": (
            "lands in the **low risk** band, which generally means it's a "
            "comfortable destination for most travellers"
        ),
        "advice": (
            "Standard precautions should serve you well — keep an eye on your "
            "belongings in crowded tourist areas and stay aware of your "
            "surroundings, but there's nothing here that should make you "
            "second-guess the trip."
        ),
    },
    "moderate": {
        "emoji": "🟡",
        "label": "Moderate Risk",
        "lead": (
            "sits in the **moderate risk** band — nothing alarming, but worth "
            "applying normal travel caution"
        ),
        "advice": (
            "Keep valuables out of sight in crowded areas, be a bit more "
            "selective about where you wander at night, and it's worth glancing "
            "at local news before you arrive. Most tourist-friendly areas are "
            "fine with sensible precautions."
        ),
    },
    "elevated": {
        "emoji": "🟠",
        "label": "Elevated Risk",
        "lead": (
            "falls into the **elevated risk** band, so you'll want to be a bit "
            "more deliberate about your plans than you would in a low-risk "
            "destination"
        ),
        "advice": (
            "A few practical tips: some neighbourhoods here are significantly "
            "safer than others, so it's worth researching the specific area "
            "you'll be staying in. Try to avoid travelling alone late at night, "
            "stick to reputable transport like Uber, Lyft, or licensed taxis, "
            "and keep copies of important documents somewhere separate from "
            "the originals."
        ),
    },
    "high": {
        "emoji": "🔴",
        "label": "High Risk",
        "lead": (
            "comes out in the **high risk** band, which means this destination "
            "warrants serious caution before and during your trip"
        ),
        "advice": (
            "I'd strongly suggest checking your government's official travel "
            "advisory before booking anything. If you do travel, stay in "
            "well-reviewed areas, keep emergency contacts on hand, maintain a "
            "low profile with valuables, and avoid venturing into unfamiliar "
            "areas alone — especially after dark."
        ),
    },
}


def _render_factor_prose(factors: dict, location: str) -> str:
    """Weave the structured factor dict into conversational paragraphs.

    All factors here are city-specific (KNN averages over nearby cities
    plus the single nearest labelled city). Country-level macros are
    intentionally excluded from the response because they're identical
    for every city in the same country.
    """
    nb_crime = factors.get("neighbourhood_crime")
    nb_safety = factors.get("neighbourhood_safety")
    near_crime = factors.get("nearest_city_crime")
    near_safety = factors.get("nearest_city_safety")

    parts: list[str] = []

    # ── Neighbourhood (KNN-5 average) sentence ─────────────────────────────
    nb_bits: list[str] = []
    if nb_crime is not None:
        nb_bits.append(
            f"a crime index of around **{nb_crime:.0f}/100** (lower is safer)"
        )
    if nb_safety is not None:
        nb_bits.append(
            f"a perceived-safety score near **{nb_safety:.0f}/100** "
            "(higher is safer)"
        )

    if nb_bits:
        joined = " and ".join(nb_bits)
        parts.append(
            f"{location} itself isn't directly in my labelled dataset, so I "
            f"look at the area around it. The five nearest labelled cities "
            f"average {joined} — referenced against global averages of "
            f"roughly 45 for crime and 55 for safety."
        )

    # ── Nearest-city sentence ──────────────────────────────────────────────
    near_bits: list[str] = []
    if near_crime is not None:
        near_bits.append(f"**{near_crime:.0f}/100** for crime")
    if near_safety is not None:
        near_bits.append(f"**{near_safety:.0f}/100** for perceived safety")

    if near_bits:
        joined = " and ".join(near_bits)
        parts.append(
            f"The single closest labelled city in my dataset scores "
            f"{joined}, which gives a more focused read on the immediate "
            f"urban area."
        )

    return "\n\n".join(parts)


def render_safety_result(result_str: str) -> str | None:
    """
    Renders a get_safety_assessment tool result into a natural, conversational
    markdown response. Returns None if the payload is not a valid safety result.
    """
    try:
        payload = json.loads(result_str)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict) or "safety_score" not in payload:
        return None

    if payload.get("success") is False:
        error = str(payload.get("error", "")).strip()
        return error or "Sorry, I couldn't run the safety assessment for that location."

    location = str(payload.get("location_name", "this location")).strip() or "this location"
    score = payload.get("safety_score")
    band = str(payload.get("risk_band", "unknown")).lower()
    factors: dict = payload.get("factors") or {}

    score_str = f"{score:.1f}" if isinstance(score, (int, float)) else "?"
    meta = _BAND_META.get(band, {
        "emoji": "⚪",
        "label": "Unknown",
        "lead": "didn't match a known risk band in my model",
        "advice": "",
    })

    # ── Header ─────────────────────────────────────────────────────────────
    lines = [
        f"## {meta['emoji']} {location} — {meta['label']}",
        "",
        f"**Safety score: {score_str} / 100**",
        "",
    ]

    # ── Lead paragraph (natural sentence with the band) ───────────────────
    lines.append(
        f"Based on the data I have, **{location}** {meta['lead']}. "
        "Here's what's behind that number:"
    )
    lines.append("")

    # ── Factor prose ───────────────────────────────────────────────────────
    factor_prose = _render_factor_prose(factors, location)
    if factor_prose:
        lines.append(factor_prose)
        lines.append("")

    # ── Advice paragraph ───────────────────────────────────────────────────
    if meta["advice"]:
        lines.append(meta["advice"])
        lines.append("")

    # ── Disclaimer ─────────────────────────────────────────────────────────
    lines.append(
        "*One thing to keep in mind: this is a model-based estimate built from "
        "geographic and socioeconomic data — not an official government travel "
        "advisory. For the most up-to-date guidance, always check your own "
        "government's travel advisory for the destination.*"
    )

    return "\n".join(lines)


_SAFETY_BAND_EMOJI = {
    "low": "🟢",
    "moderate": "🟡",
    "elevated": "🟠",
    "high": "🔴",
}

# Bar spans positions 0-20 (21 cells), so each tick (0/25/50/75/100)
# lands on a cell boundary and the scale/divider/bar all line up.
_DIAL_CELLS = 21
_DIAL_SCALE = "0    25   50   75   100"
_DIAL_DIVIDER = "├────┼────┼────┼────┤"


def _render_safety_dial(brief: dict[str, Any] | None) -> str:
    """
    Renders a compact numbered-dial gauge for a safety brief. Returns an
    empty string when the brief lacks a score so callers can skip cleanly.

    The dial is a fenced code block so monospace alignment holds across
    Streamlit's markdown renderer. Heading and band label sit above the
    fence where emoji render correctly.
    """
    if not brief:
        return ""
    score = brief.get("score")
    if score is None:
        return ""

    band = str(brief.get("band") or "").lower()
    city = str(brief.get("city") or "this destination").strip()

    try:
        clamped = max(0.0, min(100.0, float(score)))
    except (TypeError, ValueError):
        return ""

    # Map 0..100 onto cells 0..(_DIAL_CELLS-1) so 100 lands on the last cell.
    filled = int(round(clamped / 100.0 * (_DIAL_CELLS - 1)))
    filled = max(0, min(_DIAL_CELLS, filled))
    bar = "█" * filled + "░" * (_DIAL_CELLS - filled)

    # Pointer caret sits directly under the score's column so the reader
    # can read the exact position on the 0–100 scale.
    pointer_row = " " * filled + "▲"

    emoji = _SAFETY_BAND_EMOJI.get(band, "⚪")
    band_label = band.capitalize() if band else "Unknown"

    return (
        f"**{emoji} Safety · {city}** — **{clamped:.1f}/100** · {band_label} risk\n"
        "```\n"
        f"{_DIAL_SCALE}\n"
        f"{_DIAL_DIVIDER}\n"
        f"{bar}\n"
        f"{pointer_row}\n"
        "```"
    )


def render_multi_airport_results(results: list[dict[str, Any]]) -> str:
    """
    Renders flight results across multiple destination airports into
    clean markdown grouped by airport, with color-coded stop badges.
    """
    if not results:
        return "No flights found."

    origin = results[0]["origin"]
    departure_date = results[0]["departure_date"]

    try:
        date_display = datetime.date.fromisoformat(departure_date).strftime(
            "%A, %B %d %Y"
        )
    except ValueError:
        date_display = departure_date

    total_flights = sum(len(r["flights"]) for r in results)
    airport_count = len(results)

    lines = [
        f"## ✈️ Flights from {origin} · {date_display}",
        f"*Found **{total_flights} flight{'s' if total_flights != 1 else ''}** "
        f"across **{airport_count} airport{'s' if airport_count != 1 else ''}***",
        "",
    ]

    for result in results:
        destination = result["destination"]
        dest_name = str(result.get("destination_name") or "").strip()
        dest_city = str(result.get("destination_city") or "").strip()
        dest_country = str(result.get("destination_country") or "").strip()
        safety_brief = result.get("destination_safety")
        flights = result["flights"]

        header_label_parts = [destination]
        if dest_name and dest_name.upper() != destination:
            header_label_parts.append(dest_name)
        header_label = " · ".join(header_label_parts)

        location_meta_parts = [p for p in (dest_city, dest_country) if p]
        location_meta = " · ".join(location_meta_parts)

        lines += ["---", f"### {origin} → {header_label}"]
        if location_meta:
            lines.append(f"*{location_meta}*")
        lines.append("")
        safety_dial = _render_safety_dial(safety_brief)
        if safety_dial:
            lines.append(safety_dial)
            lines.append("")

        for i, flight in enumerate(flights, 1):
            airline = flight.get("airline", "Unknown airline")
            departure = flight.get("departure_time", "—")
            arrival = flight.get("arrival_time", "—")
            duration = flight.get("duration", "—")
            stops = flight.get("stops", "—")
            price = flight.get("price", "—")

            stops_badge = (
                "🟢 Nonstop"
                if stops == "nonstop"
                else "🟡 1 stop"
                if stops == "1 stop"
                else f"🔴 {stops}"
            )

            lines += [
                f"**{i}. {airline}**",
                f"&nbsp;&nbsp;🕐 {departure} → {arrival} &nbsp;·&nbsp; "
                f"⏱ {duration} &nbsp;·&nbsp; {stops_badge} &nbsp;·&nbsp; "
                f"💰 **{price}**",
                "",
            ]

    lines += [
        "---",
        "*Prices and availability may vary. "
        "Ask me to filter by stops, price, or airline — "
        "or pick a flight to get more details.*",
    ]

    return "\n".join(lines)
