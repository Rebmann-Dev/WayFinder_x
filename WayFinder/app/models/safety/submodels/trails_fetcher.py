"""
trails_fetcher.py
WayFinder Travel Safety App — Hiking Trails Overlay Module

Fetches hiking trails near a given location using the OpenStreetMap
Overpass API (free, no key required).
"""

from __future__ import annotations

import logging
import math
from typing import Any

import requests

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HTTP_TIMEOUT = 30  # seconds — Overpass can be slow
MAX_TRAILS = 50
MAX_GEOMETRY_POINTS = 200

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres between two points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _centroid(coords: list[list[float]]) -> tuple[float, float]:
    """Return (lat, lon) centroid of a list of [lat, lon] coordinate pairs."""
    if not coords:
        return (0.0, 0.0)
    lat = sum(c[0] for c in coords) / len(coords)
    lon = sum(c[1] for c in coords) / len(coords)
    return (lat, lon)


def _thin_geometry(
    coords: list[list[float]], max_points: int = MAX_GEOMETRY_POINTS
) -> list[list[float]]:
    """
    Reduce a coordinate list to at most *max_points* by uniform stride sampling.
    Always keeps the first and last point.
    """
    if len(coords) <= max_points:
        return coords
    step = (len(coords) - 1) / (max_points - 1)
    indices = {round(i * step) for i in range(max_points)}
    indices.add(0)
    indices.add(len(coords) - 1)
    return [coords[i] for i in sorted(indices)]


def _polyline_length_km(coords: list[list[float]]) -> float:
    """Approximate trail length in km from its coordinate list."""
    total = 0.0
    for i in range(1, len(coords)):
        total += _haversine_km(coords[i - 1][0], coords[i - 1][1], coords[i][0], coords[i][1])
    return round(total, 2)


# ---------------------------------------------------------------------------
# Overpass query builder
# ---------------------------------------------------------------------------

def _build_overpass_query(lat: float, lon: float, radius_m: int) -> str:
    """
    Build an Overpass QL query that retrieves:
    - ways tagged with hiking/footway/path/track + optional sac_scale
    - ways tagged route=hiking
    - relations tagged route=hiking

    All results include full geometry (out geom).
    """
    return f"""
[out:json][timeout:25];
(
  way["highway"~"path|footway|track"]["sac_scale"](around:{radius_m},{lat},{lon});
  way["route"="hiking"](around:{radius_m},{lat},{lon});
  relation["route"="hiking"](around:{radius_m},{lat},{lon});
  way["highway"~"path|footway|track"](around:{radius_m},{lat},{lon});
);
out geom;
""".strip()


# ---------------------------------------------------------------------------
# OSM element parsers
# ---------------------------------------------------------------------------

_RELEVANT_TAG_KEYS = {
    "name", "highway", "route", "sac_scale", "trail_visibility",
    "surface", "difficulty", "description", "access", "foot",
    "mtb:scale", "bicycle", "operator", "network", "ref",
    "ele", "tourism", "leisure",
}


def _extract_relevant_tags(raw_tags: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in raw_tags.items() if k in _RELEVANT_TAG_KEYS}


def _parse_way(element: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a way element from Overpass JSON into a trail dict."""
    tags = element.get("tags", {})
    geometry_raw = element.get("geometry", [])

    # geometry is a list of {"lat": ..., "lon": ...} dicts
    coords = [[g["lat"], g["lon"]] for g in geometry_raw if "lat" in g and "lon" in g]
    if len(coords) < 2:
        return None

    coords_thinned = _thin_geometry(coords)
    center_lat, center_lon = _centroid(coords)

    name = tags.get("name") or tags.get("ref") or "Unnamed Trail"
    highway = tags.get("highway", "")
    route = tags.get("route", "")
    trail_type = route if route == "hiking" else (highway or "path")
    difficulty = tags.get("sac_scale") or tags.get("difficulty") or tags.get("mtb:scale")
    surface = tags.get("surface")
    length_km = _polyline_length_km(coords)

    return {
        "name": name,
        "trail_type": trail_type,
        "difficulty": difficulty,
        "surface": surface,
        "length_km": length_km if length_km > 0 else None,
        "lat": round(center_lat, 6),
        "lon": round(center_lon, 6),
        "geometry": [[round(c[0], 6), round(c[1], 6)] for c in coords_thinned],
        "osm_id": f"way/{element.get('id', '')}",
        "tags": _extract_relevant_tags(tags),
    }


def _parse_relation(element: dict[str, Any]) -> dict[str, Any] | None:
    """
    Parse a relation element.  Relations don't carry full geometry directly in
    `out geom;` — individual member ways are not expanded inline for relations
    unless we use `(._;>;)`.  We include the relation bounding-box centroid as
    a point with no geometry polyline.
    """
    tags = element.get("tags", {})
    bounds = element.get("bounds", {})

    if bounds:
        center_lat = (bounds.get("minlat", 0) + bounds.get("maxlat", 0)) / 2
        center_lon = (bounds.get("minlon", 0) + bounds.get("maxlon", 0)) / 2
    else:
        center_lat, center_lon = 0.0, 0.0

    name = tags.get("name") or tags.get("ref") or "Unnamed Route"
    difficulty = tags.get("sac_scale") or tags.get("difficulty")
    surface = tags.get("surface")

    return {
        "name": name,
        "trail_type": "hiking_route",
        "difficulty": difficulty,
        "surface": surface,
        "length_km": None,
        "lat": round(center_lat, 6),
        "lon": round(center_lon, 6),
        "geometry": [],
        "osm_id": f"relation/{element.get('id', '')}",
        "tags": _extract_relevant_tags(tags),
    }


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------


class TrailsFetcher:
    """
    Retrieves hiking trails near a geographic point using the Overpass API.

    Usage:
        fetcher = TrailsFetcher()
        result = fetcher.get_trails(lat=47.5596, lon=8.8492, radius_km=25)
        for trail in result["trails"]:
            print(trail["name"], trail["length_km"])
    """

    def get_trails(
        self,
        lat: float,
        lon: float,
        radius_km: int = 25,
    ) -> dict[str, Any]:
        """
        Fetch hiking trails within *radius_km* of the given coordinates.

        Parameters
        ----------
        lat : float
            Centre latitude.
        lon : float
            Centre longitude.
        radius_km : int
            Search radius in kilometres (default 25).

        Returns
        -------
        dict with keys:
            trails  list[dict]
            count   int
            source  str  ("openstreetmap")
        """
        radius_m = radius_km * 1000
        query = _build_overpass_query(lat, lon, radius_m)

        try:
            resp = requests.post(
                OVERPASS_URL,
                data={"data": query},
                timeout=HTTP_TIMEOUT,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            elements: list[dict[str, Any]] = resp.json().get("elements", [])
        except requests.exceptions.Timeout:
            logger.error("Overpass API timed out after %s seconds.", HTTP_TIMEOUT)
            return {"trails": [], "count": 0, "source": "openstreetmap"}
        except Exception as exc:  # noqa: BLE001
            logger.error("Overpass API request failed: %s", exc)
            return {"trails": [], "count": 0, "source": "openstreetmap"}

        trails = self._parse_elements(elements, lat, lon)
        return {
            "trails": trails,
            "count": len(trails),
            "source": "openstreetmap",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_elements(
        self,
        elements: list[dict[str, Any]],
        origin_lat: float,
        origin_lon: float,
    ) -> list[dict[str, Any]]:
        """
        Parse Overpass elements, deduplicate by OSM id, sort by proximity,
        and return at most MAX_TRAILS results.
        """
        seen_ids: set[str] = set()
        parsed: list[dict[str, Any]] = []

        for element in elements:
            etype = element.get("type")
            try:
                if etype == "way":
                    trail = _parse_way(element)
                elif etype == "relation":
                    trail = _parse_relation(element)
                else:
                    continue
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed to parse element %s: %s", element.get("id"), exc)
                continue

            if trail is None:
                continue

            osm_id = trail["osm_id"]
            if osm_id in seen_ids:
                continue
            seen_ids.add(osm_id)

            # Attach distance for sorting (not exposed in output)
            trail["_distance_km"] = _haversine_km(
                origin_lat, origin_lon, trail["lat"], trail["lon"]
            )
            parsed.append(trail)

        # Sort by proximity
        parsed.sort(key=lambda t: t["_distance_km"])

        # Trim to limit
        parsed = parsed[:MAX_TRAILS]

        # Remove internal distance key
        for t in parsed:
            t.pop("_distance_km", None)

        return parsed


# ---------------------------------------------------------------------------
# Quick smoke-test (run directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    fetcher = TrailsFetcher()

    test_cases = [
        ("Zermatt, Switzerland", 46.0207, 7.7491, 20),
        ("Banff, Canada", 51.1784, -115.5708, 15),
    ]

    for name, lat, lon, radius in test_cases:
        print(f"\n=== {name} (radius={radius}km) ===")
        result = fetcher.get_trails(lat=lat, lon=lon, radius_km=radius)
        print(f"Found {result['count']} trails (source: {result['source']})")
        for trail in result["trails"][:5]:
            print(
                f"  {trail['name']!r} | {trail['trail_type']} | "
                f"len={trail['length_km']} km | diff={trail['difficulty']}"
            )
