"""Compact Tkinter desktop interface for resource predictions."""

from __future__ import annotations

import csv
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

import psutil

from collector.config_loader import load_apps
from collector.user_apps import load_all_apps, load_user_apps, register_user_app
from config import REPO_ROOT, resolve_path
from gui.api_client import ApiClient, ApiError, ApiUnreachable

_METRICS = (
    ("cpu_pct", "CPU", "%"),
    ("ram_mb", "RAM", "MB"),
    ("disk_mbps", "Disk", "MB/s"),
    ("net_kbps", "Network", "KB/s"),
)
_DEFAULT_SCALES = {"disk_mbps": 10.0, "net_kbps": 1000.0}


def _executable_from_icon(value: str) -> Path | None:
    """Extract an existing executable path from a Windows DisplayIcon value."""
    unquoted_path = re.sub(r",\s*-?\d+\s*$", "", value.strip()).strip('"')
    if not unquoted_path:
        return None
    expanded = os.path.expandvars(unquoted_path)
    candidate = Path(expanded)
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


def _installed_applications() -> dict[str, Path]:
    """Find installed Windows applications with registered executable paths."""
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
                subkey_count = winreg.QueryInfoKey(key)[0]
                subkeys = [
                    winreg.EnumKey(key, index) for index in range(subkey_count)
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
            if not isinstance(display_name, str) or not isinstance(display_icon, str):
                continue
            executable = _executable_from_icon(display_icon)
            if executable is not None:
                found.setdefault(display_name.strip(), executable)

        try:
            with winreg.OpenKey(root, app_paths_key, 0, winreg.KEY_READ | view) as key:
                subkey_count = winreg.QueryInfoKey(key)[0]
                subkeys = [
                    winreg.EnumKey(key, index) for index in range(subkey_count)
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
                    executable_value = winreg.QueryValueEx(entry, None)[0]
            except OSError:
                continue
            if isinstance(executable_value, str):
                executable = _executable_from_icon(executable_value)
                if executable is not None:
                    found.setdefault(Path(subkey).stem, executable)
    return found


def _metric_scales() -> dict[str, float]:
    """Return chart limits based on system capacity and available sample data."""
    scales = {
        "cpu_pct": float((psutil.cpu_count(logical=True) or 1) * 100),
        "ram_mb": psutil.virtual_memory().total / (1024 * 1024),
        **_DEFAULT_SCALES,
    }
    for relative_path in (
        Path("data") / "processed" / "dataset.csv",
        Path("data") / "sample" / "sample_dataset.csv",
    ):
        path = resolve_path(*relative_path.parts)
        try:
            with path.open("r", newline="", encoding="utf-8") as file:
                rows = csv.DictReader(file)
                maxima = {metric: 0.0 for metric in _DEFAULT_SCALES}
                for row in rows:
                    for metric in maxima:
                        try:
                            maxima[metric] = max(maxima[metric], float(row[metric]))
                        except (KeyError, TypeError, ValueError):
                            continue
        except OSError:
            continue
        for metric, fallback in _DEFAULT_SCALES.items():
            if maxima[metric] > 0:
                scales[metric] = maxima[metric] * 1.5
            else:
                scales[metric] = fallback
        break
    return scales


def _error_percent(predicted: float, actual: float) -> str:
    """Format signed prediction error relative to the measured value."""
    if actual == 0:
        return "n/a"
    return f"{(predicted - actual) / actual * 100:.1f}%"


def _draw_gauge(canvas: tk.Canvas, value: float, maximum: float) -> None:
    """Draw a compact colored horizontal resource gauge."""
    canvas.delete("all")
    width = max(canvas.winfo_width(), 220)
    height = 32
    left, right = 2, width - 2
    bar_top, bar_bottom = 8, 23
    canvas.create_rectangle(left, bar_top, right, bar_bottom, fill="#e5e7eb", outline="")
    fraction = min(max(value / max(maximum, 1e-9), 0.0), 1.0)
    color = "#22a06b" if fraction < 0.5 else "#e5a000" if fraction < 0.8 else "#d14343"
    canvas.create_rectangle(
        left, bar_top, left + (right - left) * fraction, bar_bottom,
        fill=color, outline="",
    )
    canvas.configure(height=height)


def _draw_comparison(
    canvas: tk.Canvas,
    title: str,
    unit: str,
    predicted: float,
    actual: float,
) -> None:
    """Draw predicted and observed values as a paired bar chart."""
    canvas.delete("all")
    width = max(canvas.winfo_width(), 300)
    height = max(canvas.winfo_height(), 170)
    left, right, top, bottom = 42, width - 12, 32, height - 35
    canvas.create_text(left, 12, anchor="w", text=title, font=("Segoe UI", 10, "bold"))
    canvas.create_line(left, top, left, bottom, fill="#9ca3af")
    canvas.create_line(left, bottom, right, bottom, fill="#9ca3af")
    maximum = max(predicted, actual, 1e-9) * 1.2
    bar_width = min(64, (right - left) / 4)
    centers = (left + (right - left) * 0.34, left + (right - left) * 0.72)
    for center, value, label, color in (
        (centers[0], predicted, "Predicted", "#6366f1"),
        (centers[1], actual, "Actual", "#14b8a6"),
    ):
        bar_height = (bottom - top) * value / maximum
        x0, x1 = center - bar_width / 2, center + bar_width / 2
        y0 = bottom - bar_height
        canvas.create_rectangle(x0, y0, x1, bottom, fill=color, outline="")
        canvas.create_text(center, max(top - 8, y0 - 10), text=f"{value:.2f} {unit}")
        canvas.create_text(center, bottom + 14, text=label)


def _terminate_process_tree(pid: int) -> None:
    """Stop an API process and its descendants using psutil."""
    try:
        root = psutil.Process(pid)
        processes = root.children(recursive=True) + [root]
    except psutil.NoSuchProcess:
        return
    for process in processes:
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            continue
    _, alive = psutil.wait_procs(processes, timeout=3)
    for process in alive:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            continue


class ResourceApp:
    """Desktop UI for selecting workloads, predicting, and training."""

    def __init__(self, root: tk.Tk) -> None:
        """Create the window and initialize API and UI state."""
        self.root = root
        self.root.title("AI Resource Allocation Engine")
        self.root.geometry("1000x760")
        self.root.minsize(820, 640)
        self.api = ApiClient()
        self.api_process: subprocess.Popen[bytes] | None = None
        self.pipeline_process: subprocess.Popen[str] | None = None
        self.process_lock = threading.Lock()
        self.closing = False
        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.busy = False
        self.scales = _metric_scales()
        self.app_options = self._application_options()
        self.app_names = list(self.app_options)
        self.selected_app = tk.StringVar(value=self.app_names[0] if self.app_names else "")
        self.status = tk.StringVar(value="Connecting to local API...")
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(100, self._poll_messages)
        self._start_worker(self._ensure_api, "api_ready")

    @staticmethod
    def _application_options() -> dict[str, tuple[str, Path | None]]:
        """Build selector choices from configured and installed applications."""
        options: dict[str, tuple[str, Path | None]] = {}
        try:
            for name in sorted(load_apps()):
                options[name] = (name, None)
            for name, spec in sorted(load_user_apps().items()):
                label = f"{spec.exe.stem} ({spec.exe.name})"
                if label in options:
                    label = f"{label} - {name[-8:]}"
                options[label] = (name, spec.exe)
        except (OSError, ValueError):
            pass
        for label, executable in sorted(
            _installed_applications().items(), key=lambda item: item[0].casefold()
        ):
            unique_label = label
            if unique_label in options:
                unique_label = f"{label} ({executable.name})"
            if unique_label in options:
                unique_label = f"{unique_label} - {executable.parent.name}"
            options[unique_label] = ("", executable)
        return options

    def _build_ui(self) -> None:
        """Build the selector, actions, resource charts, and compact history."""
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer, text="AI Resource Allocation Engine", font=("Segoe UI", 16, "bold")
        ).pack(anchor="w")

        controls = ttk.Frame(outer, padding=(0, 12, 0, 8))
        controls.pack(fill="x")
        ttk.Label(controls, text="Application").pack(side="left")
        self.app_picker = ttk.Combobox(
            controls,
            textvariable=self.selected_app,
            values=self.app_names,
            state="readonly" if self.app_names else "disabled",
            width=24,
        )
        self.app_picker.pack(side="left", padx=(8, 14))
        self.browse_button = ttk.Button(
            controls,
            text="Browse .exe..." if os.name == "nt" else "Browse executable...",
            command=self._browse_executable,
        )
        self.browse_button.pack(side="left", padx=3)
        self.predict_button = ttk.Button(
            controls, text="Predict", command=self._predict
        )
        self.predict_button.pack(side="left", padx=3)
        self.compare_button = ttk.Button(
            controls, text="Run & compare", command=self._compare
        )
        self.compare_button.pack(side="left", padx=3)
        self.prepare_button = ttk.Button(
            controls, text="Prepare selected app", command=self._prepare_model
        )
        self.prepare_button.pack(side="left", padx=3)
        ttk.Label(outer, textvariable=self.status).pack(anchor="w", pady=(0, 8))

        self.result_title = ttk.Label(outer, text="Resource prediction")
        self.result_title.pack(anchor="w", pady=(4, 3))
        self.chart_frame = ttk.Frame(outer)
        self.chart_frame.pack(fill="x")
        self.gauge_widgets: list[tuple[str, str, ttk.Label, tk.Canvas]] = []
        for index, (metric, title, unit) in enumerate(_METRICS):
            card = ttk.Frame(self.chart_frame, padding=7, relief="groove")
            card.grid(row=index // 2, column=index % 2, sticky="ew", padx=4, pady=4)
            self.chart_frame.columnconfigure(index % 2, weight=1)
            value_label = ttk.Label(card, text=f"{title}: —")
            value_label.pack(anchor="w")
            gauge = tk.Canvas(card, height=32, highlightthickness=0)
            gauge.pack(fill="x", pady=(2, 0))
            self.gauge_widgets.append((metric, unit, value_label, gauge))

        self.compare_frame = ttk.LabelFrame(outer, text="Predicted vs actual", padding=6)
        self.chart_grid = ttk.Frame(self.compare_frame)
        self.chart_grid.pack(fill="x")
        self.comparison_canvases: list[tuple[str, str, tk.Canvas]] = []
        for index, (metric, title, unit) in enumerate(_METRICS):
            canvas = tk.Canvas(self.chart_grid, height=170, highlightthickness=0)
            canvas.grid(row=index // 2, column=index % 2, sticky="ew", padx=3, pady=2)
            self.chart_grid.columnconfigure(index % 2, weight=1)
            self.comparison_canvases.append((title, unit, canvas))
        self.error_table = ttk.Treeview(
            self.compare_frame,
            columns=("metric", "predicted", "actual", "absolute_error", "error_pct"),
            show="headings",
            height=4,
        )
        for key, label, width in (
            ("metric", "Metric", 120),
            ("predicted", "Predicted", 120),
            ("actual", "Actual", 120),
            ("absolute_error", "Absolute error", 130),
            ("error_pct", "Error %", 100),
        ):
            self.error_table.heading(key, text=label)
            self.error_table.column(key, width=width, anchor="center")
        self.error_table.pack(fill="x", pady=(4, 0))
        self.compare_frame.pack_forget()

        self.detail_frame = ttk.Frame(outer)
        self.detail_frame.pack(fill="x", pady=(5, 0))
        self.detail_label = ttk.Label(self.detail_frame, text="")
        self.detail_label.pack(anchor="w")

        history_frame = ttk.LabelFrame(outer, text="Recent comparisons", padding=5)
        history_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.history = ttk.Treeview(
            history_frame,
            columns=("time", "app", "cpu", "ram", "disk", "network"),
            show="headings",
            height=4,
        )
        for key, label, width in (
            ("time", "Time", 150),
            ("app", "App", 160),
            ("cpu", "CPU error", 110),
            ("ram", "RAM error", 110),
            ("disk", "Disk error", 110),
            ("network", "Network error", 120),
        ):
            self.history.heading(key, text=label)
            self.history.column(key, width=width, anchor="center")
        self.history.pack(fill="both", expand=True)

        for button in (self.predict_button, self.compare_button, self.prepare_button):
            if not self.app_names:
                button.configure(state="disabled")

    def _start_worker(
        self, function: Callable[[], Any], result_kind: str
    ) -> None:
        """Run a blocking operation away from the Tk event loop."""
        if self.busy:
            return
        self.busy = True
        self._set_buttons(False)

        def work() -> None:
            try:
                self.messages.put((result_kind, function()))
            except Exception as error:
                self.messages.put(("error", str(error)))
            finally:
                self.messages.put(("worker_done", None))

        threading.Thread(target=work, daemon=True).start()

    def _set_buttons(self, enabled: bool) -> None:
        """Enable or disable action buttons."""
        state = "normal" if enabled and self.app_names else "disabled"
        for button in (self.predict_button, self.compare_button, self.prepare_button):
            button.configure(state=state)
        self.browse_button.configure(state="normal" if enabled else "disabled")

    def _browse_executable(self) -> None:
        """Add an executable selected through the platform file picker."""
        selected_path = filedialog.askopenfilename(
            title="Select an application",
            filetypes=(
                (("Applications", "*.exe"),)
                if os.name == "nt"
                else (("Applications", "*"),)
            ),
        )
        if selected_path:
            self._add_application(Path(selected_path))

    def _add_application(self, executable: Path) -> None:
        """Register an executable and select it in the application picker."""
        try:
            app_name = register_user_app(executable)
            spec = load_all_apps()[app_name]
        except (OSError, ValueError) as error:
            messagebox.showerror("Cannot select application", str(error))
            return
        label = f"{spec.exe.stem} ({spec.exe.name})"
        if label in self.app_options and self.app_options[label][0] != app_name:
            label = f"{label} - {app_name[-8:]}"
        self.app_options[label] = (app_name, spec.exe)
        self.app_names = list(self.app_options)
        self.app_picker.configure(values=self.app_names, state="readonly")
        self.selected_app.set(label)
        self._set_buttons(True)

    def _selected_identity(self) -> tuple[str, Path | None] | None:
        """Resolve the visible selection to its identifier and executable path."""
        selection = self.app_options.get(self.selected_app.get())
        if selection is None:
            return None
        app_name, executable = selection
        if executable is not None and not app_name:
            try:
                app_name = register_user_app(executable)
            except (OSError, ValueError) as error:
                messagebox.showerror("Cannot select application", str(error))
                return None
            self.app_options[self.selected_app.get()] = (app_name, executable)
        return app_name, executable

    def _ensure_api(self) -> dict[str, Any]:
        """Connect to the API or start a local server and wait until ready."""
        try:
            return self.api.health()
        except ApiUnreachable:
            if self.api.base_url != "http://127.0.0.1:8000":
                raise RuntimeError(
                    f"Could not reach the configured API at {self.api.base_url}."
                )
            log_path = resolve_path("logs", "api.log")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_file = log_path.open("ab")
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            with self.process_lock:
                if self.closing:
                    log_file.close()
                    raise RuntimeError("The desktop app is closing.")
                self.api_process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "service.app:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000",
                    ],
                    cwd=REPO_ROOT,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
            log_file.close()
            for _ in range(40):
                if self.api_process.poll() is not None:
                    raise RuntimeError(
                        f"API could not start. See {log_path} for details."
                    )
                try:
                    return self.api.health()
                except ApiUnreachable:
                    time.sleep(0.5)
            raise RuntimeError(f"API did not become ready. See {log_path} for details.")

    def _predict(self) -> None:
        """Request a prediction for the selected application."""
        selection = self._selected_identity()
        if selection:
            app_name, _ = selection
            self.status.set(f"Predicting {app_name}...")
            self._start_worker(
                lambda: self._request_prediction(app_name), "prediction"
            )

    def _compare(self) -> None:
        """Run the selected workload and request its measured comparison."""
        selection = self._selected_identity()
        if selection:
            app_name, _ = selection
            self.status.set(f"Running {app_name} and measuring usage...")
            self._start_worker(
                lambda: self._request_comparison(app_name), "comparison"
            )

    def _request_prediction(self, app_name: str) -> dict[str, Any]:
        """Request a prediction and guide users when an app has no history."""
        try:
            return self.api.predict(app_name)
        except ApiError as error:
            if error.status_code == 503 and "No prediction profile" in error.message:
                raise RuntimeError(
                    f"No history is available for {self._display_name(app_name)}. "
                    "Choose Prepare selected app first."
                ) from error
            raise

    def _request_comparison(self, app_name: str) -> dict[str, Any]:
        """Request a run comparison and explain missing app history."""
        try:
            return self.api.run_and_compare(app_name)
        except ApiError as error:
            if error.status_code == 503 and "No prediction profile" in error.message:
                raise RuntimeError(
                    f"No history is available for {self._display_name(app_name)}. "
                    "Choose Prepare selected app first."
                ) from error
            raise

    def _prepare_model(self) -> None:
        """Collect the selected workload, rebuild the dataset, and train/evaluate."""
        selection = self._selected_identity()
        if selection is None:
            return
        app_name, _ = selection
        if not messagebox.askyesno(
            "Prepare selected app",
            "This will launch the app up to 8 times with no arguments. "
            "Each run is stopped after 15 seconds. Save any work in that app "
            "before continuing.",
        ):
            return
        self.status.set(f"Preparing model for {app_name}...")
        self._start_worker(lambda: self._run_pipeline(app_name), "pipeline_done")

    def _run_pipeline(self, app_name: str) -> str:
        """Run the selected-app collection and model preparation commands."""
        commands = (
            (
                "Collecting selected app",
                ["-m", "collector.run_logger", "--runs", "8", "--only", app_name],
            ),
            ("Building dataset", ["-m", "features.build_dataset"]),
            (
                "Training model",
                ["-m", "model.train", "--data", "data/processed/dataset.csv"],
            ),
            ("Evaluating model", ["-m", "model.evaluate"]),
        )
        for phase, arguments in commands:
            self.messages.put(("status", f"{phase}..."))
            with self.process_lock:
                if self.closing:
                    raise RuntimeError("The desktop app is closing.")
                process = subprocess.Popen(
                    [sys.executable, *arguments],
                    cwd=REPO_ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self.pipeline_process = process
            stdout, stderr = process.communicate()
            with self.process_lock:
                if self.pipeline_process is process:
                    self.pipeline_process = None
            if process.returncode:
                detail = stderr.strip() or stdout.strip()
                raise RuntimeError(
                    f"{phase} failed (exit {process.returncode}): "
                    f"{detail[-1200:] or 'No error details were provided.'}"
                )
            if phase == "Building dataset":
                profile_path = resolve_path("data", "processed", "app_profiles.csv")
                with profile_path.open("r", newline="", encoding="utf-8") as profile_file:
                    profile_names = {
                        row["app_name"] for row in csv.DictReader(profile_file)
                    }
                if app_name not in profile_names:
                    raise RuntimeError(
                        "No usable run history was collected for this app. "
                        "It may close immediately, require interaction, or need "
                        "command-line arguments."
                    )
        return f"Model prepared for {app_name}."

    def _show_prediction(self, result: dict[str, Any]) -> None:
        """Update resource gauges and display the prediction source."""
        predicted = result["predicted"]
        display_name = self._display_name(result["app_name"])
        self.result_title.configure(
            text=f"Resource prediction — {display_name} ({result['source']})"
        )
        for metric, unit, label, canvas in self.gauge_widgets:
            value = float(predicted[metric])
            label.configure(text=f"{metric.replace('_', ' ').title()}: {value:.2f} {unit}")
            _draw_gauge(canvas, value, self.scales[metric])
        self.compare_frame.pack_forget()
        self.detail_label.configure(text="")

    def _show_comparison(self, result: dict[str, Any]) -> None:
        """Update comparison charts, error table, and enforcement summary."""
        predicted, actual = result["predicted"], result["actual"]
        display_name = self._display_name(result["app_name"])
        self.result_title.configure(text=f"Resource comparison — {display_name}")
        for metric, unit, label, gauge in self.gauge_widgets:
            value = float(predicted[metric])
            label.configure(text=f"Predicted {metric.replace('_', ' ')}: {value:.2f} {unit}")
            _draw_gauge(gauge, value, self.scales[metric])
        for index, (metric, title, unit) in enumerate(_METRICS):
            predicted_value = float(predicted[metric])
            actual_value = float(actual[metric])
            _draw_comparison(
                self.comparison_canvases[index][2],
                title,
                unit,
                predicted_value,
                actual_value,
            )
        for item in self.error_table.get_children():
            self.error_table.delete(item)
        for metric, title, _ in _METRICS:
            predicted_value = float(predicted[metric])
            actual_value = float(actual[metric])
            self.error_table.insert(
                "",
                "end",
                values=(
                    title,
                    f"{predicted_value:.2f}",
                    f"{actual_value:.2f}",
                    f"{abs(predicted_value - actual_value):.2f}",
                    _error_percent(predicted_value, actual_value),
                ),
            )
        self.compare_frame.pack(fill="x", before=self.detail_frame, pady=(8, 0))
        errors = " | ".join(
            f"{title}: {_error_percent(float(predicted[metric]), float(actual[metric]))}"
            for metric, title, _ in _METRICS
        )
        enforcement = result["enforcement"]
        self.detail_label.configure(
            text=(
                f"{errors}    |    Duration: {float(result['duration_s']):.1f}s"
                f"    |    Admitted: {'Yes' if enforcement['admitted'] else 'No'}"
                f"    |    Job Object caps: "
                f"{'Applied' if enforcement['cgroup_applied'] else 'Unavailable'}"
                f"    |    Priority: {enforcement.get('niceness', 'n/a')}"
            )
        )
        if enforcement.get("reason"):
            self.detail_label.configure(
                text=f"{self.detail_label.get()}    |    {enforcement['reason']}"
            )
        self.history.insert(
            "",
            0,
            values=(
                datetime.now().astimezone().strftime("%H:%M:%S"),
                display_name,
                _error_percent(float(predicted["cpu_pct"]), float(actual["cpu_pct"])),
                _error_percent(float(predicted["ram_mb"]), float(actual["ram_mb"])),
                _error_percent(float(predicted["disk_mbps"]), float(actual["disk_mbps"])),
                _error_percent(float(predicted["net_kbps"]), float(actual["net_kbps"])),
            ),
        )
        for item in self.history.get_children()[5:]:
            self.history.delete(item)

    def _display_name(self, app_name: str) -> str:
        """Return the user-facing app label for an API application identifier."""
        return next(
            (
                label
                for label, (registered_name, _) in self.app_options.items()
                if registered_name == app_name
            ),
            app_name,
        )

    def _poll_messages(self) -> None:
        """Apply background task updates on the Tk main thread."""
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "api_ready":
                if self.app_names:
                    self.status.set(
                        f"API ready - {payload.get('predictor', 'unknown')} predictor"
                    )
                else:
                    self.status.set(
                        "No configured apps are available; check the app configuration."
                    )
            elif kind == "prediction":
                self._show_prediction(payload)
                self.status.set("Prediction ready.")
            elif kind == "comparison":
                self._show_comparison(payload)
                self.status.set("Run complete.")
            elif kind == "pipeline_done":
                self.status.set(payload)
                messagebox.showinfo("Model ready", payload)
            elif kind == "status":
                self.status.set(payload)
            elif kind == "error":
                self.status.set("Action failed.")
                messagebox.showerror("Unable to complete action", payload)
            elif kind == "worker_done":
                self.busy = False
                self._set_buttons(True)
        self.root.after(100, self._poll_messages)

    def _close(self) -> None:
        """Close the window and stop only the API process started by this GUI."""
        with self.process_lock:
            self.closing = True
            processes = (self.api_process, self.pipeline_process)
        for process in processes:
            if process is not None and process.poll() is None:
                _terminate_process_tree(process.pid)
        self.api.session.close()
        self.root.destroy()


def main() -> None:
    """Launch the Tkinter application."""
    root = tk.Tk()
    ResourceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
