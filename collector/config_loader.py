"""Load and validate configured resource workload applications."""

import os
import re
import shutil
import sys
import warnings
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

import yaml

from config import REPO_ROOT, resolve_path

_APP_NAME_PATTERN = re.compile(r"^[a-z0-9_.-]{1,64}$")
_PLACEHOLDER_PATTERN = re.compile(r"\{([^{}]+)\}")
_SUPPORTED_PLACEHOLDERS = {"python", "repo", "tmp"}
_REQUIRED_FIELDS = {
    "name",
    "category",
    "command",
    "cwd",
    "timeout_s",
    "variants",
    "exe",
}
_ALLOWED_FIELDS = _REQUIRED_FIELDS | {"optional"}
_STATIC_PLACEHOLDERS = {
    "{python}": sys.executable,
    "{repo}": str(REPO_ROOT),
}


@dataclass(frozen=True)
class AppSpec:
    """Validated workload configuration and executable metadata."""

    name: str
    category: str
    command: tuple[str, ...]
    cwd: str
    timeout_s: float
    variants: tuple[tuple[str, ...], ...]
    exe: Path
    exe_size_mb: float
    optional: bool = False

    def command_for_run(self, tmp_dir: Path, variant_index: int = 0) -> list[str]:
        """Expand a variant into command arguments for one launcher-created temp dir."""
        if not 0 <= variant_index < len(self.variants):
            raise IndexError(f"variant index out of range for app {self.name}")
        placeholders = dict(_STATIC_PLACEHOLDERS)
        placeholders["{tmp}"] = str(tmp_dir.resolve())
        tokens = (*self.command, *self.variants[variant_index])
        return [_expand_placeholders(token, placeholders) for token in tokens]

    def working_directory_for_run(self, tmp_dir: Path) -> Path:
        """Resolve the configured working directory for a single run."""
        placeholders = dict(_STATIC_PLACEHOLDERS)
        placeholders["{tmp}"] = str(tmp_dir.resolve())
        return Path(_expand_placeholders(self.cwd, placeholders))


def _expand_placeholders(value: str, placeholders: dict[str, str]) -> str:
    """Replace supported launcher placeholders in a string."""
    expanded = value
    for placeholder, replacement in placeholders.items():
        expanded = expanded.replace(placeholder, replacement)
    return expanded


def _validate_placeholders(value: str, field: str, app_name: str) -> None:
    """Reject unknown placeholder names in configured values."""
    unknown = {
        placeholder
        for placeholder in _PLACEHOLDER_PATTERN.findall(value)
        if placeholder not in _SUPPORTED_PLACEHOLDERS
    }
    if unknown:
        raise ValueError(
            f"app {app_name!r}: {field} has unsupported placeholders: "
            f"{sorted(unknown)}"
        )


def _resolve_config_path(path: str | Path | None) -> Path:
    """Resolve the app YAML path relative to the repository unless absolute."""
    if path is None:
        return resolve_path("collector", "apps_config.yaml")
    candidate = Path(path)
    return candidate if candidate.is_absolute() else resolve_path(str(path))


def _validate_text(value: Any, field: str, app_name: str) -> str:
    """Validate a non-empty string field from one app mapping."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"app {app_name!r}: {field} must be a non-empty string")
    return value


def _resolve_executable(value: str, app_name: str) -> Path | None:
    """Resolve an executable from PATH, an absolute path, or a repo-relative path."""
    expanded = os.path.expandvars(os.path.expanduser(value))
    candidate = Path(expanded)
    if candidate.is_absolute():
        resolved = candidate
    elif "\\" in expanded or "/" in expanded:
        resolved = resolve_path(expanded)
    else:
        located = shutil.which(expanded)
        if located is None:
            return None
        resolved = Path(located)

    resolved = resolved.resolve()
    if not resolved.is_file():
        return None
    return resolved


def _validate_app(raw: Any, index: int) -> AppSpec | None:
    """Validate one YAML app mapping and return its spec or skip an optional app."""
    if not isinstance(raw, dict):
        raise ValueError(f"apps[{index}] must be a mapping")

    raw_name = raw.get("name")
    if not isinstance(raw_name, str) or not _APP_NAME_PATTERN.fullmatch(raw_name):
        raise ValueError(
            f"apps[{index}].name must match ^[a-z0-9_.-]{{1,64}}$"
        )
    name = raw_name

    missing = sorted(_REQUIRED_FIELDS - raw.keys())
    if missing:
        raise ValueError(f"app {name!r} is missing fields: {missing}")
    unexpected = sorted(raw.keys() - _ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"app {name!r} has unknown fields: {unexpected}")

    category = _validate_text(raw["category"], "category", name)
    if not isinstance(raw["command"], list) or not raw["command"]:
        raise ValueError(f"app {name!r}: command must be a non-empty list")
    for token_index, token in enumerate(raw["command"]):
        if isinstance(token, str):
            _validate_placeholders(token, f"command[{token_index}]", name)
    command = tuple(
        _expand_placeholders(
            _validate_text(token, f"command[{token_index}]", name),
            _STATIC_PLACEHOLDERS,
        )
        for token_index, token in enumerate(raw["command"])
    )

    cwd = _validate_text(raw["cwd"], "cwd", name)
    _validate_placeholders(cwd, "cwd", name)
    cwd = _expand_placeholders(cwd, _STATIC_PLACEHOLDERS)
    if "{tmp}" not in cwd:
        cwd_path = Path(cwd)
        if not cwd_path.is_absolute():
            cwd_path = resolve_path(cwd)
        if not cwd_path.is_dir():
            raise ValueError(f"app {name!r}: cwd is not an existing directory: {cwd}")

    timeout = raw["timeout_s"]
    if isinstance(timeout, bool) or not isinstance(timeout, (float, int)):
        raise ValueError(f"app {name!r}: timeout_s must be a positive number")
    timeout_s = float(timeout)
    if not isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError(f"app {name!r}: timeout_s must be a positive number")

    raw_variants = raw["variants"]
    if (
        not isinstance(raw_variants, list)
        or not 2 <= len(raw_variants) <= 3
    ):
        raise ValueError(f"app {name!r}: variants must contain 2 or 3 argument sets")
    variants: list[tuple[str, ...]] = []
    for variant_index, variant in enumerate(raw_variants):
        if not isinstance(variant, list) or not variant:
            raise ValueError(
                f"app {name!r}: variants[{variant_index}] must be a non-empty list"
            )
        for token_index, token in enumerate(variant):
            if isinstance(token, str):
                _validate_placeholders(
                    token,
                    f"variants[{variant_index}][{token_index}]",
                    name,
                )
        variants.append(
            tuple(
                _expand_placeholders(
                    _validate_text(
                        token,
                        f"variants[{variant_index}][{token_index}]",
                        name,
                    ),
                    _STATIC_PLACEHOLDERS,
                )
                for token_index, token in enumerate(variant)
            )
        )

    optional = raw.get("optional", False)
    if not isinstance(optional, bool):
        raise ValueError(f"app {name!r}: optional must be a boolean")
    exe_value = _validate_text(raw["exe"], "exe", name)
    _validate_placeholders(exe_value, "exe", name)
    if "{tmp}" in exe_value:
        raise ValueError(f"app {name!r}: exe cannot use the {{tmp}} placeholder")
    exe_value = _expand_placeholders(exe_value, _STATIC_PLACEHOLDERS)
    exe_path = _resolve_executable(exe_value, name)
    if exe_path is None:
        message = f"app {name!r}: executable not found: {exe_value}"
        if optional:
            warnings.warn(f"Skipping optional {message}", RuntimeWarning, stacklevel=2)
            return None
        raise ValueError(message)

    exe_size_mb = exe_path.stat().st_size / (1024 * 1024)
    return AppSpec(
        name=name,
        category=category,
        command=command,
        cwd=cwd,
        timeout_s=timeout_s,
        variants=tuple(variants),
        exe=exe_path,
        exe_size_mb=exe_size_mb,
        optional=optional,
    )


def load_apps(path: str | Path | None = None) -> dict[str, AppSpec]:
    """Load app specs from YAML, validating fields and resolving executables."""
    config_path = _resolve_config_path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"App configuration file not found: {config_path}")
    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            document = yaml.safe_load(config_file)
    except yaml.YAMLError as error:
        raise ValueError(f"Invalid YAML in {config_path}: {error}") from error

    if not isinstance(document, dict) or set(document) != {"apps"}:
        raise ValueError(f"{config_path} must contain only an 'apps' list")
    if not isinstance(document["apps"], list):
        raise ValueError(f"{config_path}: apps must be a list")

    apps: dict[str, AppSpec] = {}
    names: set[str] = set()
    for index, raw_app in enumerate(document["apps"]):
        if isinstance(raw_app, dict):
            raw_name = raw_app.get("name")
            if isinstance(raw_name, str) and raw_name in names:
                raise ValueError(f"Duplicate app name: {raw_name}")
            if isinstance(raw_name, str):
                names.add(raw_name)
        spec = _validate_app(raw_app, index)
        if spec is not None:
            apps[spec.name] = spec
    return apps


def main() -> None:
    """Print configured applications and executable size information."""
    apps = load_apps()
    headers = ("name", "category", "exe path", "exe_size_mb", "variants")
    rows = [
        (
            spec.name,
            spec.category,
            str(spec.exe),
            f"{spec.exe_size_mb:.4f}",
            str(len(spec.variants)),
        )
        for spec in apps.values()
    ]
    widths = [
        max([len(headers[column]), *(len(row[column]) for row in rows)])
        for column in range(len(headers))
    ]
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


if __name__ == "__main__":
    main()
