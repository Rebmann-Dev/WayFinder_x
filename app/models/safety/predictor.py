from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from .feature_pipeline import SafetyFeaturePipeline


ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


class GeoSafetyMLP(nn.Module):
    def __init__(self, input_dim: int, hidden_layers: list[int]) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        prev = input_dim

        for hidden in hidden_layers:
            layers.append(nn.Linear(prev, hidden))
            layers.append(nn.ReLU())
            prev = hidden

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

        loaded = torch.load(model_path, map_location="cpu")

        if isinstance(loaded, nn.Module):
            return loaded

        if isinstance(loaded, dict):
            state_dict = loaded.get("model_state_dict", loaded.get("state_dict"))
            config = loaded.get("config", {})
            hidden_layers = config.get("hidden_layers", [128, 128])

            model = GeoSafetyMLP(
                input_dim=len(self.feature_cols),
                hidden_layers=list(hidden_layers),
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