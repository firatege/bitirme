"""Warm-path pipeline — reuse cached hyperparameters + winning EXOG method choices.

Skips ROCV / probe / escalate / choose_best_exog_per_var; refits the winning Y-model
family on the extended train+val window with fixed hyperparameters, then forecasts.

Mode values: 'warm' when VAL residuals from cache are reused verbatim,
'warm_with_refit' when refit happens against the new data window.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from services.worker.config import get_config
from services.worker.features.calendar import ensure_ms_freq
from services.worker.features.pipeline import mae_rmse_mape, prep_features_y
from services.worker.forecasting.bootstrap import add_bootstrap_intervals
from services.worker.forecasting.exog import build_exog_by_method, build_hybrid_exog
from services.worker.forecasting.recursive import recursive_forward_predict_y
from services.worker.io.blobs import blob_path, save_blob, uri_for
from services.worker.models.y_rf import YRandomForest
from services.worker.models.y_xgb import YXGBoost, HAVE_XGB
from services.worker.oms.policy import infer_starting_stock, round_moq_lot
from services.worker.oms.stockout import cum_demand_quantile, stockout_probability
from services.worker.schemas.requests import ForecastWarmRequest
from services.worker.schemas.responses import (
    CombinationRow,
    ExogSelectionRow,
    ForecastResult,
    ModelRow,
    RecommendationRow,
    ValResidualRow,
    WinningCombo,
)


def _panel_to_df(request: ForecastWarmRequest) -> pd.DataFrame:
    rows = [
        {"ds": pd.Timestamp(r.ds), "y": r.y, "orders": r.orders, "stock": r.stock}
        for r in request.panel_rows
    ]
    return ensure_ms_freq(pd.DataFrame(rows))


def run_warm(request: ForecastWarmRequest) -> ForecastResult:
    cfg = get_config()
    cached = request.cached_spec

    d = _panel_to_df(request)
    mask_train = d["ds"] < cfg.val_start
    mask_val = (d["ds"] >= cfg.val_start) & (d["ds"] <= cfg.val_end)
    train_df = prep_features_y(d.loc[mask_train].copy(), causal=False)
    val_df = prep_features_y(d.loc[mask_val].copy(), causal=True)
    trainval_df = pd.concat([train_df, val_df], ignore_index=True)

    blob_dir = Path(request.blob_dir)
    models_out: list[ModelRow] = []

    # Find cached hyperparams for winning Y model
    cached_by_slot = {m.model_slot: m for m in cached.models}
    winning_phase = cached.winning_phase  # 'PRE' or 'REFIT'
    # Refit RF + XGB using cached hyperparams on the extended (train+val) data.
    rf_slot = "rf_y_refit" if winning_phase == "REFIT" else "rf_y_pre"
    rf_cached = cached_by_slot.get(rf_slot) or cached_by_slot.get("rf_y_pre")
    rf_params = rf_cached.hyperparams if rf_cached else {}
    t0 = time.time()
    feats = list(cfg.features_y)
    rf_fresh = YRandomForest.fit(trainval_df[feats], trainval_df["y"].to_numpy(), rf_params)
    rf_secs = time.time() - t0
    rf_path = blob_path(blob_dir.parent.parent, request.sku, request.run_id, rf_slot)
    rf_fresh.save(rf_path)
    models_out.append(ModelRow(
        model_slot=rf_slot, column_target="y",
        hyperparams=rf_params, blob_uri=uri_for(rf_path), fit_seconds=rf_secs,
    ))

    xgb_fresh = None
    if HAVE_XGB:
        xgb_slot = "xgb_y_refit" if winning_phase == "REFIT" else "xgb_y_pre"
        xgb_cached = cached_by_slot.get(xgb_slot) or cached_by_slot.get("xgb_y_pre")
        if xgb_cached is not None:
            xgb_params = xgb_cached.hyperparams
            t0 = time.time()
            xgb_fresh = YXGBoost.fit(trainval_df[feats], trainval_df["y"].to_numpy(), xgb_params)
            xgb_secs = time.time() - t0
            xgb_path = blob_path(blob_dir.parent.parent, request.sku, request.run_id, xgb_slot)
            xgb_fresh.save(xgb_path)
            models_out.append(ModelRow(
                model_slot=xgb_slot, column_target="y",
                hyperparams=xgb_params, blob_uri=uri_for(xgb_path), fit_seconds=xgb_secs,
            ))

    # Build the winning EXOG table for TEST using the cached per-column method map.
    exog_map: dict[str, str] = {s.column_target: s.chosen_method for s in cached.exog_selection}
    winning_exog = cached.winning_exog
    if winning_exog.startswith("Hybrid[") and exog_map:
        test_full, _ = build_hybrid_exog(
            d, cfg.test_start, cfg.test_end, cfg.test_start, exog_map
        )
        test_short, _ = build_hybrid_exog(
            d, cfg.test_start, cfg.test_end_short, cfg.test_start, exog_map
        )
    else:
        test_full = build_exog_by_method(
            d, cfg.test_start, cfg.test_end, cfg.test_start, winning_exog
        ).forecast
        test_short = build_exog_by_method(
            d, cfg.test_start, cfg.test_end_short, cfg.test_start, winning_exog
        ).forecast

    # Predict the winning variant on both horizons.
    hist_min = trainval_df[["ds", "y", "orders", "stock", "month", "year"]].copy()
    variant = cached.winning_y_variant
    w_rf = cached.winning_w_rf
    w_xgb = cached.winning_w_xgb

    def _predict(ex_tbl: pd.DataFrame):
        if variant == "RF":
            p, _ = recursive_forward_predict_y(
                rf_fresh, hist_min.copy(), ex_tbl, cfg.test_start, ex_tbl["ds"].max()
            )
            return p
        if variant == "XGB" and HAVE_XGB and xgb_fresh is not None:
            p, _ = recursive_forward_predict_y(
                xgb_fresh, hist_min.copy(), ex_tbl, cfg.test_start, ex_tbl["ds"].max()
            )
            return p
        # Y-ENS
        prf, _ = recursive_forward_predict_y(
            rf_fresh, hist_min.copy(), ex_tbl, cfg.test_start, ex_tbl["ds"].max()
        )
        if HAVE_XGB and xgb_fresh is not None:
            pxg, _ = recursive_forward_predict_y(
                xgb_fresh, hist_min.copy(), ex_tbl, cfg.test_start, ex_tbl["ds"].max()
            )
            p = prf.merge(pxg, on="ds", suffixes=("_rf", "_xgb"))
            p["yhat"] = (w_rf or 0.5) * p["yhat_rf"] + (w_xgb or 0.5) * p["yhat_xgb"]
            return p[["ds", "yhat"]]
        return prf

    # Bootstrap residuals come from cache.
    resid_rows = [r for r in cached.val_residuals if r.exog == winning_exog and r.y_variant == variant]
    residuals = np.asarray(resid_rows[0].residuals, dtype=float) if resid_rows else np.array([])

    truth_full = d[(d["ds"] >= cfg.test_start) & (d["ds"] <= cfg.test_end)][["ds", "y"]]
    truth_short = d[(d["ds"] >= cfg.test_start) & (d["ds"] <= cfg.test_end_short)][["ds", "y"]]
    combinations: list[CombinationRow] = []
    per_combo_preds: dict[tuple, tuple[pd.DataFrame, np.ndarray]] = {}
    start_stock = infer_starting_stock(d, cfg.test_start, request.params_row.starting_stock_override)

    for horizon_name, end_ds, ex_tbl, truth in (
        ("Full", cfg.test_end, test_full, truth_full),
        ("Short3", cfg.test_end_short, test_short, truth_short),
    ):
        preds = _predict(ex_tbl)
        preds_pi, sims = add_bootstrap_intervals(preds, residuals)
        eval_df = truth.merge(preds_pi, on="ds", how="left")
        mae, rmse, mape = mae_rmse_mape(eval_df["y"], eval_df["yhat"])
        p3, p6, e_t = stockout_probability(start_stock, sims)
        combinations.append(CombinationRow(
            horizon=horizon_name, exog=winning_exog, y_variant=variant, phase=winning_phase,
            mae=float(mae), rmse=float(rmse), mape=float(mape),
            w_rf=(float(w_rf) if variant == "Y-ENS" and w_rf is not None else None),
            w_xgb=(float(w_xgb) if variant == "Y-ENS" and w_xgb is not None else None),
            p_stockout_3m=float(p3), p_stockout_6m=float(p6),
            e_t_stockout_mo=(float(e_t) if np.isfinite(e_t) else None),
        ))
        per_combo_preds[(horizon_name, winning_exog, variant, winning_phase)] = (preds_pi, sims)

    full_row = combinations[0]
    winning = WinningCombo(
        horizon=full_row.horizon, exog=full_row.exog, y_variant=full_row.y_variant,
        phase=full_row.phase, mae=full_row.mae, rmse=full_row.rmse, mape=full_row.mape,
        w_rf=full_row.w_rf, w_xgb=full_row.w_xgb,
        p_stockout_3m=full_row.p_stockout_3m, p_stockout_6m=full_row.p_stockout_6m,
        e_t_stockout_mo=full_row.e_t_stockout_mo,
    )

    _, sims_best = per_combo_preds[(full_row.horizon, full_row.exog, full_row.y_variant, full_row.phase)]
    params = request.params_row
    cum_q = cum_demand_quantile(sims_best, int(params.h_cover), float(params.q_target))
    order_qty_raw = float(cum_q - start_stock)
    order_qty_rounded = round_moq_lot(order_qty_raw, params.moq, params.lot_size)
    recommendation = RecommendationRow(
        starting_stock=float(start_stock),
        t_check=int(params.t_check), h_cover=int(params.h_cover),
        q_target=float(params.q_target), moq=float(params.moq), lot_size=float(params.lot_size),
        cum_demand_q=float(cum_q),
        order_qty_raw=float(order_qty_raw),
        order_qty_rounded=float(order_qty_rounded),
    )

    # Pass through the cached per-column exog selection so Rust can re-affirm it.
    exog_selection_rows = [
        ExogSelectionRow(column_target=s.column_target, chosen_method=s.chosen_method, val_mae=s.val_mae)
        for s in cached.exog_selection
    ]
    val_residuals_rows = [
        ValResidualRow(exog=r.exog, y_variant=r.y_variant, residuals=list(r.residuals))
        for r in cached.val_residuals
    ]

    return ForecastResult(
        sku=request.sku, run_id=request.run_id, mode="warm_with_refit",
        winning=winning, combinations=combinations, models=models_out,
        exog_selection=exog_selection_rows, val_residuals=val_residuals_rows,
        recommendation=recommendation,
    )
