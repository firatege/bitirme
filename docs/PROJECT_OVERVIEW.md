# Project Overview — Multi-SKU Sales Forecasting & Order Management System

> Turkish graduation thesis ("bitirme") project. Builds a per-SKU demand forecasting + automated purchase-order recommendation system for a Motul-like lubricant distributor. Uses time-series ensembles (Prophet + SARIMA + ETS) for exogenous variables, tree ensembles (Random Forest + XGBoost) for the target, NNLS stacking for blending, intermittent-demand models for sparse SKUs, bootstrap prediction intervals, and MOQ/lot-constrained order sizing.

A Turkish-language, thesis-style walkthrough already exists in [`proje_ozeti.md`](../proje_ozeti.md). A Turkish translation of this engineering doc is in [`PROJECT_OVERVIEW_TR.md`](PROJECT_OVERVIEW_TR.md). This document is the engineering-facing counterpart: file map, module responsibilities, data flow, and architecture.

---

## 1. What This Project Does

Given a monthly panel of `(sku, ds, y, orders, stock)` — realized sales, incoming purchase orders, and end-of-month stock — and a per-SKU policy file `sku_config.csv` (MOQ, lot size, coverage horizon, service-level quantile), the system answers two questions for every SKU:

1. **How many units will sell over the next 3 / 6 months?** — with an 80% and 95% prediction interval, not just a point estimate.
2. **How many units should we order now, and should we order at all this review cycle?** — respecting MOQ and lot-size rounding, driven by stockout probability against current on-hand stock.

The pipeline is built around the observation that naive sales forecasting is misleading when demand is **censored by stock** (a SKU that sold zero last month may have had high demand but no inventory). The model uses stock and incoming orders as exogenous regressors to recover the true demand signal.

---

## 2. Technology Stack

| Layer | Stack |
|---|---|
| Language | Python 3 (production scripts), Jupyter notebooks (research) |
| Data | `pandas`, `numpy` |
| Classical time series | `prophet`, `statsmodels` (`SARIMAX`, `ExponentialSmoothing`) |
| ML models | `scikit-learn` (`RandomForestRegressor`), `xgboost` (`XGBRegressor`) |
| Intermittent demand | Hand-implemented `Croston`, `SBA` (Syntetos-Boylan), `TSB` |
| Stacking | Hand-implemented NNLS via projected gradient (no `scipy.optimize.nnls` dependency) |
| Parallelism | `concurrent.futures.ProcessPoolExecutor` (CLI) / `ThreadPoolExecutor` (Jupyter fallback), `multiprocessing.get_context("spawn")` |
| Plots | `matplotlib` |
| Persistence | `joblib` for serialized models, plain CSV + JSON for outputs |

No web framework, no database, no package manager lockfile — pure script + notebook workflow.

---

## 3. Repository Layout

```
bitirme/
├── proje_ozeti.md                      # Turkish thesis summary (existing)
├── CLAUDE.md                           # Working notes for Claude Code (must live at root)
├── .claudeignore                       # Excludes large artifacts from Claude context
├── docs/
│   ├── PROJECT_OVERVIEW.md             # This file (English engineering doc)
│   ├── PROJECT_OVERVIEW_TR.md          # Turkish translation
│   └── CLAUDE_TR.md                    # Turkish translation of CLAUDE.md (reference)
│
├── scripts/
│   ├── __init__.py
│   ├── model_v3.py     (1416 lines)    # PRIMARY production script — latest
│   ├── model_v2.py     (1417 lines)    # Near-twin of v3, research-tuned constants
│   └── OMS.py          (1237 lines)    # Earlier standalone pipeline (prototype)
│
├── Sales Forecast v7_full.ipynb        # Latest research notebook (v7, ~1.7 MB)
│
├── panel_sales_orders_stock.csv        # Canonical monthly panel input
├── sku_config.csv                      # Per-SKU policy params (MOQ, lot, H_COVER, …)
├── motul_data.csv                      # Raw transaction-level sales
├── veri_matrisi_final_sales_orders_stock_calendar_lags_fx.csv  # Intermediate wide matrix
│
├── serialized_models/
│   └── best_y_model_rf_full.joblib     # Frozen experimental RF (not used by v3/v2)
│
├── outputs/
│   └── {SKU}/                          # Per-SKU forecast artifacts (preds_*.csv,
│       ├── preds_Full_*.csv            #   plot_*.png, reorder_recommendation.json,
│       ├── preds_Full_*_REFIT.csv      #   test_summary_ALL*.csv, …)
│       ├── test_summary_ALL.csv
│       ├── test_summary_ALL_REFIT.csv
│       ├── reorder_recommendation.json
│       ├── plot_full_*.png
│       └── plot_3m_*.png
│
├── v7_full/
│   ├── forecasts/                      # Flat-format v7 notebook outputs
│   └── plots/
│
├── mnt/data/                           # Colab/cloud-mount mirrors
│   ├── panel_sales_orders_stock.csv
│   ├── sku_config.csv
│   ├── v7_per_sku_outputs/
│   └── v7_select/
│
├── logs/
├── .idea/                              # JetBrains (ignore)
├── __MACOSX/                           # macOS zip cruft (ignore)
└── Archive.zip                         # (ignore)
```

**Dozens of archival Jupyter notebooks** (Phase 1–4; see §5) sit in the repo root. They document the evolution from a single-SKU experiment (`303-104092`) through exogenous ensemble exploration, NNLS blending, multi-SKU parallelization, REFIT rollback, and intermittent demand handling. They are superseded by `scripts/model_v3.py` + `Sales Forecast v7_full.ipynb` and are listed in `.claudeignore` to keep the context window clean.

---

## 4. Primary Module: `scripts/model_v3.py`

`scripts/model_v3.py` is the canonical production entry point. Run with `python scripts/model_v3.py` to produce forecasts + order recommendations for every SKU in `panel_sales_orders_stock.csv`.

### 4.1 Top-level layout

| Lines | Section |
|---|---|
| 1–155 | Module docstring, imports, global config constants |
| 160–237 | Utility helpers (`ensure_ms_freq`, `add_calendar`, `build_lags_y`, `prep_features_y`, metric helpers) |
| 239–268 | Baseline forecasters (`seasonal_naive_forecast`, `ma3_forecast`, `baseline_val_mae`) |
| 270–476 | EXOG model layer (Prophet / SARIMA / ETS fit & forecast; `build_exog_univar`, `build_exog_inverse`, `build_exog_ml`) |
| 477–584 | NNLS stacking (`project_simplex`, `nnls_ridge`, `nnls_ridge_weighted`, `nnls_adapt`, `fit_nnls_weights_on_val`, `combine_exogs_weighted`) |
| 586–658 | Intermittent demand (`select_intermittent`, `croston_forecast`, `sba_forecast`, `tsb_forecast`, `predict_intermittent`) |
| 660–706 | Y-model ROCV (`rolling_origin_splits`, `optimize_rf_rocv`, `optimize_xgb_rocv`) |
| 708–728 | `recursive_forward_predict_y` — the recursive Y forecast loop |
| 730–803 | Bootstrap PI + stockout + MOQ rounding (`add_bootstrap_intervals`, `stockout_probability`, `cum_demand_quantile`, `round_moq_lot`) |
| 805–835 | Y-ensemble weights + REFIT (`y_ensemble_weights`, `refit_models_on_full`) |
| 838–960 | Per-variable EXOG selection — `choose_best_exog_per_var`, `build_hybrid_exog` (⚠ contains dead refactoring debris; see §8) |
| 963–979 | `choose_methods_for_sku` (defined but unused; dead) |
| 982–1312 | **`run_for_sku`** — master per-SKU orchestrator |
| 1314–1335 | `load_params` |
| 1338–1344 | `_run_worker` — parallel wrapper |
| 1347–1412 | **`main`** — panel load, SKU groupby, dispatch, summary |

### 4.2 Per-SKU pipeline (`run_for_sku`)

```
 1. Data prep            ensure_ms_freq, prep_features_y      (lags, calendar, winsorize)
 2. Y model ROCV         optimize_rf_rocv, optimize_xgb_rocv  (3-fold rolling-origin CV)
 3. Probe EXOG on VAL    _build_exog_by_method                (cheap candidates: ETS, Intermittent, ML-Exog RF)
 4. Escalate if needed   baseline_val_mae check               (add XGB + Prophet if probe < seasonal naive + 2%)
 5. Per-var hybrid       choose_best_exog_per_var             (best method for `orders` ⨯ best for `stock`)
 6. Build test EXOG      build_exog_*                         (project forward to TEST_END / TEST_END_SHORT)
 7. TEST eval (PRE)      recursive_forward_predict_y,         (recursive forecast + Laplace bootstrap PI +
                         add_bootstrap_intervals,              stockout probability + E[T])
                         stockout_probability
 8. REFIT                refit_models_on_full                 (retrain on train+val; rollback if worse)
 9. OMS order policy     stockout_probability,                (order = max(0, cumDemand(H, q) - startStock),
                         cum_demand_quantile, round_moq_lot    rounded to MOQ + lot)
10. Output               per-variant CSV, reorder JSON, PNGs  (writes outputs/{SKU}/)
```

### 4.3 Parallelism

Dual-mode execution:

- **CLI (`python scripts/model_v3.py`)** — `ProcessPoolExecutor(mp.get_context("spawn"))`, one SKU per worker, `MAX_WORKERS = int(cpu_count * 0.75)`.
- **Jupyter / interactive** — detected via `IS_INTERACTIVE` flag, falls back to `ThreadPoolExecutor` (spawn doesn't survive notebook reloads).
- `PARALLEL_SKU = False` by default in v3 (on in v2/OMS) — the latest iteration runs serially by default and opts in explicitly.

---

## 5. Notebook Evolution (Phases 1–5)

| Phase | Theme | Representative notebooks |
|---|---|---|
| 1 | Single-SKU EDA + baselines (`303-104092`) | `motul_data_analysis.ipynb`, `veri hazırlama.ipynb`, `303-104092-3-Model.ipynb`, `303-104092-Probhet-XGBoost-Hybrid*.ipynb` |
| 2 | Exog ensemble exploration | `Auto-Exog Forecast*.ipynb`, `3 Exog Strategy*.ipynb`, `Exog Ensemble Tuning + Sızıntısız-Kausal + PI.ipynb` |
| 3 | OMS integration + scenarios | `Sales Forecast v2–v6.1 — OMS Edition*.ipynb` |
| 4 | Multi-SKU parallelization + REFIT + intermittent | `Sales Forecast V6_multi_sku*.ipynb`, `v6_multi_sku.py — OMS Edition*.ipynb` |
| 5 | **Current** — v7 full production run | `Sales Forecast v7_full.ipynb` (latest) |

Phases 1–4 are archival. Live artifacts are `scripts/model_v3.py`, `scripts/OMS.py`, and `Sales Forecast v7_full.ipynb`.

---

## 6. Data Schemas

### `panel_sales_orders_stock.csv`

| Column | Type | Description |
|---|---|---|
| `ds` | date | First-of-month timestamp (MS frequency) |
| `sku` | string | Product code (e.g. `303-104092`) |
| `y` | float | Realized monthly sales (units) |
| `orders` | float | Incoming purchase orders placed that month |
| `stock` | int | End-of-month stock on hand |

### `sku_config.csv`

| Column | Description |
|---|---|
| `sku` | Product code |
| `T_CHECK` | Review cycle in months; reorder fires if `E[T_stockout] ≤ T_CHECK` |
| `H_COVER` | Coverage horizon — how many months of demand the order should cover |
| `q_target` | Service-level quantile on cumulative demand (e.g. 0.5 = median) |
| `lead_time_mo` | Supplier lead time in months |
| `MOQ` | Minimum order quantity (0 = no minimum) |
| `lot_size` | Rounding granularity (1 = unit, else round up to nearest lot) |

### `outputs/{SKU}/` artifact naming

`preds_{Horizon}_{EnsembleMethod}_{YVariant}[_REFIT].csv`

- **Horizon** — `Full` (6-month window) or `Short3` (3-month window, also seen as `3m` in plot names)
- **EnsembleMethod** — how the EXOG regressors were forecast forward. Examples: `Adaptive5-NNLS-w3` (5 base models × NNLS weights on 3-period window), `Top3-NNLS-Ridge`, `All-5-INV` (inverse-MAE), `Ensemble` (simple average), `ML-Exog_XGB`, `Prophet`, `SARIMA`, `ETS`, `Intermittent` (Croston/SBA/TSB)
- **YVariant** — the Y-model used for recursive forecasting: `RF`, `XGB`, or `Y-ENS` (NNLS blend of RF + XGB)
- **`_REFIT` suffix** — predictions after retraining on train + val (kept only if not worse than the PRE-REFIT result)

Prediction CSV columns: `ds, yhat, pi80_lo, pi80_hi, pi95_lo, pi95_hi`.

`reorder_recommendation.json` — terminal output per SKU. Contains chosen combo, starting stock, `P(stockout ≤ 3m)`, `P(stockout ≤ 6m)`, `E[T_stockout]`, cumulative demand quantile, and the final `order_qty_rounded`.

---

## 7. Architecture Diagram (Data Flow)

```
                     ┌────────────────────┐
                     │   motul_data.csv   │  (raw transactions)
                     └─────────┬──────────┘
                               │ veri hazırlama.ipynb
                               ▼
                ┌──────────────────────────────┐
                │ panel_sales_orders_stock.csv │  (cleaned monthly panel)
                └──────────────┬───────────────┘
                               │
                               ▼
   ┌──────────────────────────────────────────────────────────┐
   │              scripts/model_v3.py :: main                 │
   │                                                          │
   │   for each SKU (parallel optional):                      │
   │       run_for_sku(sku_df, sku_params)                    │
   │           │                                              │
   │           ├── prep_features_y           (lags, calendar) │
   │           │                                              │
   │           ├── optimize_rf_rocv  ──┐                      │
   │           ├── optimize_xgb_rocv ──┴── ROCV grid search   │
   │           │                                              │
   │           ├── EXOG probe (ETS, IM, ML-Exog-RF)           │
   │           │      └── escalate → +XGB +Prophet if weak    │
   │           │                                              │
   │           ├── choose_best_exog_per_var   (orders, stock) │
   │           │                                              │
   │           ├── build_hybrid_exog                          │
   │           │                                              │
   │           ├── recursive_forward_predict_y                │
   │           │      └── add_bootstrap_intervals (Laplace)   │
   │           │                                              │
   │           ├── refit_models_on_full  (+ rollback)         │
   │           │                                              │
   │           ├── stockout_probability, cum_demand_quantile  │
   │           │                                              │
   │           └── round_moq_lot  → reorder_recommendation    │
   └───────────────────────────┬──────────────────────────────┘
                               │
                               ▼
            ┌──────────────────────────────────┐
            │          outputs/{SKU}/          │
            │                                  │
            │  preds_*.csv  (with PI columns)  │
            │  preds_*_REFIT.csv               │
            │  test_summary_ALL.csv            │
            │  test_summary_ALL_REFIT.csv      │
            │  reorder_recommendation.json     │
            │  plot_full_*.png, plot_3m_*.png  │
            └──────────────────────────────────┘
                               │
                               ▼
                ┌──────────────────────────┐
                │ outputs/_SUMMARY/        │
                │  test_summary_ALL_SKUs.csv│
                └──────────────────────────┘
```

---

## 8. Patterns, Anti-Patterns, Notes

**Design choices that are load-bearing:**
- **Recursive Y forecast.** Instead of direct multi-step (T+6 at once), `recursive_forward_predict_y` feeds each T+1 prediction back into the lag features for T+2. More faithful to time-series semantics but bias compounds if the first step is off.
- **NNLS ensemble weights with `time_decay`.** Recent validation errors count more than distant ones. `fit_nnls_weights_recent` operates on the tail `REFIT_TAIL_K` months.
- **Per-variable EXOG selection.** `orders` and `stock` are forecast independently — the best method family for orders may differ from the best for stock, and naive fusion obscures that.
- **Probe → Escalate.** Cheap EXOG methods run first; heavy methods (Prophet, XGB-Exog) only engage if cheap methods cannot beat `seasonal_naive + DELTA_BETTER_THAN_BASELINE`. Speed optimization, not quality compromise.
- **Intermittent gate.** SKUs with high zero ratio / high ADI switch to Croston/SBA/TSB instead of continuous models. Triggered in `select_intermittent` via zero-rate + ADI thresholds.
- **Bootstrap PI > parametric CI.** `add_bootstrap_intervals` produces calibrated 80%/95% intervals that drive the stockout probability calculation rather than a single point estimate.
- **REFIT + rollback.** After initial training/eval split, models retrain on train + val. If the refit result is *worse* than pre-refit (measured on the test window), the pre-refit result is kept. Prevents overfitting to recent noise.

**Known code-health issues (to investigate before refactoring):**
- ⚠ `val_mae_exog_for_col` is **defined twice** in `scripts/model_v3.py` (lines 899 and 909). The first definition is shadowed and dead. Lines 848–897 contain five prior broken attempts (`_val_mae_exog_col`, `_val_mae_col_clean`, …) left in place as commented-out dead code. The final (line 909) definition does work correctly, but this block is the main readability hazard in the file.
- ⚠ `choose_methods_for_sku` (line 964) is never called — `run_for_sku` inlines its logic instead.
- ⚠ `scripts/model_v2.py` and `scripts/model_v3.py` are near-identical — they differ only in ~10 config constants (`B_BOOT`, `ADAPT_WINS`, `ENABLE_TIME_DECAY_NNLS`, `IM_METHODS`, `FAST_MODE`, `PARALLEL_SKU`). v3 is the speed-pruned variant of v2. Any logic fix must be applied manually to both.
- ⚠ `scripts/OMS.py`'s `ENABLE_INV_ENSEMBLES` / `ENABLE_NNLS_ENSEMBLES` flags (False by default) only gate file output, not computation — the adaptive NNLS block at lines 846–876 runs unconditionally, wasting CPU.
- ⚠ Jupyter notebooks from Phases 1–4 (dozens of files) are committed in the repo root and heavily overlap — consider archiving to an `archive/` subfolder in a future cleanup pass.

---

## 9. Entry Points at a Glance

| Goal | File | Command |
|---|---|---|
| Run the full pipeline for all SKUs | `scripts/model_v3.py` | `python scripts/model_v3.py` |
| Reference implementation (no Probe/Escalate) | `scripts/OMS.py` | `python scripts/OMS.py` |
| Research / thesis walkthrough | `Sales Forecast v7_full.ipynb` | Open in Jupyter |
| Recreate the panel from raw data | `veri hazırlama.ipynb` | Open in Jupyter |

---

## 10. Where to Start Reading the Code

Ordered by importance:

1. `scripts/model_v3.py:983` — `run_for_sku` (master pipeline)
2. `scripts/model_v3.py:709` — `recursive_forward_predict_y` (Y forecast loop)
3. `scripts/model_v3.py:731` — `add_bootstrap_intervals` (PI construction)
4. `scripts/model_v3.py:909` — `val_mae_exog_for_col` (second, live definition)
5. `scripts/model_v3.py:928` — `choose_best_exog_per_var` (per-variable hybrid)
6. `scripts/model_v3.py:676` — `optimize_rf_rocv` (ROCV grid search)
7. `scripts/model_v3.py:441` — `fit_nnls_weights_on_val` (stacking weights)
8. `scripts/model_v3.py:586` — `select_intermittent` (sparse/dense routing)
9. `scripts/model_v3.py:1347` — `main` (panel load + parallel dispatch)
10. `scripts/OMS.py:715` — reference `run_for_sku` without Probe→Escalate (compare against v3 to understand what the newer routing replaced)
