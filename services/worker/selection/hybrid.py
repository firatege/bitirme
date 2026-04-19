"""Per-variable EXOG selection (Hybrid) — pick best method per (orders, stock) on VAL.

Mirrors scripts/model_v3.py `choose_best_exog_per_var` (line 928).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.worker.config import get_config
from services.worker.features.pipeline import mae_rmse_mape
from services.worker.forecasting.exog import build_exog_by_method


def val_mae_exog_for_col(
    d: pd.DataFrame, method: str, col: str, val_start: pd.Timestamp, val_end: pd.Timestamp
) -> float:
    """MAE on VAL for `col` forecasted by `method`. Matches the intent of the
    reference's `val_mae_exog_for_col` (line 909) — dead-code attempts in the reference
    are ignored; this is the clean version."""
    try:
        ex = build_exog_by_method(d, val_start, val_end, val_start, method)
    except Exception:
        return np.inf
    truth = d[(d["ds"] >= val_start) & (d["ds"] <= val_end)][["ds", col]]
    pred_merged = truth.merge(ex.forecast[["ds", col]], on="ds", how="left",
                              suffixes=("_truth", "_pred"))
    true = pd.to_numeric(pred_merged[f"{col}_truth"], errors="coerce").to_numpy()
    pred = pd.to_numeric(pred_merged[f"{col}_pred"], errors="coerce").to_numpy()
    pred = np.nan_to_num(pred, nan=0.0)
    return mae_rmse_mape(true, pred)[0]


def choose_best_exog_per_var(
    candidates: list[str],
    d: pd.DataFrame,
    val_start: pd.Timestamp,
    val_end: pd.Timestamp,
) -> dict[str, str]:
    """For each of {orders, stock}, pick the method with the lowest VAL MAE on that
    column. Returns {"orders": method, "stock": method}."""
    cfg = get_config()
    allowed_global = set(cfg.exog_methods_enabled_global) | {"ML-Exog RF", "ML-Exog XGB"}
    best: dict[str, str] = {}
    for col in ("orders", "stock"):
        scores: list[tuple[float, str]] = []
        for m in candidates:
            if m == "Intermittent":
                continue
            if m not in allowed_global:
                continue
            try:
                mae = val_mae_exog_for_col(d, m, col, val_start, val_end)
            except Exception:
                mae = np.inf
            scores.append((mae, m))
        scores.sort(key=lambda x: (x[0], x[1]))
        best[col] = scores[0][1] if scores else "ETS"
    return best
