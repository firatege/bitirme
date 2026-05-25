"""Per-process config. Defaults mirror scripts/model_v3.py; env vars can override.

Per-request overrides are also supported via the `config` field of ForecastColdRequest /
ForecastWarmRequest — route handlers build a RequestConfig by merging request payload
on top of the process-level defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import pandas as pd


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v is not None and v != "" else default


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class WorkerConfig:
    # Paths
    model_dir: Path = Path(_env("MODEL_DIR", "/app/models"))

    # Dates (strings in env; parsed to Timestamp)
    val_start: pd.Timestamp = pd.Timestamp(_env("VAL_START", "2024-08-01"))
    val_end: pd.Timestamp = pd.Timestamp(_env("VAL_END", "2025-01-01"))
    test_start: pd.Timestamp = pd.Timestamp(_env("TEST_START", "2025-02-01"))
    test_end: pd.Timestamp = pd.Timestamp(_env("TEST_END", "2025-08-01"))
    test_end_short: pd.Timestamp = pd.Timestamp(_env("TEST_END_SHORT", "2025-04-01"))

    # Speed preset
    fast_mode: bool = _env_bool("FAST_MODE", True)

    # Global EXOG whitelist
    exog_methods_enabled_global: tuple[str, ...] = ("ETS", "ML-Exog XGB", "Prophet", "SARIMA", "Ensemble")
    exog_per_var_selection: bool = _env_bool("EXOG_PER_VAR_SELECTION", True)

    # Bootstrap
    b_boot: int = _env_int("B_BOOT", 150)
    boot_mode: str = _env("BOOT_MODE", "parametric")  # auto | parametric | smooth | resample

    # Random seed + sklearn random_state
    seed: int = _env_int("SEED", 1337)
    random_state: int = _env_int("RANDOM_STATE", 42)

    # sklearn/XGBoost thread budget per SKU.
    # With MAX_PARALLEL_JOBS=8 on a 20-thread CPU: 8×3=24 — light oversubscription,
    # far better than 8×20=160 with n_jobs=-1.
    sklearn_n_jobs: int = _env_int("SKLEARN_N_JOBS", 3)

    # ROCV / Refit
    enable_refit: bool = _env_bool("ENABLE_REFIT", True)
    refit_tail_k: int = _env_int("REFIT_TAIL_K", 2)
    refit_rollback_eps: float = _env_float("REFIT_ROLLBACK_EPS", 0.0)

    # Intermittent
    enable_intermittent: bool = _env_bool("ENABLE_INTERMITTENT", True)
    im_methods: tuple[str, ...] = ("TSB",)
    intermittent_alpha: float = _env_float("INTERMITTENT_ALPHA", 0.10)
    intermittent_selector: str = _env("INTERMITTENT_SELECTOR", "auto")  # auto | all | none
    dense_override_last_n: int = _env_int("DENSE_OVERRIDE_LAST_N", 6)
    tsb_near_zero_eps: float = _env_float("TSB_NEAR_ZERO_EPS", 1e-6)
    # Zero-ratio threshold above which TSB is forced as winner (bypasses MAE competition).
    # Motivation: RF/XGB are biased high on >50% zero series; TSB's level estimate is safer.
    # Months with no sales before test_start → skip all ML, emit zero forecast.
    dead_sku_window_mo: int = _env_int("DEAD_SKU_WINDOW_MO", 12)
    intermittent_force_zero_ratio: float = _env_float("INTERMITTENT_FORCE_ZERO_RATIO", 0.50)

    # Bias correction: scale predictions by val-period mean(y)/mean(yhat).
    bias_correction_enabled: bool = _env_bool("BIAS_CORRECTION", True)
    # Max multiplicative factor (factor clipped to [1/clip, clip]).
    bias_correction_clip: float = _env_float("BIAS_CORRECTION_CLIP", 3.0)

    # Probe → escalate
    probe_methods: tuple[str, ...] = ("CarryForward", "ETS", "Intermittent", "ML-Exog RF")
    escalate_methods_dense: tuple[str, ...] = ("ML-Exog XGB",)
    escalate_methods_seasonal: tuple[str, ...] = ("Prophet",)
    delta_better_than_baseline: float = _env_float("DELTA_BETTER_THAN_BASELINE", 0.02)
    baseline_kind: str = _env("BASELINE_KIND", "seasonal_naive")  # seasonal_naive | ma3

    # Drift gate
    drift_eps: float = _env_float("DRIFT_EPS", 0.20)

    # Y feature columns (order matters — RF/XGB use .fit(X[FEATURES], y))
    features_y: tuple[str, ...] = (
        "orders", "stock",
        "orders_lag1", "orders_lag3",
        "stock_lag1", "stock_lag3",
        "y_lag1", "orders_ratio",
        "month", "year",
    )

    # EXOG feature columns for ML-Exog
    features_exog: tuple[str, ...] = ("lag1", "lag3", "month", "year")

    # Generate plots (thesis-oriented; off by default in service mode)
    generate_plots: bool = _env_bool("GENERATE_PLOTS", False)

    # GPU (XGBoost)
    use_gpu_xgb: bool = _env_bool("USE_GPU_XGB", False)


# Singleton accessor; lazy so tests can override env and reinit.
_cached: Optional[WorkerConfig] = None


def get_config() -> WorkerConfig:
    global _cached
    if _cached is None:
        _cached = WorkerConfig()
    return _cached


def reset_config_cache() -> None:
    """Test helper — re-reads env on next get_config() call."""
    global _cached
    _cached = None
