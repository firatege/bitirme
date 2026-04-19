"""Rolling-origin cross-validation splits for the Y-model grid search."""
from __future__ import annotations

from typing import Iterator

import pandas as pd


def rolling_origin_splits(
    df: pd.DataFrame, n_splits: int = 3, min_train_months: int = 24
) -> Iterator[tuple[pd.DataFrame, pd.DataFrame]]:
    """Yield (train, val) folds. Mirrors scripts/model_v3.py `rolling_origin_splits` (line 661)."""
    d = df.sort_values("ds")
    if d["ds"].nunique() < (min_train_months + n_splits):
        yield (
            d[d["ds"] < d["ds"].max() - pd.DateOffset(months=3)],
            d[d["ds"] >= d["ds"].max() - pd.DateOffset(months=3)],
        )
        return
    for k in range(n_splits, 0, -1):
        val_end = d["ds"].max() - pd.DateOffset(months=k - 1)
        val_start = val_end - pd.DateOffset(months=2)
        tr = d[d["ds"] <= val_start - pd.DateOffset(days=1)]
        va = d[(d["ds"] >= val_start) & (d["ds"] <= val_end)]
        if len(tr) >= min_train_months and len(va) >= 2:
            yield tr, va
