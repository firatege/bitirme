"""YXGBoost — XGBoost wrapper for Y-model. HAVE_XGB=False graceful fallback."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from services.worker.config import get_config

try:
    from xgboost import XGBRegressor
    HAVE_XGB = True
except ImportError:
    HAVE_XGB = False


class YXGBoost:
    def __init__(self, model, params: dict) -> None:
        self._model = model
        self._params = params

    @classmethod
    def fit(cls, X: pd.DataFrame, y: np.ndarray, params: dict) -> "YXGBoost | None":
        if not HAVE_XGB:
            return None
        cfg = get_config()
        kwargs: dict = {
            "n_estimators": params.get("n_estimators", 400),
            "learning_rate": params.get("learning_rate", 0.08),
            "max_depth": params.get("max_depth", 3),
            "subsample": params.get("subsample", 0.9),
            "colsample_bytree": params.get("colsample_bytree", 0.9),
            "reg_lambda": params.get("reg_lambda", 1.2),
            "random_state": cfg.random_state,
            "verbosity": 0,
            "nthread": cfg.sklearn_n_jobs,
        }
        if cfg.use_gpu_xgb:
            kwargs["tree_method"] = "hist"
            kwargs["device"] = "cuda"
        m = XGBRegressor(**kwargs)
        m.fit(X.to_numpy() if hasattr(X, "to_numpy") else X, y, verbose=False)
        return cls(m, params)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self._model.predict(X.to_numpy() if hasattr(X, "to_numpy") else X)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    def hyperparams(self) -> dict:
        return dict(self._params)

    @classmethod
    def load(cls, path: Path) -> "YXGBoost":
        return joblib.load(path)
