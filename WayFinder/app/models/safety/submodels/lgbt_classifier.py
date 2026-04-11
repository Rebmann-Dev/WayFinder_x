"""
lgbt_classifier.py — LGBT Safety Classifier for WayFinder.

Provides an ordinal 1-5 safety score for LGBT travellers based on a country's
legal equality index (ei_legal, 0–100 scale).  All country data is embedded at
import time — no file I/O is performed at runtime.

Score bands
-----------
  1 – Very High Risk  : ei_legal  0–20   (criminalization likely)
  2 – High Risk       : ei_legal 20–40   (no recognition, high hostility)
  3 – Moderate Risk   : ei_legal 40–60   (partial protections, mixed culture)
  4 – Low Risk        : ei_legal 60–80   (solid protections, some variation)
  5 – Very Safe       : ei_legal 80–100  (full equality, inclusive culture)

Usage
-----
    from lgbt_classifier import LGBTSafetyClassifier

    clf = LGBTSafetyClassifier()
    result = clf.predict("Germany")
    # {'lgbt_safety_score': 5, 'lgbt_safety_label': 'Very Safe', ...}
"""
from __future__ import annotations

import difflib
import unicodedata
from typing import Optional

from lgbt_data import COUNTRY_DATA, REGIONAL_AVERAGES, REGION_MAP

# ---------------------------------------------------------------------------
# Score band definitions
# ---------------------------------------------------------------------------
_BANDS: list[tuple[float, float, int, str]] = [
    # (lower_inclusive, upper_exclusive, score, label)
    (0.0,  20.0, 1, "Very High Risk"),
    (20.0, 40.0, 2, "High Risk"),
    (40.0, 60.0, 3, "Moderate Risk"),
    (60.0, 80.0, 4, "Low Risk"),
    (80.0, 101.0, 5, "Very Safe"),
]

# Details text per score band
_BAND_DETAILS: dict[int, dict] = {
    1: {
        "summary": "Same-sex relations are criminalized or effectively persecuted.",
        "travel_advice": (
            "Avoid public displays of affection. Conceal LGBT identity. "
            "Research local laws before travel. Consider avoiding."
        ),
        "legal_situation": "Criminalization likely; imprisonment or corporal punishment possible.",
        "social_climate": "Extreme hostility; no social acceptance.",
    },
    2: {
        "summary": "No legal recognition; discrimination widespread and socially normalized.",
        "travel_advice": (
            "Exercise significant caution. Avoid displays of affection. "
            "LGBT venues, if any, are discreet. Travel with trusted contacts."
        ),
        "legal_situation": "Same-sex acts may be legal but no anti-discrimination protections exist.",
        "social_climate": "High hostility; religious and social pressure pervasive.",
    },
    3: {
        "summary": "Partial legal protections exist; social climate varies widely.",
        "travel_advice": (
            "Urban areas generally safer than rural. Discretion advised outside "
            "major cities. LGBT venues present in capitals."
        ),
        "legal_situation": "Some anti-discrimination laws; no or limited partnership recognition.",
        "social_climate": "Moderate; urban-rural divide common.",
    },
    4: {
        "summary": "Solid legal framework; generally welcoming with some regional variation.",
        "travel_advice": (
            "Comfortable for most travel. Rural or conservative regions may be "
            "less welcoming. Check local context."
        ),
        "legal_situation": "Partnership or marriage recognized; anti-discrimination protections in place.",
        "social_climate": "Broadly accepting; Pride events held; LGBT community visible.",
    },
    5: {
        "summary": "Full legal equality; inclusive culture highly friendly to LGBT travellers.",
        "travel_advice": (
            "Generally very safe and welcoming. Major cities have vibrant LGBT scenes. "
            "Public displays of affection broadly accepted."
        ),
        "legal_situation": "Marriage equality; comprehensive anti-discrimination and hate-crime laws.",
        "social_climate": "High social acceptance; robust civil society support.",
    },
}

# ---------------------------------------------------------------------------
# Alias / alternate-name lookup table
# ---------------------------------------------------------------------------
_ALIASES: dict[str, str] = {
    # United States
    "us": "USA", "usa": "USA", "u.s.": "USA", "u.s.a.": "USA",
    "united states": "USA", "united states of america": "USA",
    "america": "USA", "the united states": "USA",
    # United Kingdom
    "uk": "GBR", "u.k.": "GBR", "great britain": "GBR",
    "britain": "GBR", "england": "GBR", "scotland": "GBR",
    "wales": "GBR", "northern ireland": "GBR",
    # Russia
    "russia": "RUS", "russian federation": "RUS",
    # South Korea
    "south korea": "KOR", "korea": "KOR", "republic of korea": "KOR",
    # North Korea
    "north korea": "PRK", "dprk": "PRK",
    # DR Congo
    "dr congo": "COD", "drc": "COD", "democratic republic of the congo": "COD",
    "congo kinshasa": "COD",
    # Republic of Congo
    "republic of the congo": "COG", "congo brazzaville": "COG",
    # Taiwan
    "taiwan": "TWN", "chinese taipei": "TWN", "republic of china": "TWN",
    # Palestine
    "palestine": "PSE", "west bank": "PSE", "gaza": "PSE",
    # UAE
    "uae": "ARE", "emirates": "ARE", "united arab emirates": "ARE",
    "dubai": "ARE", "abu dhabi": "ARE",
    # Czech Republic
    "czech republic": "CZE", "czechia": "CZE",
    # North Macedonia
    "north macedonia": "MKD", "macedonia": "MKD",
    # Bosnia
    "bosnia": "BIH", "bosnia and herzegovina": "BIH",
    # Ivory Coast
    "ivory coast": "CIV", "cote d'ivoire": "CIV", "côte d'ivoire": "CIV",
    # Eswatini
    "eswatini": "SWZ", "swaziland": "SWZ",
    # Timor-Leste
    "timor-leste": "TLS", "east timor": "TLS",
    # Myanmar / Burma
    "myanmar": "MMR", "burma": "MMR",
    # Iran
    "iran": "IRN", "islamic republic of iran": "IRN",
    # Venezuela
    "venezuela": "VEN",
    # Saudi Arabia
    "saudi arabia": "SAU", "ksa": "SAU", "kingdom of saudi arabia": "SAU",
    # New Zealand
    "new zealand": "NZL", "nz": "NZL", "aotearoa": "NZL",
    # Papua New Guinea
    "papua new guinea": "PNG", "png": "PNG",
    # Solomon Islands
    "solomon islands": "SLB",
    # Turks and Caicos
    "turks and caicos": "TCA", "turks & caicos": "TCA",
    # Germany
    "germany": "DEU", "deutschland": "DEU",
    # Japan
    "japan": "JPN", "nippon": "JPN",
    # China
    "china": "CHN", "prc": "CHN", "people's republic of china": "CHN",
    # Netherlands
    "netherlands": "NLD", "holland": "NLD", "the netherlands": "NLD",
    # Trinidad
    "trinidad": "TTO", "trinidad and tobago": "TTO",
    # El Salvador
    "el salvador": "SLV",
    # Saint Kitts
    "saint kitts": "KNA", "st kitts": "KNA", "st. kitts": "KNA",
    # Saint Lucia
    "saint lucia": "LCA", "st lucia": "LCA",
    # Saint Vincent
    "saint vincent": "VCT", "st vincent": "VCT",
    # Brunei
    "brunei": "BRN", "brunei darussalam": "BRN",
    # Kosovo
    "kosovo": "XKX",
    # Vatican
    "vatican": "VAT", "holy see": "VAT", "vatican city": "VAT",
    # Micronesia
    "micronesia": "FSM", "federated states of micronesia": "FSM",
    # Marshall Islands
    "marshall islands": "MHL",
    # Cape Verde
    "cape verde": "CPV", "cabo verde": "CPV",
    # Sao Tome
    "sao tome": "STP", "são tomé": "STP", "sao tome and principe": "STP",
}


def _normalize(name: str) -> str:
    """Lowercase, strip accents, remove punctuation for fuzzy matching."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_str.lower().strip()


class LGBTSafetyClassifier:
    """
    Rule-based LGBT safety classifier for WayFinder.

    Converts a country's legal equality index (0–100) into an ordinal
    safety score (1–5) with labels, travel advice, and legal facts.

    All data is embedded in the module — no external file I/O at runtime.

    Parameters
    ----------
    None

    Examples
    --------
    >>> clf = LGBTSafetyClassifier()
    >>> clf.predict("Germany")
    {'lgbt_safety_score': 5, 'lgbt_safety_label': 'Very Safe', ...}
    >>> clf.predict("Uganda")
    {'lgbt_safety_score': 1, 'lgbt_safety_label': 'Very High Risk', ...}
    """

    def __init__(self) -> None:
        # Build forward lookup: ISO3 → entry
        self._data: dict[str, dict] = COUNTRY_DATA

        # Build name → ISO3 lookup from entity names
        self._name_index: dict[str, str] = {}
        for code, entry in self._data.items():
            key = _normalize(entry["entity"])
            self._name_index[key] = code

        # Merge alias table
        for alias, code in _ALIASES.items():
            self._name_index[_normalize(alias)] = code

        # Pre-build sorted canonical name list for fuzzy matching
        self._canonical_names: list[str] = sorted(self._name_index.keys())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, country: Optional[str]) -> dict:
        """
        Predict the LGBT safety score for a given country name.

        Parameters
        ----------
        country : str or None
            Country name in any common form (English, alias, abbreviation).

        Returns
        -------
        dict with keys:
            lgbt_safety_score  : int   — 1 (Very High Risk) to 5 (Very Safe)
            lgbt_safety_label  : str   — human-readable label
            lgbt_legal_index   : float — raw 0–100 legal equality score
            confidence         : str   — "high" | "medium" | "low"
            details            : dict  — travel advice and legal facts
            matched_country    : str   — canonical country name used
            criminalized       : bool
            death_penalty_risk : bool
            legal_partnership  : bool
            full_marriage_equality : bool
        """
        if not country or not isinstance(country, str) or not country.strip():
            return self._fallback_result(reason="empty_input")

        norm = _normalize(country)

        # 1. Exact alias / name match
        if norm in self._name_index:
            code = self._name_index[norm]
            return self._build_result(code, confidence="high")

        # 2. ISO3 code match (uppercased)
        upper = country.strip().upper()
        if upper in self._data:
            return self._build_result(upper, confidence="high")

        # 3. Fuzzy match on canonical names
        close = difflib.get_close_matches(norm, self._canonical_names, n=1, cutoff=0.6)
        if close:
            code = self._name_index[close[0]]
            return self._build_result(code, confidence="medium")

        # 4. Regional fallback — try to detect a region keyword
        region = self._detect_region_keyword(norm)
        if region:
            return self._regional_fallback(region)

        # 5. Global fallback
        return self._fallback_result(reason="not_found")

    def available_countries(self) -> list[str]:
        """Return a sorted list of all canonical country names."""
        return sorted(entry["entity"] for entry in self._data.values())

    def score_from_index(self, ei_legal: float) -> tuple[int, str]:
        """
        Convert a raw ei_legal value (0–100) to (score, label).

        Useful for inline scoring without a full country lookup.
        """
        return self._score_label(ei_legal)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_label(ei_legal: float) -> tuple[int, str]:
        for lo, hi, score, label in _BANDS:
            if lo <= ei_legal < hi:
                return score, label
        # ei_legal == 100.0 falls into the last band (80–101)
        return 5, "Very Safe"

    def _build_result(self, code: str, confidence: str) -> dict:
        entry = self._data[code]
        ei = entry["ei_legal"]
        score, label = self._score_label(ei)
        band_details = dict(_BAND_DETAILS[score])

        # Augment details with death penalty note if applicable
        if entry["death_penalty_risk"]:
            band_details["death_penalty_note"] = (
                "Death penalty or corporal punishment for same-sex conduct "
                "is documented or at high risk in this country."
            )
        return {
            "lgbt_safety_score": score,
            "lgbt_safety_label": label,
            "lgbt_legal_index": round(ei, 2),
            "confidence": confidence,
            "matched_country": entry["entity"],
            "criminalized": entry["criminalized"],
            "death_penalty_risk": entry["death_penalty_risk"],
            "legal_partnership": entry["legal_partnership"],
            "full_marriage_equality": entry["full_marriage_equality"],
            "details": band_details,
        }

    def _regional_fallback(self, region: str) -> dict:
        avg = REGIONAL_AVERAGES.get(region, REGIONAL_AVERAGES.get("Global", 25.0))
        score, label = self._score_label(avg)
        return {
            "lgbt_safety_score": score,
            "lgbt_safety_label": label,
            "lgbt_legal_index": round(avg, 2),
            "confidence": "low",
            "matched_country": f"{region} (regional average)",
            "criminalized": avg < 15.0,
            "death_penalty_risk": False,
            "legal_partnership": avg > 50.0,
            "full_marriage_equality": avg > 85.0,
            "details": dict(_BAND_DETAILS[score]),
        }

    def _fallback_result(self, reason: str = "not_found") -> dict:
        """Return score=1 fallback when country cannot be resolved."""
        return {
            "lgbt_safety_score": 1,
            "lgbt_safety_label": "Very High Risk",
            "lgbt_legal_index": 0.0,
            "confidence": "low",
            "matched_country": None,
            "criminalized": True,
            "death_penalty_risk": False,
            "legal_partnership": False,
            "full_marriage_equality": False,
            "details": {
                **_BAND_DETAILS[1],
                "note": f"Country not recognized ({reason}). Defaulting to most cautious score.",
            },
        }

    @staticmethod
    def _detect_region_keyword(norm: str) -> Optional[str]:
        """Very simple region keyword scanner."""
        region_keywords = {
            "africa": "Africa",
            "african": "Africa",
            "europe": "Europe",
            "european": "Europe",
            "asia": "Asia",
            "asian": "Asia",
            "america": "Americas",
            "americas": "Americas",
            "latin": "Americas",
            "caribbean": "Americas",
            "oceania": "Oceania",
            "pacific": "Oceania",
            "middle east": "Asia",
        }
        for kw, region in region_keywords.items():
            if kw in norm:
                return region
        return None
