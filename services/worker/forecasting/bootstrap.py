"""Laplace bootstrap prediction intervals (80%, 95%) + simulation matrix for stockout
probability calculations.

Mirrors scripts/model_v3.py `add_bootstrap_intervals` (line 731).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.worker.config import get_config


def _rng() -> np.random.Generator:
    return np.random.default_rng(get_config().seed)


def add_bootstrap_intervals(
    pred_df: pd.DataFrame,
    residuals: np.ndarray | list[float],
    B: int | None = None,
    mode: str | None = None,
    clamp_nonneg: bool = True,
) -> tuple[pd.DataFrame, np.ndarray]:
    cfg = get_config()
    B = int(B if B is not None else cfg.b_boot)
    mode = mode or cfg.boot_mode
    rng = _rng()

    yhat = pred_df["yhat"].to_numpy().reshape(-1, 1)
    res = np.asarray(residuals, dtype=float)
    res = res[np.isfinite(res)]
    n = res.size
    if n > 0:
        med = np.median(res)
        res_c = res - med
        mad = np.median(np.abs(res_c))
    else:
        res_c = np.array([], dtype=float)
        mad = np.nan
    b_lap = (
        (mad / np.sqrt(2))
        if (mad is not None and np.isfinite(mad) and mad > 0)
        else (np.std(res_c) if n > 1 else 1.0)
    )
    b_lap = max(float(b_lap), 1e-6)

    if mode == "auto":
        use_smooth = (n < 24) or (len(np.unique(np.round(res_c, 6))) <= 8)
        mode = "smooth" if use_smooth else "resample"

    if mode == "parametric":
        noise = rng.laplace(0.0, b_lap, size=(len(pred_df), B))
    elif mode == "smooth":
        if n == 0:
            noise = rng.laplace(0.0, 0.5 * b_lap, size=(len(pred_df), B))
        else:
            idx = rng.integers(0, n, size=(len(pred_df), B))
            base = res_c[idx]
            jitter = rng.laplace(0.0, 0.25 * b_lap, size=(len(pred_df), B))
            noise = base + jitter
    else:
        noise = (
            rng.laplace(0.0, b_lap, size=(len(pred_df), B))
            if n == 0
            else res_c[rng.integers(0, n, size=(len(pred_df), B))]
        )

    sims = yhat + noise
    if clamp_nonneg:
        sims = np.maximum(0.0, sims)
    lo80 = np.nanquantile(sims, 0.10, axis=1)
    hi80 = np.nanquantile(sims, 0.90, axis=1)
    lo95 = np.nanquantile(sims, 0.025, axis=1)
    hi95 = np.nanquantile(sims, 0.975, axis=1)
    yh = yhat.ravel()
    lo80 = np.minimum(lo80, yh)
    hi80 = np.maximum(hi80, yh)
    lo95 = np.minimum(lo95, yh)
    hi95 = np.maximum(hi95, yh)
    out = pred_df.copy()
    out["pi80_lo"] = lo80
    out["pi80_hi"] = hi80
    out["pi95_lo"] = lo95
    out["pi95_hi"] = hi95
    return out, sims
