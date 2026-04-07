from __future__ import annotations

from pathlib import Path
import streamlit.components.v1 as components

_FRONTEND_DIR = Path(__file__).parent / "frontend"

_location_picker_component = components.declare_component(
    "wayfinder_location_picker",
    path=str(_FRONTEND_DIR.resolve()),
)

def location_picker(
    key: str | None = None,
    height: int = 760,
    default: dict | None = None,
):
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

    return _location_picker_component(
        key=key,
        default=default,
        height=height,
    )