"""Small Canvas-drawn monochrome action icons."""

from __future__ import annotations

import tkinter as tk

from gui.theme import tokens


def draw_action_icon(canvas: tk.Canvas, name: str, color: str) -> None:
    """Draw the named action glyph into a compact Canvas."""
    canvas.delete("all")
    size = tokens.SIZES["icon"]
    center = size / 2
    stroke = tokens.SIZES["icon_stroke"]
    inset = size * 0.2
    if name == "predict":
        canvas.create_oval(
            inset, inset, size - inset, size - inset, outline=color, width=stroke
        )
        canvas.create_oval(
            center - inset / 2, center - inset / 2,
            center + inset / 2, center + inset / 2,
            fill=color, outline=color,
        )
        canvas.create_line(center, 0, center, inset, fill=color, width=stroke)
        canvas.create_line(
            center, size - inset, center, size, fill=color, width=stroke
        )
        canvas.create_line(0, center, inset, center, fill=color, width=stroke)
        canvas.create_line(
            size - inset, center, size, center, fill=color, width=stroke
        )
    elif name == "run":
        canvas.create_polygon(
            inset, inset, size - inset, center,
            inset, size - inset, fill=color, outline=color,
        )
    elif name == "train":
        canvas.create_line(
            inset, size - inset, size - inset, size - inset,
            fill=color, width=stroke,
        )
        bar_width = size * 0.16
        for position, height in ((0.35, 0.28), (0.58, 0.48), (0.81, 0.72)):
            x0 = size * position - bar_width / 2
            y0 = size - inset - size * height
            canvas.create_rectangle(
                x0, y0, x0 + bar_width, size - inset,
                fill=color, outline=color,
            )
