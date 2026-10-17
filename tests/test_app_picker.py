"""Tests for the Streamlit application picker."""

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pandas as pd

from gui.components import app_picker
from gui.api_client import ApiError


class FakeStreamlit:
    """Capture picker UI calls and provide a controllable selection."""

    def __init__(self, selected: str = "cpu_burn", clicked: bool = True) -> None:
        self.selected = selected
        self.clicked = clicked
        self.compare_clicked = False
        self.session_state: dict[str, Any] = {}
        self.captions: list[str] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def selectbox(self, label: str, options: list[str]) -> str:
        """Return the configured app selection."""
        assert label == "Application"
        assert self.selected in options
        return self.selected

    def button(self, label: str, disabled: bool = False) -> bool:
        """Return the configured click state."""
        return {
            "Predict": self.clicked,
            "Run and compare": self.compare_clicked,
        }[label] and not disabled

    def columns(self, count: int) -> list["FakeStreamlit"]:
        """Act as inert column contexts."""
        return [self] * count

    def __enter__(self) -> "FakeStreamlit":
        """Enter a fake column context."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit a fake column context."""

    def caption(self, text: str) -> None:
        """Record a caption."""
        self.captions.append(text)

    def error(self, text: str) -> None:
        """Record an error."""
        self.errors.append(text)

    def warning(self, text: str) -> None:
        """Record a warning."""
        self.warnings.append(text)

    @contextmanager
    def spinner(self, text: str):
        """Provide a no-op spinner context."""
        yield


def test_picker_stores_prediction_and_shows_app_metadata(
    monkeypatch,
) -> None:
    """Render configured metadata and persist the clicked prediction."""
    fake_st = FakeStreamlit()
    monkeypatch.setattr(app_picker, "st", fake_st)
    monkeypatch.setattr(
        app_picker,
        "load_apps",
        lambda: {
            "cpu_burn": SimpleNamespace(
                category="synthetic_cpu",
                exe_size_mb=1.25,
            )
        },
    )

    class FakeApi:
        def predict(self, app_name: str) -> dict[str, Any]:
            return {"app_name": app_name, "predicted": {"cpu_pct": 10.0}}

    selected, clicked, compared = app_picker.render_app_picker(FakeApi())  # type: ignore[arg-type]

    assert (selected, clicked, compared) == ("cpu_burn", True, False)
    assert fake_st.captions == [
        "Category: synthetic_cpu | Executable size: 1.25 MB"
    ]
    assert fake_st.session_state["prediction"] == {
        "app_name": "cpu_burn",
        "result": {"app_name": "cpu_burn", "predicted": {"cpu_pct": 10.0}},
    }
    assert not fake_st.errors


def test_picker_falls_back_to_sample_names_and_shows_warning(
    monkeypatch,
) -> None:
    """Use sample app names when the YAML configuration cannot load."""
    fake_st = FakeStreamlit(selected="fallback_app", clicked=False)
    monkeypatch.setattr(app_picker, "st", fake_st)

    def fail_load_apps():
        raise ValueError("invalid application YAML")

    monkeypatch.setattr(app_picker, "load_apps", fail_load_apps)
    monkeypatch.setattr(
        app_picker.pd,
        "read_csv",
        lambda *args, **kwargs: pd.DataFrame(
            {"app_name": ["fallback_app", "fallback_app", None]}
        ),
    )

    selected, clicked, compared = app_picker.render_app_picker(object())  # type: ignore[arg-type]

    assert (selected, clicked, compared) == ("fallback_app", False, False)
    assert len(fake_st.warnings) == 1
    assert fake_st.captions == [
        "Category and executable size are unavailable for fallback apps."
    ]


def test_picker_displays_api_error_without_storing_prediction(
    monkeypatch,
) -> None:
    """Display API details inline without allowing an exception to escape."""
    fake_st = FakeStreamlit()
    monkeypatch.setattr(app_picker, "st", fake_st)
    monkeypatch.setattr(
        app_picker,
        "load_apps",
        lambda: {
            "cpu_burn": SimpleNamespace(category="synthetic_cpu", exe_size_mb=1.0)
        },
    )

    class FailingApi:
        def predict(self, app_name: str) -> dict[str, Any]:
            raise ApiError(409, "Admission refused")

    selected, clicked, compared = app_picker.render_app_picker(FailingApi())  # type: ignore[arg-type]

    assert (selected, clicked, compared) == ("cpu_burn", True, False)
    assert fake_st.errors == ["Admission refused"]
    assert "prediction" not in fake_st.session_state
