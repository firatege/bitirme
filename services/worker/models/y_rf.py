"""YRandomForest — sklearn RF wrapper for Y-model."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from services.worker.config import get_config


class YRandomForest:
    def __init__(self, model: RandomForestRegressor, params: dict) -> None:
        self._model = model
        self._params = params

    @classmethod
    def fit(cls, X: pd.DataFrame, y: np.ndarray, params: dict) -> "YRandomForest":
        cfg = get_config()
        p = {
            "n_estimators": params.get("n_estimators", 300),
            "max_depth": params.get("max_depth", 8),
            "min_samples_split": params.get("min_samples_split", 2),
            "min_samples_leaf": params.get("min_samples_leaf", 1),
            "random_state": cfg.random_state,
            "n_jobs": cfg.sklearn_n_jobs,
        }
        rf = RandomForestRegressor(**p)
        rf.fit(X, y)
        return cls(rf, params)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self._model.predict(X)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    def hyperparams(self) -> dict:
        return dict(self._params)

    @classmethod
    def load(cls, path: Path) -> "YRandomForest":
        return joblib.load(path)
