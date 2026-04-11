from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


class SafetyFeaturePipeline:
    def __init__(self, artifacts_dir: Path | None = None) -> None:
        self.artifacts_dir = artifacts_dir or ARTIFACTS_DIR

    def load_feature_columns(self) -> list[str]:
        path = self.artifacts_dir / "v6_feature_columns.txt"
        with open(path, "r", encoding="utf-8") as f:
            cols = [line.strip() for line in f if line.strip()]
        return cols

    def build_features(
        self,
        latitude: float,
        longitude: float,
        country: str | None = None,
    ) -> pd.DataFrame:
        feature_cols = self.load_feature_columns()
        feature_values: dict[str, Any] = {col: 0.0 for col in feature_cols}

        basic = self._build_basic_features(latitude, longitude, country)
        feature_values.update(basic)

        knn_like = self._build_knn_like_features(latitude, longitude, country)
        feature_values.update(knn_like)

        density_like = self._build_density_like_features(latitude, longitude, country)
        feature_values.update(density_like)

        macro_like = self._build_macro_like_features(latitude, longitude, country)
        feature_values.update(macro_like)

        ordered = [feature_values.get(col, 0.0) for col in feature_cols]
        df = pd.DataFrame([ordered], columns=feature_cols)

        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

        return df

    def _build_basic_features(
        self,
        latitude: float,
        longitude: float,
        country: str | None,
    ) -> dict[str, float]:
        return {
            "lat": float(latitude),
            "lon": float(longitude),
            "crimeindex_2020": 0.0,
            "crimeindex_2023": 0.0,
            "safetyindex_2020": 0.0,
            "age_0_14": 0.0,
            "age_15_64": 0.0,
            "age_65_plus": 0.0,
            "population": 0.0,
            "density_per_km2": 0.0,
        }

    def _build_knn_like_features(
        self,
        latitude: float,
        longitude: float,
        country: str | None,
    ) -> dict[str, float]:
        return {
            "dist_nearest_labeled_city": 0.0,
            "log1p_dist_nearest_labeled_city": 0.0,
            "crime_nearest_labeled_city": 0.0,
            "safety_nearest_labeled_city": 0.0,
            "same_country_as_nearest_labeled": 0.0,
            "avg_crime_k5": 0.0,
            "avg_safety_k5": 0.0,
            "avg_crime_k10": 0.0,
            "avg_safety_k10": 0.0,
            "wavg_crime_k5": 0.0,
            "wavg_safety_k5": 0.0,
            "log1p_num_labeled_within_50km": 0.0,
            "log1p_num_labeled_within_100km": 0.0,
            "log1p_num_labeled_within_250km": 0.0,
            "avg_crime_same_country_k5": 0.0,
            "avg_safety_same_country_k5": 0.0,
            "log1p_num_same_country_within_250km": 0.0,
        }

    def _build_density_like_features(
        self,
        latitude: float,
        longitude: float,
        country: str | None,
    ) -> dict[str, float]:
        return {
            "log1p_num_cities_50km": 0.0,
            "log1p_sum_pop_50km": 0.0,
            "log1p_pop_gravity_50km": 0.0,
            "log1p_num_cities_100km": 0.0,
            "log1p_sum_pop_100km": 0.0,
            "log1p_pop_gravity_100km": 0.0,
            "dist_to_nearest_large_city": 0.0,
            "log1p_dist_to_nearest_large_city": 0.0,
            "log1p_pop_of_nearest_large_city": 0.0,
        }

    def _build_macro_like_features(
        self,
        latitude: float,
        longitude: float,
        country: str | None,
    ) -> dict[str, float]:
        return {
            "gdp": 0.0,
            "gdp_per_capita": 0.0,
            "unemployment": 0.0,
            "homicide_rate": 0.0,
            "life_expectancy_male": 0.0,
            "life_expectancy_female": 0.0,
            "infant_mortality": 0.0,
            "urban_population_growth": 0.0,
            "tourists": 0.0,
        }

    def scale_features(self, X: pd.DataFrame) -> np.ndarray:
        mean_path = self.artifacts_dir / "v6_scaler_mean.npy"
        scale_path = self.artifacts_dir / "v6_scaler_scale.npy"

        mean = np.load(mean_path)
        scale = np.load(scale_path)

        x = X.to_numpy(dtype=np.float32)
        scale = np.where(scale == 0, 1.0, scale)
        x_scaled = (x - mean) / scale
        return x_scaled.astype(np.float32)