"""Bootstrap prediction interval tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.worker.forecasting.bootstrap import add_bootstrap_intervals


def test_pi95_wider_than_pi80():
    preds = pd.DataFrame({"ds": pd.date_range("2025-01-01", periods=6, freq="MS"),
                          "yhat": np.full(6, 10.0)})
    residuals = np.random.default_rng(0).normal(0, 2, 100)
    out, sims = add_bootstrap_intervals(preds, residuals, B=200, mode="parametric")
    assert (out["pi95_hi"] - out["pi95_lo"] >= out["pi80_hi"] - out["pi80_lo"]).all()


def test_pi_envelopes_contain_yhat():
    preds = pd.DataFrame({"ds": pd.date_range("2025-01-01", periods=3, freq="MS"),
                          "yhat": np.array([5.0, 8.0, 12.0])})
    residuals = np.random.default_rng(0).normal(0, 1, 50)
    out, _ = add_bootstrap_intervals(preds, residuals, B=200, mode="parametric")
    assert (out["pi80_lo"] <= out["yhat"]).all() and (out["yhat"] <= out["pi80_hi"]).all()
    assert (out["pi95_lo"] <= out["yhat"]).all() and (out["yhat"] <= out["pi95_hi"]).all()


def test_sims_matrix_shape():
    preds = pd.DataFrame({"ds": pd.date_range("2025-01-01", periods=4, freq="MS"),
                          "yhat": np.full(4, 10.0)})
    _, sims = add_bootstrap_intervals(preds, np.array([1.0, -1.0, 0.5, -0.5]), B=128, mode="parametric")
    assert sims.shape == (4, 128)


def test_clamp_nonneg_prevents_negative_sims():
    preds = pd.DataFrame({"ds": pd.date_range("2025-01-01", periods=2, freq="MS"),
                          "yhat": np.array([1.0, 1.0])})
    _, sims = add_bootstrap_intervals(preds, np.array([-100.0, -100.0]), B=64, mode="parametric")
    assert (sims >= 0).all()


def test_mode_smooth_handles_empty_residuals():
    preds = pd.DataFrame({"ds": pd.date_range("2025-01-01", periods=2, freq="MS"),
                          "yhat": np.array([10.0, 10.0])})
    out, sims = add_bootstrap_intervals(preds, np.array([]), B=64, mode="smooth")
    assert np.isfinite(sims).all()
    assert len(out) == 2
