"""Grid-search ROCV for the Y-model (RF and XGB)."""
from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

from services.worker.config import get_config
from services.worker.models.y_rf import YRandomForest
from services.worker.models.y_xgb import YXGBoost, HAVE_XGB
from services.worker.selection.rocv import rolling_origin_splits


RF_GRID_FAST = {
    "n_estimators": [300],
    "max_depth": [8],
    "min_samples_split": [2],
    "min_samples_leaf": [1],
}
RF_GRID_FULL = {
    "n_estimators": [400, 700],
    "max_depth": [None, 8, 12],
    "min_samples_split": [2, 5],
    "min_samples_leaf": [1, 2],
}

XGB_GRID_FAST = {
    "n_estimators": [400],
    "learning_rate": [0.08],
    "max_depth": [3],
    "subsample": [0.9],
    "colsample_bytree": [0.9],
    "reg_lambda": [1.2],
}
XGB_GRID_FULL = {
    "n_estimators": [500, 800],
    "learning_rate": [0.05, 0.1],
    "max_depth": [3, 4],
    "subsample": [0.8, 1.0],
    "colsample_bytree": [0.8, 1.0],
    "reg_lambda": [1.0, 2.0],
}


def _iter_params(grid: dict):
    keys = list(grid.keys())
    for v in product(*(grid[k] for k in keys)):
        yield dict(zip(keys, v))


def optimize_rf_rocv(df_tv: pd.DataFrame) -> tuple[YRandomForest, dict, float]:
    cfg = get_config()
    feats = list(cfg.features_y)
    grid = RF_GRID_FAST if cfg.fast_mode else RF_GRID_FULL
    best, score = None, np.inf
    for p in _iter_params(grid):
        maes = []
        for tr, va in rolling_origin_splits(df_tv, 3, 24):
            mdl = YRandomForest.fit(tr[feats], tr["y"].to_numpy(), p)
            pr = mdl.predict(va[feats])
            maes.append(mean_absolute_error(va["y"], pr))
        sc = float(np.mean(maes)) if maes else np.inf
        if sc < score:
            score, best = sc, p
    final = YRandomForest.fit(df_tv[feats], df_tv["y"].to_numpy(), best or {})
    return final, (best or {}), float(score)


def optimize_xgb_rocv(df_tv: pd.DataFrame) -> tuple[YXGBoost | None, dict, float]:
    if not HAVE_XGB:
        return None, {}, np.inf
    cfg = get_config()
    feats = list(cfg.features_y)
    grid = XGB_GRID_FAST if cfg.fast_mode else XGB_GRID_FULL
    best, score = None, np.inf
    for p in _iter_params(grid):
        maes = []
        for tr, va in rolling_origin_splits(df_tv, 3, 24):
            mdl = YXGBoost.fit(tr[feats], tr["y"].to_numpy(), p)
            pr = mdl.predict(va[feats])
            maes.append(mean_absolute_error(va["y"], pr))
        sc = float(np.mean(maes)) if maes else np.inf
        if sc < score:
            score, best = sc, p
    final = YXGBoost.fit(df_tv[feats], df_tv["y"].to_numpy(), best or {})
    return final, (best or {}), float(score)
