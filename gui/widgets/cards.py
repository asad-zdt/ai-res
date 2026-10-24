"""Canvas-backed rounded cards and resource metric cards."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from gui.theme import tokens
from gui.theme.manager import ThemeManager
from gui.dashboard_data import gauge_color


class SurfaceCard(tk.Canvas):
    """A lightweight rounded Canvas surface containing normal Tk widgets."""

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        padding: int = tokens.SPACING["card"],
        **kwargs: object,
    ) -> None:
        """Create a content surface with a subtle outline and rounded corners."""
        self.theme = theme
        self.padding = padding
        super().__init__(
            parent,
            highlightthickness=0,
            borderwidth=0,
            background=theme.colors["background"],
            **kwargs,
        )
        self.content = ttk.Frame(self, padding=padding, style="Surface.TFrame")
        self._window = self.create_window(
            (tokens.SIZES["radius"], tokens.SIZES["radius"]),
            window=self.content,
            anchor="nw",
        )
        self.bind("<Configure>", self._redraw)
        self.content.bind("<Configure>", self._sync_size)

    def refresh_theme(self) -> None:
        """Redraw the card surface after a palette change."""
        self.configure(background=self.theme.colors["background"])
        self.content.configure(style="Surface.TFrame")
        self._redraw()

    def _sync_size(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        """Keep the canvas large enough to fit its child content."""
        self.after_idle(self._redraw)

    def _redraw(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        """Draw a rounded surface behind the content frame."""
        self.delete("card")
        width = max(self.winfo_width(), self.content.winfo_reqwidth() + self.padding * 2)
        height = max(self.winfo_height(), self.content.winfo_reqheight() + self.padding * 2)
        self.configure(width=width, height=height)
        radius = tokens.SIZES["radius"]
        self.create_polygon(
            radius, 0, width - radius, 0, width, radius, width, height - radius,
            width - radius, height, radius, height, 0, height - radius, 0, radius,
            smooth=True,
            splinesteps=tokens.SIZES["curve_steps"],
            fill=self.theme.colors["surface"],
            outline=self.theme.colors["outline"],
            width=tokens.SIZES["border"],
            tags=("card",),
        )
        self.tag_lower("card")
        self.coords(self._window, (radius, radius))
        self.itemconfigure(
            self._window,
            width=max(width - radius * 2, 1),
            height=max(height - radius * 2, 1),
        )


class MetricCard:
    """A reusable metric card with value, semantic status, and gauge."""

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        metric: str,
        title: str,
        unit: str,
        maximum: float,
        on_resize: Callable[[], None] | None = None,
    ) -> None:
        """Build a metric card using a shared palette and capacity scale."""
        self.theme = theme
        self.metric = metric
        self.title = title
        self.unit = unit
        self.maximum = maximum
        self.on_resize = on_resize
        self.card = SurfaceCard(parent, theme)
        body = self.card.content
        header = ttk.Frame(body, style="Surface.TFrame")
        header.pack(fill="x")
        self.icon = tk.Canvas(
            header, width=tokens.SIZES["icon"], height=tokens.SIZES["icon"],
            highlightthickness=0, background=theme.colors["surface"],
        )
        self.icon.pack(side="left", padx=(0, tokens.SPACING["sm"]))
        self._draw_icon()
        ttk.Label(header, text=title, style="Surface.Title.TLabel").pack(side="left")
        self.status = tk.Label(
            header,
            text="No data",
            background=theme.colors["selection"],
            foreground=theme.colors["text_secondary"],
            padx=tokens.SPACING["sm"],
            pady=tokens.SPACING["xs"],
            font=(theme.font_family, tokens.TYPOGRAPHY["caption"]),
        )
        self.status.pack(side="right")
        self.value = ttk.Label(
            body, text="—", style="Surface.Headline.TLabel", anchor="w"
        )
        self.value.pack(fill="x", pady=(tokens.SPACING["md"], tokens.SPACING["sm"]))
        self.gauge = tk.Canvas(
            body, height=tokens.SIZES["gauge_height"],
            highlightthickness=0, background=theme.colors["surface"],
        )
        self.gauge.pack(fill="x")
        self.gauge.bind("<Configure>", self._draw_gauge)
        if self.on_resize:
            self.card.bind("<Configure>", lambda _event: self.on_resize())

    def grid(self, **kwargs: object) -> None:
        """Grid the card Canvas in its parent."""
        self.card.grid(**kwargs)

    def pack(self, **kwargs: object) -> None:
        """Pack the card Canvas in its parent."""
        self.card.pack(**kwargs)

    def update_value(self, value: float | None, label: str = "") -> None:
        """Update the displayed measurement and semantic status."""
        if value is None:
            self.value.configure(text="—")
            self.update_status("No data")
        else:
            self.value.configure(text=f"{value:,.2f} {self.unit}")
            self.update_status(label or self._status_for(value))
        self._draw_gauge()

    def update_status(self, status: str) -> None:
        """Update the semantic metric status chip."""
        color = (
            self.theme.colors["success"] if status == "Within typical range"
            else self.theme.colors["warning"] if status == "Above typical"
            else self.theme.colors["text_secondary"]
        )
        self.status.configure(
            text=status,
            background=self.theme.colors["selection"],
            foreground=color,
        )

    def refresh_theme(self) -> None:
        """Refresh Canvas surfaces and gauge colors after theme changes."""
        self.card.refresh_theme()
        self.icon.configure(background=self.theme.colors["surface"])
        self.gauge.configure(background=self.theme.colors["surface"])
        self.update_status(str(self.status.cget("text")))
        self._draw_icon()
        self._draw_gauge()

    def _status_for(self, value: float) -> str:
        """Compare a resource value with this chart's scale."""
        fraction = value / max(self.maximum, 1e-9)
        return (
            "Within typical range"
            if fraction < tokens.GAUGE_THRESHOLDS["warning_max"]
            else "Above typical"
        )

    def _draw_gauge(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        """Draw a rounded green/amber/red capacity gauge."""
        self.gauge.delete("all")
        width = max(
            self.gauge.winfo_width(), tokens.SIZES["metric_gauge_min_width"]
        )
        height = tokens.SIZES["gauge_height"]
        radius = height / 2
        self.gauge.create_oval(
            0, 0, height, height, fill=self.theme.colors["gauge_track"], outline=""
        )
        self.gauge.create_rectangle(
            radius, 0, width - radius, height,
            fill=self.theme.colors["gauge_track"], outline="",
        )
        self.gauge.create_oval(
            width - height, 0, width, height,
            fill=self.theme.colors["gauge_track"], outline="",
        )
        text = self.value.cget("text")
        try:
            value = float(str(text).split()[0].replace(",", ""))
        except (IndexError, ValueError):
            return
        fraction = min(max(value / max(self.maximum, 1e-9), 0.0), 1.0)
        fill_width = width * fraction
        color = gauge_color(value, self.maximum, self.theme.colors)
        self.gauge.create_rectangle(
            0, 0, max(fill_width, radius), height, fill=color, outline=""
        )
        if fill_width < height:
            self.gauge.create_oval(
                0, 0, height, height, fill=color, outline=""
            )

    def _draw_icon(self) -> None:
        """Draw a small monochrome vector glyph for the resource type."""
        self.icon.delete("all")
        color = self.theme.colors["text_secondary"]
        center = tokens.SIZES["icon"] / 2
        if self.metric == "cpu_pct":
            self.icon.create_oval(4, 4, 18, 18, outline=color, width=2)
            self.icon.create_line(11, 4, 11, 0, fill=color, width=2)
            self.icon.create_line(11, 18, 11, 22, fill=color, width=2)
            self.icon.create_line(4, 11, 0, 11, fill=color, width=2)
            self.icon.create_line(18, 11, 22, 11, fill=color, width=2)
        elif self.metric == "ram_mb":
            self.icon.create_rectangle(2, 6, 20, 16, outline=color, width=2)
            for x in (6, 11, 16):
                self.icon.create_line(x, 9, x, 13, fill=color, width=1)
        elif self.metric == "disk_mbps":
            self.icon.create_line(3, 17, 8, 11, 13, 14, 19, 5, fill=color, width=2)
            self.icon.create_line(15, 5, 19, 5, 19, 9, fill=color, width=2)
        else:
            self.icon.create_arc(2, 3, 20, 21, start=35, extent=110, outline=color, width=2)
            self.icon.create_arc(2, 3, 20, 21, start=215, extent=110, outline=color, width=2)
            self.icon.create_oval(center - 2, center - 2, center + 2, center + 2, fill=color)
