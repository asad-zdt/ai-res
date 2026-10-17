"""Streamlit application selector and prediction action."""

from typing import Any
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from collector.config_loader import AppSpec, load_apps
from config import resolve_path
from gui.api_client import ApiClient, ApiError, ApiUnreachable


def _load_app_options() -> tuple[list[str], dict[str, AppSpec], bool]:
    """Load configured apps, falling back to names in the sample CSV."""
    try:
        apps = load_apps()
    except (OSError, ValueError) as error:
        st.warning(
            "Could not load the application configuration; using application "
            f"names from the sample dataset instead. ({error})"
        )
        sample_path = resolve_path("data", "sample", "sample_dataset.csv")
        try:
            frame = pd.read_csv(sample_path, usecols=["app_name"])
        except (OSError, ValueError, pd.errors.ParserError) as csv_error:
            st.error(f"Could not load fallback application names: {csv_error}")
            return [], {}, True
        names = sorted(
            {
                name.strip()
                for name in frame["app_name"].dropna()
                if isinstance(name, str) and name.strip()
            }
        )
        return names, {}, True
    return sorted(apps), apps, False


def _record_comparison(app_name: str, result: dict[str, Any]) -> None:
    """Append one successful comparison and its per-target error percentages."""
    predicted = result["predicted"]
    actual = result["actual"]
    row: dict[str, Any] = {
        "time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "app": app_name,
    }
    for metric in ("cpu_pct", "ram_mb", "disk_mbps", "net_kbps"):
        actual_value = float(actual[metric])
        row[f"{metric} error %"] = (
            "n/a"
            if actual_value == 0
            else f"{(float(predicted[metric]) - actual_value) / actual_value * 100:.1f}%"
        )
    history = st.session_state.setdefault("comparison_history", [])
    history.append(row)


def render_app_picker(api: ApiClient) -> tuple[str | None, bool, bool]:
    """Render app selection and request a prediction when clicked."""
    names, apps, fallback = _load_app_options()
    selected_app: str | None = None
    predict_clicked = False
    compare_clicked = False

    if names:
        selected_app = st.selectbox("Application", names)
        if fallback:
            st.caption("Category and executable size are unavailable for fallback apps.")
        else:
            spec = apps[selected_app]
            st.caption(
                f"Category: {spec.category} | Executable size: "
                f"{spec.exe_size_mb:.2f} MB"
            )
    else:
        st.error("No applications are available to select.")

    predict_col, compare_col = st.columns(2)
    with predict_col:
        predict_clicked = st.button("Predict", disabled=not names)
    with compare_col:
        compare_clicked = st.button("Run and compare", disabled=not names)

    if predict_clicked and selected_app is not None:
        try:
            with st.spinner(f"Predicting resources for {selected_app}..."):
                prediction: dict[str, Any] = api.predict(selected_app)
            st.session_state["prediction"] = {
                "app_name": selected_app,
                "result": prediction,
            }
        except ApiError as error:
            st.error(str(error))
        except ApiUnreachable as error:
            st.error(str(error))

    if compare_clicked and selected_app is not None:
        st.session_state.pop("comparison", None)
        try:
            with st.spinner(
                f"Running {selected_app}, this can take up to a minute..."
            ):
                comparison = api.run_and_compare(selected_app)
            st.session_state["comparison"] = {
                "app_name": selected_app,
                "result": comparison,
            }
            _record_comparison(selected_app, comparison)
        except ApiError as error:
            if error.status_code == 409:
                st.warning(str(error))
            else:
                st.error(str(error))
        except ApiUnreachable as error:
            st.error(str(error))

    return selected_app, predict_clicked, compare_clicked
