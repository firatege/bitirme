"""Calendar features — year, month derived from the `ds` date column."""
from __future__ import annotations

import pandas as pd


def add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["year"] = d["ds"].dt.year
    d["month"] = d["ds"].dt.month
    return d


def ensure_ms_freq(df: pd.DataFrame) -> pd.DataFrame:
    """Canonicalize `ds` to month-start timestamps; drop duplicate months."""
    d = df.copy().sort_values("ds")
    d["ds"] = pd.to_datetime(d["ds"]).dt.to_period("M").dt.to_timestamp(how="start")
    d = d.drop_duplicates(["ds"]).set_index("ds").sort_index()
    d.index = pd.DatetimeIndex(d.index, freq="MS")
    return d.reset_index()
