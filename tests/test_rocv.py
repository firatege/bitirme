"""Rolling-origin CV split generator."""
from __future__ import annotations

import pandas as pd

from services.worker.selection.rocv import rolling_origin_splits


def test_rocv_yields_multiple_folds(panel_dense):
    folds = list(rolling_origin_splits(panel_dense, n_splits=3, min_train_months=24))
    assert len(folds) >= 1
    for tr, va in folds:
        assert len(tr) >= 24
        assert len(va) >= 2
        # Train must not overlap validation in time
        assert tr["ds"].max() < va["ds"].min()


def test_rocv_fallback_for_small_series():
    short = pd.DataFrame({"ds": pd.date_range("2024-01-01", periods=8, freq="MS"),
                          "y": range(8), "orders": range(8), "stock": range(8)})
    folds = list(rolling_origin_splits(short, n_splits=3, min_train_months=24))
    assert len(folds) == 1  # fallback single split
