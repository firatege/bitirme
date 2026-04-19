"""Health + readiness probes. /readyz asserts every optional dep imports cleanly."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz():
    return {"ok": True}


@router.get("/readyz")
def readyz():
    errors: list[str] = []
    try:
        import xgboost  # noqa: F401
    except Exception as e:
        errors.append(f"xgboost: {e}")
    try:
        import prophet  # noqa: F401
    except Exception as e:
        errors.append(f"prophet: {e}")
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing  # noqa: F401
        from statsmodels.tsa.statespace.sarimax import SARIMAX  # noqa: F401
    except Exception as e:
        errors.append(f"statsmodels: {e}")
    try:
        from services.worker.pipelines import cold, warm, drift  # noqa: F401
    except Exception as e:
        errors.append(f"pipelines import: {e}")
    return {"ok": not errors, "imports_ok": not errors, "errors": errors}
