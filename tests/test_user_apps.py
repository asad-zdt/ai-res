"""Tests for user-selected executable registration."""

from pathlib import Path

import pytest

import collector.user_apps as user_apps


def test_register_user_app_creates_stable_safe_identifier(tmp_path: Path) -> None:
    executable = tmp_path / "Example App.exe"
    executable.write_bytes(b"binary")
    registry = tmp_path / "registry.yaml"

    first_name = user_apps.register_user_app(executable, registry)
    second_name = user_apps.register_user_app(executable, registry)

    assert first_name == second_name
    assert first_name.startswith("user_example_app_")
    assert user_apps._read_registry(registry) == {first_name: executable.resolve()}


def test_register_user_app_rejects_non_executable_files(tmp_path: Path) -> None:
    script = tmp_path / "app.py"
    script.write_text("pass", encoding="utf-8")

    with pytest.raises(ValueError, match="Windows .exe"):
        user_apps.register_user_app(script, tmp_path / "registry.yaml")


def test_load_user_apps_builds_no_argument_workload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "Example.exe"
    executable.write_bytes(b"binary")
    registry = tmp_path / "registry.yaml"
    app_name = user_apps.register_user_app(executable, registry)
    monkeypatch.setattr(user_apps, "load_apps", lambda: {})

    apps = user_apps.load_user_apps(registry)
    spec = apps[app_name]

    assert spec.command == (str(executable.resolve()),)
    assert spec.variants == ((),)
    assert spec.cwd == str(tmp_path)
    assert spec.exe == executable.resolve()


def test_load_user_apps_rejects_configured_name_collisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "Example.exe"
    executable.write_bytes(b"binary")
    registry = tmp_path / "registry.yaml"
    app_name = user_apps.register_user_app(executable, registry)
    monkeypatch.setattr(user_apps, "load_apps", lambda: {app_name: object()})

    with pytest.raises(ValueError, match="conflict"):
        user_apps.load_user_apps(registry)
