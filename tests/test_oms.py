"""OMS policy + stockout computations."""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.worker.oms.policy import infer_starting_stock, round_moq_lot
from services.worker.oms.stockout import cum_demand_quantile, stockout_probability


def test_round_moq_lot_respects_minimum():
    assert round_moq_lot(3.0, moq=10.0, lot=1.0) == 10.0


def test_round_moq_lot_rounds_up_to_lot():
    assert round_moq_lot(11.0, moq=0.0, lot=5.0) == 15.0


def test_round_moq_lot_negative_clips_to_zero():
    assert round_moq_lot(-5.0, moq=0.0, lot=1.0) == 0.0


def test_round_moq_lot_lot_zero_defaults_to_one():
    assert round_moq_lot(3.2, moq=0.0, lot=0) == 4.0


def test_infer_starting_stock_uses_override():
    df = pd.DataFrame({"ds": pd.date_range("2024-01-01", periods=3, freq="MS"),
                       "stock": [10.0, 20.0, 30.0]})
    assert infer_starting_stock(df, pd.Timestamp("2025-01-01"), override=99.0) == 99.0


def test_infer_starting_stock_uses_last_prior_observation():
    df = pd.DataFrame({"ds": pd.date_range("2024-01-01", periods=3, freq="MS"),
                       "stock": [10.0, 20.0, 30.0]})
    got = infer_starting_stock(df, pd.Timestamp("2025-01-01"), override=None)
    assert got == 30.0


def test_stockout_probability_high_when_stock_small():
    # 100 months simulated, all demand=10. Stock of 5 must stockout by month 1.
    sims = np.full((12, 100), 10.0)
    p3, p6, e_t = stockout_probability(start_stock=5.0, sims=sims)
    assert p3 == 1.0
    assert p6 == 1.0
    assert e_t == 1.0


def test_stockout_probability_zero_when_stock_huge():
    sims = np.full((12, 100), 10.0)
    p3, p6, _ = stockout_probability(start_stock=10_000.0, sims=sims)
    assert p3 == 0.0 and p6 == 0.0


def test_cum_demand_quantile_matches_numpy():
    sims = np.tile(np.arange(1, 7, dtype=float).reshape(-1, 1), (1, 50))
    got = cum_demand_quantile(sims, months=3, q=0.5)
    expected = 1 + 2 + 3  # median of a constant-per-month distribution
    assert np.isclose(got, expected)
