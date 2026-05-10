"""ExogSarima — ARIMA(1,1,1) for orders/stock EXOG forecasting.

Uses fixed (1,1,1)(0,1,0,12) — grid search dropped per opt/sarima_grid_bulgu.md
finding: grid adds runtime without consistent MAE gain on this dataset.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX


class ExogSarima:
    def __init__(self, result, col: str) -> None:
        self._result = result
        self._col = col

    @classmethod
    def fit(cls, train_df: pd.DataFrame, col: str) -> "ExogSarima | None":
        y = train_df.set_index("ds")[col]
        y.index.freq = "MS"
        try:
            result = SARIMAX(
                y,
                order=(1, 1, 1),
                seasonal_order=(0, 1, 0, 12),
                enforce_stationarity=False,
                enforce_invertibility=False,
            ).fit(disp=False)
            return cls(result, col)
        except Exception:
            return None

    def forecast(self, steps: int, future_idx: pd.DatetimeIndex) -> pd.DataFrame:
        pred = self._result.get_forecast(steps=steps).predicted_mean
        return pd.DataFrame({"ds": pd.DatetimeIndex(future_idx), self._col: pred.values})
