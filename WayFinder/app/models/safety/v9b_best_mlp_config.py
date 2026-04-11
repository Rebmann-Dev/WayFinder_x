"""
Configuration and path constants for the v9b TorchMLP safety model.
Artifacts live at: app/models/safety/artifacts/geo_safety_model_v9b_torch_mlp_targeted_2000max/
"""
from __future__ import annotations
from pathlib import Path
import joblib

_SAFETY_DIR = Path(__file__).resolve().parent  # WayFinder/app/models/safety/
V9B_ARTIFACT_DIR = _SAFETY_DIR / "artifacts" / "geo_safety_model_v9b_torch_mlp_targeted_2000max"

# File paths (canonical names used by training notebook)
V9B_FEATURE_FILE  = V9B_ARTIFACT_DIR / "v9b_best_mlp_features.joblib"
V9B_IMPUTER_FILE  = V9B_ARTIFACT_DIR / "v9b_best_mlp_imputer.joblib"
V9B_SCALER_FILE   = V9B_ARTIFACT_DIR / "v9b_best_mlp_scaler.joblib"
V9B_STATE_DICT    = V9B_ARTIFACT_DIR / "v9b_best_mlp_state_dict.pt"

# Aliases expected by predictor.py
V9B_STATE_DICT_PATH = V9B_STATE_DICT
V9B_SCALER_PATH     = V9B_SCALER_FILE
V9B_IMPUTER_PATH    = V9B_IMPUTER_FILE
V9B_FEATURE_PATH    = V9B_FEATURE_FILE

# Model metadata
V9B_MODEL_VERSION = "v9b_torch_mlp_targeted_2000max"

# Architecture hyperparameters (must match training)
V9B_HIDDEN_LAYERS  = (256, 256)
V9B_HIDDEN_SIZES   = V9B_HIDDEN_LAYERS   # alias
V9B_DROPOUT        = 0.3
V9B_ACTIVATION     = "relu"
V9B_BATCH_NORM     = True
V9B_USE_BATCHNORM  = V9B_BATCH_NORM      # alias


def load_v9b_features() -> list[str]:
    """Load the list of feature column names used by v9b."""
    if not V9B_FEATURE_FILE.exists():
        raise FileNotFoundError(
            f"v9b feature list not found at {V9B_FEATURE_FILE}. "
            "Check that artifacts are present in app/models/safety/artifacts/"
        )
    return joblib.load(V9B_FEATURE_FILE)


def validate_artifacts() -> bool:
    """Return True if all four v9b artifact files exist on disk."""
    files = [V9B_STATE_DICT, V9B_SCALER_FILE, V9B_IMPUTER_FILE, V9B_FEATURE_FILE]
    missing = [str(f) for f in files if not f.exists()]
    if missing:
        import logging
        logging.getLogger(__name__).warning(
            "v9b artifacts missing: %s", missing
        )
        return False
    return True
