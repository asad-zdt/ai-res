"""A lightweight vertically scrollable frame for dashboard pages."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.theme.manager import ThemeManager
from gui.theme import tokens


class ScrollableFrame(ttk.Frame):
    """Provide a ttk content frame that reflows to the visible Canvas width."""

    def __init__(self, parent: tk.Misc, theme: ThemeManager) -> None:
        """Create the Canvas viewport and its hosted content frame."""
        super().__init__(parent)
        self.theme = theme
        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            background=theme.colors["background"],
        )
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.content.bind("<Configure>", self._update_scrollregion)
        self.canvas.bind("<Configure>", self._resize_content)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def refresh_theme(self) -> None:
        """Apply the active background after a theme switch."""
        self.canvas.configure(background=self.theme.colors["background"])

    def _update_scrollregion(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_content(self, event: tk.Event[tk.Misc]) -> None:
        self.canvas.itemconfigure(self.window, width=event.width)

    def _bind_mousewheel(self, _event: tk.Event[tk.Misc]) -> None:
        self.canvas.bind_all("<MouseWheel>", self._mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event[tk.Misc]) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _mousewheel(self, event: tk.Event[tk.Misc]) -> None:
        self.canvas.yview_scroll(int(-event.delta / tokens.SPACING["sm"]), "units")
