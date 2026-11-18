"""Colores y tipografía de la ventana (tema oscuro)."""

from __future__ import annotations

import tkinter.font as tkfont

BG = "#0e1217"
PANEL = "#161c24"
CARD = "#1b232d"
LINE = "#2a3441"
INK = "#e6edf3"
MUTED = "#8b98a8"
ACCENT = "#3fb68b"
ACCENT_HOVER = "#35a07a"
DANGER = "#e5534b"
WARN = "#f0a14a"
BLUE = "#4c9aff"

NODE_FILL = "#1d5c4c"
NODE_LINE = "#3fb68b"
NODE_OFF_FILL = "#2c3239"
NODE_OFF_LINE = "#58616c"
EDGE = "#46525f"

# Resaltado por tipo de paso: (relleno, borde)
HIGHLIGHT = {
    "compare": ("#1f4f8f", BLUE),
    "found": ("#1f7a4d", "#5be39a"),
    "place": ("#1f7a4d", "#5be39a"),
    "rotate": ("#8a5314", WARN),
    "remove": ("#8a2b27", DANGER),
    "height": ("#2a4f55", "#6fd3e0"),
}


def pick_family(root) -> str:
    """Primera fuente disponible de la lista; si no, la de Tk."""
    available = set(tkfont.families(root))
    for name in ("Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", "Roboto"):
        if name in available:
            return name
    return "TkDefaultFont"
