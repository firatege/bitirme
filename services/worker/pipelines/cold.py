"""Cold-path pipeline — full ROCV + probe + escalate + Hybrid + REFIT, then persist to
blob store. Composes every module under services.worker.* and produces a ForecastResult.

This is the rewrite of scripts/model_v3.py `run_for_sku` (line 983). No imports from
`scripts/` — this pipeline is self-contained.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from services.worker.config import get_config
from services.worker.features.calendar import ensure_ms_freq
from services.worker.features.pipeline import mae_rmse_mape, prep_features_y
from services.worker.forecasting.bootstrap import add_bootstrap_intervals
from services.worker.forecasting.exog import build_exog_by_method, build_hybrid_exog
from services.worker.forecasting.recursive import (
    recursive_forward_predict_y,
    recursive_predict_for_val,
    y_ensemble_weights,
)
from services.worker.forecasting.refit import decide_phase, refit_models_on_full
from services.worker.io.blobs import blob_dir_for, blob_path, save_blob, uri_for
from services.worker.models.intermittent import (
    predict_intermittent,
    select_intermittent,
)
from services.worker.models.y_xgb import HAVE_XGB
from services.worker.oms.policy import infer_starting_stock, round_moq_lot
from services.worker.oms.stockout import cum_demand_quantile, stockout_probability
from services.worker.schemas.requests import ForecastColdRequest
from services.worker.schemas.responses import (
    CombinationRow,
    ExogSelectionRow,
    ForecastResult,
    ModelRow,
    RecommendationRow,
    ValResidualRow,
    WinningCombo,
)
from services.worker.selection.baselines import baseline_val_mae
from services.worker.selection.hybrid import choose_best_exog_per_var
from services.worker.selection.probe_escalate import (
    build_escalate_list,
    build_probe_list,
    should_escalate,
)
from services.worker.selection.y_search import optimize_rf_rocv, optimize_xgb_rocv


def _panel_to_df(request: ForecastColdRequest) -> pd.DataFrame:
    rows = [
        {"ds": pd.Timestamp(r.ds), "y": r.y, "orders": r.orders, "stock": r.stock}
        for r in request.panel_rows
    ]
    df = pd.DataFrame(rows)
    return ensure_ms_freq(df)


def run_cold(request: ForecastColdRequest, critical_skus: set[str] | None = None) -> ForecastResult:
    cfg = get_config()
    critical_skus = critical_skus or set()

    d = _panel_to_df(request)
    mask_train = d["ds"] < cfg.val_start
    mask_val = (d["ds"] >= cfg.val_start) & (d["ds"] <= cfg.val_end)

    train_df = prep_features_y(d.loc[mask_train].copy(), causal=False)
    val_df = prep_features_y(d.loc[mask_val].copy(), causal=True)
    trainval_df = pd.concat([train_df, val_df], ignore_index=True)

    blob_dir = Path(request.blob_dir)
    models_out: list[ModelRow] = []

    # --- Y-models (PRE) ---
    t0 = time.time()
    rf_model, rf_params, _ = optimize_rf_rocv(trainval_df)
    rf_secs = time.time() - t0
    rf_path = blob_path(blob_dir.parent.parent, request.sku, request.run_id, "rf_y_pre")
    rf_model.save(rf_path)
    models_out.append(ModelRow(
        model_slot="rf_y_pre", column_target="y",
        hyperparams=rf_params, blob_uri=uri_for(rf_path), fit_seconds=rf_secs,
    ))

    xgb_model = None
    if HAVE_XGB:
        t0 = time.time()
        xgb_model, xgb_params, _ = optimize_xgb_rocv(trainval_df)
        xgb_secs = time.time() - t0
        xgb_path = blob_path(blob_dir.parent.parent, request.sku, request.run_id, "xgb_y_pre")
        if xgb_model is not None:
            xgb_model.save(xgb_path)
            models_out.append(ModelRow(
                model_slot="xgb_y_pre", column_target="y",
                hyperparams=xgb_params, blob_uri=uri_for(xgb_path), fit_seconds=xgb_secs,
            ))

    # --- Probe → Escalate on VAL ---
    base_mae = baseline_val_mae(d, cfg.val_start, cfg.val_end, cfg.baseline_kind)
    probe_methods = build_probe_list(d)
    exog_val: dict[str, pd.DataFrame] = {}
    val_rep: dict[str, dict] = {}

    hist_for_val = train_df[["ds", "y", "orders", "stock", "month", "year"]].copy()

    basic_methods = [m for m in probe_methods if m != "Intermittent"]
    for m in basic_methods:
        fitted = build_exog_by_method(d, cfg.val_start, cfg.val_end, cfg.val_start, m)
        exog_val[m] = fitted.forecast
        val_rep[m] = recursive_predict_for_val(
            fitted.forecast, rf_model, xgb_model, hist_for_val, val_df,
            cfg.val_start, cfg.val_end, HAVE_XGB,
        )

    probe_best = min((r["mae_ens"] for r in val_rep.values()), default=np.inf)
    if should_escalate(probe_best, base_mae):
        for m in build_escalate_list(d, request.sku, critical_skus):
            if m not in exog_val:
                fitted = build_exog_by_method(d, cfg.val_start, cfg.val_end, cfg.val_start, m)
                exog_val[m] = fitted.forecast
                val_rep[m] = recursive_predict_for_val(
                    fitted.forecast, rf_model, xgb_model, hist_for_val, val_df,
                    cfg.val_start, cfg.val_end, HAVE_XGB,
                )
                basic_methods.append(m)

    # --- Hybrid (per-variable best) ---
    hybrid_tag: str | None = None
    exog_selection_rows: list[ExogSelectionRow] = []
    if cfg.exog_per_var_selection and basic_methods:
        chosen = choose_best_exog_per_var(basic_methods, d, cfg.val_start, cfg.val_end)
        ex_h_val, hybrid_tag = build_hybrid_exog(
            d, cfg.val_start, cfg.val_end, cfg.val_start, chosen
        )
        exog_val[hybrid_tag] = ex_h_val
        val_rep[hybrid_tag] = recursive_predict_for_val(
            ex_h_val, rf_model, xgb_model, hist_for_val, val_df,
            cfg.val_start, cfg.val_end, HAVE_XGB,
        )
        # Capture per-column selection with VAL MAE for DB
        from services.worker.selection.hybrid import val_mae_exog_for_col
        for col in ("orders", "stock"):
            m = chosen[col]
            mae_val = val_mae_exog_for_col(d, m, col, cfg.val_start, cfg.val_end)
            exog_selection_rows.append(
                ExogSelectionRow(column_target=col, chosen_method=m, val_mae=float(mae_val))
            )

    # --- Build TEST EXOG tables per active method ---
    exog_test_full: dict[str, pd.DataFrame] = {}
    exog_test_short: dict[str, pd.DataFrame] = {}
    for m in basic_methods:
        f = build_exog_by_method(d, cfg.test_start, cfg.test_end, cfg.test_start, m)
        s = build_exog_by_method(d, cfg.test_start, cfg.test_end_short, cfg.test_start, m)
        exog_test_full[m] = f.forecast
        exog_test_short[m] = s.forecast
    if hybrid_tag:
        chosen = choose_best_exog_per_var(basic_methods, d, cfg.val_start, cfg.val_end)
        f_h, tag_h = build_hybrid_exog(d, cfg.test_start, cfg.test_end, cfg.test_start, chosen)
        s_h, _ = build_hybrid_exog(d, cfg.test_start, cfg.test_end_short, cfg.test_start, chosen)
        exog_test_full[hybrid_tag] = f_h
        exog_test_short[hybrid_tag] = s_h

    # --- Per-combination TEST evaluation (PRE) ---
    hist_min = trainval_df[["ds", "y", "orders", "stock", "month", "year"]].copy()
    variants: list[str] = ["RF", "XGB", "Y-ENS"] if HAVE_XGB else ["RF"]
    combinations: list[CombinationRow] = []
    val_residuals_rows: list[ValResidualRow] = []
    per_combo_preds: dict[tuple, tuple[pd.DataFrame, np.ndarray]] = {}

    truth_full = d[(d["ds"] >= cfg.test_start) & (d["ds"] <= cfg.test_end)][["ds", "y"]]
    truth_short = d[(d["ds"] >= cfg.test_start) & (d["ds"] <= cfg.test_end_short)][["ds", "y"]]
    start_stock = infer_starting_stock(d, cfg.test_start, request.params_row.starting_stock_override)

    def _predict_variant(ex_tbl: pd.DataFrame, variant: str, weights: tuple[float, float]):
        if variant == "RF":
            p, _ = recursive_forward_predict_y(
                rf_model, hist_min.copy(), ex_tbl, cfg.test_start, ex_tbl["ds"].max()
            )
        elif variant == "XGB" and HAVE_XGB and xgb_model is not None:
            p, _ = recursive_forward_predict_y(
                xgb_model, hist_min.copy(), ex_tbl, cfg.test_start, ex_tbl["ds"].max()
            )
        else:  # Y-ENS
            prf, _ = recursive_forward_predict_y(
                rf_model, hist_min.copy(), ex_tbl, cfg.test_start, ex_tbl["ds"].max()
            )
            if HAVE_XGB and xgb_model is not None:
                pxg, _ = recursive_forward_predict_y(
                    xgb_model, hist_min.copy(), ex_tbl, cfg.test_start, ex_tbl["ds"].max()
                )
                p = prf.merge(pxg, on="ds", suffixes=("_rf", "_xgb"))
                w_rf, w_xgb = weights
                p["yhat"] = w_rf * p["yhat_rf"] + w_xgb * p["yhat_xgb"]
                p = p[["ds", "yhat"]]
            else:
                p = prf
        return p

    for horizon_name, end_ds, pool, truth in (
        ("Full", cfg.test_end, exog_test_full, truth_full),
        ("Short3", cfg.test_end_short, exog_test_short, truth_short),
    ):
        for ex_name, ex_tbl in pool.items():
            rep = val_rep.get(ex_name) or next(iter(val_rep.values()))
            for variant in variants:
                preds = _predict_variant(ex_tbl, variant, rep["weights"])
                resid_key = "ENS" if (variant == "Y-ENS" and HAVE_XGB) else (
                    "RF" if variant == "RF" else "XGB"
                )
                resids = np.array(rep["residuals"][resid_key], dtype=float)
                preds_pi, sims = add_bootstrap_intervals(preds, resids)
                eval_df = truth.merge(preds_pi, on="ds", how="left")
                mae, rmse, mape = mae_rmse_mape(eval_df["y"], eval_df["yhat"])
                p3, p6, e_t = stockout_probability(start_stock, sims)
                wrf, wxgb = rep["weights"]
                combinations.append(CombinationRow(
                    horizon=horizon_name, exog=ex_name, y_variant=variant, phase="PRE",
                    mae=float(mae), rmse=float(rmse), mape=float(mape),
                    w_rf=(float(wrf) if variant == "Y-ENS" and HAVE_XGB else None),
                    w_xgb=(float(wxgb) if variant == "Y-ENS" and HAVE_XGB else None),
                    p_stockout_3m=float(p3), p_stockout_6m=float(p6),
                    e_t_stockout_mo=(float(e_t) if np.isfinite(e_t) else None),
                ))
                per_combo_preds[(horizon_name, ex_name, variant, "PRE")] = (preds_pi, sims)
                # Residual row (one per exog×variant, not per horizon — pick Full only to avoid dup)
                if horizon_name == "Full":
                    val_residuals_rows.append(ValResidualRow(
                        exog=ex_name, y_variant=variant, residuals=list(map(float, resids)),
                    ))

        # Intermittent variants — only on the Y axis if series is sparse
        if cfg.enable_intermittent and "Intermittent" in probe_methods:
            for im in cfg.im_methods:
                fc = predict_intermittent(
                    d[d["ds"] < cfg.test_start][["ds", "y"]],
                    cfg.test_start, end_ds, im, cfg.intermittent_alpha,
                )
                val_hist = d[d["ds"] < cfg.val_start][["ds", "y"]]
                val_fc = predict_intermittent(
                    val_hist, cfg.val_start, cfg.val_end, im, cfg.intermittent_alpha
                )
                vjoin = val_df[["ds", "y"]].merge(val_fc, on="ds", how="left")
                resids = (vjoin["y"].to_numpy() - vjoin["yhat"].to_numpy())
                preds_pi, sims = add_bootstrap_intervals(fc, resids)
                eval_df = truth.merge(preds_pi, on="ds", how="left")
                mae, rmse, mape = mae_rmse_mape(eval_df["y"], eval_df["yhat"])
                p3, p6, e_t = stockout_probability(start_stock, sims)
                combinations.append(CombinationRow(
                    horizon=horizon_name, exog="Intermittent", y_variant=im, phase="PRE",
                    mae=float(mae), rmse=float(rmse), mape=float(mape),
                    p_stockout_3m=float(p3), p_stockout_6m=float(p6),
                    e_t_stockout_mo=(float(e_t) if np.isfinite(e_t) else None),
                ))
                per_combo_preds[(horizon_name, "Intermittent", im, "PRE")] = (preds_pi, sims)

    # --- REFIT + rollback decision ---
    if cfg.enable_refit and exog_test_full:
        t0 = time.time()
        rf_refit, xgb_refit = refit_models_on_full(trainval_df)
        refit_secs = time.time() - t0

        rf_refit_path = blob_path(blob_dir.parent.parent, request.sku, request.run_id, "rf_y_refit")
        rf_refit.save(rf_refit_path)
        models_out.append(ModelRow(
            model_slot="rf_y_refit", column_target="y",
            hyperparams=rf_refit.hyperparams(), blob_uri=uri_for(rf_refit_path),
            fit_seconds=refit_secs / 2 if HAVE_XGB else refit_secs,
        ))
        if HAVE_XGB and xgb_refit is not None:
            xgb_refit_path = blob_path(
                blob_dir.parent.parent, request.sku, request.run_id, "xgb_y_refit"
            )
            xgb_refit.save(xgb_refit_path)
            models_out.append(ModelRow(
                model_slot="xgb_y_refit", column_target="y",
                hyperparams=xgb_refit.hyperparams(), blob_uri=uri_for(xgb_refit_path),
                fit_seconds=refit_secs / 2,
            ))

        # REFIT: recompute VAL weights + residuals with refitted models
        val_rep_refit: dict[str, dict] = {}
        for tag, ex in exog_val.items():
            val_rep_refit[tag] = recursive_predict_for_val(
                ex, rf_refit, xgb_refit, hist_for_val, val_df,
                cfg.val_start, cfg.val_end, HAVE_XGB,
            )

        for horizon_name, end_ds, pool, truth in (
            ("Full", cfg.test_end, exog_test_full, truth_full),
            ("Short3", cfg.test_end_short, exog_test_short, truth_short),
        ):
            for ex_name, ex_tbl in pool.items():
                rep = val_rep_refit.get(ex_name) or next(iter(val_rep_refit.values()))
                for variant in variants:
                    # Match scripts/model_v3.py: REFIT predicts from train-only history
                    # (hist_for_val), not train+val (hist_min). This makes the lag features
                    # at test_start differ from PRE, producing distinct predictions even
                    # when the refit models are deterministic clones of PRE's final fit.
                    if variant == "RF":
                        p, _ = recursive_forward_predict_y(
                            rf_refit, hist_for_val.copy(), ex_tbl, cfg.test_start, ex_tbl["ds"].max()
                        )
                    elif variant == "XGB" and HAVE_XGB and xgb_refit is not None:
                        p, _ = recursive_forward_predict_y(
                            xgb_refit, hist_for_val.copy(), ex_tbl, cfg.test_start, ex_tbl["ds"].max()
                        )
                    else:
                        prf, _ = recursive_forward_predict_y(
                            rf_refit, hist_for_val.copy(), ex_tbl, cfg.test_start, ex_tbl["ds"].max()
                        )
                        if HAVE_XGB and xgb_refit is not None:
                            pxg, _ = recursive_forward_predict_y(
                                xgb_refit, hist_for_val.copy(), ex_tbl, cfg.test_start, ex_tbl["ds"].max()
                            )
                            p = prf.merge(pxg, on="ds", suffixes=("_rf", "_xgb"))
                            w_rf, w_xgb = rep["weights"]
                            p["yhat"] = w_rf * p["yhat_rf"] + w_xgb * p["yhat_xgb"]
                            p = p[["ds", "yhat"]]
                        else:
                            p = prf
                    resid_key = "ENS" if (variant == "Y-ENS" and HAVE_XGB) else (
                        "RF" if variant == "RF" else "XGB"
                    )
                    resids = np.array(rep["residuals"][resid_key], dtype=float)
                    preds_pi, sims = add_bootstrap_intervals(p, resids)
                    eval_df = truth.merge(preds_pi, on="ds", how="left")
                    mae, rmse, mape = mae_rmse_mape(eval_df["y"], eval_df["yhat"])
                    p3, p6, e_t = stockout_probability(start_stock, sims)
                    wrf, wxgb = rep["weights"]
                    combinations.append(CombinationRow(
                        horizon=horizon_name, exog=ex_name, y_variant=variant, phase="REFIT",
                        mae=float(mae), rmse=float(rmse), mape=float(mape),
                        w_rf=(float(wrf) if variant == "Y-ENS" and HAVE_XGB else None),
                        w_xgb=(float(wxgb) if variant == "Y-ENS" and HAVE_XGB else None),
                        p_stockout_3m=float(p3), p_stockout_6m=float(p6),
                        e_t_stockout_mo=(float(e_t) if np.isfinite(e_t) else None),
                    ))
                    per_combo_preds[(horizon_name, ex_name, variant, "REFIT")] = (preds_pi, sims)

    # --- Winning combination selection on Horizon='Full' ---
    combined_full = [c for c in combinations if c.horizon == "Full"]
    pre_best = min((c.mae for c in combined_full if c.phase == "PRE"), default=np.inf)
    refit_rows = [c for c in combined_full if c.phase == "REFIT"]
    if refit_rows:
        refit_best = min(c.mae for c in refit_rows)
        if decide_phase(pre_best, refit_best) == "PRE":
            # Roll back — discard REFIT rows
            combinations = [c for c in combinations if c.phase == "PRE"]
            combined_full = [c for c in combined_full if c.phase == "PRE"]

    best = min(combined_full, key=lambda c: c.mae)
    winning = WinningCombo(
        horizon=best.horizon, exog=best.exog, y_variant=best.y_variant,
        phase=best.phase, mae=best.mae, rmse=best.rmse, mape=best.mape,
        w_rf=best.w_rf, w_xgb=best.w_xgb,
        p_stockout_3m=best.p_stockout_3m, p_stockout_6m=best.p_stockout_6m,
        e_t_stockout_mo=best.e_t_stockout_mo,
    )

    # --- OMS recommendation using winning combo's sims ---
    _, sims_best = per_combo_preds[(best.horizon, best.exog, best.y_variant, best.phase)]
    params = request.params_row
    h_cover = int(params.h_cover)
    q_target = float(params.q_target)
    cum_q = cum_demand_quantile(sims_best, h_cover, q_target)
    order_qty_raw = float(cum_q - start_stock)
    order_qty_rounded = round_moq_lot(order_qty_raw, params.moq, params.lot_size)
    recommendation = RecommendationRow(
        starting_stock=float(start_stock),
        t_check=int(params.t_check), h_cover=h_cover,
        q_target=q_target, moq=float(params.moq), lot_size=float(params.lot_size),
        cum_demand_q=float(cum_q),
        order_qty_raw=float(order_qty_raw),
        order_qty_rounded=float(order_qty_rounded),
    )

    # --- Ensure blob_dir exists even if empty (Rust verifies later) ---
    blob_dir_for(blob_dir.parent.parent, request.sku, request.run_id).mkdir(parents=True, exist_ok=True)

    return ForecastResult(
        sku=request.sku, run_id=request.run_id, mode="cold",
        winning=winning, combinations=combinations, models=models_out,
        exog_selection=exog_selection_rows, val_residuals=val_residuals_rows,
        recommendation=recommendation,
    )
