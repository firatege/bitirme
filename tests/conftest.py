"""Shared pytest fixtures — synthetic panel data sized to exercise train/val/test splits."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.worker.config import get_config


@pytest.fixture(scope="session", autouse=True)
def _seed_numpy():
    np.random.seed(42)


@pytest.fixture
def cfg():
    return get_config()


def _make_panel(months: int = 80, start: str = "2019-01-01", seed: int = 0) -> pd.DataFrame:
    """Monthly panel resembling a dense SKU: trending + seasonal + noise."""
    rng = np.random.default_rng(seed)
    ds = pd.date_range(start, periods=months, freq="MS")
    t = np.arange(months)
    seasonal = 20 * np.sin(2 * np.pi * t / 12)
    trend = 0.5 * t
    y = np.clip(60 + trend + seasonal + rng.normal(0, 8, months), 0, None)
    orders = np.clip(y * 1.05 + rng.normal(0, 5, months), 0, None)
    stock = np.clip(200 - np.cumsum(y - orders) + rng.normal(0, 10, months), 0, None)
    return pd.DataFrame({"ds": ds, "y": y, "orders": orders, "stock": stock})


@pytest.fixture
def panel_dense() -> pd.DataFrame:
    return _make_panel(months=80, seed=0)


@pytest.fixture
def panel_sparse() -> pd.DataFrame:
    """Intermittent series — ~70% zeros."""
    rng = np.random.default_rng(3)
    months = 60
    ds = pd.date_range("2020-01-01", periods=months, freq="MS")
    occ = rng.random(months) < 0.35
    mag = rng.integers(5, 20, months)
    y = np.where(occ, mag, 0).astype(float)
    orders = np.clip(y + rng.normal(0, 2, months), 0, None)
    stock = np.cumsum(orders - y) + 30
    return pd.DataFrame({"ds": ds, "y": y, "orders": orders, "stock": stock})


@pytest.fixture
def params_row_simple():
    from services.worker.schemas.requests import ParamsRow

    return ParamsRow(t_check=3, h_cover=6, q_target=0.5, lead_time_mo=0, moq=0.0, lot_size=1.0)
