"""Baseline forecasters (seasonal naive, MA3)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.worker.selection.baselines import (
    baseline_val_mae,
    ma3_forecast,
    seasonal_naive_forecast,
)


def test_seasonal_naive_repeats_same_month_one_year_ago():
    ds = pd.date_range("2020-01-01", periods=36, freq="MS")
    y = np.arange(36, dtype=float)
    hist = pd.DataFrame({"ds": ds, "y": y})
    fc = seasonal_naive_forecast(hist, pd.Timestamp("2023-01-01"), pd.Timestamp("2023-03-01"))
    # Jan 2023 should map to the latest observation available for "Jan", which is 2022-01 (y=24)
    assert fc["yhat"].iloc[0] == 24.0


def test_ma3_forecast_constant_extension():
    ds = pd.date_range("2020-01-01", periods=6, freq="MS")
    y = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    hist = pd.DataFrame({"ds": ds, "y": y})
    fc = ma3_forecast(hist, pd.Timestamp("2020-07-01"), pd.Timestamp("2020-09-01"))
    assert len(fc) == 3
    expected = np.mean([4.0, 5.0, 6.0])
    assert (fc["yhat"] == expected).all()


def test_baseline_val_mae_finite(panel_dense):
    mae = baseline_val_mae(
        panel_dense, pd.Timestamp("2024-08-01"), pd.Timestamp("2025-01-01"), "seasonal_naive"
    )
    assert np.isfinite(mae)
    assert mae >= 0
