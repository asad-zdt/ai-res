"""Non-blocking snackbar, contextual tooltip, and Material-style dialogs."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from gui.theme import tokens
from gui.theme.manager import ThemeManager


class Snackbar:
    """Display a short-lived success or informational message."""

    def __init__(self, parent: tk.Misc, theme: ThemeManager) -> None:
        """Create a snackbar anchored to the bottom edge of its parent."""
        self.parent = parent
        self.theme = theme
        self.window: tk.Toplevel | None = None

    def show(self, message: str, duration_ms: int = tokens.SIZES["snackbar_duration_ms"]) -> None:
        """Show a non-modal toast without interrupting the workflow."""
        self.dismiss()
        window = tk.Toplevel(self.parent)
        self.window = window
        window.wm_overrideredirect(True)
        window.attributes("-topmost", True)
        background = self.theme.colors["text"]
        foreground = self.theme.colors["surface"]
        frame = tk.Frame(window, background=background, padx=tokens.SPACING["lg"],
                         pady=tokens.SPACING["sm"])
        frame.pack()
        tk.Label(
            frame, text=message, background=background, foreground=foreground,
            font=(self.theme.font_family, tokens.TYPOGRAPHY["body"]),
        ).pack()
        window.update_idletasks()
        x = self.parent.winfo_rootx() + max(
            tokens.SPACING["md"],
            self.parent.winfo_width() - window.winfo_reqwidth() - tokens.SPACING["lg"],
        )
        y = self.parent.winfo_rooty() + self.parent.winfo_height() - window.winfo_reqheight() - tokens.SPACING["xl"]
        window.geometry(f"+{x}+{y}")
        window.after(duration_ms, self.dismiss)

    def dismiss(self) -> None:
        """Close the active snackbar, if any."""
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None


class Tooltip:
    """Attach a short hover hint to a Tk widget."""

    def __init__(
        self, widget: tk.Widget, text: str, theme: ThemeManager
    ) -> None:
        """Bind enter/leave events to show a non-interactive hint."""
        self.widget = widget
        self.text = text
        self.theme = theme
        self.window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event: tk.Event[tk.Misc]) -> None:
        if self.window is not None:
            return
        window = tk.Toplevel(self.widget)
        self.window = window
        window.wm_overrideredirect(True)
        colors = self.theme.colors
        window.configure(background=colors["text"])
        x = self.widget.winfo_rootx() + tokens.SPACING["sm"]
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + tokens.SPACING["xs"]
        window.geometry(f"+{x}+{y}")
        tk.Label(
            window, text=self.text, background=colors["text"],
            foreground=colors["surface"], padx=tokens.SPACING["sm"],
            pady=tokens.SPACING["xs"],
        ).pack()

    def _hide(self, _event: tk.Event[tk.Misc]) -> None:
        if self.window is not None:
            self.window.destroy()
            self.window = None


class MaterialDialog:
    """Custom Toplevel helper for confirmation and expandable error details."""

    @staticmethod
    def confirm(
        parent: tk.Misc, theme: ThemeManager, title: str, message: str
    ) -> bool:
        """Display a modal confirmation and return the user's decision."""
        result = {"accepted": False}
        window = tk.Toplevel(parent)
        window.title(title)
        window.transient(parent)
        window.configure(background=theme.colors["surface"])
        window.resizable(False, False)
        body = ttk.Frame(
            window, padding=tokens.SPACING["lg"], style="Surface.TFrame"
        )
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=title, style="Surface.Title.TLabel").pack(anchor="w")
        ttk.Label(
            body, text=message, wraplength=tokens.TEXT_LAYOUT["dialog_wrap"], justify="left",
            style="Surface.TLabel",
        ).pack(anchor="w", pady=(tokens.SPACING["md"], tokens.SPACING["lg"]))
        actions = ttk.Frame(body, style="Surface.TFrame")
        actions.pack(fill="x")
        ttk.Button(
            actions, text="Cancel", style="Secondary.TButton",
            command=window.destroy,
        ).pack(side="right", padx=(tokens.SPACING["sm"], 0))
        ttk.Button(
            actions, text="Continue", style="Primary.TButton",
            command=lambda: (result.update(accepted=True), window.destroy()),
        ).pack(side="right")
        window.bind("<Escape>", lambda _event: window.destroy())
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.grab_set()
        parent.wait_window(window)
        return result["accepted"]

    @staticmethod
    def error(
        parent: tk.Misc,
        theme: ThemeManager,
        title: str,
        summary: str,
        details: str,
    ) -> None:
        """Show a concise error with optional expandable diagnostic text."""
        window = tk.Toplevel(parent)
        window.title(title)
        window.transient(parent)
        window.configure(background=theme.colors["surface"])
        window.resizable(False, False)
        body = ttk.Frame(
            window, padding=tokens.SPACING["lg"], style="Surface.TFrame"
        )
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=title, style="Surface.Title.TLabel").pack(anchor="w")
        ttk.Label(
            body, text=summary, wraplength=tokens.TEXT_LAYOUT["error_wrap"],
            justify="left", style="Surface.TLabel",
        ).pack(
            anchor="w", pady=(tokens.SPACING["md"], tokens.SPACING["sm"])
        )
        detail_frame = ttk.Frame(body, style="Surface.TFrame")
        expanded = {"value": False}
        details_text = tk.Text(
            detail_frame,
            height=tokens.TEXT_LAYOUT["detail_lines"],
            width=tokens.TEXT_LAYOUT["detail_columns"],
            wrap="word",
            background=theme.colors["surface_alt"],
            foreground=theme.colors["text"],
            relief="flat", font=(theme.font_family, tokens.TYPOGRAPHY["caption"]),
        )
        details_text.insert("1.0", details or "No additional details.")
        details_text.configure(state="disabled")
        details_text.pack(fill="both", expand=True)
        toggle_text = tk.StringVar(value="Show details")

        def toggle_details() -> None:
            if expanded["value"]:
                detail_frame.pack_forget()
                toggle_text.set("Show details")
            else:
                detail_frame.pack(fill="both", expand=True, pady=tokens.SPACING["sm"])
                toggle_text.set("Hide details")
            expanded["value"] = not expanded["value"]

        footer = ttk.Frame(body, style="Surface.TFrame")
        footer.pack(fill="x", pady=(tokens.SPACING["md"], 0))
        ttk.Button(
            footer, textvariable=toggle_text, style="Secondary.TButton",
            command=toggle_details,
        ).pack(side="left")
        ttk.Button(
            footer, text="Close", style="Primary.TButton",
            command=window.destroy,
        ).pack(side="right")
        window.bind("<Escape>", lambda _event: window.destroy())
        window.grab_set()
