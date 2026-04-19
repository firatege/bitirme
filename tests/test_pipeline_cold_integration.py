"""End-to-end integration test for pipelines/cold.py on real SKU data.

Loads panel_sales_orders_stock.csv + sku_config.csv from the repo root, picks one dense
SKU, runs the full cold pipeline, and asserts the essential invariants hold. This is the
Phase 1 parity gate — it won't perfectly match scripts/model_v3.py output (different
random seeding paths, rolling-origin differences, etc.) but it must produce a valid,
finite winning combo and a reasonable recommendation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from services.worker.pipelines.cold import run_cold
from services.worker.schemas.requests import ForecastColdRequest, PanelRow, ParamsRow


REPO_ROOT = Path(__file__).resolve().parent.parent
PANEL_CSV = REPO_ROOT / "panel_sales_orders_stock.csv"
CONFIG_CSV = REPO_ROOT / "sku_config.csv"


pytestmark = pytest.mark.skipif(
    not PANEL_CSV.exists() or not CONFIG_CSV.exists(),
    reason="Real panel CSVs not available",
)


def _load_sku_request(sku: str, run_id: int, blob_dir: Path) -> ForecastColdRequest:
    panel = pd.read_csv(PANEL_CSV, parse_dates=["ds"])
    cfg_df = pd.read_csv(CONFIG_CSV)
    panel["sku"] = panel["sku"].astype(str)
    cfg_df["sku"] = cfg_df["sku"].astype(str)
    rows = panel[panel["sku"] == sku].sort_values("ds")
    cfg_row = cfg_df[cfg_df["sku"] == sku].iloc[0]
    params = ParamsRow(
        t_check=int(cfg_row["T_CHECK"]),
        h_cover=int(cfg_row["H_COVER"]),
        q_target=float(cfg_row["q_target"]),
        lead_time_mo=int(cfg_row["lead_time_mo"]),
        moq=float(cfg_row["MOQ"]),
        lot_size=float(cfg_row["lot_size"]),
        starting_stock_override=None,
    )
    panel_rows = [
        PanelRow(ds=r["ds"].date(), y=float(r["y"]), orders=float(r["orders"]), stock=float(r["stock"]))
        for _, r in rows.iterrows()
    ]
    return ForecastColdRequest(
        sku=sku,
        run_id=run_id,
        panel_rows=panel_rows,
        params_row=params,
        blob_dir=str(blob_dir),
    )


@pytest.mark.slow
def test_cold_pipeline_on_real_sku(tmp_path):
    sku = "303-104092"
    run_id = 1
    blob_dir = tmp_path / "models" / sku / str(run_id)
    blob_dir.mkdir(parents=True, exist_ok=True)

    req = _load_sku_request(sku, run_id, blob_dir)
    result = run_cold(req)

    # Shape + finiteness
    assert result.sku == sku
    assert result.run_id == run_id
    assert result.mode == "cold"
    assert result.winning.mae >= 0
    assert result.winning.rmse >= 0
    assert result.winning.horizon == "Full"
    assert result.winning.phase in ("PRE", "REFIT")
    assert result.winning.y_variant in ("RF", "XGB", "Y-ENS", "TSB", "Croston", "SBA")

    # At least one combination per active variant × horizon
    horizons = {c.horizon for c in result.combinations}
    assert "Full" in horizons
    variants = {c.y_variant for c in result.combinations}
    assert "RF" in variants
    assert all(c.mae >= 0 for c in result.combinations)

    # Models persisted
    assert len(result.models) >= 1  # at least rf_y_pre
    for m in result.models:
        assert m.blob_uri.startswith("file://")
        # The actual file should exist on disk
        from services.worker.io.blobs import path_from_uri
        assert path_from_uri(m.blob_uri).exists()

    # Recommendation sanity
    rec = result.recommendation
    assert rec.starting_stock >= 0
    assert rec.order_qty_rounded >= 0
    assert rec.t_check == 3 and rec.h_cover == 6
    assert rec.cum_demand_q >= 0

    # JSON round-trip — what Rust will deserialize
    payload = result.model_dump_json()
    parsed = json.loads(payload)
    assert parsed["sku"] == sku
    assert parsed["winning"]["exog"] == result.winning.exog
