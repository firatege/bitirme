"""Y-model wrapper tests — RF always, XGB when installed."""
from __future__ import annotations

import numpy as np
import pytest

from services.worker.config import get_config
from services.worker.models.y_rf import YRandomForest
from services.worker.models.y_xgb import HAVE_XGB, YXGBoost


def _train_frame(panel_dense):
    from services.worker.features.pipeline import prep_features_y
    return prep_features_y(panel_dense.copy(), causal=False)


def test_y_rf_fit_predict_save_load(tmp_path, panel_dense):
    df = _train_frame(panel_dense)
    feats = list(get_config().features_y)
    params = {"n_estimators": 50, "max_depth": 6, "min_samples_split": 2, "min_samples_leaf": 1}
    m = YRandomForest.fit(df[feats], df["y"].to_numpy(), params)
    pred = m.predict(df[feats])
    assert pred.shape == (len(df),)
    assert m.hyperparams() == params
    p = tmp_path / "rf.joblib"
    m.save(p)
    m2 = YRandomForest.load(p)
    pred2 = m2.predict(df[feats])
    assert np.allclose(pred, pred2)


@pytest.mark.skipif(not HAVE_XGB, reason="xgboost not installed")
def test_y_xgb_fit_predict_save_load(tmp_path, panel_dense):
    df = _train_frame(panel_dense)
    feats = list(get_config().features_y)
    params = {"n_estimators": 50, "learning_rate": 0.1, "max_depth": 3,
              "subsample": 0.9, "colsample_bytree": 0.9, "reg_lambda": 1.0}
    m = YXGBoost.fit(df[feats], df["y"].to_numpy(), params)
    pred = m.predict(df[feats])
    assert pred.shape == (len(df),)
    p = tmp_path / "xgb.joblib"
    m.save(p)
    m2 = YXGBoost.load(p)
    pred2 = m2.predict(df[feats])
    assert np.allclose(pred, pred2)
