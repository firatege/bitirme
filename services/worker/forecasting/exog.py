"""EXOG-table construction: orders/stock forecasts produced by one of the EXOG families.

Dispatches by method name. Mirrors scripts/model_v3.py
`_build_exog_by_method` / `build_exog_univar` / `build_exog_ml` / `build_exog_inverse`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from services.worker.features.winsorize import nonneg, smooth_causal_ma, winsorize_series
from services.worker.models.exog_ets import ExogEts
from services.worker.models.exog_ml_rf import MLExogRF
from services.worker.models.exog_ml_xgb import MLExogXGB
from services.worker.models.exog_prophet import ExogProphet, HAVE_PROPHET
from services.worker.models.exog_sarima import ExogSarima


EXOG_COLUMNS = ("orders", "stock")


@dataclass
class FittedExog:
    """A fitted EXOG model plus its forecast table for one or both columns."""

    method: str
    column_models: dict  # {col: fitted model instance}
    forecast: pd.DataFrame  # ds + orders/stock columns


def _post_exog(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    for c in EXOG_COLUMNS:
        if c in d.columns:
            d[c] = smooth_causal_ma(d[c], 3)
            d[c] = winsorize_series(d[c], 0.05, 0.95)
            d[c] = nonneg(d[c])
    return d


def build_exog_univariate(
    df_all: pd.DataFrame,
    start_ds: pd.Timestamp,
    end_ds: pd.Timestamp,
    cutoff: pd.Timestamp,
    method: str,
) -> FittedExog:
    """method ∈ {'prophet', 'sarima', 'ets'}. Per-column fit + forecast, glued on `ds`."""
    fut = pd.date_range(start_ds, end_ds, freq="MS")
    out = pd.DataFrame({"ds": fut})
    fitted: dict = {}
    steps = len(fut)
    for col in EXOG_COLUMNS:
        s = df_all[["ds", col]].dropna().sort_values("ds")
        s = s[s["ds"] < cutoff]
        if s.empty:
            out[col] = 0.0
            continue
        try:
            if method == "prophet":
                if not HAVE_PROPHET:
                    tmp = pd.DataFrame({"ds": fut, col: np.nan})
                else:
                    m = ExogProphet.fit(s, col)
                    fitted[col] = m
                    tmp = m.forecast(steps)
            elif method == "sarima":
                m = ExogSarima.fit(s, col)
                if m is None:
                    tmp = pd.DataFrame({"ds": fut, col: np.nan})
                else:
                    fitted[col] = m
                    tmp = m.forecast(steps, fut)
            else:  # ets
                m = ExogEts.fit(s, col)
                fitted[col] = m
                tmp = m.forecast(steps, fut)
        except Exception:
            tmp = pd.DataFrame({"ds": fut, col: np.nan})
        out = out.merge(tmp[["ds", col]], on="ds", how="left")
    return FittedExog(method=method, column_models=fitted, forecast=_post_exog(out))


def build_exog_ml(
    df_all: pd.DataFrame,
    start_ds: pd.Timestamp,
    end_ds: pd.Timestamp,
    cutoff: pd.Timestamp,
    learner: str = "rf",
) -> FittedExog:
    """learner ∈ {'rf', 'xgb'}. Per-column ML-Exog fit + recursive forward forecast."""
    fut = pd.date_range(start_ds, end_ds, freq="MS")
    out = pd.DataFrame({"ds": fut})
    fitted: dict = {}
    for col in EXOG_COLUMNS:
        hist = df_all[df_all["ds"] < cutoff][["ds", col]].copy()
        if hist.empty:
            out[col] = 0.0
            continue
        if learner == "rf":
            m = MLExogRF.train(df_all[["ds", col]], col, cutoff)
        else:
            m = MLExogXGB.train(df_all[["ds", col]], col, cutoff)
        if m is None:
            out[col] = 0.0
            continue
        fitted[col] = m
        fc = m.recursive_forecast(hist, start_ds, end_ds)
        out = out.merge(fc, on="ds", how="left")
    method_tag = "ML-Exog RF" if learner == "rf" else "ML-Exog XGB"
    return FittedExog(method=method_tag, column_models=fitted, forecast=_post_exog(out))


def build_exog_by_method(
    df_all: pd.DataFrame,
    start_ds: pd.Timestamp,
    end_ds: pd.Timestamp,
    cutoff: pd.Timestamp,
    method: str,
) -> FittedExog:
    """Single dispatcher by user-facing method name."""
    if method == "Prophet":
        return build_exog_univariate(df_all, start_ds, end_ds, cutoff, "prophet")
    if method == "SARIMA":
        return build_exog_univariate(df_all, start_ds, end_ds, cutoff, "sarima")
    if method == "ETS":
        return build_exog_univariate(df_all, start_ds, end_ds, cutoff, "ets")
    if method == "ML-Exog RF":
        return build_exog_ml(df_all, start_ds, end_ds, cutoff, "rf")
    if method == "ML-Exog XGB":
        return build_exog_ml(df_all, start_ds, end_ds, cutoff, "xgb")
    raise ValueError(f"Unknown EXOG method: {method}")


def build_hybrid_exog(
    df_all: pd.DataFrame,
    start_ds: pd.Timestamp,
    end_ds: pd.Timestamp,
    cutoff: pd.Timestamp,
    chosen_map: dict[str, str],
) -> tuple[pd.DataFrame, str]:
    """Per-column best-of EXOG merge. Returns (table, hybrid_tag)."""
    fut = pd.date_range(start_ds, end_ds, freq="MS")
    out = pd.DataFrame({"ds": fut})
    for col in EXOG_COLUMNS:
        m = chosen_map.get(col, "ETS")
        ex = build_exog_by_method(df_all, start_ds, end_ds, cutoff, m)
        out = out.merge(ex.forecast[["ds", col]], on="ds", how="left")
    tag = f"Hybrid[o={chosen_map.get('orders','ETS')},s={chosen_map.get('stock','ETS')}]"
    return _post_exog(out), tag
