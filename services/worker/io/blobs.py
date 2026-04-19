"""Joblib blob save/load for fitted models.

Path scheme: {model_dir}/{sku}/{run_id}/{slot}.joblib
Blob URI: file://{absolute_path}
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib


def blob_dir_for(model_dir: Path, sku: str, run_id: int) -> Path:
    return Path(model_dir) / sku / str(run_id)


def blob_path(model_dir: Path, sku: str, run_id: int, slot: str) -> Path:
    return blob_dir_for(model_dir, sku, run_id) / f"{slot}.joblib"


def uri_for(path: Path) -> str:
    return f"file://{path.resolve()}"


def path_from_uri(uri: str) -> Path:
    if uri.startswith("file://"):
        return Path(uri[len("file://"):])
    return Path(uri)


def save_blob(model: Any, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    return uri_for(path)


def load_blob(uri: str) -> Any:
    return joblib.load(path_from_uri(uri))
