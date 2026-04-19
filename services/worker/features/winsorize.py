"""Percentile-clip helpers."""
from __future__ import annotations

import numpy as np
import pandas as pd


def winsorize_series(s: pd.Series, lq: float = 0.05, uq: float = 0.95) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    lo = np.nanpercentile(x, lq * 100)
    hi = np.nanpercentile(x, uq * 100)
    return x.clip(lo, hi)


def nonneg(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").clip(lower=0.0)


def smooth_causal_ma(s: pd.Series, window: int = 3) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce").ffill()
    return x.rolling(window=window, min_periods=1).mean().bfill()


def rolling_impute(s: pd.Series, causal: bool = False) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    if causal:
        x = x.ffill()
        x = x.rolling(window=3, min_periods=1).mean().bfill()
    else:
        roll = x.rolling(window=3, center=True, min_periods=1).mean()
        x = x.where(~x.isna(), roll).ffill().bfill()
    return x
