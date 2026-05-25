"""ExogProphet — Prophet wrapper for orders/stock EXOG forecasting."""
from __future__ import annotations

import pandas as pd

try:
    from prophet import Prophet
    HAVE_PROPHET = True
except ImportError:
    HAVE_PROPHET = False


class ExogProphet:
    def __init__(self, model, col: str) -> None:
        self._model = model
        self._col = col

    @classmethod
    def fit(cls, train_df: pd.DataFrame, col: str) -> "ExogProphet":
        if not HAVE_PROPHET:
            raise RuntimeError("prophet not installed")
        m = Prophet(yearly_seasonality=True, weekly_seasonality=False,
                    daily_seasonality=False, uncertainty_samples=0)
        m.fit(train_df.rename(columns={col: "y"}))
        return cls(m, col)

    def forecast(self, steps: int) -> pd.DataFrame:
        fut = self._model.make_future_dataframe(periods=steps, freq="MS")
        pred = self._model.predict(fut)[["ds", "yhat"]].tail(steps)
        return pred.rename(columns={"yhat": self._col})
