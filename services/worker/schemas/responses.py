"""Response shapes returned by the Python worker.

These Pydantic types mirror the Rust controller's serde structs in
controller/src/types.rs. Rust deserializes and writes the seven tables in one transaction.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class WinningCombo(BaseModel):
    horizon: str                     # 'Full' | 'Short3'
    exog: str
    y_variant: str                   # 'RF' | 'XGB' | 'Y-ENS' | 'TSB' | ...
    phase: str                       # 'PRE' | 'REFIT'
    mae: float
    rmse: float
    mape: Optional[float] = None
    w_rf: Optional[float] = None
    w_xgb: Optional[float] = None
    p_stockout_3m: Optional[float] = None
    p_stockout_6m: Optional[float] = None
    e_t_stockout_mo: Optional[float] = None


class CombinationRow(BaseModel):
    horizon: str
    exog: str
    y_variant: str
    phase: str
    mae: float
    rmse: Optional[float] = None
    mape: Optional[float] = None
    w_rf: Optional[float] = None
    w_xgb: Optional[float] = None
    p_stockout_3m: Optional[float] = None
    p_stockout_6m: Optional[float] = None
    e_t_stockout_mo: Optional[float] = None


class ModelRow(BaseModel):
    model_slot: str                  # 'rf_y_pre' | 'xgb_y_pre' | 'prophet_orders' | ...
    column_target: str               # 'y' | 'orders' | 'stock'
    hyperparams: dict
    blob_uri: str
    fit_seconds: float


class ExogSelectionRow(BaseModel):
    column_target: str               # 'orders' | 'stock'
    chosen_method: str
    val_mae: float


class ValResidualRow(BaseModel):
    exog: str
    y_variant: str
    residuals: list[float]


class RecommendationRow(BaseModel):
    starting_stock: float
    t_check: int
    h_cover: int
    q_target: float
    moq: float
    lot_size: float
    cum_demand_q: float
    order_qty_raw: float
    order_qty_rounded: float


class PredictionRow(BaseModel):
    """Per-month prediction of the winning combination.

    `y` is the realized observation when `ds` falls inside the panel; for
    future months past the panel's last observation it is None. The PI bands
    come from the Laplace bootstrap and may be None for edge cases where
    the bootstrap is skipped (e.g. intermittent with zero residuals)."""
    ds: str                          # ISO date 'YYYY-MM-DD'
    y: Optional[float] = None
    yhat: float
    pi80_lo: Optional[float] = None
    pi80_hi: Optional[float] = None
    pi95_lo: Optional[float] = None
    pi95_hi: Optional[float] = None


class ForecastResult(BaseModel):
    sku: str
    run_id: int
    mode: str                        # 'cold' | 'warm' | 'warm_with_refit'
    winning: WinningCombo
    combinations: list[CombinationRow] = Field(default_factory=list)
    models: list[ModelRow] = Field(default_factory=list)
    exog_selection: list[ExogSelectionRow] = Field(default_factory=list)
    val_residuals: list[ValResidualRow] = Field(default_factory=list)
    predictions: list[PredictionRow] = Field(default_factory=list)
    recommendation: RecommendationRow


class DriftCheckResult(BaseModel):
    drift_triggered: bool
    new_mae: float
    cached_mae: float
    threshold: float
