# app/models/safety/v6_features.py

# app/models/safety/v6_features.py

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

# KNN neighborhood features (from KNN notebook) — snake_case v6 names
KNN_FEATURE_COLS = [
    "dist_nearest_labeled_city",
    "log1p_dist_nearest_labeled_city",
    "crime_nearest_labeled_city",
    "safety_nearest_labeled_city",
    "same_country_as_nearest_labeled",
    "avg_crime_k5",
    "avg_safety_k5",
    "avg_crime_k10",
    "avg_safety_k10",
    "wavg_crime_k5",
    "wavg_safety_k5",
    "log1p_num_labeled_within_50km",
    "log1p_num_labeled_within_100km",
    "log1p_num_labeled_within_250km",
    "avg_crime_same_country_k5",
    "avg_safety_same_country_k5",
    "log1p_num_same_country_within_250km",
]

# Density / gravity features
DENSITY_GRAVITY_FEATURE_COLS = [
    "log1p_num_cities_50km",
    "log1p_sum_pop_50km",
    "log1p_pop_gravity_50km",
    "log1p_num_cities_100km",
    "log1p_sum_pop_100km",
    "log1p_pop_gravity_100km",
    "dist_to_nearest_large_city",
    "log1p_dist_to_nearest_large_city",
    "log1p_pop_of_nearest_large_city",
]

# Base city + country features already in v5 table
BASE_FEATURE_COLS = [
    "lat",
    "lon",
    "crimeindex_2020",
    "crimeindex_2023",
    "safetyindex_2020",
    "age_0_14",
    "age_15_64",
    "age_65_plus",
    "population",
    "density_per_km2",
]

# Macro columns built in data_cleaner (macro v5)
MACRO_COLS_V6 = [
    "gdp",
    "gdp_per_capita",
    "unemployment",
    "homicide_rate",
    "life_expectancy_male",
    "life_expectancy_female",
    "infant_mortality",
    "urban_population_growth",
    "tourists",
]

FEATURE_COLS_V6 = list(
    dict.fromkeys(
        KNN_FEATURE_COLS
        + DENSITY_GRAVITY_FEATURE_COLS
        + BASE_FEATURE_COLS
        + MACRO_COLS_V6
    )
)

# Paths into your repo data layout
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CITY_TABLE_V5 = DATA_DIR / "compiled_model_ready" / "MR_cities_worldpop_knn_macro_v5.csv"
COUNTRY_MACRO_V5 = DATA_DIR / "global_data" / "country_macro_v5.csv"


def _norm_country(x: Optional[str]) -> str:
    if x is None:
        return ""
    return str(x).strip().lower()


def _haversine_km(
    lat1: float, lon1: float, lats2: np.ndarray, lons2: np.ndarray
) -> np.ndarray:
    r = 6371.0088
    lat1r = np.radians(lat1)
    lon1r = np.radians(lon1)
    lat2r = np.radians(lats2.astype(float))
    lon2r = np.radians(lons2.astype(float))

    dlat = lat2r - lat1r
    dlon = lon2r - lon1r
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2.0) ** 2
    )
    return 2 * r * np.arcsin(np.sqrt(a))


class SafetyV6FeatureBuilder:
    """
    Build v6 feature dicts from lat/lon/country that align with FEATURE_COLS_V6.
    Uses the v5 compiled table (MR_cities_worldpop_knn_macro_v5.csv) to
    recompute KNN + density/gravity + macro features at inference.
    """

    def __init__(self) -> None:
        # Load the full v5 modeling-ready table
        self.city_df = pd.read_csv(CITY_TABLE_V5).copy()

        # Normalize column names so we can use compact, no-underscore names downstream
        # e.g. crime_index -> crimeindex, safety_index -> safetyindex, density_per_km2 -> densityperkm2
        self.city_df.columns = (
            self.city_df.columns
            .str.strip()
            .str.lower()
            .str.replace(" ", "", regex=False)
            .str.replace("_", "", regex=False)
        )

        # At this point, the CSV columns you showed become:
        # 'crime_index'      -> 'crimeindex'
        # 'safety_index'     -> 'safetyindex'
        # 'crimeindex_2023'  -> 'crimeindex2023'
        # 'crimeindex_2020'  -> 'crimeindex2020'
        # 'safetyindex_2020' -> 'safetyindex2020'
        # 'density_per_km2'  -> 'densityperkm2'
        # 'country_norm_x'   -> 'countrynormx'
        # 'country_norm_y'   -> 'countrynormy'
        # etc.

        # Build unified countrynorm after normalization
        if "countrynorm" in self.city_df.columns:
            self.city_df["countrynorm"] = self.city_df["countrynorm"].map(_norm_country)
        elif "countrynormx" in self.city_df.columns:
            self.city_df["countrynorm"] = self.city_df["countrynormx"].map(
                _norm_country
            )
        else:
            self.city_df["countrynorm"] = self.city_df["country"].map(_norm_country)

        required_cols = ["crimeindex", "safetyindex", "lat", "lon", "countrynorm"]
        missing = [c for c in required_cols if c not in self.city_df.columns]
        if missing:
            raise ValueError(
                f"CITY_TABLE_V5 missing required columns: {missing}. "
                f"Available columns: {self.city_df.columns.tolist()}"
            )

        # Subset with valid KNN source fields
        self.labeled_df = self.city_df.dropna(
            subset=["lat", "lon", "crimeindex", "safetyindex"]
        ).copy()
        self.labeled_lats = self.labeled_df["lat"].to_numpy(dtype=float)
        self.labeled_lons = self.labeled_df["lon"].to_numpy(dtype=float)
        self.labeled_crime = self.labeled_df["crimeindex"].to_numpy(dtype=float)
        self.labeled_safety = self.labeled_df["safetyindex"].to_numpy(dtype=float)
        self.labeled_country = self.labeled_df["countrynorm"].astype(str).to_numpy()

        # Optional dedicated macro table (built in macro v5 cleaner)
        self.country_macro: Optional[pd.DataFrame] = None
        if COUNTRY_MACRO_V5.exists():
            macro = pd.read_csv(COUNTRY_MACRO_V5).copy()
            macro.columns = (
                macro.columns
                .str.strip()
                .str.lower()
                .str.replace(" ", "", regex=False)
                .str.replace("_", "", regex=False)
            )
            macro["countrynorm"] = macro["countrynorm"].map(_norm_country)
            self.country_macro = macro.drop_duplicates("countrynorm").set_index(
                "countrynorm"
            )

    # ---------- KNN-like neighborhood features ----------

    def _build_knn_like_features(
        self, lat: float, lon: float, country: Optional[str]
    ) -> Dict[str, float]:
        country_norm = _norm_country(country)
        dists = _haversine_km(lat, lon, self.labeled_lats, self.labeled_lons)

        order = np.argsort(dists)
        d_sorted = dists[order]
        crime_sorted = self.labeled_crime[order]
        safety_sorted = self.labeled_safety[order]
        country_sorted = self.labeled_country[order]

        nearest_dist = float(d_sorted[0])
        nearest_crime = float(crime_sorted[0])
        nearest_safety = float(safety_sorted[0])
        same_country_nearest = float(country_sorted[0] == country_norm)

        def mean_k(arr: np.ndarray, k: int) -> float:
            kk = min(k, len(arr))
            return float(np.mean(arr[:kk]))

        def weighted_mean_k(values: np.ndarray, d: np.ndarray, k: int) -> float:
            kk = min(k, len(values))
            vals = values[:kk]
            dd = d[:kk]
            w = 1.0 / np.maximum(dd, 1.0)
            return float(np.sum(vals * w) / np.sum(w))

        log1p_n_50 = float(np.log1p(np.sum(dists <= 50.0)))
        log1p_n_100 = float(np.log1p(np.sum(dists <= 100.0)))
        log1p_n_250 = float(np.log1p(np.sum(dists <= 250.0)))

        # Same-country neighborhood aggregates
        same_mask = self.labeled_country == country_norm
        same_d = dists[same_mask]
        same_crime = self.labeled_crime[same_mask]
        same_safety = self.labeled_safety[same_mask]

        if same_d.size > 0:
            same_order = np.argsort(same_d)
            same_crime = same_crime[same_order]
            same_safety = same_safety[same_order]
            avgcrime_same_k5 = float(np.mean(same_crime[: min(5, len(same_crime))]))
            avgsafety_same_k5 = float(np.mean(same_safety[: min(5, len(same_safety))]))
            log1p_n_same_250 = float(np.log1p(np.sum(same_d <= 250.0)))
        else:
            avgcrime_same_k5 = nearest_crime
            avgsafety_same_k5 = nearest_safety
            log1p_n_same_250 = 0.0

        return {
            "dist_nearest_labeled_city": nearest_dist,
            "log1p_dist_nearest_labeled_city": float(np.log1p(nearest_dist)),
            "crime_nearest_labeled_city": nearest_crime,
            "safety_nearest_labeled_city": nearest_safety,
            "same_country_as_nearest_labeled": same_country_nearest,
            "avg_crime_k5": mean_k(crime_sorted, 5),
            "avg_safety_k5": mean_k(safety_sorted, 5),
            "avg_crime_k10": mean_k(crime_sorted, 10),
            "avg_safety_k10": mean_k(safety_sorted, 10),
            "wavg_crime_k5": weighted_mean_k(crime_sorted, d_sorted, 5),
            "wavg_safety_k5": weighted_mean_k(safety_sorted, d_sorted, 5),
            "log1p_num_labeled_within_50km": log1p_n_50,
            "log1p_num_labeled_within_100km": log1p_n_100,
            "log1p_num_labeled_within_250km": log1p_n_250,
            "avg_crime_same_country_k5": avgcrime_same_k5,
            "avg_safety_same_country_k5": avgsafety_same_k5,
            "log1p_num_same_country_within_250km": log1p_n_same_250,
        }

    # ---------- Density / gravity and nearest large city ----------

    def _build_density_like_features(
        self, lat: float, lon: float
    ) -> Dict[str, float]:
        dists = _haversine_km(lat, lon, self.labeled_lats, self.labeled_lons)
        idx = int(np.argmin(dists))
        row = self.labeled_df.iloc[idx]

        return {
            "log1p_num_cities_50km": float(row["log1pnumcities50km"]),
            "log1p_sum_pop_50km": float(row["log1psumpop50km"]),
            "log1p_pop_gravity_50km": float(row["log1ppopgravity50km"]),
            "log1p_num_cities_100km": float(row["log1pnumcities100km"]),
            "log1p_sum_pop_100km": float(row["log1psumpop100km"]),
            "log1p_pop_gravity_100km": float(row["log1ppopgravity100km"]),
            "dist_to_nearest_large_city": float(row["disttonearestlargecity"]),
            "log1p_dist_to_nearest_large_city": float(
                row["log1pdisttonearestlargecity"]
            ),
            "log1p_pop_of_nearest_large_city": float(
                row["log1ppopofnearestlargecity"]
            ),
        }

    # ---------- Base city + country features ----------

    def _build_basic_features(
        self, lat: float, lon: float, country: Optional[str]
    ) -> Dict[str, float]:
        country_norm = _norm_country(country)

        if country_norm:
            same = self.city_df[self.city_df["countrynorm"] == country_norm]
        else:
            same = self.city_df.iloc[0:0]

        def pick_row() -> pd.Series:
            if len(same) > 0:
                lats = same["lat"].to_numpy(dtype=float)
                lons = same["lon"].to_numpy(dtype=float)
                dists = _haversine_km(lat, lon, lats, lons)
                j = int(np.argmin(dists))
                return same.iloc[j]
            dists = _haversine_km(lat, lon, self.labeled_lats, self.labeled_lons)
            j = int(np.argmin(dists))
            return self.labeled_df.iloc[j]

        row = pick_row()

        return {
            "lat": float(lat),
            "lon": float(lon),
            "crimeindex_2020": float(row["crimeindex2020"]),
            "crimeindex_2023": float(row["crimeindex2023"]),
            "safetyindex_2020": float(row["safetyindex2020"]),
            "age_0_14": float(row["age014"]),
            "age_15_64": float(row["age1564"]),
            "age_65_plus": float(row["age65plus"]),
            "population": float(row["population"]),
            "density_per_km2": float(row["densityperkm2"]),
        }

    # ---------- Macro-level country features ----------

    def _build_macro_like_features(self, country: Optional[str]) -> Dict[str, float]:
        country_norm = _norm_country(country)

        if self.country_macro is not None and country_norm in self.country_macro.index:
            r = self.country_macro.loc[country_norm]
            return {
                "gdp": float(r["gdp"]),
                "gdp_per_capita": float(r["gdppercapita"]),
                "unemployment": float(r["unemployment"]),
                "homicide_rate": float(r["homiciderate"]),
                "life_expectancy_male": float(r["lifeexpectancymale"]),
                "life_expectancy_female": float(r["lifeexpectancyfemale"]),
                "infant_mortality": float(r["infantmortality"]),
                "urban_population_growth": float(r["urbanpopulationgrowth"]),
                "tourists": float(r["tourists"]),
            }

        same = self.city_df[self.city_df["countrynorm"] == country_norm]
        if len(same) > 0:
            r = same.iloc[0]
            return {
                "gdp": float(r["gdp"]),
                "gdp_per_capita": float(r["gdppercapita"]),
                "unemployment": float(r["unemployment"]),
                "homicide_rate": float(r["homiciderate"]),
                "life_expectancy_male": float(r["lifeexpectancymale"]),
                "life_expectancy_female": float(r["lifeexpectancyfemale"]),
                "infant_mortality": float(r["infantmortality"]),
                "urban_population_growth": float(r["urbanpopulationgrowth"]),
                "tourists": float(r["tourists"]),
            }

        meds = self.city_df[
            [
                "gdp",
                "gdppercapita",
                "unemployment",
                "homiciderate",
                "lifeexpectancymale",
                "lifeexpectancyfemale",
                "infantmortality",
                "urbanpopulationgrowth",
                "tourists",
            ]
        ].median(numeric_only=True)

        return {
            "gdp": float(meds["gdp"]),
            "gdp_per_capita": float(meds["gdppercapita"]),
            "unemployment": float(meds["unemployment"]),
            "homicide_rate": float(meds["homiciderate"]),
            "life_expectancy_male": float(meds["lifeexpectancymale"]),
            "life_expectancy_female": float(meds["lifeexpectancyfemale"]),
            "infant_mortality": float(meds["infantmortality"]),
            "urban_population_growth": float(meds["urbanpopulationgrowth"]),
            "tourists": float(meds["tourists"]),
        }

    # ---------- Public API ----------

    def build_all_features(
        self, lat: float, lon: float, country: Optional[str]
    ) -> Dict[str, float]:
        feats: Dict[str, float] = {}
        feats.update(self._build_knn_like_features(lat, lon, country))
        feats.update(self._build_density_like_features(lat, lon))
        feats.update(self._build_basic_features(lat, lon, country))
        feats.update(self._build_macro_like_features(country))

        for col in FEATURE_COLS_V6:
            feats.setdefault(col, 0.0)

        return feats

    # ISO-3166-2 US state codes that appear as `country` in the city table
    _US_STATE_CODES: frozenset[str] = frozenset({
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        "DC",
    })

    def geocode_place(self, location_name: str) -> "tuple[float, float, str] | None":
        """Return (lat, lon, country) for the closest matching city name, or None."""
        q = location_name.strip().lower()
        if not q or "city" not in self.city_df.columns:
            return None

        city_lower = self.city_df["city"].str.strip().str.lower()

        for mask in (
            city_lower == q,
            city_lower.str.startswith(q),
            city_lower.str.contains(q, na=False, regex=False),
        ):
            if mask.any():
                row = self.city_df[mask].iloc[0]
                country_val = str(row["country"]) if "country" in row.index else ""
                # Normalize US state codes → "United States" for macro feature lookup
                if country_val.upper() in self._US_STATE_CODES:
                    country_val = "United States"
                return float(row["lat"]), float(row["lon"]), country_val

        return None

''' older implemtaition below
# KNN neighborhood features (from KNN notebook)
KNN_FEATURE_COLS = [
    "dist_nearest_labeled_city",
    "log1p_dist_nearest_labeled_city",
    "crime_nearest_labeled_city",
    "safety_nearest_labeled_city",
    "same_country_as_nearest_labeled",
    "avg_crime_k5",
    "avg_safety_k5",
    "avg_crime_k10",
    "avg_safety_k10",
    "wavg_crime_k5",
    "wavg_safety_k5",
    "log1p_num_labeled_within_50km",
    "log1p_num_labeled_within_100km",
    "log1p_num_labeled_within_250km",
    "avg_crime_same_country_k5",
    "avg_safety_same_country_k5",
    "log1p_num_same_country_within_250km",
]

# Density / gravity features
DENSITY_GRAVITY_FEATURE_COLS = [
    "log1p_num_cities_50km",
    "log1p_sum_pop_50km",
    "log1p_pop_gravity_50km",
    "log1p_num_cities_100km",
    "log1p_sum_pop_100km",
    "log1p_pop_gravity_100km",
    "dist_to_nearest_large_city",
    "log1p_dist_to_nearest_large_city",
    "log1p_pop_of_nearest_large_city",
]

# Base city + country features already in v5 table
BASE_FEATURE_COLS = [
    "lat",
    "lon",
    "crimeindex_2020",
    "crimeindex_2023",
    "safetyindex_2020",
    "age_0_14",
    "age_15_64",
    "age_65_plus",
    "population",
    "density_per_km2",
]

# Macro columns built in data_cleaner (macro v5) 
MACRO_COLS_V6 = [
    "gdp",
    "gdp_per_capita",
    "unemployment",
    "homicide_rate",
    "life_expectancy_male",
    "life_expectancy_female",
    "infant_mortality",
    "urban_population_growth",
    "tourists",
]

FEATURE_COLS_V6 = list(
    dict.fromkeys(
        KNN_FEATURE_COLS + DENSITY_GRAVITY_FEATURE_COLS + BASE_FEATURE_COLS + MACRO_COLS_V6
    )
)
'''