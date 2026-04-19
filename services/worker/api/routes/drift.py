"""POST /drift/check — cheap MAE comparison for the warm-vs-cold decision on Rust side."""
from __future__ import annotations

from fastapi import APIRouter

from services.worker.pipelines.drift import run_drift_check
from services.worker.schemas.requests import DriftCheckRequest
from services.worker.schemas.responses import DriftCheckResult

router = APIRouter()


@router.post("/drift/check", response_model=DriftCheckResult)
def drift_check(req: DriftCheckRequest) -> DriftCheckResult:
    return run_drift_check(req)
