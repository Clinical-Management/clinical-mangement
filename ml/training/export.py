"""Helpers for saving trained models where the backend can serve them."""

from pathlib import Path

import joblib

BACKEND_ARTIFACTS = Path(__file__).resolve().parents[2] / "backend" / "app" / "ml" / "artifacts"


def save_sklearn(model, filename: str) -> Path:
    """Save a scikit-learn model/pipeline, e.g. save_sklearn(pipe, "diabetes.joblib")."""
    BACKEND_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = BACKEND_ARTIFACTS / filename
    joblib.dump(model, path)
    print(f"Saved {path}")
    return path
