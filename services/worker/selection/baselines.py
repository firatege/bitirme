"""Baseline forecasters and baseline VAL MAE for the probe-gate threshold."""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.worker.features.pipeline import mae_rmse_mape


def seasonal_naive_forecast(
    hist_df: pd.DataFrame, start_ds: pd.Timestamp, end_ds: pd.Timestamp
) -> pd.DataFrame:
    """Seasonal naive: value from the same calendar month one year ago."""
    fut = pd.date_range(start_ds, end_ds, freq="MS")
    y = hist_df.set_index("ds")["y"].astype(float)
    y.index = pd.DatetimeIndex(y.index, freq="MS")
    out = []
    for ds in fut:
        last_year = ds - pd.DateOffset(years=1)
        val = y.get(last_year, np.nan)
        if not np.isfinite(val):
            val = y.iloc[-1] if len(y) else 0.0
        out.append({"ds": ds, "yhat": max(0.0, float(val))})
    return pd.DataFrame(out)


def ma3_forecast(
    hist_df: pd.DataFrame, start_ds: pd.Timestamp, end_ds: pd.Timestamp
) -> pd.DataFrame:
    """Constant forward extension of the last 3-month moving average."""
    fut = pd.date_range(start_ds, end_ds, freq="MS")
    y = pd.to_numeric(hist_df["y"], errors="coerce").fillna(0.0)
    ma = y.rolling(3, min_periods=1).mean().iloc[-1] if len(y) else 0.0
    return pd.DataFrame({"ds": fut, "yhat": [max(0.0, float(ma))] * len(fut)})


def baseline_val_mae(
    d: pd.DataFrame,
    val_start: pd.Timestamp,
    val_end: pd.Timestamp,
    kind: str = "seasonal_naive",
) -> float:
    hist = d[d["ds"] < val_start][["ds", "y"]]
    truth = d[(d["ds"] >= val_start) & (d["ds"] <= val_end)][["ds", "y"]]
    fc = (
        seasonal_naive_forecast(hist, val_start, val_end)
        if kind == "seasonal_naive"
        else ma3_forecast(hist, val_start, val_end)
    )
    join = truth.merge(fc, on="ds", how="left")
    mae, _, _ = mae_rmse_mape(join["y"], join["yhat"])
    return mae
