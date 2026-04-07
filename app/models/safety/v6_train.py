# app/models/safety/v6_train.py
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.neural_network import MLPRegressor

from .v6_config import (
    ARTIFACTS_DIR,
    MLP_MODEL_PATH,
    RF_MODEL_PATH,
    SCALER_PATH,
    METRICS_PATH,
    FEATURE_COLUMNS_PATH,
    TEST_PREDICTIONS_PATH,
    RF_IMPORTANCE_PATH,
    TARGET_COL,
)
from .v6_data_loading import load_v6_data
from .v6_features import FEATURE_COLS_V6


def _ensure_dirs() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def _eval(y_true, y_pred) -> dict:
    mse = mean_squared_error(y_true, y_pred)
    rmse = float(mse ** 0.5)

    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": rmse,
        "r2": float(r2_score(y_true, y_pred)),
    }


def train_v6_models(random_state: int = 42) -> None:
    _ensure_dirs()
    data = load_v6_data(random_state=random_state)

    # ----- MLP v6 -----
    mlp = MLPRegressor(
        hidden_layer_sizes=(128, 64, 32),
        activation="relu",
        solver="adam",
        alpha=0.0005,
        learning_rate_init=0.001,
        max_iter=3000,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=50,
        random_state=random_state,
    )
    mlp.fit(data.X_train_scaled, data.y_train)

    y_train_pred_mlp = mlp.predict(data.X_train_scaled)
    y_test_pred_mlp = mlp.predict(data.X_test_scaled)

    mlp_train = _eval(data.y_train, y_train_pred_mlp)
    mlp_test = _eval(data.y_test, y_test_pred_mlp)
    mlp_train["n_iter"] = int(mlp.n_iter_)

    # ----- Random Forest v6 -----
    rf = RandomForestRegressor(
        n_estimators=500,
        max_depth=None,
        min_samples_split=4,
        min_samples_leaf=2,
        random_state=random_state,
        n_jobs=-1,
    )
    rf.fit(data.X_train, data.y_train)

    y_train_pred_rf = rf.predict(data.X_train)
    y_test_pred_rf = rf.predict(data.X_test)

    rf_train = _eval(data.y_train, y_train_pred_rf)
    rf_test = _eval(data.y_test, y_test_pred_rf)

    # ----- Test predictions table -----
    results = data.df.loc[data.idx_test, ["city", "country", TARGET_COL]].copy()
    results["mlp_pred_v6"] = y_test_pred_mlp
    results["mlp_abs_error_v6"] = (results[TARGET_COL] - results["mlp_pred_v6"]).abs()
    results["rf_pred_v6"] = y_test_pred_rf
    results["rf_abs_error_v6"] = (results[TARGET_COL] - results["rf_pred_v6"]).abs()
    results = results.sort_values("mlp_abs_error_v6").reset_index(drop=True)

    # ----- RF feature importance -----
    rf_importance = pd.DataFrame(
        {"feature": FEATURE_COLS_V6, "importance": rf.feature_importances_}
    ).sort_values("importance", ascending=False)

    # ----- Save artifacts -----
    joblib.dump(mlp, MLP_MODEL_PATH)
    joblib.dump(rf, RF_MODEL_PATH)
    joblib.dump(data.scaler, SCALER_PATH)

    metrics = [
        {"model": "MLPRegressor_v6", "split": "train", **mlp_train},
        {"model": "MLPRegressor_v6", "split": "test", **mlp_test},
        {"model": "RandomForestRegressor_v6", "split": "train", **rf_train},
        {"model": "RandomForestRegressor_v6", "split": "test", **rf_test},
    ]
    pd.DataFrame(metrics).to_csv(METRICS_PATH, index=False)

    with open(FEATURE_COLUMNS_PATH, "w", encoding="utf-8") as f:
        for col in FEATURE_COLS_V6:
            f.write(col + "\n")

    results.to_csv(TEST_PREDICTIONS_PATH, index=False)
    rf_importance.to_csv(RF_IMPORTANCE_PATH, index=False)

    print(json.dumps({"mlp": {"train": mlp_train, "test": mlp_test},
                      "rf": {"train": rf_train, "test": rf_test}}, indent=2))


if __name__ == "__main__":
    train_v6_models()