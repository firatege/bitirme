"""POST /forecast/cold and POST /forecast/warm."""
from __future__ import annotations

from fastapi import APIRouter

from services.worker.pipelines.cold import run_cold
from services.worker.pipelines.warm import run_warm
from services.worker.schemas.requests import ForecastColdRequest, ForecastWarmRequest
from services.worker.schemas.responses import ForecastResult

router = APIRouter()


@router.post("/forecast/cold", response_model=ForecastResult)
def forecast_cold(req: ForecastColdRequest) -> ForecastResult:
    return run_cold(req)


@router.post("/forecast/warm", response_model=ForecastResult)
def forecast_warm(req: ForecastWarmRequest) -> ForecastResult:
    return run_warm(req)
