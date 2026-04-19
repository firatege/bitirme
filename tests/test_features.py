"""Feature-engineering unit tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.worker.config import get_config
from services.worker.features.calendar import add_calendar, ensure_ms_freq
from services.worker.features.lags import build_lags_y, make_exog_frame
from services.worker.features.pipeline import mae_rmse_mape, prep_features_y
from services.worker.features.winsorize import nonneg, rolling_impute, smooth_causal_ma, winsorize_series


def test_add_calendar_columns(panel_dense):
    d = add_calendar(panel_dense)
    assert "month" in d.columns and "year" in d.columns
    assert d["month"].between(1, 12).all()


def test_ensure_ms_freq_snaps_to_month_start(panel_dense):
    shuffled = panel_dense.sample(frac=1.0, random_state=0).reset_index(drop=True)
    d = ensure_ms_freq(shuffled)
    assert (d["ds"].dt.day == 1).all()
    assert d["ds"].is_monotonic_increasing


def test_build_lags_y_produces_expected_columns(panel_dense):
    d = build_lags_y(panel_dense)
    for col in ("orders_ratio", "y_lag1", "orders_lag1", "orders_lag3", "stock_lag1", "stock_lag3"):
        assert col in d.columns
    # First row lags must be NaN (no prior data)
    assert np.isnan(d["y_lag1"].iloc[0])


def test_build_lags_y_is_causal(panel_dense):
    d = build_lags_y(panel_dense)
    # y_lag1 at row i must equal y at row i-1
    for i in range(1, 5):
        assert d["y_lag1"].iloc[i] == panel_dense["y"].iloc[i - 1]


def test_make_exog_frame_columns(panel_dense):
    d = make_exog_frame(panel_dense, "orders")
    assert set(["ds", "orders", "lag1", "lag3", "month", "year"]).issubset(d.columns)


def test_winsorize_clips_extremes():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 1000.0])
    out = winsorize_series(s, lq=0.0, uq=0.80)
    assert out.max() < 1000.0


def test_nonneg_clips_negative():
    s = pd.Series([-1.0, 0.0, 5.0])
    assert (nonneg(s) >= 0).all()


def test_rolling_impute_causal_does_not_peek():
    s = pd.Series([1.0, np.nan, np.nan, 10.0, 10.0])
    out = rolling_impute(s, causal=True)
    # Position 1 must not be influenced by the future 10.0
    assert out.iloc[1] == 1.0


def test_smooth_causal_ma_matches_rolling_mean():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = smooth_causal_ma(s, window=3)
    assert np.isclose(out.iloc[-1], np.mean([3.0, 4.0, 5.0]))


def test_prep_features_y_has_all_configured_features(panel_dense):
    d = prep_features_y(panel_dense.copy(), causal=False)
    for f in get_config().features_y:
        assert f in d.columns


def test_prep_features_y_no_nan_no_inf(panel_dense):
    d = prep_features_y(panel_dense.copy(), causal=True)
    feats = list(get_config().features_y)
    arr = d[feats].to_numpy()
    assert np.isfinite(arr).all()


def test_mae_rmse_mape_matches_known_values():
    y_true = np.array([10.0, 20.0, 30.0])
    y_pred = np.array([12.0, 18.0, 33.0])
    mae, rmse, mape = mae_rmse_mape(y_true, y_pred)
    assert np.isclose(mae, (2 + 2 + 3) / 3)
    assert np.isclose(rmse, np.sqrt((4 + 4 + 9) / 3))
    assert mape > 0
