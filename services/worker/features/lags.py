"""Lag features for the Y-model and EXOG ML models.

All lags are strictly causal — shift() introduces a lookup into the past with no
future leakage.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_lags_y(df: pd.DataFrame) -> pd.DataFrame:
    """Build the lag / ratio features the Y-model consumes.

    Mirrors scripts/model_v3.py `build_lags_y` (line 202).
    """
    d = df.copy()
    if {"orders", "stock"}.issubset(d.columns):
        d["orders_ratio"] = d["orders"] / d["stock"].replace(0, np.nan)
    if "y" in d:
        d["y_lag1"] = d["y"].shift(1)
    if "orders" in d:
        d["orders_lag1"] = d["orders"].shift(1)
        d["orders_lag3"] = d["orders"].shift(3)
    if "stock" in d:
        d["stock_lag1"] = d["stock"].shift(1)
        d["stock_lag3"] = d["stock"].shift(3)
    return d


def make_exog_frame(dfv: pd.DataFrame, col: str) -> pd.DataFrame:
    """Build the ML-Exog feature frame for a single column (orders | stock).

    Columns produced: lag1, lag3, month, year. Mirrors scripts/model_v3.py `make_exog_frame`
    (line 364).
    """
    d = dfv[["ds", col]].sort_values("ds").copy()
    d["lag1"] = d[col].shift(1)
    d["lag3"] = d[col].shift(3)
    d["month"] = d["ds"].dt.month
    d["year"] = d["ds"].dt.year
    return d
