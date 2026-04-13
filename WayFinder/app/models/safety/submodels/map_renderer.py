"""
map_renderer.py
WayFinder Travel Safety App — Folium Map Trail Renderer

Adds hiking trail polylines (from TrailsFetcher output) to an existing
Folium map object, with popups and a layer control toggle.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # folium is an optional dependency — only needed at runtime when rendering maps
    import folium

logger = logging.getLogger(__name__)

TRAIL_COLOR = "#2ecc71"        # green
TRAIL_WEIGHT = 3               # line width in pixels
TRAIL_OPACITY = 0.85
LAYER_NAME = "Hiking Trails"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_trails_on_map(map_obj: "folium.Map", trails_data: dict[str, Any]) -> None:
    """
    Overlay hiking trails from `TrailsFetcher.get_trails()` onto a Folium map.

    Parameters
    ----------
    map_obj : folium.Map
        An instantiated Folium map object to which layers will be added.
    trails_data : dict
        The dict returned by `TrailsFetcher.get_trails()`.  Expected keys:
          - trails : list[dict]   — trail objects with geometry, name, etc.
          - count  : int
          - source : str

    Side effects
    ------------
    - Adds a `folium.FeatureGroup` named "Hiking Trails" to *map_obj*.
    - Adds a `folium.LayerControl` to *map_obj* (call this last if you are
      adding multiple feature groups yourself).

    Returns None — the map is mutated in place.
    """
    try:
        import folium  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "folium is required for map rendering. Install with: pip install folium"
        ) from exc

    trails = trails_data.get("trails", [])

    # Always create the feature group, even if empty, so the layer control works.
    feature_group = folium.FeatureGroup(name=LAYER_NAME, show=True)

    if not trails:
        logger.info("render_trails_on_map: no trails to render.")
        feature_group.add_to(map_obj)
        folium.LayerControl(collapsed=False).add_to(map_obj)
        return

    rendered_count = 0
    for trail in trails:
        geometry = trail.get("geometry", [])
        name = trail.get("name", "Unnamed Trail")
        trail_type = trail.get("trail_type", "")
        difficulty = trail.get("difficulty")
        length_km = trail.get("length_km")
        surface = trail.get("surface")

        if len(geometry) < 2:
            # No renderable geometry — skip polyline but optionally add a marker
            lat = trail.get("lat")
            lon = trail.get("lon")
            if lat is not None and lon is not None:
                popup_html = _build_popup_html(name, trail_type, difficulty, length_km, surface)
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=6,
                    color=TRAIL_COLOR,
                    fill=True,
                    fill_opacity=0.7,
                    popup=folium.Popup(popup_html, max_width=300),
                    tooltip=name,
                ).add_to(feature_group)
            continue

        # Folium expects (lat, lon) tuples
        latlons = [(pt[0], pt[1]) for pt in geometry]

        popup_html = _build_popup_html(name, trail_type, difficulty, length_km, surface)

        folium.PolyLine(
            locations=latlons,
            color=TRAIL_COLOR,
            weight=TRAIL_WEIGHT,
            opacity=TRAIL_OPACITY,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=name,
        ).add_to(feature_group)

        rendered_count += 1

    feature_group.add_to(map_obj)
    folium.LayerControl(collapsed=False).add_to(map_obj)

    logger.info(
        "render_trails_on_map: rendered %d/%d trails onto map.",
        rendered_count,
        len(trails),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_popup_html(
    name: str,
    trail_type: str,
    difficulty: str | None,
    length_km: float | None,
    surface: str | None,
) -> str:
    """Build the HTML string for a trail popup."""
    rows: list[str] = [f"<b>{name}</b>"]
    if trail_type:
        rows.append(f"<i>Type:</i> {trail_type}")
    if difficulty:
        rows.append(f"<i>Difficulty:</i> {difficulty}")
    if length_km is not None:
        rows.append(f"<i>Length:</i> {length_km:.1f} km")
    if surface:
        rows.append(f"<i>Surface:</i> {surface}")
    return "<br>".join(rows)


# ---------------------------------------------------------------------------
# Convenience factory — create a ready-to-save map with trails
# ---------------------------------------------------------------------------


def create_trail_map(
    lat: float,
    lon: float,
    trails_data: dict[str, Any],
    zoom_start: int = 12,
) -> "folium.Map":
    """
    Convenience function: create a Folium map centred on *lat/lon*,
    render trails onto it, and return the map object.

    Parameters
    ----------
    lat, lon : float
        Centre of the map.
    trails_data : dict
        Output of `TrailsFetcher.get_trails()`.
    zoom_start : int
        Initial zoom level (default 12).

    Returns
    -------
    folium.Map
        A configured map ready for `.save("map.html")`.

    Example
    -------
        m = create_trail_map(47.56, 8.85, trails_data)
        m.save("zermatt_trails.html")
    """
    try:
        import folium  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "folium is required. Install with: pip install folium"
        ) from exc

    m = folium.Map(location=[lat, lon], zoom_start=zoom_start, tiles="OpenStreetMap")
    render_trails_on_map(m, trails_data)
    return m


# ---------------------------------------------------------------------------
# Quick smoke-test (run directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Minimal self-test: create a map with synthetic trail data and save it.
    synthetic_trails = {
        "trails": [
            {
                "name": "Test Ridge Trail",
                "trail_type": "path",
                "difficulty": "hiking",
                "surface": "rock",
                "length_km": 4.2,
                "lat": 47.5596,
                "lon": 8.8492,
                "geometry": [
                    [47.5596, 8.8492],
                    [47.5620, 8.8510],
                    [47.5650, 8.8550],
                    [47.5680, 8.8600],
                ],
                "osm_id": "way/99999",
                "tags": {"highway": "path", "sac_scale": "hiking"},
            },
            {
                "name": "Valley Walk",
                "trail_type": "footway",
                "difficulty": None,
                "surface": "gravel",
                "length_km": 2.1,
                "lat": 47.5550,
                "lon": 8.8430,
                "geometry": [
                    [47.5550, 8.8430],
                    [47.5530, 8.8450],
                    [47.5510, 8.8480],
                ],
                "osm_id": "way/88888",
                "tags": {"highway": "footway"},
            },
        ],
        "count": 2,
        "source": "openstreetmap",
    }

    try:
        m = create_trail_map(47.5596, 8.8492, synthetic_trails)
        out_path = "/tmp/test_trails_map.html"
        m.save(out_path)
        print(f"Map saved to {out_path}")
    except ImportError:
        print("folium not installed — skipping map render test.")
