"""REFIT (retrain on train+val) + rollback comparison.

If REFIT's best-MAE on TEST (Full horizon) is worse than PRE's best by more than
`refit_rollback_eps`, the caller should keep PRE. Mirrors scripts/model_v3.py
`refit_models_on_full` (line 830) + rollback logic (lines 1220-1227).
"""
from __future__ import annotations

import pandas as pd

from services.worker.config import get_config
from services.worker.selection.y_search import optimize_rf_rocv, optimize_xgb_rocv


def refit_models_on_full(df_full: pd.DataFrame):
    rf, _, _ = optimize_rf_rocv(df_full)
    xgb, _, _ = optimize_xgb_rocv(df_full)
    return rf, xgb


def decide_phase(pre_best_mae: float, refit_best_mae: float) -> str:
    """'REFIT' if REFIT is not worse than PRE (within eps); otherwise 'PRE'."""
    cfg = get_config()
    if refit_best_mae > pre_best_mae * (1.0 + cfg.refit_rollback_eps):
        return "PRE"
    return "REFIT"
