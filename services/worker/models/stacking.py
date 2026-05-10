"""NNLS-based stacking weights for Y-ENS and EXOG combination.

Pure numpy. Mirrors scripts/model_v3.py (lines 478-584).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def project_simplex(w: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """Project `w` onto the non-negative simplex (w >= 0, sum = 1)."""
    u = np.sort(np.maximum(w, 0))[::-1]
    css = np.cumsum(u)
    rho = np.where(u > (css - 1) / (np.arange(len(u)) + 1))[0]
    if len(rho) == 0:
        return np.ones_like(w) / len(w)
    rho = rho[-1]
    theta = (css[rho] - 1) / (rho + 1.0)
    w = np.maximum(w - theta, 0)
    s = w.sum()
    return (w / s) if s > eps else (np.ones_like(w) / len(w))


def nnls_ridge(A: np.ndarray, y: np.ndarray, alpha: float = 0.0, iters: int = 800) -> np.ndarray:
    """Projected-gradient NNLS with ridge regularization, constrained to the simplex."""
    A = np.asarray(A, dtype=float)
    y = np.asarray(y, dtype=float)
    K = A.shape[1]
    if K == 1:
        return np.array([1.0])
    L = np.linalg.norm(A, 2) ** 2 + alpha + 1e-6
    step = 1.0 / L
    AT = A.T
    w = np.ones(K) / K
    for _ in range(iters):
        grad = 2 * (AT @ (A @ w - y)) + 2 * alpha * w
        w = project_simplex(w - step * grad)
    return w


def nnls_ridge_weighted(
    A: np.ndarray, y: np.ndarray, sample_w: np.ndarray, alpha: float = 0.0, iters: int = 800
) -> np.ndarray:
    """Sample-weighted NNLS+ridge. Weights become row-scalings in a standard least-squares equivalent."""
    sw = np.asarray(sample_w, dtype=float).reshape(-1)
    sw = np.where(np.isfinite(sw) & (sw > 0), sw, 1.0)
    r = np.sqrt(sw).reshape(-1, 1)
    A_w = A * r
    y_w = y * r.ravel()
    return nnls_ridge(A_w, y_w, alpha=alpha, iters=iters)


def fit_y_ens_weights(
    val_yhat_rf: np.ndarray, val_yhat_xgb: np.ndarray, val_truth: np.ndarray, alpha: float = 0.0
) -> tuple[float, float]:
    """Fit (w_rf, w_xgb) on VAL for the Y-ENS stack. Returns simplex-normalized pair."""
    A = np.column_stack([val_yhat_rf, val_yhat_xgb])
    w = nnls_ridge(A, val_truth, alpha=alpha)
    return float(w[0]), float(w[1])


def fit_exog_nnls_weights(
    exog_dict: dict[str, pd.DataFrame],
    df_true: pd.DataFrame,
    alpha: float = 0.0,
) -> dict[str, dict[str, float]]:
    """NNLS weights per variable (orders, stock) over a dict of candidate EXOG tables.

    Mirrors scripts/model_v3.py `fit_nnls_weights_on_val` (line 535).
    """
    names = list(exog_dict.keys())
    base = df_true[["ds"]].copy()
    A_o_cols, A_s_cols = [], []
    for nm in names:
        tmp = base.merge(exog_dict[nm][["ds", "orders", "stock"]], on="ds", how="left")
        o = pd.to_numeric(tmp["orders"], errors="coerce").ffill().bfill().fillna(0.0).to_numpy()
        s = pd.to_numeric(tmp["stock"], errors="coerce").ffill().bfill().fillna(0.0).to_numpy()
        A_o_cols.append(o)
        A_s_cols.append(s)
    A_o = np.column_stack(A_o_cols)
    A_s = np.column_stack(A_s_cols)
    y_o = pd.to_numeric(df_true["orders"], errors="coerce").ffill().bfill().fillna(0.0).to_numpy()
    y_s = pd.to_numeric(df_true["stock"], errors="coerce").ffill().bfill().fillna(0.0).to_numpy()
    w_o = nnls_ridge(A_o, y_o, alpha=alpha)
    w_s = nnls_ridge(A_s, y_s, alpha=alpha)
    return {
        "orders": {names[i]: float(w_o[i]) for i in range(len(names))},
        "stock": {names[i]: float(w_s[i]) for i in range(len(names))},
    }
