"""
predictor.py
WayFinder safety prediction stack.

Models served:
  - v6_ensemble  : MLP (Torch) + RF (sklearn), averaged (original production model)
  - v9b_torch_mlp: Targeted Torch MLP with batchnorm, best from 2000-run search

New specialised sub-models (additive safety dimensions):
  - lgbt_safety   : Ordinal classifier (1-5) for LGBT traveler safety
  - ecuador_safety: Ecuador-specific wildlife + crime risk model
  - weather_risk  : Seasonal weather risk assessor
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from .v6_features import FEATURE_COLS_V6, SafetyV6FeatureBuilder
from .v9b_model import TorchMLP
from .v9b_best_mlp_config import (
    V9B_ARTIFACT_DIR,
    V9B_STATE_DICT_PATH,
    V9B_SCALER_PATH,
    V9B_IMPUTER_PATH,
    V9B_MODEL_VERSION,
    V9B_HIDDEN_SIZES,
    V9B_DROPOUT,
    V9B_ACTIVATION,
    V9B_USE_BATCHNORM,
    load_v9b_features,
    validate_artifacts,
)

# Specialised sub-models — imported lazily so app still starts if one is missing
try:
    from .submodels.lgbt_classifier import LGBTSafetyClassifier
    _LGBT_AVAILABLE = True
except ImportError:
    _LGBT_AVAILABLE = False

try:
    from .submodels.ecuador_safety import EcuadorSafetyModel
    _ECUADOR_AVAILABLE = True
except ImportError:
    _ECUADOR_AVAILABLE = False

try:
    from .submodels.weather_risk import WeatherRiskAssessor
    _WEATHER_AVAILABLE = True
except ImportError:
    _WEATHER_AVAILABLE = False


ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


# ── Legacy v6 MLP architecture (kept for loading v6 checkpoints) ───────────────
class MLPRegressorTorch(nn.Module):
    def __init__(
        self,
        in_dim: int,
        hidden_dims: tuple[int, ...] = (128, 128),
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        prev = in_dim
        for h in hidden_dims:
            layers.append(nn.Linear(prev, h))
            layers.append(nn.ReLU())
            if dropout > 0:
                layers.append(nn.Dropout(dropout))
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


# ── Main predictor ─────────────────────────────────────────────────────────────
class SafetyPredictor:
    """
    Unified safety prediction interface.

    Core models:
      predict_score()         → v6 ensemble (MLP + RF)
      predict_v9b()           → v9b Torch MLP only
      predict_with_features() → v6 ensemble + full feature dump
      compare_all_models()    → side-by-side comparison across all loaded models

    Specialised dimension models (when sub-modules are present):
      predict_lgbt()          → LGBT safety score (1-5)
      predict_ecuador()       → Ecuador-specific risk
      predict_weather()       → Seasonal weather risk
      predict_full()          → All dimensions combined
    """

    def __init__(self, artifacts_dir: Path | None = None) -> None:
        self.artifacts_dir = artifacts_dir or ARTIFACTS_DIR

        # ── v6 stack ──────────────────────────────────────────────────────────
        self.feature_builder = SafetyV6FeatureBuilder()
        self.feature_cols = FEATURE_COLS_V6
        self.scaler_v6 = self._load_artifact("scaler_v6.pkl", joblib.load)
        self.mlp_v6 = self._load_mlp_v6()
        self.mlp_v6.eval()
        self.rf_v6 = self._load_artifact("rf_v6.pkl", joblib.load)

        # ── v9b stack ─────────────────────────────────────────────────────────
        self._v9b_available = False
        try:
            validate_artifacts()
            self.v9b_features = load_v9b_features()
            self.v9b_imputer  = joblib.load(V9B_IMPUTER_PATH)
            self.v9b_scaler   = joblib.load(V9B_SCALER_PATH)
            self.v9b_mlp      = self._load_v9b_mlp()
            self.v9b_mlp.eval()
            self._v9b_available = True
        except (FileNotFoundError, Exception):
            self._v9b_available = False

        # ── Specialised sub-models ────────────────────────────────────────────
        self._lgbt = LGBTSafetyClassifier() if _LGBT_AVAILABLE else None
        self._ecuador = EcuadorSafetyModel() if _ECUADOR_AVAILABLE else None
        self._weather = WeatherRiskAssessor() if _WEATHER_AVAILABLE else None

    # ── Artifact loaders ───────────────────────────────────────────────────────

    def _load_artifact(self, filename: str, loader: Any) -> Any:
        path = self.artifacts_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {path}")
        return loader(path)

    def _load_mlp_v6(self) -> nn.Module:
        path = self.artifacts_dir / "mlp_v6_best_torch.pt"
        if not path.exists():
            raise FileNotFoundError(f"MLP v6 artifact not found: {path}")
        loaded = torch.load(path, map_location="cpu", weights_only=False)
        if isinstance(loaded, nn.Module):
            return loaded
        if isinstance(loaded, dict):
            state = loaded.get("model_state_dict", loaded.get("state_dict"))
            cfg = loaded.get("config", {})
            hidden = tuple(cfg.get("hidden") or cfg.get("hidden_dims") or [128, 128])
            dropout = float(cfg.get("dropout", 0.2))
            model = MLPRegressorTorch(in_dim=len(self.feature_cols), hidden_dims=hidden, dropout=dropout)
            model.load_state_dict(state)
            return model
        raise ValueError("Unsupported v6 MLP checkpoint format.")

    def _load_v9b_mlp(self) -> nn.Module:
        n_features = len(self.v9b_features)
        model = TorchMLP(
            in_dim=n_features,
            hidden_sizes=V9B_HIDDEN_SIZES,
            dropout=V9B_DROPOUT,
            activation=V9B_ACTIVATION,
            use_batchnorm=V9B_USE_BATCHNORM,
        )
        state_dict = torch.load(V9B_STATE_DICT_PATH, map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict)
        return model

    # ── Feature builders ───────────────────────────────────────────────────────

    def _build_v6_df(self, lat: float, lon: float, country: str | None) -> pd.DataFrame:
        feats = self.feature_builder.build_all_features(lat=lat, lon=lon, country=country)
        missing = [c for c in self.feature_cols if c not in feats]
        if missing:
            raise ValueError(f"Missing v6 feature keys: {missing}")
        return pd.DataFrame([[feats[c] for c in self.feature_cols]], columns=self.feature_cols)

    def _build_v9b_input(self, lat: float, lon: float, country: str | None) -> np.ndarray:
        """Build v9b feature vector: start from v6 features, select v9b subset."""
        feats = self.feature_builder.build_all_features(lat=lat, lon=lon, country=country)
        row = np.array([feats.get(c, 0.0) for c in self.v9b_features], dtype=np.float32).reshape(1, -1)
        row = self.v9b_imputer.transform(row)
        row = self.v9b_scaler.transform(row)
        return row

    # ── Core prediction methods ────────────────────────────────────────────────

    def predict_score(self, latitude: float, longitude: float, country: str | None = None) -> dict[str, Any]:
        """v6 ensemble prediction (MLP + RF averaged)."""
        X_rf = self._build_v6_df(latitude, longitude, country)
        X_scaled = self.scaler_v6.transform(X_rf)

        with torch.no_grad():
            mlp_score = float(self.mlp_v6(torch.tensor(np.asarray(X_scaled), dtype=torch.float32)).item())
        rf_score = float(self.rf_v6.predict(X_rf)[0])
        combined = (mlp_score + rf_score) / 2.0
        spread = abs(mlp_score - rf_score)

        return {
            "safety_score": combined,
            "mlp_score_v6": mlp_score,
            "rf_score_v6": rf_score,
            "model_spread": spread,
            "agreement_band": "high" if spread < 3 else "medium" if spread < 7 else "low",
            "model_version": "v6_ensemble",
            "models_used": ["mlp_v6_torch", "rf_v6_sklearn"],
            "feature_count": len(self.feature_cols),
            "features_used": self.feature_cols,
            "input": {"latitude": latitude, "longitude": longitude, "country": country},
        }

    def predict_v9b(self, latitude: float, longitude: float, country: str | None = None) -> dict[str, Any]:
        """v9b Torch MLP prediction."""
        if not self._v9b_available:
            return {"error": "v9b model not available — artifacts missing.", "model_version": V9B_MODEL_VERSION}

        X = self._build_v9b_input(latitude, longitude, country)
        with torch.no_grad():
            score = float(self.v9b_mlp(torch.tensor(X, dtype=torch.float32)).item())

        return {
            "safety_score": score,
            "model_version": V9B_MODEL_VERSION,
            "models_used": [V9B_MODEL_VERSION],
            "feature_count": len(self.v9b_features),
            "features_used": self.v9b_features,
            "input": {"latitude": latitude, "longitude": longitude, "country": country},
        }

    def predict_with_features(self, latitude: float, longitude: float, country: str | None = None) -> dict[str, Any]:
        """v6 ensemble with full feature dump for debugging."""
        X_rf = self._build_v6_df(latitude, longitude, country)
        X_scaled = self.scaler_v6.transform(X_rf)

        with torch.no_grad():
            mlp_score = float(self.mlp_v6(torch.tensor(np.asarray(X_scaled), dtype=torch.float32)).item())
        rf_score = float(self.rf_v6.predict(X_rf)[0])
        combined = (mlp_score + rf_score) / 2.0
        spread = abs(mlp_score - rf_score)

        return {
            "safety_score": combined,
            "mlp_score_v6": mlp_score,
            "rf_score_v6": rf_score,
            "model_spread": spread,
            "agreement_band": "high" if spread < 3 else "medium" if spread < 7 else "low",
            "model_version": "v6_ensemble",
            "models_used": ["mlp_v6_torch", "rf_v6_sklearn"],
            "feature_count": len(self.feature_cols),
            "features_used": self.feature_cols,
            "features": X_rf.iloc[0].to_dict(),
            "input": {"latitude": latitude, "longitude": longitude, "country": country},
        }

    def compare_all_models(
        self,
        latitude: float,
        longitude: float,
        country: str | None = None,
    ) -> dict[str, Any]:
        """
        Run all available models and return side-by-side results.
        Used by the comparison harness in chat_page.py.
        """
        results: dict[str, Any] = {}

        # v6 ensemble
        try:
            v6 = self.predict_score(latitude, longitude, country)
            results["v6_ensemble"] = {
                "safety_score": round(v6["safety_score"], 2),
                "mlp_score_v6": round(v6["mlp_score_v6"], 2),
                "rf_score_v6": round(v6["rf_score_v6"], 2),
                "model_spread": round(v6["model_spread"], 2),
                "agreement_band": v6["agreement_band"],
                "status": "ok",
            }
        except Exception as e:
            results["v6_ensemble"] = {"status": "error", "error": str(e)}

        # v9b
        v9b = self.predict_v9b(latitude, longitude, country)
        if "error" in v9b:
            results["v9b_torch_mlp"] = {"status": "unavailable", "error": v9b["error"]}
        else:
            results["v9b_torch_mlp"] = {
                "safety_score": round(v9b["safety_score"], 2),
                "model_version": v9b["model_version"],
                "feature_count": v9b["feature_count"],
                "status": "ok",
            }

        # LGBT
        if self._lgbt and country:
            try:
                lgbt = self._lgbt.predict(country)
                results["lgbt_safety"] = {**lgbt, "status": "ok"}
            except Exception as e:
                results["lgbt_safety"] = {"status": "error", "error": str(e)}

        # Ecuador
        if self._ecuador:
            try:
                ec = self._ecuador.assess(latitude, longitude, country)
                results["ecuador_safety"] = {**ec, "status": "ok"}
            except Exception as e:
                results["ecuador_safety"] = {"status": "error", "error": str(e)}

        # Weather
        if self._weather:
            try:
                wx = self._weather.assess(latitude, longitude)
                results["weather_risk"] = {**wx, "status": "ok"}
            except Exception as e:
                results["weather_risk"] = {"status": "error", "error": str(e)}

        return {
            "models": results,
            "input": {"latitude": latitude, "longitude": longitude, "country": country},
            "models_available": list(results.keys()),
        }

    def predict_lgbt(self, country: str | None) -> dict[str, Any]:
        """LGBT safety score for a country (1-5 ordinal)."""
        if not self._lgbt:
            return {"error": "LGBT classifier not available.", "lgbt_safety_score": None}
        return self._lgbt.predict(country)

    def predict_full(
        self,
        latitude: float,
        longitude: float,
        country: str | None = None,
        travel_date: Any = None,
    ) -> dict[str, Any]:
        """
        Full multi-dimensional safety assessment combining all available models.
        Returns the primary safety score plus all specialised dimension scores.
        """
        # Primary: prefer v9b if available, else v6
        if self._v9b_available:
            primary = self.predict_v9b(latitude, longitude, country)
        else:
            primary = self.predict_score(latitude, longitude, country)

        dimensions: dict[str, Any] = {}

        if self._lgbt and country:
            try:
                dimensions["lgbt_safety"] = self._lgbt.predict(country)
            except Exception:
                pass

        if self._ecuador:
            try:
                dimensions["ecuador_safety"] = self._ecuador.assess(latitude, longitude, country)
            except Exception:
                pass

        if self._weather:
            try:
                dimensions["weather_risk"] = self._weather.assess(latitude, longitude, travel_date, country)
            except Exception:
                pass

        return {
            "safety_score": primary.get("safety_score"),
            "model_version": primary.get("model_version"),
            "dimensions": dimensions,
            "input": {"latitude": latitude, "longitude": longitude, "country": country},
        }

    def predict_batch(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.predict_score(float(r["latitude"]), float(r["longitude"]), r.get("country")) for r in rows]
