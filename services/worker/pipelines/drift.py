"""Drift gate — cheap cached-vs-fresh MAE comparison on the newest VAL window.

Used by Rust before dispatching to /forecast/warm; if drift is detected, Rust
re-dispatches to /forecast/cold instead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.worker.config import get_config
from services.worker.features.calendar import ensure_ms_freq
from services.worker.features.pipeline import mae_rmse_mape, prep_features_y
from services.worker.forecasting.exog import build_exog_by_method, build_hybrid_exog
from services.worker.forecasting.recursive import recursive_forward_predict_y
from services.worker.io.blobs import load_blob
from services.worker.schemas.requests import DriftCheckRequest
from services.worker.schemas.responses import DriftCheckResult


def run_drift_check(request: DriftCheckRequest) -> DriftCheckResult:
    cfg = get_config()
    cached = request.cached_spec

    df = pd.DataFrame(
        [
            {"ds": pd.Timestamp(r.ds), "y": r.y, "orders": r.orders, "stock": r.stock}
            for r in request.panel_rows
        ]
    )
    d = ensure_ms_freq(df)
    mask_train = d["ds"] < cfg.val_start
    train_df = prep_features_y(d.loc[mask_train].copy(), causal=False)
    val_df = prep_features_y(d.loc[(d["ds"] >= cfg.val_start) & (d["ds"] <= cfg.val_end)].copy(), causal=True)
    if val_df.empty:
        return DriftCheckResult(drift_triggered=False, new_mae=0.0, cached_mae=0.0, threshold=cfg.drift_eps)

    # Load the cached winning Y model (RF or XGB blob).
    variant = cached.winning_y_variant
    cached_by_slot = {m.model_slot: m for m in cached.models}
    rf_slot = "rf_y_refit" if cached.winning_phase == "REFIT" else "rf_y_pre"
    rf_ref = cached_by_slot.get(rf_slot) or cached_by_slot.get("rf_y_pre")
    if rf_ref is None:
        return DriftCheckResult(drift_triggered=True, new_mae=0.0, cached_mae=0.0, threshold=cfg.drift_eps)
    rf_blob = load_blob(rf_ref.blob_uri)
    rf_model = rf_blob["model"] if isinstance(rf_blob, dict) else rf_blob

    # Build the cached-winning EXOG over the VAL window using cached per-column choices.
    exog_map = {s.column_target: s.chosen_method for s in cached.exog_selection}
    if cached.winning_exog.startswith("Hybrid[") and exog_map:
        ex_tbl, _ = build_hybrid_exog(d, cfg.val_start, cfg.val_end, cfg.val_start, exog_map)
    else:
        ex_tbl = build_exog_by_method(
            d, cfg.val_start, cfg.val_end, cfg.val_start, cached.winning_exog
        ).forecast

    hist_for_val = train_df[["ds", "y", "orders", "stock", "month", "year"]].copy()
    preds, _ = recursive_forward_predict_y(rf_model, hist_for_val, ex_tbl, cfg.val_start, cfg.val_end)
    join = val_df[["ds", "y"]].merge(preds, on="ds", how="left")
    new_mae, _, _ = mae_rmse_mape(join["y"].values, join["yhat"].values)

    # The cached MAE we're comparing to — the winning MAE stored in the cached spec
    # (or the residuals' absolute mean as a fallback).
    cached_mae = 0.0
    if cached.val_residuals:
        for r in cached.val_residuals:
            if r.exog == cached.winning_exog and r.y_variant == variant:
                arr = np.asarray(r.residuals, dtype=float)
                cached_mae = float(np.mean(np.abs(arr))) if arr.size else 0.0
                break

    threshold = cfg.drift_eps
    drift = (cached_mae > 0 and new_mae > cached_mae * (1.0 + threshold))
    return DriftCheckResult(
        drift_triggered=bool(drift), new_mae=float(new_mae),
        cached_mae=float(cached_mae), threshold=float(threshold),
    )
