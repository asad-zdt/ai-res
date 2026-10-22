"""Register user-selected Windows applications for prediction and collection."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

from collector.config_loader import AppSpec, load_apps
from config import resolve_path

_DEFAULT_REGISTRY = resolve_path("data", "user_apps.yaml")
_APP_NAME_PATTERN = re.compile(r"[^a-z0-9_.-]+")
_APP_TIMEOUT_SECONDS = 15.0


def _app_name(executable: Path) -> str:
    """Create a stable, API-safe identifier from an executable path."""
    stem = _APP_NAME_PATTERN.sub("_", executable.stem.lower()).strip("_.-") or "app"
    suffix = hashlib.sha256(str(executable).casefold().encode("utf-8")).hexdigest()[:8]
    return f"user_{stem[:50]}_{suffix}"


def _read_registry(path: Path) -> dict[str, Path]:
    """Read the selected-app registry and validate its entries."""
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as registry_file:
            document: Any = yaml.safe_load(registry_file)
    except yaml.YAMLError as error:
        raise ValueError(f"Invalid selected-app registry {path}: {error}") from error
    if document is None:
        return {}
    if not isinstance(document, dict) or set(document) != {"apps"}:
        raise ValueError(f"{path} must contain only an 'apps' mapping")
    raw_apps = document["apps"]
    if not isinstance(raw_apps, dict):
        raise ValueError(f"{path}: apps must be a mapping")

    apps: dict[str, Path] = {}
    for name, raw_path in raw_apps.items():
        if not isinstance(name, str) or not isinstance(raw_path, str):
            raise ValueError(f"{path}: application names and paths must be strings")
        executable = Path(raw_path).resolve()
        if executable.is_file():
            apps[name] = executable
    return apps


def register_user_app(
    executable_path: str | Path,
    registry_path: Path | None = None,
) -> str:
    """Register an executable selected by the user and return its app identifier."""
    executable = Path(executable_path).expanduser().resolve(strict=True)
    if not executable.is_file() or executable.suffix.casefold() != ".exe":
        raise ValueError("Select an existing Windows .exe application.")

    path = registry_path or _DEFAULT_REGISTRY
    apps = _read_registry(path)
    name = _app_name(executable)
    apps[name] = executable
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as registry_file:
        yaml.safe_dump(
            {"apps": {key: str(value) for key, value in sorted(apps.items())}},
            registry_file,
            sort_keys=False,
        )
    temporary_path.replace(path)
    return name


def load_user_apps(registry_path: Path | None = None) -> dict[str, AppSpec]:
    """Load previously selected executable apps as safe no-argument workloads."""
    registry = registry_path or _DEFAULT_REGISTRY
    user_paths = _read_registry(registry)
    configured_names = set(load_apps())
    collisions = sorted(configured_names.intersection(user_paths))
    if collisions:
        raise ValueError(f"Selected app names conflict with configured apps: {collisions}")

    return {
        name: AppSpec(
            name=name,
            category="desktop_application",
            command=(str(executable),),
            cwd=str(executable.parent),
            timeout_s=_APP_TIMEOUT_SECONDS,
            variants=((),),
            exe=executable,
            exe_size_mb=executable.stat().st_size / (1024 * 1024),
        )
        for name, executable in user_paths.items()
    }


def load_all_apps() -> dict[str, AppSpec]:
    """Load configured workloads together with selected desktop applications."""
    apps = load_apps()
    apps.update(load_user_apps())
    return apps
