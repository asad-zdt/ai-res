"""Tests for workload app configuration loading."""

from pathlib import Path

import pytest

from collector.config_loader import load_apps
from config import REPO_ROOT


def test_load_default_config_and_expand_command_placeholders(tmp_path: Path) -> None:
    """Load registered apps and expand Python, repo, and run-temp placeholders."""
    apps = load_apps()
    assert {
        "cpu_burn",
        "mem_hog",
        "disk_writer",
        "sort_big",
        "compile_build",
    } <= apps.keys()
    assert all(2 <= len(spec.variants) <= 3 for spec in apps.values())

    temp_directory = tmp_path / "run"
    temp_directory.mkdir()
    command = apps["disk_writer"].command_for_run(temp_directory, variant_index=0)
    assert command[0].endswith("python.exe") or command[0].endswith("python")
    assert command[1] == str(REPO_ROOT / "collector" / "workloads" / "disk_writer.py")
    assert command[-1] == str(temp_directory.resolve())
    assert apps["disk_writer"].working_directory_for_run(temp_directory) == REPO_ROOT


def test_load_apps_rejects_duplicate_names(tmp_path: Path) -> None:
    """Reject duplicated app identifiers even if one app could be optional."""
    script_path = REPO_ROOT / "collector" / "workloads" / "cpu_burn.py"
    app_definition = f"""\
name: cpu_burn
category: test
command: ['{script_path}']
cwd: '{REPO_ROOT}'
timeout_s: 10
variants: [['--x', '1'], ['--x', '2']]
exe: '{script_path}'
"""
    config_path = tmp_path / "apps.yaml"
    config_path.write_text(f"apps:\n  - {app_definition.replace(chr(10), chr(10) + '    ')}\n  - {app_definition.replace(chr(10), chr(10) + '    ')}", encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate app name: cpu_burn"):
        load_apps(config_path)


def test_missing_optional_app_is_skipped_with_warning(tmp_path: Path) -> None:
    """Warn and skip an optional app whose executable cannot be resolved."""
    config_path = tmp_path / "apps.yaml"
    config_path.write_text(
        f"""\
apps:
  - name: optional_tool
    category: test
    command: [missing-tool]
    cwd: '{REPO_ROOT}'
    timeout_s: 10
    variants:
      - [--first]
      - [--second]
    exe: missing-tool
    optional: true
""",
        encoding="utf-8",
    )

    with pytest.warns(RuntimeWarning, match="Skipping optional"):
        assert load_apps(config_path) == {}


def test_linux_uses_additional_linux_workload_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Select the separate Linux config without changing the Windows config."""
    import collector.config_loader as config_loader

    monkeypatch.setattr(config_loader.sys, "platform", "linux")

    apps = load_apps()

    assert {"cpu_burn", "mem_hog", "disk_writer", "sort_big", "compile_build"} <= (
        apps.keys()
    )
    disk_writer = apps["disk_writer"]
    assert disk_writer.command[0] == config_loader.sys.executable
    assert disk_writer.command[1].endswith(
        "collector/workloads/disk_writer.py"
    )
