"""Application choices collected from project configuration and Windows."""

from __future__ import annotations

import os
import re
import shlex
import sys
from pathlib import Path

from collector.config_loader import load_apps
from collector.user_apps import load_user_apps

ApplicationOption = tuple[str, Path | None, str]


def executable_from_icon(value: str) -> Path | None:
    """Resolve an executable path from a Windows DisplayIcon value."""
    unquoted_path = re.sub(r",\s*-?\d+\s*$", "", value.strip()).strip('"')
    if unquoted_path:
        candidate = Path(os.path.expandvars(unquoted_path))
        if candidate.is_file() and candidate.suffix.casefold() == ".exe":
            return candidate.resolve()
    try:
        first_argument = shlex.split(value, posix=False)[0].strip('"')
    except (IndexError, ValueError):
        return None
    candidate = Path(os.path.expandvars(first_argument))
    if candidate.is_file() and candidate.suffix.casefold() == ".exe":
        return candidate.resolve()
    return None


def installed_applications() -> dict[str, Path]:
    """Discover Windows applications with registry-backed executable paths."""
    if sys.platform != "win32":
        return {}
    import winreg

    found: dict[str, Path] = {}
    uninstall_key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    app_paths_key = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
    registry_roots = (
        (winreg.HKEY_CURRENT_USER, 0),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
    )
    for root, view in registry_roots:
        try:
            with winreg.OpenKey(root, uninstall_key, 0, winreg.KEY_READ | view) as key:
                subkeys = [
                    winreg.EnumKey(key, index)
                    for index in range(winreg.QueryInfoKey(key)[0])
                ]
        except OSError:
            subkeys = []
        for subkey in subkeys:
            try:
                with winreg.OpenKey(
                    root, f"{uninstall_key}\\{subkey}", 0, winreg.KEY_READ | view
                ) as entry:
                    display_name = winreg.QueryValueEx(entry, "DisplayName")[0]
                    display_icon = winreg.QueryValueEx(entry, "DisplayIcon")[0]
            except OSError:
                continue
            if isinstance(display_name, str) and isinstance(display_icon, str):
                executable = executable_from_icon(display_icon)
                if executable is not None:
                    found.setdefault(display_name.strip(), executable)

        try:
            with winreg.OpenKey(root, app_paths_key, 0, winreg.KEY_READ | view) as key:
                subkeys = [
                    winreg.EnumKey(key, index)
                    for index in range(winreg.QueryInfoKey(key)[0])
                ]
        except OSError:
            subkeys = []
        for subkey in subkeys:
            if not subkey.casefold().endswith(".exe"):
                continue
            try:
                with winreg.OpenKey(
                    root, f"{app_paths_key}\\{subkey}", 0, winreg.KEY_READ | view
                ) as entry:
                    value = winreg.QueryValueEx(entry, None)[0]
            except OSError:
                continue
            if isinstance(value, str):
                executable = executable_from_icon(value)
                if executable is not None:
                    found.setdefault(Path(subkey).stem, executable)
    return found


def application_options() -> dict[str, ApplicationOption]:
    """Build selector entries with stable application IDs and category labels."""
    options: dict[str, ApplicationOption] = {}
    try:
        for name in sorted(load_apps()):
            options[f"[Configured] {name}"] = (name, None, "Configured")
        for name, spec in sorted(load_user_apps().items()):
            label = f"{spec.exe.stem} ({spec.exe.name})"
            visible = f"[Custom] {label}"
            if visible in options:
                visible = f"{visible} - {name[-8:]}"
            options[visible] = (name, spec.exe, "Custom")
    except (OSError, ValueError):
        pass
    for label, executable in sorted(
        installed_applications().items(), key=lambda item: item[0].casefold()
    ):
        visible = f"[Installed] {label}"
        if visible in options:
            visible = f"{visible} ({executable.name})"
        if visible in options:
            visible = f"{visible} - {executable.parent.name}"
        options[visible] = ("", executable, "Installed")
    return options
