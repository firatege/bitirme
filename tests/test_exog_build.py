"""EXOG dispatcher — build_exog_by_method + build_hybrid_exog."""
from __future__ import annotations

import pandas as pd
import pytest

from services.worker.forecasting.exog import (
    build_exog_by_method,
    build_exog_ml,
    build_hybrid_exog,
)


START = pd.Timestamp("2025-02-01")
END = pd.Timestamp("2025-05-01")
CUTOFF = pd.Timestamp("2025-01-01")


def test_build_exog_ml_rf_returns_both_columns(panel_dense):
    out = build_exog_ml(panel_dense, START, END, CUTOFF, "rf")
    assert set(["ds", "orders", "stock"]).issubset(out.forecast.columns)
    assert (out.forecast["orders"] >= 0).all()
    assert (out.forecast["stock"] >= 0).all()


def test_build_exog_by_method_ml_rf_shape(panel_dense):
    out = build_exog_by_method(panel_dense, START, END, CUTOFF, "ML-Exog RF")
    assert out.method == "ML-Exog RF"
    assert len(out.forecast) == 4


def test_build_exog_by_method_unknown_raises(panel_dense):
    with pytest.raises(ValueError):
        build_exog_by_method(panel_dense, START, END, CUTOFF, "NotAMethod")


def test_build_hybrid_exog_returns_tag(panel_dense):
    chosen = {"orders": "ML-Exog RF", "stock": "ML-Exog RF"}
    tbl, tag = build_hybrid_exog(panel_dense, START, END, CUTOFF, chosen)
    assert tag.startswith("Hybrid[")
    assert set(["ds", "orders", "stock"]).issubset(tbl.columns)


@pytest.mark.slow
def test_build_exog_ets_smoke(panel_dense):
    out = build_exog_by_method(panel_dense, START, END, CUTOFF, "ETS")
    assert out.method == "ets"
    assert len(out.forecast) == 4
