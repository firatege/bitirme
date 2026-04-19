"""EXOG model tests — cheap families always, Prophet/SARIMA marked slow."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.worker.models.exog_ets import ExogEts
from services.worker.models.exog_ml_rf import MLExogRF
from services.worker.models.exog_ml_xgb import HAVE_XGB, MLExogXGB
from services.worker.models.exog_sarima import ExogSarima


CUTOFF = pd.Timestamp("2025-01-01")


def test_ml_exog_rf_train_and_forecast(panel_dense, tmp_path):
    m = MLExogRF.train(panel_dense[["ds", "orders"]], "orders", CUTOFF)
    assert m is not None
    hist = panel_dense[panel_dense["ds"] < CUTOFF][["ds", "orders"]]
    fc = m.recursive_forecast(hist, pd.Timestamp("2025-02-01"), pd.Timestamp("2025-05-01"))
    assert len(fc) == 4
    assert (fc["orders"] >= 0).all()
    p = tmp_path / "rf.joblib"
    m.save(p)
    m2 = MLExogRF.load(p)
    fc2 = m2.recursive_forecast(hist, pd.Timestamp("2025-02-01"), pd.Timestamp("2025-05-01"))
    assert np.allclose(fc["orders"], fc2["orders"])


@pytest.mark.skipif(not HAVE_XGB, reason="xgboost not installed")
def test_ml_exog_xgb_train_and_forecast(panel_dense, tmp_path):
    m = MLExogXGB.train(panel_dense[["ds", "stock"]], "stock", CUTOFF)
    assert m is not None
    hist = panel_dense[panel_dense["ds"] < CUTOFF][["ds", "stock"]]
    fc = m.recursive_forecast(hist, pd.Timestamp("2025-02-01"), pd.Timestamp("2025-04-01"))
    assert len(fc) == 3


@pytest.mark.slow
def test_exog_ets_fit_and_forecast(panel_dense):
    train = panel_dense[panel_dense["ds"] < CUTOFF][["ds", "orders"]]
    m = ExogEts.fit(train, "orders")
    fut = pd.date_range(CUTOFF + pd.DateOffset(months=1), periods=3, freq="MS")
    fc = m.forecast(3, fut)
    assert len(fc) == 3


@pytest.mark.slow
def test_exog_sarima_fit_and_forecast(panel_dense):
    train = panel_dense[panel_dense["ds"] < CUTOFF][["ds", "orders"]]
    m = ExogSarima.fit(train, "orders")
    if m is None:
        pytest.skip("SARIMA fit did not converge on this synthetic series")
    fut = pd.date_range(CUTOFF + pd.DateOffset(months=1), periods=3, freq="MS")
    fc = m.forecast(3, fut)
    assert len(fc) == 3
