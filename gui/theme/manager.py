"""Theme persistence, ttk styling, font selection, and Windows DPI setup."""

from __future__ import annotations

import ctypes
import json
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk

from config import resolve_path
from gui.theme import tokens

_PREFERENCES_PATH = resolve_path("data", "gui_preferences.json")


def enable_windows_dpi_awareness() -> None:
    """Request per-monitor DPI awareness before creating the Tk root window."""
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_context = user32.SetProcessDpiAwarenessContext
        set_context.argtypes = [ctypes.c_void_p]
        set_context.restype = ctypes.c_bool
        if set_context(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            return


def set_tk_scaling(root: tk.Tk) -> float:
    """Set Tk's point scaling from the active display DPI."""
    try:
        dpi = float(root.winfo_fpixels("1i"))
    except tk.TclError:
        dpi = tokens.DPI["base"]
    scale = max(1.0, dpi / tokens.DPI["base"])
    root.tk.call("tk", "scaling", dpi / tokens.DPI["point"])
    return scale


def preferred_font(root: tk.Misc) -> str:
    """Choose the first installed product font, falling back to Segoe UI."""
    try:
        available = {name.casefold(): name for name in tkfont.families(root)}
    except tk.TclError:
        available = {}
    for candidate in tokens.FONT_CANDIDATES:
        if candidate.casefold() in available:
            return available[candidate.casefold()]
    return "Segoe UI"


def load_theme_preference() -> str:
    """Load the saved light/dark preference, defaulting to light."""
    try:
        preference = json.loads(_PREFERENCES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "light"
    theme = preference.get("theme") if isinstance(preference, dict) else None
    return theme if theme in {"light", "dark"} else "light"


def save_theme_preference(theme: str) -> None:
    """Persist the selected theme without exposing a settings file to Git."""
    if theme not in {"light", "dark"}:
        raise ValueError("theme must be 'light' or 'dark'")
    _PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _PREFERENCES_PATH.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps({"theme": theme}, indent=2) + "\n", encoding="utf-8"
    )
    temporary_path.replace(_PREFERENCES_PATH)


class ThemeManager:
    """Apply centralized palette, font, and ttk widget styles."""

    def __init__(self, root: tk.Tk, theme: str | None = None) -> None:
        """Initialize theme state and select a compatible font."""
        self.root = root
        self.theme_name = theme or load_theme_preference()
        self.font_family = preferred_font(root)
        self.style = ttk.Style(root)
        self.apply()

    @property
    def colors(self) -> dict[str, str]:
        """Return the active palette."""
        return tokens.DARK if self.theme_name == "dark" else tokens.LIGHT

    def toggle(self) -> str:
        """Switch themes, save the preference, and return the new theme name."""
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        save_theme_preference(self.theme_name)
        self.apply()
        return self.theme_name

    def apply(self) -> None:
        """Configure the root and standard ttk styles from design tokens."""
        c = self.colors
        self.root.configure(background=c["background"])
        self.style.theme_use("clam")
        self.style.configure(
            ".",
            background=c["background"],
            foreground=c["text"],
            font=(self.font_family, tokens.TYPOGRAPHY["body"]),
        )
        self.style.configure("TFrame", background=c["background"])
        self.style.configure(
            "Surface.TFrame",
            background=c["surface"],
            bordercolor=c["outline"],
            relief="solid",
            borderwidth=tokens.SIZES["border"],
        )
        self.style.configure(
            "Surface.TLabel",
            background=c["surface"],
            foreground=c["text"],
        )
        self.style.configure(
            "Surface.Muted.TLabel",
            background=c["surface"],
            foreground=c["text_secondary"],
        )
        self.style.configure(
            "Surface.Title.TLabel",
            background=c["surface"],
            foreground=c["text"],
            font=(self.font_family, tokens.TYPOGRAPHY["title"], "bold"),
        )
        self.style.configure(
            "Surface.Headline.TLabel",
            background=c["surface"],
            foreground=c["text"],
            font=(self.font_family, tokens.TYPOGRAPHY["headline"], "bold"),
        )
        self.style.configure(
            "Surface.Caption.TLabel",
            background=c["surface"],
            foreground=c["text_secondary"],
            font=(self.font_family, tokens.TYPOGRAPHY["caption"]),
        )
        self.style.configure(
            "TLabel",
            background=c["background"],
            foreground=c["text"],
        )
        self.style.configure(
            "Muted.TLabel", foreground=c["text_secondary"]
        )
        self.style.configure(
            "Headline.TLabel",
            font=(self.font_family, tokens.TYPOGRAPHY["headline"], "bold"),
        )
        self.style.configure(
            "Title.TLabel",
            font=(self.font_family, tokens.TYPOGRAPHY["title"], "bold"),
        )
        self.style.configure(
            "Caption.TLabel",
            font=(self.font_family, tokens.TYPOGRAPHY["caption"]),
            foreground=c["text_secondary"],
        )
        self.style.configure(
            "Primary.TButton",
            background=c["primary"],
            foreground=c["white"] if self.theme_name == "light" else c["background"],
            padding=(tokens.SPACING["md"], tokens.SPACING["sm"]),
            borderwidth=0,
            font=(self.font_family, tokens.TYPOGRAPHY["button"], "bold"),
        )
        self.style.map(
            "Primary.TButton",
            background=[
                ("disabled", c["outline"]),
                ("pressed", c["primary_pressed"]),
                ("active", c["primary_hover"]),
            ],
            foreground=[("disabled", c["text_secondary"])],
            focuscolor=[("focus", c["outline_focus"])],
        )
        self.style.configure(
            "Secondary.TButton",
            background=c["surface"],
            foreground=c["primary"],
            padding=(tokens.SPACING["md"], tokens.SPACING["sm"]),
            bordercolor=c["outline"],
            borderwidth=1,
            focusthickness=2,
            focuscolor=c["outline_focus"],
        )
        self.style.map(
            "Secondary.TButton",
            background=[("pressed", c["selection"]), ("active", c["surface_alt"])],
        )
        self.style.configure(
            "TEntry",
            fieldbackground=c["surface"],
            foreground=c["text"],
            bordercolor=c["outline"],
            insertcolor=c["text"],
            padding=tokens.SPACING["sm"],
        )
        self.style.configure(
            "TCombobox",
            fieldbackground=c["surface"],
            background=c["surface"],
            foreground=c["text"],
            arrowcolor=c["text_secondary"],
            bordercolor=c["outline"],
            padding=tokens.SPACING["sm"],
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", c["surface"])],
            selectbackground=[("readonly", c["selection"])],
            selectforeground=[("readonly", c["text"])],
        )
        self.style.configure(
            "TNotebook",
            background=c["surface"],
            borderwidth=0,
        )
        self.style.configure(
            "TNotebook.Tab",
            background=c["surface_alt"],
            foreground=c["text_secondary"],
            padding=(tokens.SPACING["md"], tokens.SPACING["sm"]),
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", c["surface"])],
            foreground=[("selected", c["primary"])],
        )
        self.style.configure(
            "Treeview",
            background=c["surface"],
            fieldbackground=c["surface"],
            foreground=c["text"],
            rowheight=tokens.SPACING["xl"],
            bordercolor=c["outline"],
        )
        self.style.configure(
            "Treeview.Heading",
            background=c["surface_alt"],
            foreground=c["text_secondary"],
            font=(self.font_family, tokens.TYPOGRAPHY["caption"], "bold"),
            padding=tokens.SPACING["sm"],
        )
        self.style.map(
            "Treeview",
            background=[("selected", c["selection"])],
            foreground=[("selected", c["text"])],
        )
        self.style.configure(
            "Horizontal.TProgressbar",
            background=c["primary"],
            troughcolor=c["surface_alt"],
            bordercolor=c["surface_alt"],
        )
