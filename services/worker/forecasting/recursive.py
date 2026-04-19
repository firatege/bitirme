"""Recursive T+1 → T+H forecast for the Y-model.

Mirrors scripts/model_v3.py `recursive_forward_predict_y` + `recursive_predict_for_val`
+ `y_ensemble_weights` (lines 709-828).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

from services.worker.config import get_config
from services.worker.features.pipeline import mae_rmse_mape, prep_features_y
from services.worker.features.winsorize import rolling_impute


def recursive_forward_predict_y(
    model,
    hist_df: pd.DataFrame,
    exog_future: pd.DataFrame,
    start_ds: pd.Timestamp,
    end_ds: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = get_config()
    feats = list(cfg.features_y)
    fut = pd.date_range(start_ds, end_ds, freq="MS")
    future_part = pd.DataFrame({"ds": fut}).merge(exog_future, on="ds", how="left")
    full = pd.concat([hist_df, future_part], ignore_index=True).sort_values("ds")
    preds: list[dict] = []
    for ds in fut:
        tmp = prep_features_y(full.copy(), causal=True)
        row = (
            tmp.loc[tmp["ds"] == ds, feats]
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0)
            .to_numpy()
        )
        yhat = float(model.predict(row)[0])
        if not np.isfinite(yhat):
            yhat = 0.0
        yhat = max(0.0, yhat)
        preds.append({"ds": ds, "yhat": yhat})
        full.loc[full["ds"] == ds, "y"] = yhat
        for c in ("orders", "stock"):
            if c in full.columns:
                full[c] = rolling_impute(full[c], causal=True)
    return pd.DataFrame(preds), full.loc[full["ds"].isin(fut)].copy()


def y_ensemble_weights(
    y_true: np.ndarray, yhat_rf: np.ndarray, yhat_xgb: np.ndarray, eps: float = 1e-6
) -> tuple[float, float, float, float]:
    """Inverse-MAE stacking weights — simple closed form.

    (Distinct from the NNLS stacker in models/stacking.py; cheap and deterministic,
    used for the Y-ENS row in VAL tables.)
    """
    mae_rf = mean_absolute_error(y_true, yhat_rf)
    mae_xgb = mean_absolute_error(y_true, yhat_xgb)
    wrf = 1.0 / (mae_rf + eps)
    wxgb = 1.0 / (mae_xgb + eps)
    s = wrf + wxgb
    return wrf / s, wxgb / s, mae_rf, mae_xgb


def recursive_predict_for_val(
    exog_tbl: pd.DataFrame,
    rf_model,
    xgb_model,
    hist_for_val: pd.DataFrame,
    val_df: pd.DataFrame,
    val_start: pd.Timestamp,
    val_end: pd.Timestamp,
    have_xgb: bool,
) -> dict:
    prf, _ = recursive_forward_predict_y(
        rf_model, hist_for_val.copy(), exog_tbl, val_start, val_end
    )
    if have_xgb and xgb_model is not None:
        pxgb, _ = recursive_forward_predict_y(
            xgb_model, hist_for_val.copy(), exog_tbl, val_start, val_end
        )
    else:
        pxgb = prf.copy()
    join = (
        val_df[["ds", "y"]]
        .merge(prf, on="ds", how="left")
        .rename(columns={"yhat": "yhat_rf"})
    )
    join = join.merge(pxgb, on="ds", how="left").rename(columns={"yhat": "yhat_xgb"})
    if not have_xgb:
        join["yhat_xgb"] = join["yhat_rf"]
    wrf, wxgb, mae_rf, mae_xgb = y_ensemble_weights(
        join["y"].values, join["yhat_rf"].values, join["yhat_xgb"].values
    )
    yhat_ens = wrf * join["yhat_rf"].values + wxgb * join["yhat_xgb"].values
    mae_ens, rmse_ens, mape_ens = mae_rmse_mape(join["y"].values, yhat_ens)
    return {
        "weights": (wrf, wxgb),
        "mae_rf": mae_rf,
        "mae_xgb": mae_xgb,
        "mae_ens": mae_ens,
        "rmse_ens": rmse_ens,
        "mape_ens": mape_ens,
        "residuals": {
            "RF": (join["y"].values - join["yhat_rf"].values),
            "XGB": (join["y"].values - join["yhat_xgb"].values),
            "ENS": (join["y"].values - yhat_ens),
        },
    }
