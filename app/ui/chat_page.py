import streamlit as st

import datetime
import os

from services.memory_service import MemoryService
from services.model_service import ModelService
from services.safety_service import SafetyService
from ui.chat_handlers import handle_assistant_response, handle_user_message
from ui.styles import inject_global_styles
from components.location_picker import location_picker
from models.safety.schemas import SafetyRequest


@st.cache_resource
def get_model_service(_cache_version: str = "v6-mps-eager-attn") -> ModelService:
    return ModelService()


@st.cache_resource
def get_safety_service() -> SafetyService:
    return SafetyService()


def get_selected_location_fields() -> dict:
    selected = st.session_state.get("selected_location")
    if not selected:
        return {"lat": None, "lon": None, "country": None, "location_name": None}

    short_location_name = (
        selected.get("city")
        or selected.get("county")
        or selected.get("state_region")
        or selected.get("country")
    )
    return {
        "lat": selected.get("lat"),
        "lon": selected.get("lon"),
        "country": selected.get("country"),
        "location_name": short_location_name,
    }


# ── only show raw debug JSON in local dev ──────────────────────────────────────
_DEBUG = os.getenv("WAYFINDER_DEBUG", "").lower() in ("1", "true", "yes")


@st.dialog("Pick a destination", width="large")
def _location_picker_modal(safety_service: SafetyService) -> None:
    picked_location = location_picker(
        key="wayfinder_location_picker_modal",
        height=520,
        default=st.session_state["selected_location"],
    )

    if picked_location and picked_location.get("lat") is not None:
        st.session_state["selected_location"] = picked_location
        st.session_state["safety_result"] = None
        st.rerun()


def _render_sidebar(safety_service: SafetyService) -> None:
    with st.sidebar:
        st.html(
            '<div class="wf-brand">'
            '<span class="wf-brand-icon">✈️</span>'
            '<span>WayFinder</span>'
            "</div>"
        )

        if st.button("🗑️ Clear conversation", use_container_width=True):
            MemoryService.clear()
            st.rerun()

        # ── Travel date ───────────────────────────────────────────────────
        st.html('<div class="wf-label">Travel date</div>')

        if "departure_date_picker" not in st.session_state:
            st.session_state["departure_date_picker"] = st.session_state.get(
                "departure_date"
            ) or datetime.date.today() + datetime.timedelta(days=1)
        else:
            # Sync from canonical store — only safe before the widget renders
            stored = st.session_state.get("departure_date")
            if (
                stored
                and stored != st.session_state["departure_date_picker"]
                and st.session_state.get("_date_from_chat")
            ):
                st.session_state["departure_date_picker"] = stored

        picked_date = st.date_input(
            label="Travel date",
            label_visibility="collapsed",
            min_value=datetime.date.today(),
            key="departure_date_picker",
        )

        if picked_date:
            st.session_state["departure_date"] = picked_date
            date_source = st.session_state.get("_date_from_chat")
            prefix = "💬 From chat · " if date_source else ""
            st.caption(
                f"{prefix}**{picked_date.strftime('%A, %b %d %Y')}**"
            )
            st.session_state["_date_from_chat"] = None

        # ── Departure city ────────────────────────────────────────────────
        st.html('<div class="wf-label">Departure city</div>')
        departure_input = st.text_input(
            label="Departure city",
            label_visibility="collapsed",
            placeholder="e.g. Phoenix, PHX, New York…",
            key="departure_input_field",
            value=st.session_state.get("departure_city_raw", ""),
        )

        if departure_input != st.session_state.get("departure_city_raw", ""):
            st.session_state["departure_city_raw"] = departure_input
            st.session_state["departure_city_resolved"] = None
            st.session_state["departure_city_candidates"] = []

        if departure_input and len(departure_input.strip()) >= 2:
            from services.airport_search_service import search_airports as _search

            # Only re-search if candidates aren't already loaded for this input
            if not st.session_state.get("departure_city_candidates"):
                matches = _search(departure_input.strip(), limit=5)
                st.session_state["departure_city_candidates"] = matches

            candidates = st.session_state.get("departure_city_candidates", [])

            if not candidates:
                st.caption("⚠️ No airport found — try a city name or IATA code")

            elif len(candidates) == 1:
                # Unambiguous — auto-resolve
                st.session_state["departure_city_resolved"] = candidates[0]
                resolved = candidates[0]
                st.success(f"✈️ **{resolved['iata']}** · {resolved['name']}")

            else:
                # Multiple matches — let the user pick inline, no chat loop needed
                resolved = st.session_state.get("departure_city_resolved")
                options = {
                    f"{c['iata']} — {c['name']} ({c['city']})": c for c in candidates
                }
                current_label = next(
                    (
                        k
                        for k, v in options.items()
                        if resolved and v["iata"] == resolved["iata"]
                    ),
                    None,
                )
                chosen_label = st.selectbox(
                    "Which airport?",
                    options=list(options.keys()),
                    index=list(options.keys()).index(current_label)
                    if current_label
                    else 0,
                    key="departure_airport_select",
                )
                st.session_state["departure_city_resolved"] = options[chosen_label]
                resolved = options[chosen_label]
                st.success(f"✈️ **{resolved['iata']}** · {resolved['name']}")

        # ── Destination picker ────────────────────────────────────────────
        st.html('<div class="wf-label">Destination</div>')
        if st.button("📍 Pick on the map", use_container_width=True):
            _location_picker_modal(safety_service)

        # ── Selected location summary ─────────────────────────────────────
        if st.session_state["selected_location"]:
            fields = get_selected_location_fields()
            selected = st.session_state["selected_location"]

            display_name = (
                selected.get("city")
                or selected.get("county")
                or selected.get("state_region")
                or selected.get("country")
                or "Unknown location"
            )
            coords = f"{fields['lat']:.4f}, {fields['lon']:.4f}"
            country_suffix = (
                f" · {fields['country']}" if fields["country"] else ""
            )
            from_chat = st.session_state.get("_destination_from_chat")
            title_prefix = "💬 " if from_chat else "📌 "
            meta_prefix = "From chat · " if from_chat else ""
            st.html(
                f'<div class="wf-card">'
                f'<div class="wf-card-title">{title_prefix}{display_name}</div>'
                f'<div class="wf-card-meta">{meta_prefix}{coords}{country_suffix}</div>'
                f"</div>"
            )
            if from_chat:
                st.session_state["_destination_from_chat"] = None

            col1, col2 = st.columns(2)

            with col1:
                if st.button(
                    "✏️ Change",
                    use_container_width=True,
                    key="btn_change_location",
                ):
                    _location_picker_modal(safety_service)

            with col2:
                if st.button(
                    "✕ Clear",
                    use_container_width=True,
                    key="btn_clear_location",
                ):
                    st.session_state["selected_location"] = None
                    st.session_state["safety_result"] = None
                    st.rerun()

            # ── Safety score ──────────────────────────────────────────────
            st.html('<div class="wf-label">Safety assessment</div>')
            can_score = fields["lat"] is not None and fields["lon"] is not None

            if st.button(
                "🛡️ Run safety score",
                disabled=not can_score,
                use_container_width=True,
            ):
                try:
                    req = SafetyRequest(
                        latitude=float(fields["lat"]),
                        longitude=float(fields["lon"]),
                        country=fields["country"],
                        location_name=fields["location_name"],
                    )
                    result = safety_service.assess_request(req, include_details=True)
                    st.session_state["safety_result"] = result
                    st.session_state["safety_debug"] = {
                        "stage": "result_returned",
                        "result": result,
                    }
                except Exception as e:
                    st.session_state["safety_debug"] = {
                        "stage": "exception",
                        "error": repr(e),
                    }

            if st.session_state["safety_result"] is not None:
                result = st.session_state["safety_result"]
                if result.get("success"):
                    score = result.get("safety_score")
                    band = result.get("risk_band", "—")
                    band_color = {
                        "low": "🟢",
                        "moderate": "🟡",
                        "elevated": "🟠",
                        "high": "🔴",
                    }.get(band, "⚪")
                    st.metric(
                        "Safety score", f"{score:.2f}" if score is not None else "—"
                    )
                    st.caption(f"{band_color} Risk band: **{band}**")
                    with st.expander("Prediction details", expanded=False):
                        st.json(result)
                else:
                    st.error(f"Scoring failed: {result.get('error')}")

            if _DEBUG and st.session_state.get("safety_debug") is not None:
                with st.expander("Safety debug", expanded=False):
                    st.json(st.session_state["safety_debug"])


def render_chat_page() -> None:
    st.set_page_config(
        page_title="WayFinder",
        page_icon="✈️",
        layout="centered",
        initial_sidebar_state="expanded",
    )
    inject_global_styles()

    st.html(
        '<div class="wf-hero">'
        '<div class="wf-hero-title">'
        '<span class="wf-hero-icon">✈️</span>'
        "<span>WayFinder</span>"
        "</div>"
        '<p class="wf-hero-subtitle">'
        "Your travel planning assistant — find flights and get safety insights "
        "for any destination."
        "</p>"
        "</div>"
    )

    MemoryService.initialize()
    model_service = get_model_service()
    safety_service = get_safety_service()

    # Initialize session state keys
    for key, default in [
        ("selected_location", None),
        ("safety_result", None),
        ("safety_debug", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # ── Sidebar holds all controls ────────────────────────────────────────────
    _render_sidebar(safety_service)

    # ── Main column is purely the chat ────────────────────────────────────────
    for message in MemoryService.get_display_messages():
        with st.chat_message(message.role):
            st.markdown(message.content)

    user_input = st.chat_input(
        "Ask about flights, destinations, or safety scores…"
    )

    if user_input:
        handle_user_message(user_input)
        handle_assistant_response(model_service)
