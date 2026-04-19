"""OMS ordering policy: MOQ / lot rounding + starting stock inference."""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd


def infer_starting_stock(
    df_raw: pd.DataFrame, test_start: pd.Timestamp, override: Optional[float] = None
) -> float:
    if override is not None and pd.notna(override):
        return float(override)
    prev = df_raw[df_raw["ds"] < test_start].tail(1)
    if "stock" in prev.columns and len(prev):
        return float(max(0.0, prev["stock"].iloc[0]))
    return 0.0


def round_moq_lot(q: float, moq: float = 0.0, lot: float = 1.0) -> float:
    """Round up an order quantity to the MOQ floor and lot-size step."""
    q = max(0.0, q)
    if q > 0 and q < moq:
        q = moq
    lot = lot if lot and lot > 0 else 1.0
    return float(math.ceil(q / lot) * lot)
