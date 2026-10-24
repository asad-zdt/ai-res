"""Train and save the multi-output resource prediction model."""

import argparse
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from config import FEATURE_COLUMNS, TARGET_COLUMNS, resolve_path

_NUMERIC_FEATURES = [
    column
    for column in FEATURE_COLUMNS
    if column not in {"app_name", "app_category"}
]
_APP_PROFILE_COLUMNS = [
    column for column in FEATURE_COLUMNS if column != "app_name"
]


def load_dataset(data_path: Path) -> pd.DataFrame:
    """Load a CSV dataset and validate its required columns and values."""
    dataframe = pd.read_csv(data_path)
    required_columns = FEATURE_COLUMNS + TARGET_COLUMNS
    missing_columns = [
        column for column in required_columns if column not in dataframe.columns
    ]
    if missing_columns:
        raise ValueError(f"Dataset is missing required columns: {missing_columns}")

    null_columns = dataframe.columns[dataframe.isna().any()].tolist()
    if null_columns:
        raise ValueError(f"Dataset contains NaN values in columns: {null_columns}")
    return dataframe


def build_pipeline() -> Pipeline:
   
    preprocessing = ColumnTransformer(
        transformers=[
            (
                "category",
                OneHotEncoder(handle_unknown="ignore"),
                ["app_category"],
            ),
            ("numeric", "passthrough", _NUMERIC_FEATURES),
        ]
    )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessing),
            (
                "regressor",
                RandomForestRegressor(
                    n_estimators=500,       # more trees → lower variance
                    max_depth=15,           # prevents over-fitting on small datasets
                    min_samples_leaf=2,     # smoother leaf estimates
                    max_features="sqrt",    # standard best-practice for regression RF
                    random_state=42,
                    n_jobs=-1,              # use all CPU cores
                ),
            ),
        ]
    )


def build_model_pipeline(model_name: str) -> Pipeline:
    """Build the shared feature pipeline and selected multi-output estimator."""
    pipeline = build_pipeline()
    if model_name == "rf":
        return pipeline
    if model_name == "gbr":
        estimator = MultiOutputRegressor(
            GradientBoostingRegressor(
                n_estimators=300,       # more boosting rounds
                learning_rate=0.05,     # smaller steps → less overfitting
                max_depth=4,            # shallow trees work best for boosting
                subsample=0.8,          # stochastic boosting for variance reduction
                random_state=42,
            )
        )
        pipeline.set_params(regressor=estimator)
        return pipeline
    if model_name == "ridge":
        pipeline.steps.insert(1, ("scaler", StandardScaler()))
        pipeline.set_params(regressor=MultiOutputRegressor(Ridge()))
        return pipeline
    raise ValueError(f"Unsupported model {model_name!r}; choose rf, gbr, or ridge")


def chronological_split(
    dataframe: pd.DataFrame,
) -> tuple[pd.Index, pd.Index]:
    """Return train/test row indices with each app's latest 20% held out."""
    train_indices: list[int] = []
    test_indices: list[int] = []
    for _, group in dataframe.groupby("app_name", sort=False):
        indices = list(group.index)
        if len(indices) < 2:
            train_indices.extend(indices)
            continue
        test_size = max(1, ceil(len(indices) * 0.2))
        test_size = min(test_size, len(indices) - 1)
        train_indices.extend(indices[:-test_size])
        test_indices.extend(indices[-test_size:])
    if not train_indices or not test_indices:
        raise ValueError(
            "Chronological evaluation requires at least one training row and "
            "one test row across apps"
        )
    return pd.Index(train_indices), pd.Index(test_indices)


def _load_app_profiles(
    profile_path: Path,
    dataframe: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    """Load serving profiles from a sibling CSV or use latest training rows."""
    if profile_path.is_file():
        profiles = pd.read_csv(profile_path)
        required_columns = ["app_name", *_APP_PROFILE_COLUMNS]
        missing_columns = [
            column for column in required_columns if column not in profiles.columns
        ]
        if missing_columns:
            raise ValueError(
                f"App profiles file is missing required columns: {missing_columns}"
            )
        if profiles[required_columns].isna().any().any():
            raise ValueError(f"App profiles file contains NaN values: {profile_path}")
        profile_rows = profiles[required_columns]
    else:
        profile_rows = dataframe.drop_duplicates("app_name", keep="last")[
            ["app_name", *_APP_PROFILE_COLUMNS]
        ]

    return {
        str(row["app_name"]): {
            column: row[column] for column in _APP_PROFILE_COLUMNS
        }
        for _, row in profile_rows.iterrows()
    }


def train_and_save(
    data_path: Path,
    output_path: Path,
    model_name: str = "rf",
) -> dict[str, Any]:
    """Chronologically evaluate, refit, and save the selected model bundle."""
    dataframe = load_dataset(data_path)
    features = dataframe[FEATURE_COLUMNS]
    targets = dataframe[TARGET_COLUMNS]
    train_indices, test_indices = chronological_split(dataframe)

    pipeline = build_model_pipeline(model_name)
    pipeline.fit(features.loc[train_indices], targets.loc[train_indices])
    y_test = targets.loc[test_indices]
    predictions = pipeline.predict(features.loc[test_indices])
    print("Chronological test split MAE:")
    print(f"{'Target':<12} MAE")
    print("-" * 20)
    for index, target in enumerate(TARGET_COLUMNS):
        mae = mean_absolute_error(y_test[target], predictions[:, index])
        print(f"{target:<12} {mae:.4f}")

    pipeline.fit(features, targets)
    app_profiles = _load_app_profiles(
        data_path.parent / "app_profiles.csv",
        dataframe,
    )
    bundle: dict[str, Any] = {
        "pipeline": pipeline,
        "feature_columns": FEATURE_COLUMNS.copy(),
        "target_columns": TARGET_COLUMNS.copy(),
        "app_profiles": app_profiles,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_rows": len(dataframe),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, output_path)
    print(f"Saved model bundle to {output_path}")
    return bundle


def _resolve_path(path: str) -> Path:
    """Resolve a CLI path relative to the repository root unless absolute."""
    parsed_path = Path(path)
    return parsed_path if parsed_path.is_absolute() else resolve_path(path)


def main() -> None:
    """Parse command-line options and train the model bundle."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        default="data/sample/sample_dataset.csv",
        help="CSV training dataset path",
    )
    parser.add_argument(
        "--out",
        default="model/artifacts/model.pkl",
        help="Output path for the joblib bundle",
    )
    parser.add_argument(
        "--model",
        choices=("rf", "gbr", "ridge"),
        default="rf",
        help="Regressor to train",
    )
    args = parser.parse_args()

    try:
        train_and_save(
            _resolve_path(args.data),
            _resolve_path(args.out),
            model_name=args.model,
        )
    except ValueError as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
