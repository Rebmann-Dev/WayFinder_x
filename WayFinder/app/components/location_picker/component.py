from __future__ import annotations

from pathlib import Path

import streamlit as st

_FRONTEND_DIR = Path(__file__).parent / "frontend"

# Try to register the custom Streamlit component; fall back gracefully so
# the app can still start when the component runtime is unavailable.
_location_picker_component = None
try:
    import streamlit.components.v1 as components
    _location_picker_component = components.declare_component(
        "wayfinder_location_picker",
        path=str(_FRONTEND_DIR.resolve()),
    )
except Exception:
    pass


def _fallback_location_picker(key: str | None = None, **_kwargs) -> dict | None:
    """Simple text-input fallback when the custom component is unavailable."""
    city = st.text_input("Enter a city name", key=key)
    if city and city.strip():
        return {"city": city.strip(), "lat": None, "lon": None}
    return None


def location_picker(
    key: str | None = None,
    height: int = 760,
    default: dict | None = None,
):
    if _location_picker_component is None:
        return _fallback_location_picker(key=key)

    if default is None:
        default = {
            "lat": None,
            "lon": None,
            "place_name": None,
            "country": None,
            "country_code": None,
            "state_region": None,
            "county": None,
            "city": None,
            "postcode": None,
            "location_source": None,
        }

    try:
        return _location_picker_component(
            key=key,
            default=default,
            height=height,
        )
    except Exception:
        return _fallback_location_picker(key=key)