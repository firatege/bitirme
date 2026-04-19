"""Probe → Escalate decision: runs cheap candidates first, escalates if none beats the
baseline by a configured margin.

Mirrors scripts/model_v3.py (lines 1012-1061) as reusable pure logic; actual EXOG fitting
is delegated to services.worker.forecasting.exog.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.worker.config import get_config
from services.worker.models.intermittent import select_intermittent


def should_dense_override(d: pd.DataFrame, test_start: pd.Timestamp) -> bool:
    """Last-N-months activity vs TSB near-zero: if recently selling but TSB ~= 0,
    override to dense EXOG. Mirrors scripts/model_v3.py `should_dense_override` (line 652)."""
    from services.worker.models.intermittent import predict_intermittent

    cfg = get_config()
    last_n = d[d["ds"] < test_start].tail(cfg.dense_override_last_n)
    recent_nonzero = (pd.to_numeric(last_n["y"], errors="coerce").fillna(0.0) > 0).any()
    tsb_pred = predict_intermittent(
        d[d["ds"] < test_start][["ds", "y"]],
        test_start,
        test_start,
        "TSB",
        cfg.intermittent_alpha,
    )
    near_zero = float(tsb_pred["yhat"].iloc[0]) <= cfg.tsb_near_zero_eps
    return bool(recent_nonzero and near_zero)


def build_probe_list(d: pd.DataFrame) -> list[str]:
    """Filter the configured PROBE_METHODS down to what applies to this series.

    - Drops 'Intermittent' if the series is dense (unless selector=='all').
    - Filters method names against the global EXOG whitelist + ML-Exog family.
    """
    cfg = get_config()
    probe = list(cfg.probe_methods)
    allowed = set(cfg.exog_methods_enabled_global) | {"ML-Exog RF", "ML-Exog XGB"}
    probe = [m for m in probe if (m == "Intermittent") or (m in allowed)]
    if not select_intermittent(d, cfg.intermittent_selector):
        probe = [m for m in probe if m != "Intermittent"]
    return probe


def should_escalate(probe_best_mae: float, baseline_mae: float) -> bool:
    """Escalate if no probe candidate beats the baseline by the configured margin."""
    cfg = get_config()
    if not np.isfinite(probe_best_mae):
        return True
    return probe_best_mae > baseline_mae * (1.0 - cfg.delta_better_than_baseline)


def build_escalate_list(d: pd.DataFrame, sku: str, critical_skus: set[str]) -> list[str]:
    cfg = get_config()
    if select_intermittent(d, cfg.intermittent_selector) and not should_dense_override(
        d, cfg.test_start
    ):
        return []
    extra = list(cfg.escalate_methods_dense)
    if (d["ds"].nunique() >= 30) and (sku in critical_skus):
        for m in cfg.escalate_methods_seasonal:
            if m not in extra:
                extra.append(m)
    return extra
