"""Resumen: tarjetas con conteos e histogramas y barras de matplotlib incrustados."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from . import charts, theme
from .format import es_num, fmt_cop, fmt_km
from .widgets import Kpi


class FigureView(ctk.CTkFrame):
    """Un lienzo de matplotlib dentro de un marco."""

    def __init__(self, parent: Any):
        super().__init__(parent, fg_color=theme.PANEL, corner_radius=10)
        self.figure = charts.new_figure()
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().configure(bg=theme.PANEL, highlightthickness=0)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=4)

    def redraw(self) -> None:
        self.canvas.draw_idle()


class Dashboard(ctk.CTkFrame):
    def __init__(self, parent: Any, app: Any):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        fonts = app.fonts
        self.stats: dict = {}
        ctk.CTkLabel(self, text="Resumen", font=fonts["h1"], text_color=theme.INK, anchor="w").pack(
            fill="x", padx=2, pady=(0, 8))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        specs = [("ciudades", "Ciudades activas", theme.ACCENT), ("peajes", "Peajes activos", theme.WARN),
                 ("rutas", "Rutas efectivas", theme.BLUE), ("componentes", "Componentes conexas", theme.INK),
                 ("km", "Distancia media por ruta", theme.CRITERIA["distancia"]),
                 ("cop", "Combustible medio por ruta", theme.CRITERIA["combustible"])]
        self.kpis: dict[str, Kpi] = {}
        for column, (key, label, color) in enumerate(specs):
            row.grid_columnconfigure(column, weight=1, uniform="kpi")
            self.kpis[key] = Kpi(row, fonts, label, color)
            self.kpis[key].grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 5, 0))
        self.tabs = ctk.CTkTabview(self, fg_color=theme.PANEL, segmented_button_selected_color=theme.ACCENT,
                                   segmented_button_selected_hover_color=theme.ACCENT_HOVER,
                                   segmented_button_unselected_color=theme.CARD)
        self.tabs.pack(fill="both", expand=True)
        self.hist_view = FigureView(self.tabs.add("Histogramas"))
        self.hist_view.pack(fill="both", expand=True)
        bars = self.tabs.add("Barras")
        self.criterion = ctk.CTkSegmentedButton(bars, values=["distancia", "tiempo", "combustible", "peajes"],
                                                command=lambda _v: self.draw_bars(), font=fonts["small"],
                                                selected_color=theme.ACCENT, selected_hover_color=theme.ACCENT_HOVER)
        self.criterion.set("combustible")
        self.criterion.pack(anchor="e", pady=(0, 4))
        self.bars_view = FigureView(bars)
        self.bars_view.pack(fill="both", expand=True)
        self.empty_note = ctk.CTkLabel(self, text="", font=fonts["small"], text_color=theme.MUTED)

    def refresh(self) -> None:
        response = self.app.api({"action": "stats"})
        if not response or not response.get("ok"):
            return
        self.stats = response["result"]
        counts, graphs = self.stats["conteos"], self.stats["grafos"]
        self.kpis["ciudades"].set(f"{counts['ciudades_activas']} / {counts['ciudades']}")
        self.kpis["peajes"].set(f"{counts['peajes_activos']} / {counts['peajes']}")
        self.kpis["rutas"].set(f"{counts['rutas_efectivas']} / {counts['rutas']}")
        self.kpis["componentes"].set(str(counts["componentes"]))
        dist, fuel = graphs.get("distancia", {}), graphs.get("combustible", {})
        self.kpis["km"].set(fmt_km(dist["media"]) if dist.get("n") else "—")
        self.kpis["cop"].set(fmt_cop(fuel["media"]) if fuel.get("n") else "—")
        charts.draw_histograms(self.hist_view.figure, graphs)
        self.hist_view.redraw()
        self.draw_bars()

    def draw_bars(self) -> None:
        if not self.stats:
            return
        charts.draw_bars(self.bars_view.figure, self.stats, self.criterion.get(), self.app.city_name)
        self.bars_view.redraw()
