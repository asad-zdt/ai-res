"""Load a trained model bundle and predict resource needs by application name."""

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from config import resolve_path
from errors import UnknownAppError


def _model_path() -> Path:
    """Return the configured model bundle path."""
    configured_path = os.getenv("MODEL_PATH", "model/artifacts/model.pkl")
    path = Path(configured_path)
    return path if path.is_absolute() else resolve_path(configured_path)


@lru_cache(maxsize=None)
def _load_bundle(model_path: str) -> dict[str, Any]:
    """Load and cache one model bundle per resolved path."""
    path = Path(model_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Model bundle not found at {path}; run `python -m model.train`."
        )
    return joblib.load(path)


def predict(app_name: str) -> dict[str, float]:
    """Predict resource metrics for an application in the saved app profiles."""
    bundle = _load_bundle(str(_model_path().resolve()))
    try:
        profile = bundle["app_profiles"][app_name]
    except KeyError:
        raise UnknownAppError(app_name) from None

    features = pd.DataFrame(
        [
            {
                column: app_name if column == "app_name" else profile[column]
                for column in bundle["feature_columns"]
            }
        ]
    )
    values = bundle["pipeline"].predict(features)[0]
    return {
        target: round(max(0.0, float(value)), 2)
        for target, value in zip(bundle["target_columns"], values, strict=True)
    }


def main() -> None:
    """Print a prediction for the application name supplied on the command line."""
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m model.predict <app_name>")
    print(predict(sys.argv[1]))


if __name__ == "__main__":
    main()
