# CLAUDE.md

Working notes for Claude Code when operating in this repository. Read [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) first for the full architecture walkthrough. Turkish translations are in [`docs/PROJECT_OVERVIEW_TR.md`](docs/PROJECT_OVERVIEW_TR.md) and [`docs/CLAUDE_TR.md`](docs/CLAUDE_TR.md).

---

## Project in one paragraph

Turkish graduation thesis ("bitirme") project. Per-SKU monthly sales forecasting + automated purchase-order recommendation for a Motul-like lubricant distributor. The canonical production script is `scripts/model_v3.py`; it runs an 8-step pipeline per SKU (feature prep → ROCV grid search → EXOG probe/escalate → per-variable hybrid EXOG → recursive Y forecast → bootstrap PI → REFIT rollback → MOQ-constrained order policy). Input: `panel_sales_orders_stock.csv` + `sku_config.csv`. Output: `outputs/{SKU}/preds_*.csv` + `reorder_recommendation.json`.

---

## Canonical files (look here first)

| File | Role |
|---|---|
| `scripts/model_v3.py` | **Primary production script.** Latest, speed-pruned. Entry point: `main()` at line 1347. |
| `scripts/model_v2.py` | Near-twin of v3 — differs only in ~10 config constants. Research-tuned (higher B_BOOT, time-decay NNLS on). |
| `scripts/OMS.py` | Earlier standalone pipeline. No Probe→Escalate, no per-variable EXOG. Keep as reference, not production. |
| `Sales Forecast v7_full.ipynb` | Latest research notebook (v7). Not superseded. |
| `panel_sales_orders_stock.csv` | Canonical input panel: `ds, sku, y, orders, stock`. |
| `sku_config.csv` | Per-SKU policy: `T_CHECK, H_COVER, q_target, lead_time_mo, MOQ, lot_size`. |
| `proje_ozeti.md` | Turkish thesis summary. |
| `docs/PROJECT_OVERVIEW.md` | Engineering-facing architecture doc (EN). |
| `docs/PROJECT_OVERVIEW_TR.md` | Turkish translation of the architecture doc. |

---

## Where NOT to look

The repo root contains **dozens of archival Jupyter notebooks** from Phases 1–4 of development (single-SKU experiments on `303-104092`, Auto-Exog explorations, Sales Forecast v2–v6 iterations, `Untitled*.ipynb`). They are superseded by `scripts/model_v3.py` + `Sales Forecast v7_full.ipynb`. `.claudeignore` excludes them. Do not load them into context unless the user explicitly asks about a specific notebook.

Also excluded:
- `outputs/` — derived per-SKU forecast artifacts (thousands of CSVs + PNGs)
- `v7_full/`, `mnt/data/v7_*` — more derived outputs
- `serialized_models/*.joblib` — binary model files
- `motul_data.csv`, `veri_matrisi_final_*.csv` — large raw/intermediate data
- `__MACOSX/`, `.DS_Store`, `.idea/`, `Archive.zip`, `.ipynb_checkpoints/`

---

## Pipeline mental model

```
raw → panel_sales_orders_stock.csv → [model_v3.run_for_sku per SKU] → outputs/{SKU}/
                                                │
                                                └── reorder_recommendation.json
```

Inside `run_for_sku` (`scripts/model_v3.py:983`):

1. `prep_features_y` — lags (y_lag1, orders_lag1/3, stock_lag1/3), calendar, winsorize
2. `optimize_rf_rocv` + `optimize_xgb_rocv` — ROCV grid search on train+val
3. **EXOG probe** — cheap candidates (ETS, intermittent, ML-Exog-RF) scored on VAL
4. **EXOG escalate** — add XGB + Prophet only if probe < seasonal naive + 2%
5. `choose_best_exog_per_var` — pick best method per exogenous variable (`orders`, `stock`)
6. `recursive_forward_predict_y` — recursive T+1 → T+2 → … forecast
7. `add_bootstrap_intervals` — Laplace bootstrap for 80/95% PIs
8. `refit_models_on_full` — retrain on train+val; **rollback if test MAE is worse**
9. `stockout_probability` → `cum_demand_quantile` → `round_moq_lot` — OMS policy
10. Write per-combo CSVs + `reorder_recommendation.json` + plots

---

## Load-bearing invariants (do not break)

- **Date frequency is month-start (`MS`)**. `ensure_ms_freq` enforces this. Any new feature that indexes by date must preserve this.
- **Recursive forecast requires causal lag features only.** No future data in `build_lags_y`. Breaking causality here is the #1 way to get bogus low MAE.
- **NNLS weights are non-negative and project onto the simplex.** `project_simplex` + `nnls_ridge`. Do not replace with unconstrained least squares.
- **REFIT rollback is conservative.** If `ref_best > pre_best` → keep PRE. Do not flip the comparison.
- **`panel_sales_orders_stock.csv` exists in two locations** — repo root and `mnt/data/`. Keep them in sync if you regenerate the panel.
- **`scripts/model_v2.py` and `scripts/model_v3.py` drift freely.** A bug fix in one does not propagate — apply fixes to both, or ask the user which one is authoritative.

---

## Known code-health issues

(Do not silently clean these up — flag to user first.)

- **`val_mae_exog_for_col` is defined twice** in `scripts/model_v3.py` (lines 899 and 909). The first is dead. Lines 848–897 are broken refactoring attempts left as dead code. Only the line 909 version executes.
- **`choose_methods_for_sku`** (`scripts/model_v3.py:964`) is never called. `run_for_sku` inlines the logic.
- **v2 and v3 are near-identical**. Changes must be applied to both files manually.
- **scripts/OMS.py's `ENABLE_*_ENSEMBLES` flags only gate file output**, not computation. Expensive loops run even when flags are `False`.

---

## Common tasks

### "Run forecasting for all SKUs"
```
python scripts/model_v3.py
```
Outputs land in `outputs/{SKU}/`.

### "Add a new SKU to the pipeline"
1. Add rows to `panel_sales_orders_stock.csv` (and `mnt/data/panel_sales_orders_stock.csv`)
2. Add a row to `sku_config.csv` with MOQ, lot size, H_COVER, q_target
3. Rerun `python scripts/model_v3.py`

### "Change the forecast horizon or test window"
Constants at the top of `scripts/model_v3.py` (lines 1–155): `TEST_START`, `TEST_END`, `TEST_END_SHORT`, `H_COVER` (per-SKU overridden by `sku_config.csv`).

### "Tune for speed"
See `FAST_MODE`, `B_BOOT`, `ADAPT_WINS`, `IM_METHODS` in the v3 config block. v3 is already speed-pruned vs v2; further pruning should go through v3.

### "Add a new EXOG forecasting method"
1. Implement `build_exog_<name>` mirroring `build_exog_univar` signature in `scripts/model_v3.py:270–476`
2. Register it in `_build_exog_by_method` (~line 838)
3. Add the name to `PROBE_METHODS` or `ESCALATE_METHODS`
4. Update `choose_best_exog_per_var` if the new method should compete per-variable

---

## Style preferences for this repo

- **Match the existing Python style.** No type annotations, no dataclasses, heavy use of module-level config constants, functions named with underscores, `main()` at the bottom.
- **Do not introduce a package structure** (`src/`, `__init__.py`, `setup.py`) unless asked. This is a thesis repo, not a library.
- **Do not add `requirements.txt` or `pyproject.toml`** unless asked — inspect imports and use `pip install` ad-hoc as the user has been doing.
- **Prefer editing `scripts/model_v3.py` over creating new modules.** The user's mental model is "one script per version".
- **Keep Turkish comments where they already exist.** `proje_ozeti.md` and inline comments are bilingual by design.
- **Do not rename files or move archival notebooks** without explicit permission. Many have reference value for the thesis.

---

## When the user asks a question

- For questions about "how does X work" → read from `scripts/model_v3.py` first (not v2, not OMS, not notebooks).
- For questions about the thesis narrative / "why we did it this way" → read from `proje_ozeti.md`.
- For questions about past experiments / "what did we try before" → read from the notebook file whose name matches the phase the user is asking about; only load one at a time, they are huge.
- For questions about output artifacts → the naming convention is `preds_{Horizon}_{EnsembleMethod}_{YVariant}[_REFIT].csv`. See `PROJECT_OVERVIEW.md` §6 for the decoding table.
