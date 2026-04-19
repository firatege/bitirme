"""Recursive Y forecast tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.worker.config import get_config
from services.worker.features.pipeline import prep_features_y
from services.worker.forecasting.recursive import (
    recursive_forward_predict_y,
    recursive_predict_for_val,
    y_ensemble_weights,
)
from services.worker.models.y_rf import YRandomForest
from services.worker.models.y_xgb import HAVE_XGB, YXGBoost


def _fit_small_rf(panel):
    df = prep_features_y(panel.copy(), causal=False)
    feats = list(get_config().features_y)
    return YRandomForest.fit(df[feats], df["y"].to_numpy(),
                             {"n_estimators": 30, "max_depth": 4, "min_samples_split": 2, "min_samples_leaf": 1})


def _fit_small_xgb(panel):
    if not HAVE_XGB:
        return None
    df = prep_features_y(panel.copy(), causal=False)
    feats = list(get_config().features_y)
    return YXGBoost.fit(df[feats], df["y"].to_numpy(),
                        {"n_estimators": 50, "learning_rate": 0.1, "max_depth": 3,
                         "subsample": 0.9, "colsample_bytree": 0.9, "reg_lambda": 1.0})


def test_recursive_forward_predict_y_horizon(panel_dense):
    rf = _fit_small_rf(panel_dense)
    mask_hist = panel_dense["ds"] < pd.Timestamp("2025-02-01")
    hist = panel_dense.loc[mask_hist, ["ds", "y", "orders", "stock"]].copy()
    exog_future = pd.DataFrame({
        "ds": pd.date_range("2025-02-01", periods=4, freq="MS"),
        "orders": [50.0, 60.0, 55.0, 58.0],
        "stock": [100.0, 95.0, 90.0, 88.0],
    })
    preds, _ = recursive_forward_predict_y(rf, hist, exog_future,
                                            pd.Timestamp("2025-02-01"), pd.Timestamp("2025-05-01"))
    assert len(preds) == 4
    assert (preds["yhat"] >= 0).all()
    assert np.isfinite(preds["yhat"]).all()


def test_y_ensemble_weights_sum_to_one():
    wrf, wxgb, mae_rf, mae_xgb = y_ensemble_weights(
        np.array([1.0, 2.0, 3.0]), np.array([1.2, 2.2, 3.2]), np.array([1.0, 2.0, 3.0])
    )
    assert np.isclose(wrf + wxgb, 1.0)
    assert wxgb > wrf  # XGB is exact → gets higher weight


@pytest.mark.slow
def test_recursive_predict_for_val_returns_residuals(panel_dense):
    rf = _fit_small_rf(panel_dense)
    xgb = _fit_small_xgb(panel_dense)
    cfg = get_config()
    mask_train = panel_dense["ds"] < cfg.val_start
    mask_val = (panel_dense["ds"] >= cfg.val_start) & (panel_dense["ds"] <= cfg.val_end)
    train_df = prep_features_y(panel_dense.loc[mask_train].copy(), causal=False)
    val_df = prep_features_y(panel_dense.loc[mask_val].copy(), causal=True)
    hist_for_val = train_df[["ds", "y", "orders", "stock", "month", "year"]].copy()
    # Simple EXOG: zeros
    exog = pd.DataFrame({"ds": pd.date_range(cfg.val_start, cfg.val_end, freq="MS"),
                          "orders": 0.0, "stock": 0.0})
    rep = recursive_predict_for_val(exog, rf, xgb, hist_for_val, val_df, cfg.val_start, cfg.val_end, HAVE_XGB)
    assert set(["weights", "mae_rf", "mae_xgb", "mae_ens", "residuals"]).issubset(rep.keys())
    assert "RF" in rep["residuals"] and "ENS" in rep["residuals"]
