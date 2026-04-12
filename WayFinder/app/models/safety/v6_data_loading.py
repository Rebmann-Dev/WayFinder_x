# app/models/safety/v6_data_loading.py
from dataclasses import dataclass
from typing import Any

import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from .v6_config import V6_TRAIN_TABLE, TARGET_COL
from .v6_features import FEATURE_COLS_V6


@dataclass
class V6Data:
    df: pd.DataFrame
    X_train: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_test: pd.Series
    idx_train: pd.Index
    idx_test: pd.Index
    scaler: StandardScaler
    X_train_scaled: Any
    X_test_scaled: Any


def load_v6_data(test_size: float = 0.2, random_state: int = 42) -> V6Data:
    df = pd.read_csv(V6_TRAIN_TABLE)

    missing = [c for c in FEATURE_COLS_V6 if c not in df.columns]
    if missing:
        raise ValueError(f"Missing v6 feature columns in train table: {missing}")

    if TARGET_COL not in df.columns:
        raise ValueError(f"Target column '{TARGET_COL}' not found in train table")

    df = df.dropna(subset=[TARGET_COL]).reset_index(drop=True)

    if df[FEATURE_COLS_V6].isna().any().any():
        bad = df[FEATURE_COLS_V6].isna().sum()
        bad = bad[bad > 0]
        raise ValueError(f"Unexpected NaNs in v6 features: {bad.to_dict()}")

    X = df[FEATURE_COLS_V6].copy()
    y = df[TARGET_COL].copy()

    X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
        X, y, df.index, test_size=test_size, random_state=random_state
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    return V6Data(
        df=df,
        X_train=X_train,
        X_test=X_test,
        y_train=y_train,
        y_test=y_test,
        idx_train=idx_train,
        idx_test=idx_test,
        scaler=scaler,
        X_train_scaled=X_train_scaled,
        X_test_scaled=X_test_scaled,
    )