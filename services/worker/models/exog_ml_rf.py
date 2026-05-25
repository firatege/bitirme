"""MLExogRF — RandomForest for recursive orders/stock forecasting."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from services.worker.config import get_config
from services.worker.features.lags import make_exog_frame


class MLExogRF:
    def __init__(self, model: RandomForestRegressor, col: str) -> None:
        self._model = model
        self._col = col

    @classmethod
    def train(cls, df: pd.DataFrame, col: str, cutoff: pd.Timestamp) -> "MLExogRF | None":
        cfg = get_config()
        d = make_exog_frame(df[df["ds"] < cutoff], col).dropna()
        if d.empty:
            return None
        feats = list(cfg.features_exog)
        n_est = 300 if cfg.fast_mode else 400
        rf = RandomForestRegressor(
            n_estimators=n_est, max_depth=8,
            min_samples_split=2, min_samples_leaf=1,
            random_state=cfg.random_state, n_jobs=cfg.sklearn_n_jobs,
        )
        rf.fit(d[feats], d[col])
        return cls(rf, col)

    def recursive_forecast(
        self, hist_df: pd.DataFrame, start_ds: pd.Timestamp, end_ds: pd.Timestamp
    ) -> pd.DataFrame:
        cfg = get_config()
        feats = list(cfg.features_exog)
        col = self._col
        fut = pd.date_range(start_ds, end_ds, freq="MS")
        full = hist_df[["ds", col]].sort_values("ds").copy()
        out = []
        for ds in fut:
            tmp = make_exog_frame(full, col)
            row = tmp[tmp["ds"] == ds][feats]
            if row.empty:
                last = full[col].iloc[-1] if len(full) else 0.0
                lag3 = full[col].iloc[-3] if len(full) >= 3 else last
                row = pd.DataFrame({
                    "lag1": [last], "lag3": [lag3],
                    "month": [ds.month], "year": [ds.year],
                })
            yhat = max(0.0, float(self._model.predict(row)[0]))
            out.append({"ds": ds, col: yhat})
            full = pd.concat(
                [full, pd.DataFrame({"ds": [ds], col: [yhat]})], ignore_index=True
            )
        return pd.DataFrame(out)

    def save(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"col": self._col, "model": self._model}, path)

    @classmethod
    def load(cls, path: Path) -> "MLExogRF":
        blob = joblib.load(path)
        return cls(blob["model"], blob["col"])
