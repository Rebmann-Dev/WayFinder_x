"""Tavily web search service with JSON-first caching and enrichment."""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

log = logging.getLogger("wayfinder.tavily")

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_COUNTRIES_DIR = _DATA_DIR / "countries"
_QUERY_LOG = _DATA_DIR / "query_log.jsonl"

# Intent keywords → JSON field paths
_INTENT_MAP = {
    "surf|surfing": ["outdoors.surf_spots"],
    "hike|hiking|trek|trail": ["outdoors.top_day_hikes", "outdoors.multi_day_treks"],
    "food|eat|restaurant|dish": ["food.signature_dishes", "food.regional_specialties"],
    "wildlife|animals|birds": ["outdoors.wildlife", "outdoors.wildlife_zones"],
    "visa|entry|border": ["entry_and_border"],
    "vaccine|health|medical": ["health"],
    "safety|crime|scam": ["safety"],
    "budget|cost|price|cheap|expensive|lodging|hotel|hostel": ["budget", "accommodation"],
    "weather|climate|rain|season": ["weather_and_seasonality"],
    "national park|reserve|nature": ["outdoors.top_national_parks"],
    "transport|bus|taxi|airport": ["transport"],
    "culture|etiquette|customs": ["culture"],
}


def _resolve_dotpath(data: dict, path: str):
    """Walk a dot-separated path into a nested dict, return None on miss."""
    parts = path.split(".")
    node = data
    for p in parts:
        if not isinstance(node, dict):
            return None
        node = node.get(p)
        if node is None:
            return None
    return node


_CONTINENT_FOLDERS = ["south_america", "north_america", "europe", "asia", "africa", "oceania"]

# ISO 3166-1 alpha-2 → continent subfolder
COUNTRY_TO_CONTINENT: dict[str, str] = {
    "ec": "south_america",
    "pe": "south_america",
    "co": "south_america",
    "br": "south_america",
    "ar": "south_america",
    "cl": "south_america",
    "mx": "north_america",
    "us": "north_america",
    "ca": "north_america",
    "cr": "north_america",
    "pa": "north_america",
    "es": "europe",
    "fr": "europe",
    "it": "europe",
    "de": "europe",
    "pt": "europe",
    "th": "asia",
    "jp": "asia",
    "id": "asia",
    "vn": "asia",
    "au": "oceania",
    "nz": "oceania",
    "za": "africa",
    "ke": "africa",
    "ma": "africa",
}

_BLANK_COUNTRY_TEMPLATE: dict = {
    "meta": {
        "country_code": "",
        "country_name": "",
        "last_updated": "",
    },
    "outdoors": {},
    "food": {},
    "entry_and_border": {},
    "health": {},
    "safety": {},
    "budget": {},
    "accommodation": {},
    "weather_and_seasonality": {},
    "transport": {},
    "culture": {},
}


def _find_country_json(country_code: str) -> Path | None:
    """Locate a country JSON file by code or name prefix, checking continent subfolders."""
    if not country_code:
        return None
    cc = country_code.strip().lower()

    # Check continent subfolders first
    for continent in _CONTINENT_FOLDERS:
        candidate = _COUNTRIES_DIR / continent / f"{cc}.json"
        if candidate.exists():
            return candidate

    # Try exact code match in root (e.g. ec.json)
    candidate = _COUNTRIES_DIR / f"{cc}.json"
    if candidate.exists():
        return candidate

    # Try longer name match in root (e.g. ecuador.json)
    for p in _COUNTRIES_DIR.glob("*.json"):
        if p.stem.lower().startswith(cc):
            return p

    # Try longer name match in continent subfolders
    for continent in _CONTINENT_FOLDERS:
        continent_dir = _COUNTRIES_DIR / continent
        if continent_dir.is_dir():
            for p in continent_dir.glob("*.json"):
                if p.stem.lower().startswith(cc):
                    return p

    return None


class TavilyService:
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")

    @property
    def enabled(self) -> bool:
        return st.session_state.get("tavily_enabled", False)

    def search(self, query: str, country_code: str = None) -> dict | None:
        """JSON-first search: check local cache, fall back to Tavily API if enabled."""
        if not query:
            return None

        # 1. Check JSON cache
        if country_code:
            cached = self._check_json_cache(query, country_code)
            if cached:
                self._log_query(query, country_code, "json_cache", str(cached)[:200])
                return cached

        # 2. If Tavily disabled, return None (cache miss)
        if not self.enabled:
            log.info("Tavily disabled — cache miss for %r", query)
            self._log_query(query, country_code or "", "cache_miss", "tavily_disabled")
            return None

        # 3. Call Tavily API
        result = self._call_tavily(query)
        if result is None:
            return None

        # 4. Enrich country JSON if possible
        if country_code:
            category = self._detect_category(query)
            if category:
                self._enrich_country_json(country_code, category, result)

        self._log_query(query, country_code or "", "tavily", str(result)[:200])
        return result

    def _check_json_cache(self, query: str, country_code: str) -> dict | None:
        """Map query intent to JSON fields and return cached data if available."""
        json_path = _find_country_json(country_code)
        if json_path is None:
            return None

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        query_lower = query.lower()
        for pattern, field_paths in _INTENT_MAP.items():
            if re.search(pattern, query_lower):
                results = {}
                for fp in field_paths:
                    value = _resolve_dotpath(data, fp)
                    if value and (not isinstance(value, (list, dict)) or value):
                        results[fp] = value
                if results:
                    return {"source": "json_cache", "country_code": country_code, "data": results}
        return None

    def _call_tavily(self, query: str) -> dict | None:
        """Call Tavily search API."""
        if not self.api_key:
            log.warning("TAVILY_API_KEY not set — cannot call API")
            return None

        import requests

        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": 5,
                },
                timeout=15,
            )
            if resp.ok:
                return resp.json()
            log.error("Tavily API error %d: %s", resp.status_code, resp.text[:200])
            return None
        except Exception as e:
            log.error("Tavily API request failed: %s", e)
            return None

    def _detect_category(self, query: str) -> str | None:
        """Detect which top-level JSON category a query maps to."""
        query_lower = query.lower()
        category_map = {
            "surf|surfing": "outdoors",
            "hike|hiking|trek|trail": "outdoors",
            "wildlife|animals|birds": "outdoors",
            "national park|reserve|nature": "outdoors",
            "food|eat|restaurant|dish": "food",
            "visa|entry|border": "entry_and_border",
            "vaccine|health|medical": "health",
            "safety|crime|scam": "safety",
            "budget|cost|price|cheap|expensive|lodging|hotel|hostel": "budget",
            "weather|climate|rain|season": "weather_and_seasonality",
            "transport|bus|taxi|airport": "transport",
            "culture|etiquette|customs": "culture",
        }
        for pattern, category in category_map.items():
            if re.search(pattern, query_lower):
                return category
        return None

    def _enrich_country_json(self, country_code: str, category: str, data: dict):
        """Read country JSON, merge new data into the category field, write back.

        If no JSON file exists for the country yet, create a minimal skeleton
        under the appropriate continent subfolder (or ``unknown/`` if the
        country code isn't in ``COUNTRY_TO_CONTINENT``).
        """
        json_path = _find_country_json(country_code)
        if json_path is None:
            json_path = self._create_country_json(country_code)
            if json_path is None:
                return

        try:
            country_data = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        # Merge tavily results into the category
        if category not in country_data:
            country_data[category] = {}

        target = country_data[category]
        if isinstance(target, dict) and isinstance(data, dict):
            # Merge tavily response results into the field
            tavily_results = data.get("results", [])
            if tavily_results:
                target["tavily_enrichment"] = tavily_results
        elif isinstance(target, list) and isinstance(data, dict):
            tavily_results = data.get("results", [])
            if tavily_results:
                country_data[f"{category}_tavily"] = tavily_results

        # Update meta timestamp
        if "meta" not in country_data:
            country_data["meta"] = {}
        country_data["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()

        try:
            json_path.write_text(
                json.dumps(country_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log.info("Enriched %s with %s data", json_path.name, category)
        except OSError as e:
            log.error("Failed to write enriched JSON: %s", e)

    @staticmethod
    def _create_country_json(country_code: str) -> Path | None:
        """Create a blank country JSON skeleton and return its path."""
        cc = country_code.strip().lower()
        continent = COUNTRY_TO_CONTINENT.get(cc, "unknown")
        target_dir = _COUNTRIES_DIR / continent
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.error("Failed to create continent dir %s: %s", target_dir, e)
            return None

        json_path = target_dir / f"{cc}.json"
        skeleton = json.loads(json.dumps(_BLANK_COUNTRY_TEMPLATE))
        skeleton["meta"]["country_code"] = cc
        skeleton["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        try:
            json_path.write_text(
                json.dumps(skeleton, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log.info("Created new country JSON: %s", json_path)
            return json_path
        except OSError as e:
            log.error("Failed to write new country JSON %s: %s", json_path, e)
            return None

    def _log_query(self, query: str, country_code: str, source: str, result_preview: str):
        """Append a JSON line to the query log."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "country_code": country_code,
            "source": source,
            "result_preview": result_preview[:300],
            "session_id": str(id(st.session_state)),
        }
        try:
            _QUERY_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(_QUERY_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            log.error("Failed to write query log: %s", e)
