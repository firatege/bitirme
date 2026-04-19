"""Uvicorn entry point. Run: uvicorn services.worker.main:app --host 0.0.0.0 --port 8000"""
from __future__ import annotations

from services.worker.api.app import app  # noqa: F401 — re-exported for uvicorn
