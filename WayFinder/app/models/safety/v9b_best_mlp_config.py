"""
Configuration and path constants for the v9b TorchMLP safety model.
Artifacts live at: app/models/safety/artifacts/geo_safety_model_v9b_torch_mlp_targeted_2000max/
"""
from pathlib import Path

_SAFETY_DIR = Path(__file__).resolve().parent  # WayFinder/app/models/safety/
V9B_ARTIFACT_DIR = _SAFETY_DIR / "artifacts" / "geo_safety_model_v9b_torch_mlp_targeted_2000max"

V9B_FEATURE_FILE  = V9B_ARTIFACT_DIR / "v9b_best_mlp_features.joblib"
V9B_IMPUTER_FILE  = V9B_ARTIFACT_DIR / "v9b_best_mlp_imputer.joblib"
V9B_SCALER_FILE   = V9B_ARTIFACT_DIR / "v9b_best_mlp_scaler.joblib"
V9B_STATE_DICT    = V9B_ARTIFACT_DIR / "v9b_best_mlp_state_dict.pt"

# Model architecture hyperparameters (must match training)
V9B_HIDDEN_LAYERS = (256, 256)
V9B_DROPOUT       = 0.3
V9B_ACTIVATION    = "relu"
V9B_BATCH_NORM    = True
