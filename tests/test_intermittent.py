"""Intermittent-demand forecasters."""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.worker.models.intermittent import (
    croston_forecast,
    predict_intermittent,
    sba_forecast,
    select_intermittent,
    tsb_forecast,
)


def test_croston_zero_series_returns_zero():
    assert croston_forecast([0, 0, 0, 0], alpha=0.1) == 0.0


def test_croston_constant_series_returns_that_value():
    assert np.isclose(croston_forecast([5, 5, 5, 5], alpha=0.1), 5.0, atol=0.5)


def test_sba_applies_bias_correction():
    y = [0, 3, 0, 0, 4]
    c = croston_forecast(y, alpha=0.1)
    s = sba_forecast(y, alpha=0.1)
    assert s < c  # SBA shrinks Croston


def test_tsb_zero_series_returns_zero():
    assert tsb_forecast([0, 0, 0, 0, 0], alpha=0.1) == 0.0


def test_tsb_constant_series_positive():
    assert tsb_forecast([5, 5, 5, 5, 5], alpha=0.1) > 0


def test_predict_intermittent_shape(panel_sparse):
    out = predict_intermittent(panel_sparse[["ds", "y"]], pd.Timestamp("2025-01-01"), pd.Timestamp("2025-06-01"), "TSB", 0.1)
    assert len(out) == 6
    assert (out["yhat"] >= 0).all()
    # Flat forecast — all values identical
    assert out["yhat"].nunique() == 1


def test_select_intermittent_sparse(panel_sparse):
    assert select_intermittent(panel_sparse, "auto") is True


def test_select_intermittent_dense(panel_dense):
    assert select_intermittent(panel_dense, "auto") is False


def test_select_intermittent_override_all(panel_dense):
    assert select_intermittent(panel_dense, "all") is True


def test_select_intermittent_override_none(panel_sparse):
    assert select_intermittent(panel_sparse, "none") is False
