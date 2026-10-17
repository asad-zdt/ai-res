"""Validation helpers and shared model column definitions."""

import pandas as pd

from config import FEATURE_COLUMNS, TARGET_COLUMNS


def validate_frame(df: pd.DataFrame) -> None:
    """Validate required training columns and their basic value constraints."""
    required_columns = FEATURE_COLUMNS + TARGET_COLUMNS
    missing_columns = [column for column in required_columns if column not in df]
    if missing_columns:
        raise ValueError(f"Dataframe is missing required columns: {missing_columns}")

    null_columns = df.columns[df.isna().any()].tolist()
    if null_columns:
        raise ValueError(f"Dataframe contains NaN values in columns: {null_columns}")

    numeric_columns = df.select_dtypes(include="number").columns
    negative_columns = [
        column for column in numeric_columns if (df[column] < 0).any()
    ]
    if negative_columns:
        raise ValueError(
            f"Dataframe contains negative numeric values in columns: "
            f"{negative_columns}"
        )

    invalid_names = [
        index
        for index, value in df["app_name"].items()
        if not isinstance(value, str) or not value.strip()
    ]
    if invalid_names:
        raise ValueError(
            f"app_name must contain non-empty strings; invalid rows: {invalid_names}"
        )


__all__ = ["FEATURE_COLUMNS", "TARGET_COLUMNS", "validate_frame"]
