from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from .v6_features import FEATURE_COLS_V6, SafetyV6FeatureBuilder


ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


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


class SafetyPredictor:
    """
    Uses both:
      - Torch MLP v6 checkpoint: mlp_v6_best_torch.pt
      - sklearn RF v6: rf_v6.pkl

    Feature generation:
      - SafetyV6FeatureBuilder builds the full v6 feature row
      - StandardScaler artifact is applied only for the Torch MLP
      - RF uses raw features, matching v5/v6 training semantics

    Returns:
      - mlp_score_v6
      - rf_score_v6
      - safety_score (ensemble)
      - metadata the agent can use when crafting responses
    """

    def __init__(self, artifacts_dir: Path | None = None) -> None:
        self.artifacts_dir = artifacts_dir or ARTIFACTS_DIR

        self.feature_builder = SafetyV6FeatureBuilder()
        self.feature_cols = FEATURE_COLS_V6

        self.scaler = self._load_scaler()
        self.mlp = self._load_mlp_model()
        self.mlp.eval()
        self.rf = self._load_rf_model()

    # ---------- Loading models ----------

    def _load_scaler(self) -> Any:
        model_path = self.artifacts_dir / "scaler_v6.pkl"
        if not model_path.exists():
            raise FileNotFoundError(f"Scaler artifact not found at {model_path}")
        return joblib.load(model_path)

    def _load_mlp_model(self) -> nn.Module:
        model_path = self.artifacts_dir / "mlp_v6_best_torch.pt"
        if not model_path.exists():
            raise FileNotFoundError(f"MLP artifact not found at {model_path}")

        loaded = torch.load(model_path, map_location="cpu", weights_only=False)

        if isinstance(loaded, nn.Module):
            return loaded

        if isinstance(loaded, dict):
            state_dict = loaded.get("model_state_dict", loaded.get("state_dict"))
            config: dict[str, Any] = loaded.get("config", {})

            hidden_from_ckpt = config.get("hidden") or config.get("hidden_dims")
            if hidden_from_ckpt is None:
                hidden_dims = (128, 128)
            else:
                hidden_dims = tuple(hidden_from_ckpt)

            dropout = float(config.get("dropout", 0.2))

            model = MLPRegressorTorch(
                in_dim=len(self.feature_cols),
                hidden_dims=hidden_dims,
                dropout=dropout,
            )
            if state_dict is None:
                raise ValueError(
                    "Checkpoint dict does not contain model_state_dict or state_dict."
                )
            model.load_state_dict(state_dict)
            return model

        raise ValueError("Unsupported model checkpoint format for mlp_v6_best_torch.pt")

    def _load_rf_model(self) -> Any:
        model_path = self.artifacts_dir / "rf_v6.pkl"
        if not model_path.exists():
            raise FileNotFoundError(f"RandomForest artifact not found at {model_path}")
        return joblib.load(model_path)

    # ---------- Feature helpers ----------

    def _build_features_df(
        self,
        latitude: float,
        longitude: float,
        country: str | None = None,
    ) -> pd.DataFrame:
        feats = self.feature_builder.build_all_features(
            lat=float(latitude),
            lon=float(longitude),
            country=country,
        )

        missing_cols = [c for c in self.feature_cols if c not in feats]
        if missing_cols:
            raise ValueError(f"Missing expected feature keys from v6 feature builder: {missing_cols}")

        X = pd.DataFrame(
            [[feats[c] for c in self.feature_cols]],
            columns=self.feature_cols,
        )
        return X

    # ---------- Prediction ----------

    def predict_score(
        self,
        latitude: float,
        longitude: float,
        country: str | None = None,
    ) -> dict[str, Any]:
        """
        Build features via SafetyV6FeatureBuilder, then:
          - scaled features -> MLP v6 (Torch)
          - raw features -> RF v6 (sklearn)

        Returns both predictions plus an ensemble safety_score.
        """

        # Build feature row in exact trained column order
        X_rf = self._build_features_df(
            latitude=latitude,
            longitude=longitude,
            country=country,
        )

        # MLP uses scaled features, matching training workflow
        X_scaled = self.scaler.transform(X_rf)

        # Torch MLP prediction
        with torch.no_grad():
            x_tensor = torch.tensor(np.asarray(X_scaled), dtype=torch.float32)
            mlp_score = float(self.mlp(x_tensor).detach().cpu().numpy()[0])

        # RF prediction
        rf_score = float(self.rf.predict(X_rf)[0])

        # Ensemble: simple average for now
        combined_score = float((mlp_score + rf_score) / 2.0)

        # Helpful disagreement metric for agent-side response logic
        model_spread = float(abs(mlp_score - rf_score))

        # Optional confidence heuristic from agreement
        if model_spread < 3.0:
            agreement_band = "high"
        elif model_spread < 7.0:
            agreement_band = "medium"
        else:
            agreement_band = "low"

        return {
            "safety_score": combined_score,
            "mlp_score_v6": mlp_score,
            "rf_score_v6": rf_score,
            "model_spread": model_spread,
            "agreement_band": agreement_band,
            "model_version": "v6_ensemble",
            "models_used": ["mlp_v6_torch", "rf_v6_sklearn"],
            "feature_count": len(self.feature_cols),
            "features_used": self.feature_cols,
            "input": {
                "latitude": float(latitude),
                "longitude": float(longitude),
                "country": country,
            },
        }

    def predict_with_features(
        self,
        latitude: float,
        longitude: float,
        country: str | None = None,
    ) -> dict[str, Any]:
        """
        Same as predict_score, but also returns the built feature values.
        Useful for debugging, agent explanations, and inspecting derived signals.
        """
        X_rf = self._build_features_df(
            latitude=latitude,
            longitude=longitude,
            country=country,
        )

        X_scaled = self.scaler.transform(X_rf)

        with torch.no_grad():
            x_tensor = torch.tensor(np.asarray(X_scaled), dtype=torch.float32)
            mlp_score = float(self.mlp(x_tensor).detach().cpu().numpy()[0])

        rf_score = float(self.rf.predict(X_rf)[0])
        combined_score = float((mlp_score + rf_score) / 2.0)
        model_spread = float(abs(mlp_score - rf_score))

        if model_spread < 3.0:
            agreement_band = "high"
        elif model_spread < 7.0:
            agreement_band = "medium"
        else:
            agreement_band = "low"

        return {
            "safety_score": combined_score,
            "mlp_score_v6": mlp_score,
            "rf_score_v6": rf_score,
            "model_spread": model_spread,
            "agreement_band": agreement_band,
            "model_version": "v6_ensemble",
            "models_used": ["mlp_v6_torch", "rf_v6_sklearn"],
            "feature_count": len(self.feature_cols),
            "features_used": self.feature_cols,
            "features": X_rf.iloc[0].to_dict(),
            "input": {
                "latitude": float(latitude),
                "longitude": float(longitude),
                "country": country,
            },
        }

    def predict_batch(
        self,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Batch prediction helper for multiple user queries.

        Each row should look like:
            {"latitude": 34.05, "longitude": -118.24, "country": "United States"}
        """
        outputs: list[dict[str, Any]] = []
        for row in rows:
            outputs.append(
                self.predict_score(
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    country=row.get("country"),
                )
            )
        return outputs
'''
from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import torch
import torch.nn as nn

from .feature_pipeline import SafetyFeaturePipeline


ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


class MLPRegressorTorch(nn.Module):
    def __init__(self, in_dim: int, hidden_dims: tuple[int, ...] = (128, 128), dropout: float = 0.2) -> None:
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


class SafetyPredictor:
    """
    Uses both:
      - Torch MLP v6 checkpoint: mlp_v6_best_torch.pt
      - sklearn RF v6: rf_v6.pkl

    Interface is unchanged: predict_score(lat, lon, country) returns
    a dict with per-model scores plus a combined safety_score.
    """

    def __init__(self, artifacts_dir: Path | None = None) -> None:
        self.artifacts_dir = artifacts_dir or ARTIFACTS_DIR
        self.pipeline = SafetyFeaturePipeline(self.artifacts_dir)
        self.feature_cols = self.pipeline.load_feature_columns()

        # Load both models
        self.mlp = self._load_mlp_model()
        self.mlp.eval()
        self.rf = self._load_rf_model()

    # ---------- Loading models ----------

    def _load_mlp_model(self) -> nn.Module:
        model_path = self.artifacts_dir / "mlp_v6_best_torch.pt"
        loaded = torch.load(model_path, map_location="cpu", weights_only=False)

        if isinstance(loaded, nn.Module):
            return loaded

        if isinstance(loaded, dict):
            state_dict = loaded.get("model_state_dict", loaded.get("state_dict"))
            config: dict[str, Any] = loaded.get("config", {})

            hidden_from_ckpt = config.get("hidden") or config.get("hidden_dims")
            if hidden_from_ckpt is None:
                hidden_dims = (128, 128)
            else:
                hidden_dims = tuple(hidden_from_ckpt)

            dropout = float(config.get("dropout", 0.2))

            model = MLPRegressorTorch(
                in_dim=len(self.feature_cols),
                hidden_dims=hidden_dims,
                dropout=dropout,
            )
            if state_dict is None:
                raise ValueError("Checkpoint dict does not contain model_state_dict or state_dict.")
            model.load_state_dict(state_dict)
            return model

        raise ValueError("Unsupported model checkpoint format for mlp_v6_best_torch.pt")

    def _load_rf_model(self) -> Any:
        model_path = self.artifacts_dir / "rf_v6.pkl"
        if not model_path.exists():
            raise FileNotFoundError(f"RandomForest artifact not found at {model_path}")
        return joblib.load(model_path)

    # ---------- Prediction ----------

    def predict_score(
        self,
        latitude: float,
        longitude: float,
        country: str | None = None,
    ) -> dict[str, Any]:
        """
        Build features via SafetyFeaturePipeline, then:
          - scaled features → MLP v6 (Torch)
          - raw feature cols → RF v6 (sklearn)
        Returns both predictions and a combined safety_score.
        """

        # Build full feature matrix from your existing pipeline
        X_full = self.pipeline.build_features(
            latitude=latitude,
            longitude=longitude,
            country=country,
        )

        # Defensive check: ensure RF sees same columns it was trained on
        missing_cols = [c for c in self.feature_cols if c not in X_full.columns]
        if missing_cols:
            raise ValueError(f"Missing expected feature columns for v6 models: {missing_cols}")

        # RF: unscaled features (as trained in v6_train)
        X_rf = X_full[self.feature_cols]

        # MLP: scaled features (pipeline scaling logic)
        X_scaled = self.pipeline.scale_features(X_full[self.feature_cols])

        # MLP prediction (Torch)
        with torch.no_grad():
            x_tensor = torch.tensor(np.asarray(X_scaled), dtype=torch.float32)
            mlp_score = float(self.mlp(x_tensor).detach().cpu().numpy()[0])

        # RF prediction (sklearn)
        rf_score = float(self.rf.predict(X_rf)[0])

        # Simple ensemble: mean of both
        combined_score = float((mlp_score + rf_score) / 2.0)

        return {
            "safety_score": combined_score,          # final score your app should use
            "mlp_score_v6": mlp_score,
            "rf_score_v6": rf_score,
            "model_version": "v6_ensemble",
            "models_used": ["mlp_v6_torch", "rf_v6_sklearn"],
            "feature_count": len(self.feature_cols),
            "features_used": self.feature_cols,
        }
    ------------------------------------------------------------
     above this line is current predictor using both MLP and RF
      
        below are other integrations we do not want to part with yet
            '''

''' 
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from .feature_pipeline import SafetyFeaturePipeline


ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


class MLPRegressorTorch(nn.Module):
    def __init__(self, in_dim: int, hidden_dims: tuple[int, ...] = (128, 128), dropout: float = 0.2) -> None:
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


class SafetyPredictor:
    def __init__(self, artifacts_dir: Path | None = None) -> None:
        self.artifacts_dir = artifacts_dir or ARTIFACTS_DIR
        self.pipeline = SafetyFeaturePipeline(self.artifacts_dir)
        self.feature_cols = self.pipeline.load_feature_columns()
        self.model = self._load_model()
        self.model.eval()

    def _load_model(self) -> nn.Module:
        model_path = self.artifacts_dir / "mlp_v6_best_torch.pt"

        loaded = torch.load(model_path, map_location="cpu", weights_only=False)

        if isinstance(loaded, nn.Module):
            return loaded

        if isinstance(loaded, dict):
            state_dict = loaded.get("model_state_dict", loaded.get("state_dict"))
            config: dict[str, Any] = loaded.get("config", {})

            # v6_128_128 stores config["hidden"] and config["dropout"]
            hidden_from_ckpt = config.get("hidden") or config.get("hidden_dims")
            if hidden_from_ckpt is None:
                hidden_dims = (128, 128)
            else:
                hidden_dims = tuple(hidden_from_ckpt)

            dropout = float(config.get("dropout", 0.2))

            model = MLPRegressorTorch(
                in_dim=len(self.feature_cols),
                hidden_dims=hidden_dims,
                dropout=dropout,
            )
            if state_dict is None:
                raise ValueError("Checkpoint dict does not contain model_state_dict or state_dict.")
            model.load_state_dict(state_dict)
            return model

        raise ValueError("Unsupported model checkpoint format for mlp_v6_best_torch.pt")

    def predict_score(
        self,
        latitude: float,
        longitude: float,
        country: str | None = None,
    ) -> dict[str, Any]:
        X = self.pipeline.build_features(
            latitude=latitude,
            longitude=longitude,
            country=country,
        )
        X_scaled = self.pipeline.scale_features(X)

        with torch.no_grad():
            x_tensor = torch.tensor(X_scaled, dtype=torch.float32)
            score = float(self.model(x_tensor).detach().cpu().numpy()[0])

        return {
            "safety_score": score,
            "model_version": "v6",
            "feature_count": len(self.feature_cols),
            "features_used": self.feature_cols,
        }

"""
If mlp_v6_best_torch.pt is just a raw state dict from a different training class, you will need to match the exact hidden layer sizes from training. That is normal for PyTorch inference unless you exported a full model or TorchScript artifact. Defining a dedicated inference model that mirrors training is a common approach.


"""

# app/models/safety/predictor.py
import joblib
import pandas as pd

from .v6_config import MLP_MODEL_PATH, RF_MODEL_PATH, SCALER_PATH
from .v6_features import FEATURE_COLS_V6


class SafetyV6Predictor:
    def __init__(self):
        self.mlp = joblib.load(MLP_MODEL_PATH)
        self.rf = joblib.load(RF_MODEL_PATH)
        self.scaler = joblib.load(SCALER_PATH)

    def _check_cols(self, df: pd.DataFrame) -> None:
        missing = [c for c in FEATURE_COLS_V6 if c not in df.columns]
        if missing:
            raise ValueError(f"Missing features for safety v6 model: {missing}")

    def predict_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        df must already have FEATURE_COLS_V6 (e.g. from feature_pipeline).
        Returns df with mlp_pred_v6 and rf_pred_v6 appended.
        """
        self._check_cols(df)
        X = df[FEATURE_COLS_V6].copy()
        X_scaled = self.scaler.transform(X)

        df = df.copy()
        df["mlp_pred_v6"] = self.mlp.predict(X_scaled)
        df["rf_pred_v6"] = self.rf.predict(X)
        return df

    def predict_row(self, row: pd.Series) -> dict:
        missing = [c for c in FEATURE_COLS_V6 if c not in row.index]
        if missing:
            raise ValueError(f"Missing features in row: {missing}")

        x = row[FEATURE_COLS_V6].to_frame().T
        x_scaled = self.scaler.transform(x)

        return {
            "mlp_pred_v6": float(self.mlp.predict(x_scaled)[0]),
            "rf_pred_v6": float(self.rf.predict(x)[0]),
        }

        '''