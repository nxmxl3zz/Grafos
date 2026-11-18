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
VIOLET = "#a78bfa"

# Un color por criterio de consulta (se repite en gráficos y mapa).
CRITERIA = {"distancia": BLUE, "tiempo": WARN, "combustible": ACCENT, "peajes": VIOLET, "total": "#f472b6"}
CRITERIA_TITLES = {"distancia": "Menor distancia", "tiempo": "Menor tiempo",
                   "combustible": "Menor combustible", "peajes": "Menor costo en peajes", "total": "Menor costo total (combustible + peajes)"}


def pick_family(root) -> str:
    """Primera fuente disponible de la lista; si no, la de Tk."""
    available = set(tkfont.families(root))
    for name in ("Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", "Roboto"):
        if name in available:
            return name
    return "TkDefaultFont"
