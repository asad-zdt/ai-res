"""Material-inspired Tkinter dashboard for the resource-allocation engine."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any, Callable

import psutil

from collector.user_apps import load_all_apps, register_user_app
from config import REPO_ROOT, resolve_path
from gui.api_client import ApiClient, ApiError, ApiUnreachable
from gui.application_catalog import application_options, executable_from_icon, installed_applications
from gui.dashboard_data import (
    METRICS,
    draw_comparison,
    draw_gauge,
    draw_history_trends,
    draw_prediction_ranges,
    error_percent,
    history_statistics,
    load_app_history,
    load_profile_statistics,
    metric_scales,
)
from gui.task_runner import TaskMessage, TaskRunner
from gui.theme import tokens
from gui.theme.manager import ThemeManager
from gui.widgets.cards import MetricCard, SurfaceCard
from gui.widgets.dialogs import MaterialDialog, Snackbar, Tooltip
from gui.widgets.icons import draw_action_icon
from gui.widgets.scrollable import ScrollableFrame


class DashboardView:
    """Own the UI, task coordination, and local API lifecycle."""

    def __init__(self, root: tk.Tk) -> None:
        """Build the dashboard, start API health checking, and bind controls."""
        self.root = root
        self.root.title("AI Resource Allocation Engine")
        self.root.geometry(f"{tokens.SIZES['window_width']}x{tokens.SIZES['window_height']}")
        self.root.minsize(tokens.SIZES["min_width"], tokens.SIZES["min_height"])
        self.theme = ThemeManager(root)
        self.api = ApiClient()
        self.runner = TaskRunner()
        self.api_process: subprocess.Popen[bytes] | None = None
        self.pipeline_process: subprocess.Popen[str] | None = None
        self.process_lock = threading.Lock()
        self.closing = False
        self.scales = metric_scales()
        self.app_options = application_options()
        self.app_names = list(self.app_options)
        self.selected_app = tk.StringVar(
            value=self.app_names[0] if self.app_names else ""
        )
        self.current_predictions: dict[str, dict[str, float]] = {}
        self.current_history: list[dict[str, float]] = []
        self.current_range: dict[str, dict[str, float]] | None = None
        self.comparisons: dict[str, dict[str, Any]] = {}
        self.comparison_count = 0
        self.current_page = "overview"
        self.status = tk.StringVar(value="Connecting to local API...")
        self.last_result = tk.StringVar(value="No completed actions this session.")
        self.api_state = tk.StringVar(value="Starting")
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.bind("<Return>", self._shortcut_predict)
        self.root.bind("<Control-r>", self._shortcut_compare)
        self.root.bind("<Control-f>", self._shortcut_find)
        self.root.after(tokens.INTERACTION["worker_poll_ms"], self._poll_messages)
        self._start_worker(self._ensure_api, "api_ready")

    @property
    def busy(self) -> bool:
        """Expose whether a worker operation is currently running."""
        return self.runner.busy

    def _build_ui(self) -> None:
        """Build the app bar, navigation, shared controls, views, and status bar."""
        self.shell = ttk.Frame(self.root, padding=tokens.SPACING["md"])
        self.shell.pack(fill="both", expand=True)
        self._build_app_bar()
        self.body = ttk.Frame(self.shell)
        self.body.pack(fill="both", expand=True, pady=(tokens.SPACING["md"], 0))
        self._build_navigation()
        self.content_area = ttk.Frame(self.body)
        self.content_area.pack(side="left", fill="both", expand=True)
        self._build_control_card()
        self._build_pages()
        self._build_status_bar()
        self._show_page("overview")
        self._refresh_visualizations()
        self._set_buttons(bool(self.app_names))

    def _build_app_bar(self) -> None:
        """Create product identity, API status chip, and persistent theme toggle."""
        bar = ttk.Frame(self.shell)
        bar.pack(fill="x")
        identity = ttk.Frame(bar)
        identity.pack(side="left", fill="x", expand=True)
        ttk.Label(identity, text="AI Resource Allocation Engine", style="Headline.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            identity,
            text="Predict, allocate, and enforce resource limits",
            style="Muted.TLabel",
        ).pack(anchor="w")
        self.api_chip = tk.Label(
            bar,
            textvariable=self.api_state,
            background=self.theme.colors["selection"],
            foreground=self.theme.colors["primary"],
            padx=tokens.SPACING["md"],
            pady=tokens.SPACING["xs"],
            font=(self.theme.font_family, tokens.TYPOGRAPHY["caption"], "bold"),
        )
        self.api_chip.pack(side="right", padx=tokens.SPACING["sm"])
        self.theme_button = ttk.Button(
            bar, command=self._toggle_theme, style="Secondary.TButton"
        )
        self.theme_button.pack(side="right")
        self._update_theme_button()

    def _build_navigation(self) -> None:
        """Create the left-side page rail."""
        self.nav = ttk.Frame(self.body, width=tokens.SIZES["navigation_width"])
        self.nav.pack(side="left", fill="y", padx=(0, tokens.SPACING["md"]))
        self.nav.pack_propagate(False)
        ttk.Label(self.nav, text="WORKSPACE", style="Caption.TLabel").pack(
            anchor="w", pady=(tokens.SPACING["sm"], tokens.SPACING["md"])
        )
        self.nav_buttons: dict[str, ttk.Button] = {}
        for key, title in tokens.PAGE_NAMES:
            button = ttk.Button(
                self.nav,
                text=f"  {title}",
                style="Secondary.TButton",
                command=lambda page=key: self._show_page(page),
            )
            button.pack(fill="x", pady=(0, tokens.SPACING["xs"]))
            self.nav_buttons[key] = button

    def _build_control_card(self) -> None:
        """Create searchable app selection and primary actions."""
        self.control_card = SurfaceCard(self.content_area, self.theme)
        self.control_card.pack(fill="x")
        controls = self.control_card.content
        ttk.Label(controls, text="Application", style="Surface.Title.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, tokens.SPACING["sm"])
        )
        self.app_picker = ttk.Combobox(
            controls,
            textvariable=self.selected_app,
            values=self.app_names,
            state="normal" if self.app_names else "disabled",
            width=tokens.SIZES["picker_width"],
        )
        self.app_picker.grid(
            row=0, column=1, columnspan=5, sticky="ew",
            padx=(0, tokens.SPACING["sm"]),
        )
        self.app_picker.bind("<<ComboboxSelected>>", self._on_app_selected)
        self.app_picker.bind("<KeyRelease>", self._filter_applications)
        self.app_picker.bind("<Return>", self._select_typed_application)
        self.browse_button = ttk.Button(
            controls, text="Browse .exe…", style="Secondary.TButton",
            command=self._browse_executable,
        )
        self.browse_button.grid(
            row=1, column=0, sticky="ew", padx=(0, tokens.SPACING["xs"]),
            pady=(tokens.SPACING["sm"], 0),
        )
        self.predict_group, self.predict_icon, self.predict_button = self._action_control(
            controls, "predict", "Predict", self._predict, "Secondary.TButton"
        )
        self.predict_group.grid(
            row=1, column=1, sticky="ew", padx=tokens.SPACING["xs"],
            pady=(tokens.SPACING["sm"], 0),
        )
        self.compare_group, self.compare_icon, self.compare_button = self._action_control(
            controls, "run", "Run & compare", self._compare, "Primary.TButton"
        )
        self.compare_group.grid(
            row=1, column=2, sticky="ew", padx=tokens.SPACING["xs"],
            pady=(tokens.SPACING["sm"], 0),
        )
        self.prepare_group, self.prepare_icon, self.prepare_button = self._action_control(
            controls, "train", "Prepare app", self._prepare_model, "Secondary.TButton"
        )
        self.prepare_group.grid(
            row=1, column=3, sticky="ew", padx=tokens.SPACING["xs"],
            pady=(tokens.SPACING["sm"], 0),
        )
        controls.columnconfigure(1, weight=1)
        for column in range(2, 6):
            controls.columnconfigure(column, weight=1)
        self.control_card.pack_configure(pady=(tokens.SPACING["md"], tokens.SPACING["md"]))
        Tooltip(
            self.prepare_button,
            "Collects up to eight runs. The app launches without arguments and each attempt lasts up to 15 seconds.",
            self.theme,
        )
        Tooltip(
            self.app_picker,
            "Custom apps need collected history before a model prediction is meaningful. Some apps forward to an existing instance or need a document to do work.",
            self.theme,
        )

    def _action_control(
        self,
        parent: tk.Misc,
        icon_name: str,
        text: str,
        command: Callable[[], None],
        style: str,
    ) -> tuple[ttk.Frame, tk.Canvas, ttk.Button]:
        """Build a button group with its matching vector icon."""
        group = ttk.Frame(parent, style="Surface.TFrame")
        icon = tk.Canvas(
            group, width=tokens.SIZES["icon"], height=tokens.SIZES["icon"],
            highlightthickness=0, background=self.theme.colors["surface"],
        )
        icon.pack(side="left", padx=(0, tokens.SPACING["xs"]))
        draw_action_icon(icon, icon_name, self.theme.colors["text_secondary"])
        button = ttk.Button(group, text=text, style=style, command=command)
        button.pack(side="left", fill="x", expand=True)
        return group, icon, button

    def _build_pages(self) -> None:
        """Create the five scrollable workspace pages."""
        self.pages: dict[str, ScrollableFrame] = {}
        for page, _title in tokens.PAGE_NAMES:
            view = ScrollableFrame(self.content_area, self.theme)
            self.pages[page] = view
        self._build_overview(self.pages["overview"].content)
        self._build_history_page(self.pages["history"].content)
        self._build_range_page(self.pages["range"].content)
        self._build_comparison_page(self.pages["comparison"].content)
        self._build_settings_page(self.pages["settings"].content)

    def _build_overview(self, parent: ttk.Frame) -> None:
        """Build summary cards and current prediction output."""
        ttk.Label(parent, text="Overview", style="Title.TLabel").pack(
            anchor="w", pady=(0, tokens.SPACING["md"])
        )
        self.prediction_heading = tk.StringVar(value="Predicted resource demand")
        heading = ttk.Frame(parent)
        heading.pack(fill="x", pady=(0, tokens.SPACING["sm"]))
        ttk.Label(heading, textvariable=self.prediction_heading, style="Title.TLabel").pack(
            side="left"
        )
        self.prediction_source = ttk.Label(heading, text="No prediction yet", style="Muted.TLabel")
        self.prediction_source.pack(side="right")
        self.metric_cards: dict[str, MetricCard] = {}
        grid = ttk.Frame(parent)
        grid.pack(fill="x")
        for index, (metric, title, unit, _icon) in enumerate(METRICS):
            card = MetricCard(
                grid, self.theme, metric, title, unit, self.scales[metric]
            )
            card.grid(
                row=index // 2, column=index % 2, sticky="ew",
                padx=(0, tokens.SPACING["sm"] if index % 2 == 0 else 0),
                pady=(0, tokens.SPACING["sm"]),
            )
            self.metric_cards[metric] = card
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self.overview_hint = tk.StringVar(
            value="Select an app to see its recorded history and profile range."
        )
        hint_card = SurfaceCard(parent, self.theme)
        hint_card.pack(fill="x", pady=(tokens.SPACING["sm"], tokens.SPACING["md"]))
        ttk.Label(
            hint_card.content, textvariable=self.overview_hint,
            wraplength=tokens.TEXT_LAYOUT["page_wrap"],
            style="Surface.Muted.TLabel",
        ).pack(anchor="w")
        self.overview_hint_card = hint_card

    def _build_history_page(self, parent: ttk.Frame) -> None:
        """Create the four actual-data historical trends."""
        ttk.Label(parent, text="Run History", style="Title.TLabel").pack(
            anchor="w", pady=(0, tokens.SPACING["xs"])
        )
        self.trend_hint = ttk.Label(parent, text="", style="Muted.TLabel")
        self.trend_hint.pack(anchor="w", pady=(0, tokens.SPACING["sm"]))
        self.trend_canvas = tk.Canvas(
            parent, height=tokens.SIZES["chart_height"],
            highlightthickness=0, background=self.theme.colors["surface"],
        )
        self.trend_canvas.pack(fill="x", expand=True)
        self.trend_canvas.bind("<Configure>", self._redraw_history)

    def _build_range_page(self, parent: ttk.Frame) -> None:
        """Create the historical profile range and prediction marker view."""
        ttk.Label(parent, text="Prediction Range", style="Title.TLabel").pack(
            anchor="w", pady=(0, tokens.SPACING["xs"])
        )
        self.range_hint = ttk.Label(parent, text="", style="Muted.TLabel")
        self.range_hint.pack(anchor="w", pady=(0, tokens.SPACING["sm"]))
        self.range_canvas = tk.Canvas(
            parent, height=tokens.SIZES["chart_height"],
            highlightthickness=0, background=self.theme.colors["surface"],
        )
        self.range_canvas.pack(fill="x", expand=True)
        self.range_canvas.bind("<Configure>", self._redraw_range)
        range_tip = ttk.Label(
            parent,
            text="The band and average come only from collected profile data; the red marker is the current model prediction.",
            style="Caption.TLabel",
        )
        range_tip.pack(anchor="w", pady=tokens.SPACING["sm"])

    def _build_comparison_page(self, parent: ttk.Frame) -> None:
        """Create paired charts, error table, enforcement detail, and reload list."""
        ttk.Label(parent, text="Predicted vs actual", style="Title.TLabel").pack(
            anchor="w", pady=(0, tokens.SPACING["sm"])
        )
        self.comparison_heading = ttk.Label(
            parent, text="Run & compare to populate this view.", style="Muted.TLabel"
        )
        self.comparison_heading.pack(anchor="w", pady=(0, tokens.SPACING["sm"]))
        chart_grid = ttk.Frame(parent)
        chart_grid.pack(fill="x")
        self.comparison_canvases: dict[str, tk.Canvas] = {}
        for index, (metric, title, _unit, _icon) in enumerate(METRICS):
            chart = tk.Canvas(
                chart_grid, height=tokens.SIZES["small_chart_height"],
                highlightthickness=0, background=self.theme.colors["surface"],
            )
            chart.grid(
                row=index // 2, column=index % 2, sticky="ew",
                padx=(0, tokens.SPACING["sm"] if index % 2 == 0 else 0),
                pady=(0, tokens.SPACING["sm"]),
            )
            chart_grid.columnconfigure(index % 2, weight=1)
            self.comparison_canvases[metric] = chart
        for canvas in self.comparison_canvases.values():
            canvas.bind("<Configure>", lambda _event: self._redraw_comparison())
        table_card = SurfaceCard(parent, self.theme)
        table_card.pack(fill="x", pady=(0, tokens.SPACING["md"]))
        ttk.Label(
            table_card.content, text="Error summary", style="Surface.Title.TLabel"
        ).pack(
            anchor="w", pady=(0, tokens.SPACING["sm"])
        )
        self.error_table = ttk.Treeview(
            table_card.content,
            columns=("metric", "predicted", "actual", "absolute_error", "error_pct"),
            show="headings",
            height=tokens.TABLE["error_rows"],
        )
        for key, label, width in (
            ("metric", "Metric", tokens.TABLE["metric_width"]),
            ("predicted", "Predicted", tokens.TABLE["value_width"]),
            ("actual", "Actual", tokens.TABLE["value_width"]),
            ("absolute_error", "Absolute difference", tokens.TABLE["absolute_width"]),
            ("error_pct", "Error %", tokens.TABLE["error_width"]),
        ):
            self.error_table.heading(key, text=label)
            self.error_table.column(key, width=width, anchor="center")
        self.error_table.tag_configure("high_error", foreground=self.theme.colors["error"])
        self.error_table.tag_configure("medium_error", foreground=self.theme.colors["warning"])
        self.error_table.tag_configure("stripe", background=self.theme.colors["stripe"])
        self.error_table.pack(fill="x")
        self.enforcement_card = SurfaceCard(parent, self.theme)
        self.enforcement_card.pack(fill="x", pady=(0, tokens.SPACING["md"]))
        ttk.Label(
            self.enforcement_card.content, text="Enforcement status",
            style="Surface.Title.TLabel",
        ).pack(anchor="w")
        self.enforcement_label = ttk.Label(
            self.enforcement_card.content,
            text="No comparison result has been returned.",
            wraplength=tokens.TEXT_LAYOUT["page_wrap"],
            style="Surface.Muted.TLabel",
        )
        self.enforcement_label.pack(anchor="w", pady=(tokens.SPACING["sm"], 0))
        recent_card = SurfaceCard(parent, self.theme)
        recent_card.pack(fill="x", pady=(0, tokens.SPACING["md"]))
        ttk.Label(
            recent_card.content, text="Recent comparisons",
            style="Surface.Title.TLabel",
        ).pack(
            anchor="w", pady=(0, tokens.SPACING["sm"])
        )
        self.history = ttk.Treeview(
            recent_card.content,
            columns=("time", "app", "cpu", "ram", "disk", "network"),
            show="headings",
            height=tokens.TABLE["recent_rows"],
        )
        self.history.tag_configure("stripe", background=self.theme.colors["stripe"])
        for key, label, width in (
            ("time", "Time", tokens.TABLE["history_time_width"]),
            ("app", "Application", tokens.TABLE["history_app_width"]),
            ("cpu", "CPU error", tokens.TABLE["history_error_width"]),
            ("ram", "Memory error", tokens.TABLE["history_error_width"]),
            ("disk", "Disk error", tokens.TABLE["history_error_width"]),
            ("network", "Network error", tokens.TABLE["history_error_width"]),
        ):
            self.history.heading(key, text=label)
            self.history.column(key, width=width, anchor="center")
        self.history.pack(fill="x")
        self.history.bind("<<TreeviewSelect>>", self._reload_comparison)

    def _build_settings_page(self, parent: ttk.Frame) -> None:
        """Show theme, API, and truthful project/runtime guidance."""
        ttk.Label(parent, text="Settings / About", style="Title.TLabel").pack(
            anchor="w", pady=(0, tokens.SPACING["md"])
        )
        appearance = SurfaceCard(parent, self.theme)
        appearance.pack(fill="x", pady=(0, tokens.SPACING["md"]))
        ttk.Label(
            appearance.content, text="Appearance", style="Surface.Title.TLabel"
        ).pack(
            anchor="w"
        )
        ttk.Label(
            appearance.content,
            text="The selected light or dark appearance is saved on this machine.",
            style="Surface.Muted.TLabel",
        ).pack(anchor="w", pady=(tokens.SPACING["sm"], 0))
        api_card = SurfaceCard(parent, self.theme)
        api_card.pack(fill="x", pady=(0, tokens.SPACING["md"]))
        ttk.Label(
            api_card.content, text="Local API", style="Surface.Title.TLabel"
        ).pack(
            anchor="w"
        )
        ttk.Label(
            api_card.content, text=f"Endpoint: {self.api.base_url}",
            style="Surface.Muted.TLabel",
        ).pack(anchor="w", pady=(tokens.SPACING["sm"], 0))
        info_card = SurfaceCard(parent, self.theme)
        info_card.pack(fill="x", pady=(0, tokens.SPACING["md"]))
        ttk.Label(
            info_card.content, text="About the engine",
            style="Surface.Title.TLabel",
        ).pack(
            anchor="w"
        )
        ttk.Label(
            info_card.content,
            text=(
                "Predictions use collected application history. The local API performs "
                "admission checks and launches comparisons; Windows Job Object and "
                "priority enforcement are reported by the API response when available. "
                "Some desktop applications need arguments or user interaction and may "
                "not produce a valid collection run when launched without arguments."
            ),
            wraplength=tokens.TEXT_LAYOUT["page_wrap"], justify="left",
            style="Surface.Muted.TLabel",
        ).pack(anchor="w", pady=(tokens.SPACING["sm"], 0))

    def _build_status_bar(self) -> None:
        """Create phase text, progress indication, and the last-action summary."""
        footer = ttk.Frame(self.shell)
        footer.pack(fill="x", pady=(tokens.SPACING["md"], 0))
        ttk.Label(footer, textvariable=self.status, style="Caption.TLabel").pack(
            side="left", fill="x", expand=True
        )
        self.progress = ttk.Progressbar(
            footer, mode="indeterminate",
            length=tokens.SIZES["progress_width"],
            maximum=tokens.SIZES["progress_max"],
        )
        self.progress.pack(side="right", padx=(tokens.SPACING["md"], 0))
        ttk.Label(
            self.shell, textvariable=self.last_result, style="Caption.TLabel"
        ).pack(anchor="w", pady=(tokens.SPACING["xs"], 0))
        self.snackbar = Snackbar(self.root, self.theme)

    def _show_page(self, page: str) -> None:
        """Raise one workspace page and update navigation emphasis."""
        self.current_page = page
        for view in self.pages.values():
            view.pack_forget()
        self.pages[page].pack(fill="both", expand=True)
        for key, button in self.nav_buttons.items():
            button.configure(
                style="Primary.TButton" if key == page else "Secondary.TButton"
            )
        if page == "history":
            self._redraw_history()
        elif page == "range":
            self._redraw_range()
        elif page == "comparison":
            self._redraw_comparison()

    def _start_worker(
        self, function: Callable[[Callable[[str], None]], Any], result_kind: str
    ) -> None:
        """Start one background task and update button/progress states."""
        if not self.runner.start(function, result_kind):
            return
        self._set_buttons(False)
        self.progress.start(tokens.SPACING["xs"] * 3)

    def _set_buttons(self, enabled: bool) -> None:
        """Disable conflicting actions and app selection while work is running."""
        available = enabled and bool(self.app_names)
        for button in (self.predict_button, self.compare_button, self.prepare_button):
            button.configure(state="normal" if available else "disabled")
        self.browse_button.configure(state="normal" if enabled else "disabled")
        self.app_picker.configure(
            state=("normal" if self.app_names else "disabled")
            if enabled else "disabled"
        )

    def _filter_applications(self, _event: tk.Event[tk.Misc]) -> None:
        """Filter the grouped choices as the user types in the app field."""
        query = self.selected_app.get().strip().casefold()
        values = [
            label for label in self.app_options
            if query in label.casefold()
        ] if query else self.app_names
        self.app_picker.configure(values=values)

    def _select_typed_application(self, _event: tk.Event[tk.Misc]) -> str | None:
        """Select an exact filtered label when Enter is pressed in the picker."""
        typed = self.selected_app.get().strip()
        exact = next(
            (label for label in self.app_options if label.casefold() == typed.casefold()),
            None,
        )
        if exact is not None:
            self.selected_app.set(exact)
            self._on_app_selected(None)
            return "break"
        return None

    def _browse_executable(self) -> None:
        """Register and select an executable chosen through the Windows picker."""
        selected_path = filedialog.askopenfilename(
            parent=self.root,
            title="Select an application",
            filetypes=(("Applications", "*.exe"),),
        )
        if selected_path:
            self._add_application(Path(selected_path))

    def _add_application(self, executable: Path) -> None:
        """Register an executable and add it to the custom-app selector group."""
        try:
            app_name = register_user_app(executable)
            spec = load_all_apps()[app_name]
        except (OSError, ValueError) as error:
            MaterialDialog.error(
                self.root, self.theme, "Cannot select application",
                "The selected executable could not be registered.", str(error),
            )
            return
        label = f"[Custom] {spec.exe.stem} ({spec.exe.name})"
        if label in self.app_options and self.app_options[label][0] != app_name:
            label = f"{label} - {app_name[-8:]}"
        self.app_options[label] = (app_name, spec.exe, "Custom")
        self.app_names = list(self.app_options)
        self.app_picker.configure(values=self.app_names, state="normal")
        self.selected_app.set(label)
        self._set_buttons(True)
        self._refresh_visualizations()

    def _selected_identity(self) -> tuple[str, Path | None] | None:
        """Resolve the visible selection and lazily register installed apps."""
        selection = self.app_options.get(self.selected_app.get())
        if selection is None:
            return None
        app_name, executable, _category = selection
        if executable is not None and not app_name:
            try:
                app_name = register_user_app(executable)
            except (OSError, ValueError) as error:
                MaterialDialog.error(
                    self.root, self.theme, "Cannot select application",
                    "The installed executable could not be registered.", str(error),
                )
                return None
            self.app_options[self.selected_app.get()] = (app_name, executable, "Installed")
        return app_name, executable

    def _on_app_selected(self, _event: tk.Event[tk.Misc] | None) -> None:
        """Refresh recorded profile and chart views after app selection."""
        self._refresh_visualizations()

    def _refresh_visualizations(self) -> None:
        """Load valid app history and profile statistics from project data."""
        selection = self._selected_identity()
        if selection is None:
            self.current_history = []
            self.current_range = None
            self.trend_hint.configure(text="Select an application to view its history.")
            self.range_hint.configure(text="Select an application to view its profile.")
            self.overview_hint.set("Select an application to view its recorded history and profile range.")
            self._redraw_history()
            self._redraw_range()
            return
        app_name, _executable = selection
        self.current_history = load_app_history(app_name)
        self.current_range = load_profile_statistics(app_name) or history_statistics(
            self.current_history
        )
        predictions = self.current_predictions.get(app_name)
        if predictions is None:
            self.prediction_heading.set("Predicted resource demand")
            self.prediction_source.configure(text="No prediction yet")
            for metric, _title, _unit, _icon in METRICS:
                self.metric_cards[metric].update_value(None)
        else:
            self.prediction_heading.set(
                f"Previously predicted resource demand — {self._display_name(app_name)}"
            )
            self.prediction_source.configure(text="Saved session prediction")
            for metric, _title, _unit, _icon in METRICS:
                self.metric_cards[metric].update_value(predictions[metric])
        if self.current_history:
            self.trend_hint.configure(
                text=f"Latest {len(self.current_history)} valid collected runs"
            )
            self.overview_hint.set(
                f"{self._display_name(app_name)} has {len(self.current_history)} valid runs. "
                "Use Prediction Range to compare the model output with its actual historical profile."
            )
        else:
            self.trend_hint.configure(text="No valid run history recorded yet.")
            self.overview_hint.set(
                f"No valid history is recorded for {self._display_name(app_name)}. "
                "Prepare this app to collect runs before a prediction is meaningful."
            )
        self.range_hint.configure(
            text=(
                "Historical minimum, average, and maximum from the collected profile."
                if self.current_range else "No profile range available yet."
            )
        )
        self._update_metric_statuses()
        self._redraw_history()
        self._redraw_range()

    def _update_metric_statuses(self) -> None:
        """Mark metrics against the app's recorded upper typical value."""
        for metric, _title, _unit, _icon in METRICS:
            value_text = self.metric_cards[metric].value.cget("text")
            try:
                value = float(str(value_text).split()[0].replace(",", ""))
            except (ValueError, IndexError):
                continue
            maximum = self.current_range.get(metric, {}).get("max") if self.current_range else None
            label = (
                "No data" if maximum is None
                else "Above typical" if value > maximum
                else "Within typical range"
            )
            self.metric_cards[metric].update_status(label)

    def _redraw_history(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        """Redraw run trends using the active palette."""
        if hasattr(self, "trend_canvas"):
            draw_history_trends(
                self.trend_canvas, self.current_history,
                self.theme.colors, self.theme.font_family,
            )

    def _redraw_range(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        """Redraw profile ranges and selected prediction markers."""
        if not hasattr(self, "range_canvas"):
            return
        app_name = self.app_options.get(self.selected_app.get(), ("", None, ""))[0]
        draw_prediction_ranges(
            self.range_canvas,
            self.current_range,
            self.current_predictions.get(app_name),
            self.theme.colors,
            self.theme.font_family,
        )

    def _redraw_comparison(self) -> None:
        """Redraw paired charts when the selected comparison or canvas size changes."""
        if not hasattr(self, "active_comparison") or self.active_comparison is None:
            for canvas in getattr(self, "comparison_canvases", {}).values():
                if canvas.winfo_exists():
                    canvas.delete("all")
                    canvas.create_text(
                        max(
                            canvas.winfo_width(),
                            tokens.CHART["empty_comparison_width"],
                        ) / 2,
                        max(
                            canvas.winfo_height(),
                            tokens.CHART["empty_comparison_height"],
                        ) / 2,
                        text="Run & compare to see actual results.",
                        fill=self.theme.colors["text_secondary"],
                    )
            return
        result = self.active_comparison
        for metric, title, unit, _icon in METRICS:
            draw_comparison(
                self.comparison_canvases[metric],
                title,
                unit,
                float(result["predicted"][metric]),
                float(result["actual"][metric]),
                self.theme.colors,
                self.theme.font_family,
            )

    def _ensure_api(self, phase: Callable[[str], None]) -> dict[str, Any]:
        """Connect to the API or launch and wait for the local service."""
        phase(tokens.TASK_PHASES["health"])
        try:
            return self.api.health()
        except ApiUnreachable:
            if self.api.base_url != "http://127.0.0.1:8000":
                raise RuntimeError(
                    f"Could not reach the configured API at {self.api.base_url}."
                )
            log_path = resolve_path("logs", "api.log")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("ab") as log_file:
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                with self.process_lock:
                    if self.closing:
                        raise RuntimeError("The desktop app is closing.")
                    self.api_process = subprocess.Popen(
                        [
                            sys.executable, "-m", "uvicorn", "service.app:app",
                            "--host", "127.0.0.1", "--port", "8000",
                        ],
                        cwd=REPO_ROOT,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        creationflags=creationflags,
                    )
            for _ in range(tokens.INTERACTION["api_attempts"]):
                if self.api_process.poll() is not None:
                    raise RuntimeError(f"API could not start. See {log_path} for details.")
                try:
                    return self.api.health()
                except ApiUnreachable:
                    time.sleep(tokens.INTERACTION["api_retry_ms"] / 1000)
            raise RuntimeError(f"API did not become ready. See {log_path} for details.")

    def _predict(self) -> None:
        """Request and display a prediction for the selected application."""
        selection = self._selected_identity()
        if selection is None:
            return
        app_name, _executable = selection
        self._start_worker(
            lambda phase: self._request_prediction(app_name, phase), "prediction"
        )

    def _compare(self) -> None:
        """Submit the complete run-and-compare operation to the local API."""
        selection = self._selected_identity()
        if selection is None:
            return
        app_name, _executable = selection
        self._start_worker(
            lambda phase: self._request_comparison(app_name, phase), "comparison"
        )

    def _request_prediction(
        self, app_name: str, phase: Callable[[str], None]
    ) -> dict[str, Any]:
        """Request prediction and guide users if the selected app lacks a profile."""
        phase(tokens.TASK_PHASES["predict"])
        try:
            return self.api.predict(app_name)
        except ApiError as error:
            if error.status_code == 503 and "No prediction profile" in error.message:
                raise RuntimeError(
                    f"No history is available for {self._display_name(app_name)}. "
                    "Choose Prepare app first."
                ) from error
            raise

    def _request_comparison(
        self, app_name: str, phase: Callable[[str], None]
    ) -> dict[str, Any]:
        """Request measurement and explain missing app history."""
        phase(tokens.TASK_PHASES["compare"])
        try:
            return self.api.run_and_compare(app_name)
        except ApiError as error:
            if error.status_code == 503 and "No prediction profile" in error.message:
                raise RuntimeError(
                    f"No history is available for {self._display_name(app_name)}. "
                    "Choose Prepare app first."
                ) from error
            raise

    def _prepare_model(self) -> None:
        """Confirm and run collection, dataset rebuild, training, and evaluation."""
        selection = self._selected_identity()
        if selection is None:
            return
        app_name, _executable = selection
        confirmed = MaterialDialog.confirm(
            self.root,
            self.theme,
            "Prepare selected app",
            "Save your work first. This will launch the app with no arguments up to "
            "8 times, observing each attempt for up to 15 seconds. Some applications "
            "forward to an existing window, close immediately, or need interaction "
            "and may not yield a valid history run.",
        )
        if confirmed:
            self._start_worker(
                lambda phase: self._run_pipeline(app_name, phase), "pipeline_done"
            )

    def _run_pipeline(
        self, app_name: str, phase_callback: Callable[[str], None]
    ) -> str:
        """Collect app samples, rebuild training data, train, and evaluate."""
        commands = (
            (
                "collect", "Collecting selected app history",
                [
                    "-m", "collector.run_logger", "--runs",
                    str(tokens.TASK_SETTINGS["prepare_runs"]), "--only", app_name,
                ],
            ),
            ("dataset", "Building training data", ["-m", "features.build_dataset"]),
            (
                "train", "Training model",
                ["-m", "model.train", "--data", "data/processed/dataset.csv"],
            ),
            ("evaluate", "Evaluating model", ["-m", "model.evaluate"]),
        )
        for phase_key, phase, arguments in commands:
            phase_callback(tokens.TASK_PHASES[phase_key])
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
                    f"{detail[-tokens.TASK_SETTINGS['api_log_detail_limit']:] or 'No error details were provided.'}"
                )
            if phase_key == "dataset":
                profiles = resolve_path("data", "processed", "app_profiles.csv")
                with profiles.open("r", newline="", encoding="utf-8") as profile_file:
                    profile_names = {
                        row["app_name"] for row in csv.DictReader(profile_file)
                    }
                if app_name not in profile_names:
                    raise RuntimeError(
                        "No usable run history was collected for this app. It may "
                        "close immediately, require interaction, or need arguments."
                    )
        return f"Model prepared for {app_name}."

    def _show_prediction(self, result: dict[str, Any]) -> None:
        """Update overview gauges with the server-returned prediction."""
        app_name = result["app_name"]
        predicted = result["predicted"]
        display_name = self._display_name(app_name)
        self.prediction_heading.set(f"Predicted resource demand — {display_name}")
        self.prediction_source.configure(text=f"Source: {result['source']}")
        self.current_predictions[app_name] = {
            metric: float(predicted[metric]) for metric, _, _, _ in METRICS
        }
        for metric, _title, _unit, _icon in METRICS:
            self.metric_cards[metric].update_value(float(predicted[metric]))
        self._update_metric_statuses()
        self._redraw_range()
        self._show_page("overview")
        self.last_result.set(f"Prediction ready for {display_name}.")
        self.snackbar.show(f"Prediction ready for {display_name}")

    def _show_comparison(self, result: dict[str, Any]) -> None:
        """Update gauges, real-data charts, table, enforcement, and session history."""
        predicted, actual = result["predicted"], result["actual"]
        app_name = result["app_name"]
        display_name = self._display_name(app_name)
        self.prediction_heading.set(f"Resource comparison — {display_name}")
        self.prediction_source.configure(text="Predicted values")
        self.current_predictions[app_name] = {
            metric: float(predicted[metric]) for metric, _, _, _ in METRICS
        }
        for metric, _title, _unit, _icon in METRICS:
            self.metric_cards[metric].update_value(float(predicted[metric]))
        self._update_metric_statuses()
        self.active_comparison = result
        self.comparison_heading.configure(text=f"Comparison for {display_name}")
        self._redraw_comparison()
        for item in self.error_table.get_children():
            self.error_table.delete(item)
        for metric, title, _unit, _icon in METRICS:
            predicted_value = float(predicted[metric])
            actual_value = float(actual[metric])
            percentage = error_percent(predicted_value, actual_value)
            try:
                magnitude = abs(float(percentage.rstrip("%")))
            except ValueError:
                magnitude = 0.0
            tag = (
                "high_error"
                if magnitude >= tokens.TASK_SETTINGS["error_high_percent"]
                else "medium_error"
                if magnitude >= tokens.TASK_SETTINGS["error_medium_percent"]
                else ""
            )
            row_tags = [tag] if tag else []
            if len(self.error_table.get_children()) % 2:
                row_tags.insert(0, "stripe")
            self.error_table.insert(
                "",
                "end",
                values=(
                    title,
                    f"{predicted_value:.2f}",
                    f"{actual_value:.2f}",
                    f"{abs(predicted_value - actual_value):.2f}",
                    percentage,
                ),
                tags=tuple(row_tags),
            )
        enforcement = result["enforcement"]
        enforcement_text = (
            f"Duration: {float(result['duration_s']):.1f}s  |  "
            f"Admitted: {'Yes' if enforcement['admitted'] else 'No'}  |  "
            f"Job Object caps: {'Active' if enforcement['cgroup_applied'] else 'Unavailable'}  |  "
            f"Priority: {enforcement.get('niceness', 'n/a')}"
        )
        if enforcement.get("reason"):
            enforcement_text += f"  |  {enforcement['reason']}"
        self.enforcement_label.configure(text=enforcement_text)
        self.comparison_count += 1
        comparison_id = f"comparison-{self.comparison_count}"
        self.comparisons[comparison_id] = result
        errors = [
            error_percent(float(predicted[key]), float(actual[key]))
            for key, _title, _unit, _icon in METRICS
        ]
        self.history.insert(
            "",
            0,
            iid=comparison_id,
            values=(
                datetime.now().astimezone().strftime("%H:%M:%S"),
                display_name,
                *errors,
            ),
            tags=("stripe",) if self.comparison_count % 2 == 0 else (),
        )
        for item in self.history.get_children()[tokens.TABLE["recent_limit"]:]:
            self.history.delete(item)
            self.comparisons.pop(item, None)
        self.active_comparison = result
        self._show_page("comparison")
        enforcement_summary = (
            "Job Object active" if enforcement["cgroup_applied"]
            else "Job Object unavailable"
        )
        self.last_result.set(f"Comparison complete — enforcement: {enforcement_summary}.")
        self.snackbar.show("Run comparison complete")

    def _reload_comparison(self, _event: tk.Event[tk.Misc]) -> None:
        """Reload a session-only comparison when a row is selected."""
        selected = self.history.selection()
        if not selected:
            return
        result = self.comparisons.get(selected[0])
        if result is not None:
            self.active_comparison = result
            self._redraw_comparison()

    def _display_name(self, app_name: str) -> str:
        """Return the visible label corresponding to an API app identifier."""
        return next(
            (
                label for label, (registered_name, _path, _category)
                in self.app_options.items()
                if registered_name == app_name
            ),
            app_name,
        )

    def _poll_messages(self) -> None:
        """Apply queued task results and progress only on the Tk main thread."""
        while True:
            try:
                message = self.runner.messages.get_nowait()
            except queue.Empty:
                break
            if message.kind == "phase":
                self.status.set(str(message.payload))
            elif message.kind == "api_ready":
                self.api_state.set("Connected")
                self._style_api_chip("connected")
                predictor = message.payload.get("predictor", "unknown")
                if self.app_names:
                    self.status.set(f"API connected — {predictor} predictor.")
                else:
                    self.status.set(
                        "API connected; no apps were discovered. Browse to select an .exe."
                    )
            elif message.kind == "prediction":
                self._show_prediction(message.payload)
                self.status.set("Prediction complete.")
            elif message.kind == "comparison":
                self._show_comparison(message.payload)
                self.status.set("Comparison complete.")
            elif message.kind == "pipeline_done":
                self._refresh_visualizations()
                self.last_result.set(str(message.payload))
                self.status.set("Model preparation complete.")
                self.snackbar.show(str(message.payload))
            elif message.kind == "error":
                error = message.payload
                details = str(error)
                summary = details.splitlines()[0] if details else "The action could not be completed."
                self.status.set("Action failed.")
                if "api" in details.casefold() or "connect" in details.casefold():
                    self.api_state.set("Offline")
                    self._style_api_chip("offline")
                MaterialDialog.error(
                    self.root, self.theme, "Unable to complete action",
                    summary, details,
                )
            elif message.kind == "worker_done":
                self.runner.mark_done()
                self.progress.stop()
                self._set_buttons(True)
        self.root.after(tokens.SPACING["md"], self._poll_messages)

    def _style_api_chip(self, state: str) -> None:
        """Apply a semantic API chip color from the active palette."""
        c = self.theme.colors
        foreground = c["success"] if state == "connected" else c["error"] if state == "offline" else c["warning"]
        self.api_chip.configure(background=c["selection"], foreground=foreground)

    def _toggle_theme(self) -> None:
        """Switch and persist the appearance, then refresh all Canvas surfaces."""
        self.theme.toggle()
        self._update_theme_button()
        self.api_chip.configure(
            background=self.theme.colors["selection"],
            foreground=self.theme.colors["primary"],
        )
        for card in self.metric_cards.values():
            card.refresh_theme()
        for icon in (self.predict_icon, self.compare_icon, self.prepare_icon):
            icon.configure(background=self.theme.colors["surface"])
            name = {
                self.predict_icon: "predict",
                self.compare_icon: "run",
                self.prepare_icon: "train",
            }[icon]
            draw_action_icon(icon, name, self.theme.colors["text_secondary"])
        self.error_table.tag_configure("high_error", foreground=self.theme.colors["error"])
        self.error_table.tag_configure("medium_error", foreground=self.theme.colors["warning"])
        self.error_table.tag_configure("stripe", background=self.theme.colors["stripe"])
        self.history.tag_configure("stripe", background=self.theme.colors["stripe"])
        self._refresh_theme_widgets(self.root)
        self._redraw_history()
        self._redraw_range()
        self._redraw_comparison()

    def _refresh_theme_widgets(self, parent: tk.Misc) -> None:
        """Update explicitly colored widgets and reusable cards after theme change."""
        for widget in parent.winfo_children():
            if isinstance(widget, SurfaceCard):
                widget.refresh_theme()
            if isinstance(widget, MetricCard):
                widget.refresh_theme()
            if isinstance(widget, tk.Canvas):
                try:
                    widget.configure(background=self.theme.colors["surface"])
                except tk.TclError:
                    pass
            if isinstance(widget, ScrollableFrame):
                widget.refresh_theme()
            self._refresh_theme_widgets(widget)

    def _update_theme_button(self) -> None:
        """Set the toggle label to describe the available alternate appearance."""
        self.theme_button.configure(
            text="☾ Dark theme" if self.theme.theme_name == "light" else "☀ Light theme"
        )

    def _shortcut_predict(self, _event: tk.Event[tk.Misc]) -> str | None:
        """Predict on Enter unless keyboard focus is in a text input."""
        if self.root.focus_get() is self.app_picker:
            return None
        if not self.busy:
            self._predict()
            return "break"
        return None

    def _shortcut_compare(self, _event: tk.Event[tk.Misc]) -> str:
        """Run the comparison command on Ctrl+R."""
        if not self.busy:
            self._compare()
        return "break"

    def _shortcut_find(self, _event: tk.Event[tk.Misc]) -> str:
        """Focus and select the app search field on Ctrl+F."""
        self.app_picker.focus_set()
        self.app_picker.selection_range(0, "end")
        return "break"

    def _close(self) -> None:
        """Close the UI and stop only the API subprocess this UI created."""
        with self.process_lock:
            self.closing = True
            processes = (self.api_process, self.pipeline_process)
        for process in processes:
            if process is not None and process.poll() is None:
                _terminate_process_tree(process.pid)
        self.snackbar.dismiss()
        self.api.session.close()
        self.root.destroy()


def _terminate_process_tree(pid: int) -> None:
    """Terminate a process and descendants with psutil rather than signals."""
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
