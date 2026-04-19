"""Stockout probability + cumulative demand quantile.

Mirrors scripts/model_v3.py `stockout_probability` + `cum_demand_quantile` (lines 778-796).
"""
from __future__ import annotations

import numpy as np


def stockout_probability(start_stock: float, sims: np.ndarray) -> tuple[float, float, float]:
    """Probability that cumulative demand exceeds `start_stock` within 3 months / 6 months,
    plus expected time-to-stockout (months). `sims` shape: (H, B).
    """
    sims = np.maximum(0.0, sims)
    cum = np.cumsum(sims, axis=0)
    tts = np.full(sims.shape[1], np.nan)
    for b in range(sims.shape[1]):
        idx = np.where(cum[:, b] >= start_stock)[0]
        if idx.size > 0:
            tts[b] = idx[0] + 1
    p3 = float(np.mean(np.nan_to_num(tts, nan=np.inf) <= 3))
    p6 = float(np.mean(np.nan_to_num(tts, nan=np.inf) <= 6))
    e_t = float(np.nanmean(tts)) if np.any(~np.isnan(tts)) else float("nan")
    return p3, p6, e_t


def cum_demand_quantile(sims: np.ndarray, months: int, q: float = 0.5) -> float:
    months = int(months)
    if months <= 0:
        return 0.0
    sims = np.maximum(0.0, sims)
    sums = np.sum(sims[:months, :], axis=0)
    return float(np.nanquantile(sums, q))
