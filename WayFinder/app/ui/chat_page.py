import streamlit as st

import datetime
import os

from services.memory_service import MemoryService
from services.model_service import ModelService
from services.safety_service import SafetyService
from ui.chat_handlers import handle_assistant_response, handle_user_message
from ui.styles import inject_global_styles
from ui.translate_widget import render_translate_widget
from ui.explore_page import render_explore_page
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
        st.header("WayFinder")

        if st.button("🌿 Explore", use_container_width=True, key="btn_explore"):
            st.session_state["explore_mode"] = True
            st.rerun()

        if st.button("🗑️ Clear chat", use_container_width=True):
            MemoryService.clear()
            st.rerun()

        st.divider()

        # ── Travel date ───────────────────────────────────────────────────────────
        st.caption("📅 TRAVEL DATE")

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
            st.caption(
                f"{'💬 Updated from chat' if date_source else '📅'} "
                f"**{picked_date.strftime('%A, %b %d %Y')}**"
            )
            st.session_state["_date_from_chat"] = None

        st.divider()

        # ── Departure city ────────────────────────────────────────────────────
        st.caption("🛫 DEPARTURE CITY")
        if "departure_input_field" not in st.session_state:
            st.session_state["departure_input_field"] = st.session_state.get("departure_city_raw", "")
        departure_input = st.text_input(
            label="Departure city",
            label_visibility="collapsed",
            placeholder="e.g. Phoenix, PHX, New York…",
            key="departure_input_field",
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

        st.divider()

        # ── Location picker — opens a modal ───────────────────────────────────
        if st.button("📍 Use map to pick a destination", use_container_width=True):
            _location_picker_modal(safety_service)

        st.caption("— or type a destination —")
        typed_dest = st.text_input(
            "Destination",
            label_visibility="collapsed",
            placeholder="e.g. Quito, Montañita, Tena…",
            key="typed_destination_input",
        )
        if typed_dest and len(typed_dest.strip()) >= 2:
            # Geocode using Nominatim (no API key needed)
            import requests as _req
            if st.session_state.get("_last_typed_dest") != typed_dest:
                try:
                    r = _req.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={"q": typed_dest, "format": "json", "limit": 1},
                        headers={"User-Agent": "WayFinder/1.0"},
                        timeout=5,
                    )
                    if r.ok and r.json():
                        geo = r.json()[0]
                        st.session_state["selected_location"] = {
                            "lat": float(geo["lat"]),
                            "lon": float(geo["lon"]),
                            "country": geo.get("display_name", "").split(",")[-1].strip(),
                            "city": typed_dest,
                        }
                        st.session_state["_last_typed_dest"] = typed_dest
                        st.session_state["safety_result"] = None
                        st.rerun()
                except Exception:
                    pass

        # ── Selected location summary ─────────────────────────────────────────
        if st.session_state["selected_location"]:
            fields = get_selected_location_fields()
            selected = st.session_state["selected_location"]

            st.divider()
            st.caption("📌 Selected destination")

            # Show the most specific name available
            display_name = (
                selected.get("city")
                or selected.get("county")
                or selected.get("state_region")
                or selected.get("country")
                or "Unknown location"
            )
            st.markdown(f"**{display_name}**")
            st.caption(
                f"{fields['lat']:.4f}, {fields['lon']:.4f}"
                + (f" · {fields['country']}" if fields["country"] else "")
            )

            # ── Destination airport confirmation ──────────────────────────────
            dest_key = "destination_city_candidates"
            dest_resolved_key = "destination_city_resolved"

            if st.session_state.get("_last_dest_city") != display_name:
                from services.airport_search_service import search_airports as _asearch
                matches = _asearch(display_name, limit=5)
                st.session_state[dest_key] = matches
                st.session_state[dest_resolved_key] = matches[0] if len(matches) == 1 else None
                st.session_state["_last_dest_city"] = display_name

            dest_candidates = st.session_state.get(dest_key, [])
            if not dest_candidates:
                st.caption("⚠️ No airport found near this destination")
            elif len(dest_candidates) == 1:
                st.session_state[dest_resolved_key] = dest_candidates[0]
                r = dest_candidates[0]
                st.success(f"✈️ **{r['iata']}** · {r['name']}")
            else:
                dest_options = {
                    f"{c['iata']} — {c['name']} ({c['city']})": c
                    for c in dest_candidates
                }
                dest_resolved = st.session_state.get(dest_resolved_key)
                current_dest_label = next(
                    (
                        lbl
                        for lbl, c in dest_options.items()
                        if dest_resolved and c["iata"] == dest_resolved.get("iata")
                    ),
                    list(dest_options.keys())[0],
                )
                st.caption("Which destination airport?")
                chosen_dest_label = st.selectbox(
                    "Destination airport",
                    list(dest_options.keys()),
                    index=list(dest_options.keys()).index(current_dest_label),
                    label_visibility="collapsed",
                    key="destination_airport_select",
                )
                st.session_state[dest_resolved_key] = dest_options[chosen_dest_label]
                r = dest_options[chosen_dest_label]
                st.success(f"✈️ **{r['iata']}** · {r['name']}")

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

            # ── Safety score ──────────────────────────────────────────────────
            st.divider()
            can_score = fields["lat"] is not None and fields["lon"] is not None

            if st.button(
                "🔴 Run Safety Score", disabled=not can_score, use_container_width=True
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
                    _render_safety_results_panel(result)
                else:
                    st.error(f"Scoring failed: {result.get('error')}")

            if _DEBUG and st.session_state.get("safety_debug") is not None:
                with st.expander("Safety debug", expanded=False):
                    st.json(st.session_state["safety_debug"])

        # ── Dev Tools ────────────────────────────────────────────────────
        st.divider()
        with st.expander("⚙️ Dev Tools", expanded=False):
            tavily_on = st.toggle(
                "🌐 Enable Web Search (Tavily)",
                value=st.session_state.get("tavily_enabled", False),
                key="tavily_toggle",
            )
            st.session_state["tavily_enabled"] = tavily_on
            if tavily_on:
                st.caption("⚡ Live web search active — uses API credits")
            else:
                st.caption("📦 Using cached country data only")






def _render_safety_results_panel(result: dict, label: str = "") -> None:
    """Render all safety scoring outputs as a clean tabbed panel."""
    import datetime as _dt

    score = result.get("safety_score")
    band = result.get("risk_band", "—")
    band_emoji = {"very low": "🔵", "low": "🟢", "moderate": "🟡", "high": "🟠", "very high": "🔴"}.get(band, "⚪")
    model_version = result.get("model_version", "—")

    if label:
        st.markdown(f"**{label}**")

    # Top-line score
    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric("Safety Score", f"{score:.1f}/100" if score is not None else "—")
    m_col2.metric("Risk Band", f"{band_emoji} {band}")
    m_col3.metric("Model", model_version)

    # Tabs for each dimension
    details = result.get("details", {})
    weather = result.get("weather_risk", {})
    ecuador = result.get("ecuador_risk", {})
    peru_r  = result.get("peru_risk", {})
    lgbt    = result.get("lgbt_safety") or result.get("details", {}).get("lgbt_safety", {})

    # Build tab list dynamically based on what's available
    tab_labels = ["📊 Score Details"]
    if weather and not weather.get("error"):
        tab_labels.append("🌦️ Weather")
    if ecuador and ecuador.get("applicable"):
        tab_labels.append("🐆 Ecuador")
    if peru_r and peru_r.get("applicable"):
        tab_labels.append("🐆 Peru")
    if lgbt and "lgbt_safety_score" in lgbt:
        tab_labels.append("🏳️‍🌈 LGBT")

    tabs = st.tabs(tab_labels)
    tab_idx = 0

    # ── Score Details tab ──────────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            st.markdown("**Model breakdown**")
            mlp = details.get("mlp_score_v6")
            rf  = details.get("rf_score_v6")
            v9b = details.get("v9b_score")
            if mlp is not None:
                st.metric("MLP v6", f"{mlp:.1f}")
            if rf is not None:
                st.metric("Random Forest v6", f"{rf:.1f}")
            if v9b is not None:
                st.metric("v9b MLP", f"{v9b:.1f}")
            else:
                v9b_err = details.get("v9b_error", "artifacts missing or failed to load")
                st.caption(f"⚠️ v9b not loaded: {v9b_err}")
            st.caption(f"Active model: {result.get('model_version', '—')}")
            agreement = details.get("agreement_band", "—")
            spread = details.get("model_spread")
            st.caption(f"Model agreement: **{agreement}**" + (f" (spread: {spread:.1f})" if spread else ""))
        with d_col2:
            st.markdown("**Location**")
            lat = result.get("latitude")
            lon = result.get("longitude")
            country = result.get("country", "—")
            if lat and lon:
                st.caption(f"📍 {lat:.4f}, {lon:.4f}")
            st.caption(f"🌍 {country}")
            feat_count = details.get("feature_count")
            if feat_count:
                st.caption(f"Features used: {feat_count}")

        # Feature values expander
        features = details.get("features") or details.get("features_used") or {}
        if features:
            with st.expander("🔬 Feature values used in prediction", expanded=False):
                if isinstance(features, dict):
                    feat_rows = sorted(features.items())
                    for fname, fval in feat_rows:
                        try:
                            st.caption(f"**{fname}**: {fval:.4f}" if isinstance(fval, float) else f"**{fname}**: {fval}")
                        except Exception:
                            st.caption(f"**{fname}**: {fval}")
                else:
                    st.json(features)

        # Full raw result expander (replaces old debug JSON)
        with st.expander("🗂️ Full prediction output (all fields)", expanded=False):
            st.json({k: v for k, v in result.items() if k != "details"})
            if details:
                st.markdown("**details:**")
                st.json(details)

    # ── Weather tab ────────────────────────────────────────────────────────
    if weather and not weather.get("error") and tab_idx <= len(tabs) - 1:
        with tabs[tab_idx]:
            tab_idx += 1
            w_score = weather.get("weather_risk_score", "—")
            w_label = weather.get("weather_risk_label", "—")
            st.metric("Weather Risk", f"{w_score}/5 — {w_label}")
            assessment = weather.get("travel_month_assessment", "")
            if assessment:
                st.info(assessment)
            risks = weather.get("risks", [])
            if risks:
                st.markdown("**Active risks this month:**")
                for r in risks:
                    sev = r.get("severity", 0)
                    sev_bar = "🔴" * min(sev, 5)
                    with st.expander(f"{r['type'].replace('_',' ').title()} {sev_bar}", expanded=sev >= 4):
                        st.write(r.get("description", ""))

    # ── Ecuador tab ────────────────────────────────────────────────────────
    if ecuador and ecuador.get("applicable") and tab_idx <= len(tabs) - 1:
        with tabs[tab_idx]:
            tab_idx += 1
            e_col1, e_col2, e_col3 = st.columns(3)
            e_col1.metric("Overall Risk", f"{ecuador.get('overall_risk','—')}/5")
            e_col2.metric("Crime Risk", f"{ecuador.get('crime_risk','—')}/5")
            e_col3.metric("Wildlife Risk", f"{ecuador.get('wildlife_risk','—')}/5")
            st.caption(f"Province: **{ecuador.get('province','—')}** · Homicide rate: {ecuador.get('homicide_rate_per_100k','—')}/100k")
            crime_notes = ecuador.get("crime_notes","")
            if crime_notes:
                st.warning(crime_notes)

    # ── Peru tab ───────────────────────────────────────────────────────────
    if peru_r and peru_r.get("applicable") and tab_idx <= len(tabs) - 1:
        with tabs[tab_idx]:
            tab_idx += 1
            p_col1, p_col2, p_col3 = st.columns(3)
            p_col1.metric("Overall Risk", f"{peru_r.get('overall_risk','—')}/5")
            p_col2.metric("Crime Risk", f"{peru_r.get('crime_risk','—')}/5")
            p_col3.metric("Wildlife Risk", f"{peru_r.get('wildlife_risk','—')}/5")
            st.caption(f"Region: **{peru_r.get('region','—')}** · Homicide rate: {peru_r.get('homicide_rate_per_100k','—')}/100k")
            crime_notes = peru_r.get("crime_notes","")
            if crime_notes:
                st.warning(crime_notes)

    # ── LGBT tab ───────────────────────────────────────────────────────────
    if lgbt and "lgbt_safety_score" in lgbt and tab_idx <= len(tabs) - 1:
        with tabs[tab_idx]:
            tab_idx += 1
            score_l = lgbt.get("lgbt_safety_score")
            labels = {
                1: "Criminalized — serious legal risk",
                2: "Hostile — discrimination common",
                3: "Neutral — limited legal protections",
                4: "Accepting — legal protections exist",
                5: "Very Safe — full legal equality",
            }
            label_l = labels.get(score_l, "—")
            legal_idx = lgbt.get("lgbt_legal_index")
            confidence = lgbt.get("lgbt_confidence") or lgbt.get("confidence", "—")
            criminalized = lgbt.get("criminalized", False)
            death_risk = lgbt.get("death_penalty_risk", False)

            l_col1, l_col2 = st.columns(2)
            l_col1.metric("LGBT Safety Score", f"{score_l}/5" if score_l else "—")
            if legal_idx is not None:
                l_col2.metric("Legal Index", f"{legal_idx:.1f}/100")
            st.markdown(f"**{label_l}**")
            st.caption(f"Data confidence: {confidence}")

            if death_risk:
                st.error("🚨 Death penalty or corporal punishment may apply to same-sex relations in this country.")
            elif criminalized:
                st.warning("⚠️ Same-sex relations are criminalized in this country. Exercise extreme caution.")

            st.caption("Source: ILGA World, Rainbow Map, and WayFinder LGBT classifier (1 = Criminalized → 5 = Very Safe)")




def render_chat_page() -> None:
    try:
        st.set_page_config(layout="wide", page_title="WayFinder", page_icon="✈️")
    except Exception:
        pass
    st.title("✈️ WayFinder")
    inject_global_styles()
    render_translate_widget()

    MemoryService.initialize()
    model_service = get_model_service()
    safety_service = get_safety_service()

    # Initialize session state keys
    for key, default in [
        ("selected_location", None),
        ("safety_result", None),
        ("safety_debug", None),
        ("explore_mode", False),
        ("explore_country", "Ecuador"),
        ("explore_safety_result", None),
        ("explore_scored_location", ""),
        ("explore_click_lat", None),
        ("explore_click_lon", None),
        ("explore_click_name", ""),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # ── Sidebar holds all controls ────────────────────────────────────────────
    _render_sidebar(safety_service)

    # ── Explore mode: full-screen panel instead of chat ─────────────────────
    if st.session_state.get("explore_mode"):
        col_back, col_title = st.columns([1, 6])
        with col_back:
            if st.button("← Back to chat"):
                st.session_state["explore_mode"] = False
                st.rerun()
        render_explore_page()
        return  # don't render chat while in explore mode

    # ── Main column is purely the chat ────────────────────────────────────────
    for message in MemoryService.get_display_messages():
        with st.chat_message(message.role):
            st.markdown(message.content)

    user_input = st.chat_input("Ask about routes, destinations, or itineraries...")

    if user_input:
        handle_user_message(user_input)
        handle_assistant_response(model_service)
