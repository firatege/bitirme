"""Top-level feature-prep entry point for the Y-model.

Keeps strict causality under `causal=True` (used for val/test), allows centered
imputation under `causal=False` (train).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.worker.config import get_config
from services.worker.features.calendar import add_calendar
from services.worker.features.lags import build_lags_y
from services.worker.features.winsorize import rolling_impute


def prep_features_y(df_in: pd.DataFrame, causal: bool = False) -> pd.DataFrame:
    """Prepare Y-model features. Mirrors scripts/model_v3.py `prep_features_y` (line 218).

    Guaranteed columns: every name in WorkerConfig.features_y.
    """
    cfg = get_config()
    d = add_calendar(df_in)
    d = build_lags_y(d)

    for c in ("orders", "stock"):
        if c in d.columns:
            d[c] = rolling_impute(d[c], causal=causal)

    for c in ("orders_lag1", "orders_lag3", "stock_lag1", "stock_lag3", "y_lag1", "orders_ratio"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce").ffill().bfill().fillna(0.0)

    for f in cfg.features_y:
        if f not in d.columns:
            d[f] = 0.0

    return d.replace([np.inf, -np.inf], np.nan).fillna(0)


def mae_rmse_mape(y_true, y_pred):
    """Returns (MAE, RMSE, wMAPE).

    wMAPE = sum(|e|) / sum(y) * 100, computed over non-zero actual periods.
    Avoids the division-by-zero explosion of classic MAPE on intermittent demand.
    Field is still named 'mape' in schemas for API compatibility.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    from sklearn.metrics import mean_absolute_error
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(np.mean((y_pred - y_true) ** 2)))
    total_actual = float(np.sum(np.abs(y_true)))
    wmape = float(np.sum(np.abs(y_true - y_pred)) / total_actual * 100) if total_actual > 1e-9 else float("nan")
    return mae, rmse, wmape
