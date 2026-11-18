"""Canvas que dibuja un árbol AVL (instantánea del contrato) con movimiento suavizado."""

from __future__ import annotations

import time
import tkinter as tk
from typing import Any

from . import theme

MARGIN = 36


def ease(t: float) -> float:
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


class Placed:
    """Nodo con su posición lógica (columna in-orden, profundidad)."""
    __slots__ = ("k", "label", "active", "bf", "x", "y", "parent")

    def __init__(self, snap: dict, x: int, y: int, parent: int | None):
        self.k, self.label, self.active, self.bf = snap["k"], snap["l"], bool(snap["a"]), snap["bf"]
        self.x, self.y, self.parent = x, y, parent


def layout(snap: dict | None) -> list[Placed]:
    """Posiciones por recorrido in-orden: x = orden, y = profundidad."""
    out: list[Placed] = []

    def walk(node, depth, parent):
        if node is None:
            return
        walk(node.get("L"), depth + 1, node["k"])
        out.append(Placed(node, len(out), depth, parent))
        walk(node.get("R"), depth + 1, node["k"])

    walk(snap, 0, None)
    return out


class TreeCanvas(tk.Canvas):
    def __init__(self, parent: Any, family: str):
        super().__init__(parent, bg=theme.PANEL, highlightthickness=0, borderwidth=0)
        self.family = family
        self.snap: dict | None = None
        self.nodes: list[Placed] = []
        self.pos: dict[int, tuple[float, float]] = {}   # posición lógica actual
        self.highlight: dict[int, str] = {}
        self._from: dict[int, tuple[float, float]] = {}
        self._start = 0.0
        self._dur = 0.0
        self._job: str | None = None
        self.bind("<Configure>", lambda _e: self.redraw())

    def show(self, snap: dict | None, highlight: dict[int, str] | None = None, ms: int = 0) -> None:
        """Muestra snap; si ms > 0 mueve los nodos desde donde estaban."""
        new_nodes = layout(snap)
        by_key = {n.k: n for n in new_nodes}
        start: dict[int, tuple[float, float]] = {}
        for n in new_nodes:
            if n.k in self.pos:
                start[n.k] = self.pos[n.k]
            elif n.parent in self.pos:       # nodo nuevo: sale de su padre
                start[n.k] = self.pos[n.parent]
            elif n.parent in by_key:
                start[n.k] = (by_key[n.parent].x, by_key[n.parent].y)
            else:
                start[n.k] = (n.x, n.y)
        self.snap, self.nodes, self.highlight = snap, new_nodes, highlight or {}
        self._from = start
        self._start, self._dur = time.monotonic(), ms / 1000
        self.pos = dict(start)
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self._frame()

    def _frame(self) -> None:
        t = 1.0 if self._dur <= 0 else min(1.0, (time.monotonic() - self._start) / self._dur)
        e = ease(t)
        self.pos = {n.k: (self._from[n.k][0] + (n.x - self._from[n.k][0]) * e,
                          self._from[n.k][1] + (n.y - self._from[n.k][1]) * e) for n in self.nodes}
        self.redraw()
        self._job = self.after(16, self._frame) if t < 1.0 else None

    def _scale(self) -> tuple[float, float, float, float, float]:
        w, h = max(self.winfo_width(), 200), max(self.winfo_height(), 200)
        n = max(len(self.nodes), 1)
        depth = max((p.y for p in self.nodes), default=0)
        sx = min(80.0, (w - 2 * MARGIN) / max(n - 1, 1))
        sy = min(120.0, (h - 2 * MARGIN - 20) / max(depth, 1))
        ox = (w - sx * (n - 1)) / 2
        return sx, sy, ox, MARGIN + 6, min(27.0, max(sx * 0.46, 3.0), sy * 0.34)

    def redraw(self) -> None:
        self.delete("all")
        if not self.nodes:
            self.create_text(self.winfo_width() / 2, self.winfo_height() / 2,
                             text="Árbol vacío\nInserta una clave para empezar", justify="center",
                             fill=theme.MUTED, font=(self.family, 14))
            return
        sx, sy, ox, oy, r = self._scale()

        def at(k: int) -> tuple[float, float]:
            x, y = self.pos[k]
            return ox + x * sx, oy + y * sy

        for n in self.nodes:
            if n.parent is not None and n.parent in self.pos:
                (x1, y1), (x2, y2) = at(n.parent), at(n.k)
                self.create_line(x1, y1, x2, y2, fill=theme.EDGE, width=2)
        show_text = r >= 11
        for n in self.nodes:
            x, y = at(n.k)
            kind = self.highlight.get(n.k)
            if kind:
                fill, line = theme.HIGHLIGHT[kind]
            elif n.active:
                fill, line = theme.NODE_FILL, theme.NODE_LINE
            else:
                fill, line = theme.NODE_OFF_FILL, theme.NODE_OFF_LINE
            self.create_oval(x - r, y - r, x + r, y + r, fill=fill, outline=line, width=3 if kind else 2)
            if show_text:
                size = 12 if len(str(n.k)) <= 4 else 9
                self.create_text(x, y, text=str(n.k), fill=theme.INK if n.active else theme.MUTED,
                                 font=(self.family, size, "bold"))
                bf_color = theme.DANGER if abs(n.bf) > 1 else theme.WARN if n.bf else theme.MUTED
                self.create_text(x + r * 0.95, y - r * 1.05, text=f"{n.bf:+d}" if n.bf else "0",
                                 fill=bf_color, font=(self.family, 9, "bold"))
                if n.label and sx >= 40:
                    text = n.label if len(n.label) <= 9 else n.label[:8] + "…"
                    self.create_text(x, y + r + 9, text=text, fill=theme.MUTED, font=(self.family, 9))
