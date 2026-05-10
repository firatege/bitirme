"""ExogCarryForward — last known value forward fill for orders/stock.

Ablation finding (opt/ablation_playground.py): carry-forward beats ETS EXOG
by ~4.3% MAE on average across SKUs. ETS injects noise into recursive Y
forecasting when orders/stock series are erratic. Carry-forward is the
no-exog baseline that simply holds the last observed value constant.
"""
from __future__ import annotations

import pandas as pd


def build_exog_carry_forward(
    df_all: pd.DataFrame,
    start_ds: pd.Timestamp,
    end_ds: pd.Timestamp,
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    """Return orders/stock table where each column is the last known value before cutoff."""
    fut = pd.date_range(start_ds, end_ds, freq="MS")
    hist = df_all[df_all["ds"] < cutoff]
    out = pd.DataFrame({"ds": fut})
    for col in ("orders", "stock"):
        last_val = 0.0
        if col in hist.columns:
            valid = pd.to_numeric(hist[col], errors="coerce").dropna()
            if not valid.empty:
                last_val = float(valid.iloc[-1])
        out[col] = last_val
    return out
