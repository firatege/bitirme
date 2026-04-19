"""Request shapes for the Python worker endpoints.

These Pydantic types mirror the Rust controller's serde structs in
controller/src/types.rs. Keep field names and types in sync.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class PanelRow(BaseModel):
    ds: date
    y: float
    orders: float
    stock: float


class ParamsRow(BaseModel):
    """Policy parameters for a single SKU — mirrors a row of sku_config."""

    t_check: int
    h_cover: int
    q_target: float
    lead_time_mo: int = 0
    moq: float = 0.0
    lot_size: float = 1.0
    starting_stock_override: Optional[float] = None


class RequestConfigOverride(BaseModel):
    """Optional per-request override of process-level WorkerConfig fields.

    Only the fields that can change run-to-run; dates, grid settings, seeds stay at process level.
    """

    fast_mode: Optional[bool] = None
    b_boot: Optional[int] = None
    boot_mode: Optional[str] = None
    enable_refit: Optional[bool] = None
    enable_intermittent: Optional[bool] = None
    exog_per_var_selection: Optional[bool] = None
    use_gpu_xgb: Optional[bool] = None


class ModelHyperparams(BaseModel):
    """Opaque JSON for any model's hyperparameters.

    Keys are the constructor kwargs (e.g. n_estimators, max_depth). Stored as JSONB in Postgres.
    """

    params: dict = Field(default_factory=dict)


class CachedModelRef(BaseModel):
    model_slot: str                  # matches the model_slot enum in Postgres
    column_target: str               # 'y' | 'orders' | 'stock'
    hyperparams: dict
    blob_uri: str


class CachedExogSelection(BaseModel):
    column_target: str               # 'orders' | 'stock'
    chosen_method: str               # 'ETS' | 'ML-Exog RF' | ...
    val_mae: float


class CachedValResidual(BaseModel):
    exog: str
    y_variant: str                   # 'RF' | 'XGB' | 'Y-ENS' | ...
    residuals: list[float]


class CachedSpec(BaseModel):
    """Warm-path inputs assembled by Rust from prior-run DB state."""

    prior_run_id: int
    winning_horizon: str             # 'Full' | 'Short3'
    winning_exog: str
    winning_y_variant: str
    winning_phase: str               # 'PRE' | 'REFIT'
    winning_w_rf: Optional[float] = None
    winning_w_xgb: Optional[float] = None
    models: list[CachedModelRef]
    exog_selection: list[CachedExogSelection]
    val_residuals: list[CachedValResidual]


class ForecastColdRequest(BaseModel):
    sku: str
    run_id: int
    panel_rows: list[PanelRow]
    params_row: ParamsRow
    blob_dir: str                    # absolute path inside the container (Rust supplies it)
    config: Optional[RequestConfigOverride] = None


class ForecastWarmRequest(ForecastColdRequest):
    cached_spec: CachedSpec


class DriftCheckRequest(BaseModel):
    sku: str
    panel_rows: list[PanelRow]
    params_row: ParamsRow
    cached_spec: CachedSpec
