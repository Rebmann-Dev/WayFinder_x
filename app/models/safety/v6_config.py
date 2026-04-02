# app/models/safety/v6_config.py
from pathlib import Path

# repo root: ... / app / models / safety / v6_config.py → parents[2]
ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
COMPILED_DIR = DATA_DIR / "compiled_model_ready"

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

V6_TRAIN_TABLE = COMPILED_DIR / "MR_cities_worldpop_knn_macro_v5.csv"
TARGET_COL = "safety_index"

MLP_MODEL_PATH = ARTIFACTS_DIR / "mlp_v6.pkl"
RF_MODEL_PATH = ARTIFACTS_DIR / "rf_v6.pkl"
SCALER_PATH = ARTIFACTS_DIR / "scaler_v6.pkl"

METRICS_PATH = ARTIFACTS_DIR / "v6_model_metrics.csv"
FEATURE_COLUMNS_PATH = ARTIFACTS_DIR / "v6_feature_columns.txt"
TEST_PREDICTIONS_PATH = ARTIFACTS_DIR / "v6_test_predictions.csv"
RF_IMPORTANCE_PATH = ARTIFACTS_DIR / "v6_rf_feature_importance.csv"