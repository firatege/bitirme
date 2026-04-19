"""FastAPI app factory. No DB driver imported anywhere under services/worker."""
from __future__ import annotations

from fastapi import FastAPI

from services.worker.api.routes import drift, forecast, health
from services.worker.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="bitirme worker", version="0.1.0")
    app.include_router(health.router)
    app.include_router(forecast.router)
    app.include_router(drift.router)
    return app


app = create_app()
