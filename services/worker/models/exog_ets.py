"""ExogEts — ETS (ExponentialSmoothing) for orders/stock EXOG forecasting.

Opt finding: damp=False (add/add trend) beats dampened ETS on average by 3-5%
on noisy lubricant distributor data. Grid search still runs but excludes damp=True.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing


class ExogEts:
    def __init__(self, model, col: str) -> None:
        self._model = model
        self._col = col

    @classmethod
    def fit(cls, train_df: pd.DataFrame, col: str) -> "ExogEts":
        y = train_df.set_index("ds")[col]
        y.index.freq = "MS"
        best, best_aic = None, np.inf
        # damp=False only — opt/ets_playground finding: damped adds noise on this data
        for trend in ["add", "mul", None]:
            for seas in ["add", "mul", None]:
                try:
                    if seas is None:
                        m = ExponentialSmoothing(
                            y, trend=trend, seasonal=None, damped_trend=False
                        ).fit(optimized=True)
                    else:
                        m = ExponentialSmoothing(
                            y, trend=trend, seasonal=seas, seasonal_periods=12,
                            damped_trend=False,
                        ).fit(optimized=True)
                    aic = getattr(m, "aic", np.inf)
                    if aic < best_aic:
                        best_aic, best = aic, m
                except Exception:
                    continue
        if best is None:
            best = ExponentialSmoothing(
                y, trend="add", seasonal="add", seasonal_periods=12
            ).fit(optimized=True)
        return cls(best, col)

    def forecast(self, steps: int, future_idx: pd.DatetimeIndex) -> pd.DataFrame:
        pred = self._model.forecast(steps)
        return pd.DataFrame({"ds": pd.DatetimeIndex(future_idx), self._col: pred.values})
