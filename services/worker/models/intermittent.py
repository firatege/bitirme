"""Intermittent demand: TSB / Croston / SBA + series classifier."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _croston(y: np.ndarray, alpha: float) -> float:
    z = p = 0.0
    q = 1
    init = False
    for x in y:
        if x > 0:
            if not init:
                z, p, init = x, q, True
            else:
                z = z + alpha * (x - z)
                p = p + alpha * (q - p)
            q = 1
        else:
            q += 1
    if not init or p <= 0:
        return 0.0
    return z / p


def _sba(y: np.ndarray, alpha: float) -> float:
    return _croston(y, alpha) * (1 - alpha / 2.0)


def _tsb(y: np.ndarray, alpha: float) -> float:
    z = p = 0.0
    init = False
    for x in y:
        occ = 1.0 if x > 0 else 0.0
        if not init:
            z = x if x > 0 else z
            p = occ
            init = True
        else:
            p = p + alpha * (occ - p)
            if x > 0:
                z = z + alpha * (x - z)
    return max(0.0, z * p)


def predict_intermittent(
    hist_df: pd.DataFrame,
    start_ds: pd.Timestamp,
    end_ds: pd.Timestamp,
    method: str = "TSB",
    alpha: float = 0.10,
) -> pd.DataFrame:
    fut = pd.date_range(start_ds, end_ds, freq="MS")
    y = pd.to_numeric(hist_df["y"], errors="coerce").fillna(0.0).to_numpy()
    if method == "Croston":
        f = _croston(y, alpha)
    elif method == "SBA":
        f = _sba(y, alpha)
    else:
        f = _tsb(y, alpha)
    f = max(0.0, float(f))
    return pd.DataFrame({"ds": fut, "yhat": [f] * len(fut)})


def select_intermittent(d: pd.DataFrame, selector: str = "auto") -> bool:
    if selector == "none":
        return False
    if selector == "all":
        return True
    ser = pd.to_numeric(d["y"], errors="coerce").fillna(0.0)
    demand = (ser != 0).astype(int)
    if demand.sum() == 0:
        return True
    gaps = np.diff(
        np.where(np.concatenate([[True], demand.to_numpy().astype(bool), [True]]))[0]
    ) - 1
    adi = (gaps[gaps > 0].mean() if (gaps > 0).any() else 0) + 1
    zero_ratio = (ser == 0).mean()
    return bool((adi > 1.32) or (zero_ratio > 0.40))
