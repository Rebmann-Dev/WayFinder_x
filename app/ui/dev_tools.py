# app/ui/dev_tools.py

import json
from pathlib import Path

import streamlit as st
from core.config import settings

FEATURES_PATH = Path(__file__).resolve().parents[2] / "config" / "features.json"


def render_dev_tools() -> None:
    st.subheader("⚙️ Dev Tools")

    # Tavily toggle (existing behavior)
    tavily_on = st.toggle(
        "🌐 Enable Web Search (Tavily)",
        value=st.session_state.get("tavily_enabled", False),
        key="tavily_toggle",
    )
    st.session_state["tavily_enabled"] = tavily_on
    st.caption(
        "⚡ Live web search active — uses API credits"
        if tavily_on
        else "📦 Using cached country data only"
    )

    st.divider()

    # Flight scraper mode toggle (off / stub / live)
    current_mode = getattr(settings, "flight_scraper_mode", "off")
    options = ["off", "stub", "live"]
    mode = st.selectbox(
        "Flight scraper mode",
        options,
        index=options.index(current_mode) if current_mode in options else 0,
        help="off = no flight API; stub = mock data; live = Docker/Go scraper",
        key="flight_mode_select",
    )

    if st.button("Save flight mode", key="save_flight_mode_btn"):
        try:
            if FEATURES_PATH.exists():
                data = json.loads(FEATURES_PATH.read_text())
            else:
                data = {}
            data["flight_scraper_mode"] = mode
            FEATURES_PATH.write_text(json.dumps(data, indent=2))
            st.success(f"Flight mode set to '{mode}'. Restart app to apply.")
        except Exception as exc:
            st.error(f"Failed to update features.json: {exc}")