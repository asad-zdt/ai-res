"""Run the project build, model, API, and enforcement smoke checks."""

from __future__ import annotations

import json
import math
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import psutil
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from collector.config_loader import load_apps
from config import resolve_path
from os_integration.job_manager import JobManager

_METRIC_NAMES = ("cpu_pct", "ram_mb", "disk_mbps", "net_kbps")
_PROCESS_ERRORS = (
    psutil.NoSuchProcess,
    psutil.AccessDenied,
    psutil.ZombieProcess,
)


class E2EFailure(RuntimeError):
    """Raised when one end-to-end stage fails and later stages must stop."""


def _record(
    results: list[tuple[str, str, str]],
    name: str,
    status: str,
    detail: str = "",
) -> None:
    """Append one result row and print its immediate status."""
    results.append((name, status, detail))
    suffix = f": {detail}" if detail else ""
    print(f"{status}: {name}{suffix}")


def _run_stage(
    results: list[tuple[str, str, str]],
    name: str,
    arguments: list[str],
) -> None:
    """Run a project module and stop immediately when it returns an error."""
    python = resolve_path(".venv", "Scripts", "python.exe")
    command = [str(python), *arguments]
    print(f"\n> {' '.join(arguments)}")
    try:
        completed = subprocess.run(command, cwd=resolve_path(), check=False)
    except OSError as error:
        detail = f"could not start command: {error}"
        _record(results, name, "FAIL", detail)
        raise E2EFailure(f"{name} failed: {detail}") from error
    if completed.returncode != 0:
        detail = f"exit code {completed.returncode}"
        _record(results, name, "FAIL", detail)
        raise E2EFailure(f"{name} failed with {detail}")
    _record(results, name, "PASS")


def _free_port() -> int:
    """Ask the operating system for an available local TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _request_json(
    url: str,
    method: str = "GET",
    payload: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Send one JSON HTTP request and decode its response."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"request failed: {error}") from error

    try:
        decoded = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"response was not valid JSON: {error}") from error
    if not isinstance(decoded, dict):
        raise RuntimeError("response JSON must be an object")
    return decoded


def _wait_for_health(
    process: subprocess.Popen[bytes],
    url: str,
    timeout_s: float = 30.0,
) -> None:
    """Wait for the API health endpoint or report startup failure."""
    deadline = time.monotonic() + timeout_s
    last_error = "health endpoint did not respond"
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(f"API process exited with code {return_code}")
        try:
            response = _request_json(url)
            if response.get("status") != "ok":
                raise RuntimeError(f"unexpected health response: {response}")
            return
        except (RuntimeError, urllib.error.URLError, TimeoutError) as error:
            last_error = str(error)
            time.sleep(0.25)
    raise RuntimeError(f"API health check timed out: {last_error}")


def _assert_metrics(value: Any, context: str) -> None:
    """Require all four resource metrics to be finite, non-negative numbers."""
    if not isinstance(value, dict) or set(value) != set(_METRIC_NAMES):
        raise RuntimeError(f"{context} must contain exactly the four resource metrics")
    for name in _METRIC_NAMES:
        metric = value[name]
        if (
            isinstance(metric, bool)
            or not isinstance(metric, (int, float))
            or not math.isfinite(metric)
            or metric < 0
        ):
            raise RuntimeError(f"{context}.{name} must be a non-negative finite number")


def _configured_app_names() -> tuple[list[str], list[str]]:
    """Return configured app names, separating optional unavailable apps."""
    path = resolve_path("collector", "apps_config.yaml")
    with path.open("r", encoding="utf-8") as config_file:
        document = yaml.safe_load(config_file)
    if not isinstance(document, dict) or not isinstance(document.get("apps"), list):
        raise ValueError(f"Invalid application configuration: {path}")

    available = load_apps()
    names: list[str] = []
    skipped: list[str] = []
    for item in document["apps"]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError(f"Invalid app entry in {path}: {item!r}")
        app_name = item["name"]
        if app_name in available:
            names.append(app_name)
        elif item.get("optional") is True:
            skipped.append(app_name)
        else:
            raise ValueError(
                f"Configured app {app_name!r} is unavailable but is not optional"
            )
    return names, skipped


def _stop_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Terminate the API process and any descendants using psutil."""
    try:
        root = psutil.Process(process.pid)
        descendants = root.children(recursive=True)
    except _PROCESS_ERRORS:
        descendants = []
        root = None

    processes = [*reversed(descendants)]
    if root is not None:
        processes.append(root)
    for child in processes:
        try:
            child.terminate()
        except _PROCESS_ERRORS:
            continue

    _, survivors = psutil.wait_procs(processes, timeout=5)
    for child in survivors:
        try:
            child.kill()
        except _PROCESS_ERRORS:
            continue
    if survivors:
        psutil.wait_procs(survivors, timeout=5)
    process.wait(timeout=5)


def _print_summary(results: list[tuple[str, str, str]]) -> None:
    """Print a compact PASS/FAIL/SKIPPED table for completed stages."""
    print("\nE2E summary")
    headers = ("Stage", "Result", "Details")
    rows = [headers, *results]
    widths = [
        max(len(row[index]) for row in rows)
        for index in range(len(headers))
    ]
    print(" | ".join(headers[index].ljust(widths[index]) for index in range(3)))
    print("-+-".join("-" * width for width in widths))
    for row in results:
        print(" | ".join(row[index].ljust(widths[index]) for index in range(3)))


def main() -> int:
    """Run all end-to-end stages and return a process exit status."""
    results: list[tuple[str, str, str]] = []
    api_process: subprocess.Popen[bytes] | None = None
    try:
        _run_stage(results, "build_dataset", ["-m", "features.build_dataset"])
        _run_stage(
            results,
            "train",
            ["-m", "model.train", "--data", "data/processed/dataset.csv"],
        )
        _run_stage(results, "evaluate", ["-m", "model.evaluate"])

        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        python = resolve_path(".venv", "Scripts", "python.exe")
        command = [
            str(python),
            "-m",
            "uvicorn",
            "service.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        try:
            api_process = subprocess.Popen(
                command,
                cwd=resolve_path(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        except OSError as error:
            detail = f"could not start API: {error}"
            _record(results, "API startup", "FAIL", detail)
            raise E2EFailure(detail) from error
        _record(results, "API startup", "PASS", f"port {port}")

        try:
            _wait_for_health(api_process, f"{base_url}/health")
        except RuntimeError as error:
            _record(results, "API health", "FAIL", str(error))
            raise E2EFailure(f"API health check failed: {error}") from error
        _record(results, "API health", "PASS")

        try:
            app_names, skipped_apps = _configured_app_names()
        except (OSError, ValueError, yaml.YAMLError) as error:
            _record(results, "Application config", "FAIL", str(error))
            raise E2EFailure(f"Could not load configured apps: {error}") from error
        for app_name in skipped_apps:
            _record(
                results,
                f"predict {app_name}",
                "SKIPPED",
                "optional app executable is unavailable",
            )
        if not app_names:
            _record(results, "API predictions", "FAIL", "no available configured apps")
            raise E2EFailure("No configured apps are available for prediction")

        for app_name in app_names:
            try:
                response = _request_json(
                    f"{base_url}/predict",
                    method="POST",
                    payload={"app_name": app_name},
                )
                if response.get("app_name") != app_name:
                    raise RuntimeError(f"unexpected app_name in response: {response}")
                _assert_metrics(response.get("predicted"), "predicted")
            except RuntimeError as error:
                _record(results, f"predict {app_name}", "FAIL", str(error))
                raise E2EFailure(f"Prediction failed for {app_name}: {error}") from error
            _record(results, f"predict {app_name}", "PASS")

        try:
            comparison = _request_json(
                f"{base_url}/run-and-compare",
                method="POST",
                payload={"app_name": "cpu_burn"},
            )
            if comparison.get("app_name") != "cpu_burn":
                raise RuntimeError(f"unexpected app_name in response: {comparison}")
            _assert_metrics(comparison.get("predicted"), "predicted")
            _assert_metrics(comparison.get("actual"), "actual")
            duration = comparison.get("duration_s")
            if (
                isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or not math.isfinite(duration)
                or duration < 0
            ):
                raise RuntimeError("duration_s must be a non-negative finite number")
            enforcement = comparison.get("enforcement")
            if not isinstance(enforcement, dict):
                raise RuntimeError("enforcement must be an object")
            if enforcement.get("admitted") is not True:
                raise RuntimeError("enforcement.admitted must be true")
            if not isinstance(enforcement.get("cgroup_applied"), bool):
                raise RuntimeError("enforcement.cgroup_applied must be a boolean")
        except RuntimeError as error:
            _record(results, "run-and-compare cpu_burn", "FAIL", str(error))
            raise E2EFailure(f"run-and-compare failed: {error}") from error

        _record(results, "run-and-compare cpu_burn", "PASS")
        if not JobManager().is_available():
            reason = comparison["enforcement"].get("reason")
            _record(
                results,
                "Job Object enforcement",
                "SKIPPED",
                str(reason or "Job Objects are unavailable on this machine"),
            )
        else:
            _record(results, "Job Object enforcement", "PASS")
    except E2EFailure:
        pass
    except Exception as error:
        _record(results, "E2E workflow", "FAIL", f"{type(error).__name__}: {error}")
    finally:
        if api_process is not None:
            try:
                _stop_process_tree(api_process)
                _record(results, "API cleanup", "PASS")
            except (OSError, psutil.Error, subprocess.TimeoutExpired) as error:
                _record(results, "API cleanup", "FAIL", str(error))

    _print_summary(results)
    return 1 if any(status == "FAIL" for _, status, _ in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
