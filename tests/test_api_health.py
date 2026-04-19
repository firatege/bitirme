"""FastAPI /healthz /readyz smoke tests — no DB, no uvicorn."""
from __future__ import annotations

from fastapi.testclient import TestClient

from services.worker.api.app import create_app


def test_healthz_returns_ok():
    client = TestClient(create_app())
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_readyz_reports_import_status():
    client = TestClient(create_app())
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body and "imports_ok" in body
    # We installed all deps in this venv, so imports_ok should be True.
    assert body["imports_ok"] is True
    assert body["errors"] == []
