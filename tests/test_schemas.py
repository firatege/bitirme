"""Pydantic roundtrip tests for the service contract."""
from __future__ import annotations

from datetime import date

from services.worker.schemas.requests import (
    CachedExogSelection,
    CachedModelRef,
    CachedSpec,
    CachedValResidual,
    ForecastColdRequest,
    ForecastWarmRequest,
    PanelRow,
    ParamsRow,
)
from services.worker.schemas.responses import (
    CombinationRow,
    ExogSelectionRow,
    ForecastResult,
    ModelRow,
    RecommendationRow,
    ValResidualRow,
    WinningCombo,
)


def _sample_cold_payload() -> ForecastColdRequest:
    return ForecastColdRequest(
        sku="303-104092",
        run_id=1,
        panel_rows=[PanelRow(ds=date(2024, 1, 1), y=10.0, orders=11.0, stock=50.0)],
        params_row=ParamsRow(t_check=3, h_cover=6, q_target=0.5),
        blob_dir="/app/models/303-104092/1/",
    )


def _sample_cached_spec() -> CachedSpec:
    return CachedSpec(
        prior_run_id=1,
        winning_horizon="Full",
        winning_exog="Hybrid[o=ETS,s=ML-Exog RF]",
        winning_y_variant="Y-ENS",
        winning_phase="PRE",
        winning_w_rf=0.55,
        winning_w_xgb=0.45,
        models=[CachedModelRef(model_slot="rf_y_pre", column_target="y", hyperparams={"n_estimators": 300},
                                blob_uri="file:///app/models/303-104092/1/rf_y_pre.joblib")],
        exog_selection=[CachedExogSelection(column_target="orders", chosen_method="ETS", val_mae=4.2)],
        val_residuals=[CachedValResidual(exog="Hybrid[o=ETS,s=ML-Exog RF]", y_variant="Y-ENS",
                                          residuals=[0.1, -0.3, 0.2])],
    )


def test_cold_request_roundtrip():
    req = _sample_cold_payload()
    j = req.model_dump_json()
    req2 = ForecastColdRequest.model_validate_json(j)
    assert req2.sku == req.sku and req2.run_id == req.run_id
    assert req2.panel_rows[0].y == 10.0


def test_warm_request_roundtrip():
    cold = _sample_cold_payload()
    warm = ForecastWarmRequest(**cold.model_dump(), cached_spec=_sample_cached_spec())
    j = warm.model_dump_json()
    warm2 = ForecastWarmRequest.model_validate_json(j)
    assert warm2.cached_spec.winning_y_variant == "Y-ENS"
    assert warm2.cached_spec.val_residuals[0].residuals == [0.1, -0.3, 0.2]


def test_forecast_result_roundtrip():
    result = ForecastResult(
        sku="X", run_id=42, mode="cold",
        winning=WinningCombo(horizon="Full", exog="ETS", y_variant="RF", phase="PRE", mae=1.0, rmse=1.5),
        combinations=[CombinationRow(horizon="Full", exog="ETS", y_variant="RF", phase="PRE", mae=1.0)],
        models=[ModelRow(model_slot="rf_y_pre", column_target="y", hyperparams={}, blob_uri="file:///x", fit_seconds=1.0)],
        exog_selection=[ExogSelectionRow(column_target="orders", chosen_method="ETS", val_mae=3.0)],
        val_residuals=[ValResidualRow(exog="ETS", y_variant="RF", residuals=[0.1])],
        recommendation=RecommendationRow(
            starting_stock=100.0, t_check=3, h_cover=6, q_target=0.5,
            moq=0.0, lot_size=1.0, cum_demand_q=80.0,
            order_qty_raw=-20.0, order_qty_rounded=0.0,
        ),
    )
    j = result.model_dump_json()
    r2 = ForecastResult.model_validate_json(j)
    assert r2.winning.mae == 1.0
    assert r2.recommendation.order_qty_rounded == 0.0
