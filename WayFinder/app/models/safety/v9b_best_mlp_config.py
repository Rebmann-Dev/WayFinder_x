"""
v9b_best_mlp_config.py
Configuration for the v9b targeted Torch MLP safety model.
Single source of truth for artifact paths, model metadata, and feature schema.
"""
from __future__ import annotations

from pathlib import Path

import joblib

# ── Artifact directory ─────────────────────────────────────────────────────────
_SAFETY_DIR = Path(__file__).resolve().parent
V9B_ARTIFACT_DIR = _SAFETY_DIR / "artifacts" / "geo_safety_model_v9b_torch_mlp_targeted_2000max"

# ── File paths ─────────────────────────────────────────────────────────────────
V9B_STATE_DICT_PATH  = V9B_ARTIFACT_DIR / "v9b_best_mlp_state_dict.pt"
V9B_SCALER_PATH      = V9B_ARTIFACT_DIR / "v9b_best_mlp_scaler.joblib"
V9B_IMPUTER_PATH     = V9B_ARTIFACT_DIR / "v9b_best_mlp_imputer.joblib"
V9B_FEATURES_PATH    = V9B_ARTIFACT_DIR / "v9b_best_mlp_features.joblib"

# ── Model metadata ─────────────────────────────────────────────────────────────
V9B_MODEL_VERSION  = "v9b_torch_mlp"
V9B_HIDDEN_SIZES   = (256, 256)
V9B_DROPOUT        = 0.3
V9B_ACTIVATION     = "relu"
V9B_USE_BATCHNORM  = True

# ── Startup validation ─────────────────────────────────────────────────────────
def validate_artifacts() -> None:
    """Fail fast at startup if any artifact file is missing."""
    for path in (V9B_STATE_DICT_PATH, V9B_SCALER_PATH, V9B_IMPUTER_PATH, V9B_FEATURES_PATH):
        if not path.exists():
            raise FileNotFoundError(
                f"v9b artifact not found: {path}\n"
                f"Run scripts/rebuild_v9b_artifacts.py to regenerate."
            )

def load_v9b_features() -> list[str]:
    """Load the ordered feature column list saved at training time."""
    validate_artifacts()
    features = joblib.load(V9B_FEATURES_PATH)
    if isinstance(features, list):
        return features
    # joblib sometimes saves as numpy array
    return list(features)
