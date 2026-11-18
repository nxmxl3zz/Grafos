"""Mapa: genera el HTML de Folium y lo abre en el navegador solo cuando el usuario lo pide."""

from __future__ import annotations

from pathlib import Path
import json
import tempfile
from typing import Any
import webbrowser

import customtkinter as ctk

from . import charts, theme
from .dashboard import FigureView
from .query_screen import ORDER
from .widgets import button
from .format import fmt_cop, fmt_horas, fmt_km


class MapScreen(ctk.CTkFrame):
    def __init__(self, parent: Any, app: Any):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        fonts = app.fonts
        self.path: Path | None = None
        self.folder = Path(tempfile.mkdtemp(prefix="pera_mapa_"))
        ctk.CTkLabel(self, text="Mapa", font=fonts["h1"], text_color=theme.INK, anchor="w").pack(
            fill="x", padx=2, pady=(0, 8))
        bar = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=10)
        bar.pack(fill="x", pady=(0, 10))
        self.info = ctk.CTkLabel(bar, text="", font=fonts["small"], text_color=theme.INK, anchor="w", justify="left",
                                 wraplength=640)
        self.info.pack(side="bottom", fill="x", expand=True, padx=10, pady=(0, 6))
        bar.bind("<Configure>", lambda event: self.info.configure(wraplength=max(event.width - 24, 100)))
        self.open_button = button(bar, "Abrir en el navegador", self.open_browser, fonts, primary=True)
        self.open_button.pack(side="right", padx=(6, 14), pady=6)
        self.open_button.configure(state="disabled")
        button(bar, "Generar mapa", self.generate, fonts).pack(side="right", pady=6)
        detail = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=10)
        detail.pack(fill="x", pady=(0, 8))
        self.selector = ctk.CTkComboBox(detail, values=["Sin elementos"], command=self.show_detail,
                                        state="readonly", width=300)
        self.selector.pack(fill="x", padx=12, pady=(6, 2))
        self.detail_label = ctk.CTkLabel(detail, text="Seleccione una ruta o peaje para ver sus datos.",
                                         font=fonts["small"], text_color=theme.INK, anchor="w", justify="left",
                                         wraplength=650)
        self.detail_label.pack(fill="x", padx=12, pady=(0, 6))
        detail.bind("<Configure>", lambda event: self.detail_label.configure(wraplength=max(event.width - 30, 100)))
        self.details = {}
        self.selected_items = {}
        self.preview = FigureView(self)
        self.preview.pack(fill="both", expand=True)
        self.view = None
        self._drag = None
        self._connect_mouse()
        self.note = ctk.CTkLabel(self, text="El mapa interactivo (Folium) usa los mosaicos de OpenStreetMap: "
                                            "necesita internet al abrirlo. Capas: ciudades, rutas, peajes y la "
                                            "última consulta por criterio. Blanco: ruta seleccionada; estrella: peaje seleccionado. Trazado vial aproximado (OSRM simplificado). Condiciones estacionales y tarifas de transporte requieren confirmación.", font=fonts["small"],
                                 text_color=theme.MUTED, anchor="w", justify="left", wraplength=900)
        self.note.pack(fill="x", padx=4, pady=(8, 0))

    def refresh(self) -> None:
        self.invalidate_map()
        if not getattr(self, '_keep_view', False):
            self.view = None
        previous = self.selector.get()
        locality_query = getattr(self.app, "locality_query", None)
        if getattr(self.app, "map_mode", "graph") == "locality":
            self.note.configure(text="Ruta vial OSRM; triángulos: peajes próximos, paso no confirmado. Catálogo nacional independiente del grafo; tarifas parciales.")
            if locality_query:
                result, route = locality_query["result"], locality_query["route"]
                toll = route.get("peajes_estimados")
                toll_text = f"{fmt_cop(toll)} COP (estimación parcial)" if toll is not None else "No disponible"
                self.info.configure(text=(f"{result['origen']['nombre']}, {result['origen']['municipio']}, {result['origen']['departamento']} → "
                    f"{result['destino']['nombre']}, {result['destino']['municipio']}, {result['destino']['departamento']} · "
                    f"{fmt_km(route['km'])} · {fmt_horas(route['horas'])} · combustible "
                    f"{fmt_cop(route['combustible'])} COP · peajes {toll_text}\n{result.get('aviso', '')}"))
                charts.draw_locality_route(self.preview.figure, locality_query, self.view)
                self.preview.redraw()
            else:
                self.info.configure(text="Calcula una ruta entre localidades para verla aquí.")
                self.preview.figure.clear()
                charts.empty(self.preview.figure.add_subplot(111), "Ruta vial")
                self.preview.redraw()
            self.selector.master.pack_forget()
            return
        self.selector.master.pack(fill="x", pady=(0, 8), before=self.preview)
        self.note.configure(text="Red de carreteras (grafos PERA): trazado vial aproximado de cada ruta; naranja: peajes con su tarifa. Blanco: ruta seleccionada. Rueda: zoom · arrastrar: mover · clic en un peaje o ruta: seleccionar · doble clic: restablecer.")
        query = self.app.last_query
        if query and query.get("alcanzable"):
            lines = []
            for key in ORDER:
                info = (query.get("criterios") or {}).get(key)
                if info:
                    t = info["totales"]
                    lines.append(f"{theme.CRITERIA_TITLES[key]}: {fmt_km(t['km'])} · {fmt_horas(t['horas'])} · "
                                 f"combustible {fmt_cop(t['combustible'])} COP · peajes {fmt_cop(t['peajes'])} COP")
            text = (f"Última consulta: {self.app.city_name(query['from'])} → "
                    f"{self.app.city_name(query['to'])}\n" + "\n".join(lines))
            access = self.access_metadata().get("ciudades", {})
            for city_id in dict.fromkeys((query.get("from"), query.get("to"))):
                if city_id in access:
                    info = access[city_id]
                    text += f"\n{info['nombre']}: {info['estado']}. Condiciones y tarifas requieren confirmación."
            self.info.configure(text=text)
        elif query:
            text = "Sin ruta registrada en esta red para la última consulta."
            access = self.access_metadata().get("ciudades", {})
            for city_id in dict.fromkeys((query.get("from"), query.get("to"))):
                if city_id in access:
                    info = access[city_id]
                    text += f"\n{info['nombre']}: {info['estado']}. {info['explicacion']}"
            self.info.configure(text=text)
        else:
            self.info.configure(text="Sin consulta reciente. Seleccione una ruta o peaje para ver sus datos.")
        by_id = {c["id"]: c for c in self.app.data["city"]}
        self.details = {}
        self.selected_items = {}
        for route in self.app.data["route"]:
            a, b = by_id.get(route["origen"]), by_id.get(route["destino"])
            if a and b:
                state = "efectiva" if route.get("efectiva", True) else "inactiva"
                name = f"Ruta {route['id']} · {a['nombre']} – {b['nombre']} ({state})"
                self.selected_items[name] = ("route", route)
                self.details[name] = (f"{fmt_km(route['km'])} · {fmt_horas(route['horas'])} · "
                                      f"combustible {fmt_cop(route['combustible'])} COP · "
                                      f"peajes {fmt_cop(route['peajes_costo'])} COP")
        for toll in self.app.data["toll"]:
            state = "activo" if toll.get("activo", True) else "inactivo"
            name = f"Peaje {toll['id']} · {toll['nombre']} ({state})"
            self.selected_items[name] = ("toll", toll)
            self.details[name] = f"Tarifa: {fmt_cop(toll['tarifa'])} COP"
        values = list(self.details) or ["Sin elementos"]
        self.selector.configure(values=values)
        selected = previous if previous in self.details else values[0]
        self.selector.set(selected)
        self.show_detail(selected)

    # --- mapa interactivo (sin internet): zoom con la rueda, arrastrar, clic para seleccionar ---
    def _map_axes(self):
        axes = self.preview.figure.axes
        return axes[0] if axes else None

    def _connect_mouse(self) -> None:
        canvas = self.preview.canvas
        canvas.mpl_connect("scroll_event", self._on_scroll)
        canvas.mpl_connect("button_press_event", self._on_press)
        canvas.mpl_connect("motion_notify_event", self._on_motion)
        canvas.mpl_connect("button_release_event", self._on_release)

    def _remember_view(self, ax) -> None:
        self.view = (ax.get_xlim(), ax.get_ylim())
        self.preview.redraw()

    def _on_scroll(self, event) -> None:
        ax = self._map_axes()
        if ax is None or event.inaxes is not ax or event.xdata is None:
            return
        factor = 0.8 if event.button == "up" else 1.25
        (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
        x, y = event.xdata, event.ydata
        ax.set_xlim(x - (x - x0) * factor, x + (x1 - x) * factor)
        ax.set_ylim(y - (y - y0) * factor, y + (y1 - y) * factor)
        self._remember_view(ax)

    def _on_press(self, event) -> None:
        ax = self._map_axes()
        if ax is None or event.inaxes is not ax:
            return
        if getattr(event, "dblclick", False):
            self.view = None
            self.show_detail(self.selector.get()) if self.selector.master.winfo_ismapped() else self.refresh()
            return
        self._drag = (event.x, event.y, ax.get_xlim(), ax.get_ylim(), False)

    def _on_motion(self, event) -> None:
        ax = self._map_axes()
        if not self._drag or ax is None:
            return
        x, y, (x0, x1), (y0, y1), _moved = self._drag
        if abs(event.x - x) + abs(event.y - y) < 4 and not _moved:
            return
        inv = ax.transData.inverted()
        (ox, oy), (nx, ny) = inv.transform((x, y)), inv.transform((event.x, event.y))
        dx, dy = ox - nx, oy - ny
        ax.set_xlim(x0 + dx, x1 + dx)
        ax.set_ylim(y0 + dy, y1 + dy)
        self._drag = (x, y, (x0, x1), (y0, y1), True)
        self.preview.redraw()

    def _on_release(self, event) -> None:
        ax = self._map_axes()
        drag, self._drag = self._drag, None
        if not drag or ax is None:
            return
        if drag[4]:
            self._remember_view(ax)
        elif event.inaxes is ax:
            self.pick(ax, event.x, event.y)

    def pick(self, ax, px: float, py: float) -> None:
        """Selecciona el peaje (o, si no hay, la ruta) más cercano al clic."""
        import math
        from . import geodata
        if getattr(self.app, "map_mode", "graph") == "locality":
            return
        to_px = ax.transData.transform
        best = (12.0, None)
        for toll in self.app.data["toll"]:
            tx, ty = to_px((toll["lon"], toll["lat"]))
            d = math.hypot(tx - px, ty - py)
            if d < best[0]:
                best = (d, ("toll", toll))
        if best[1] is None:
            by_id = {c["id"]: c for c in self.app.data["city"]}
            best = (9.0, None)
            for route in self.app.data["route"]:
                pts = [to_px((p[1], p[0])) for p in geodata.route_points(route, by_id)]
                for (ax1, ay1), (bx1, by1) in zip(pts, pts[1:]):
                    dx, dy = bx1 - ax1, by1 - ay1
                    length2 = dx * dx + dy * dy
                    t = max(0.0, min(1.0, ((px - ax1) * dx + (py - ay1) * dy) / length2)) if length2 else 0.0
                    d = math.hypot(ax1 + t * dx - px, ay1 + t * dy - py)
                    if d < best[0]:
                        best = (d, ("route", route))
        if best[1] is None:
            return
        kind, item = best[1]
        for name, (k, obj) in self.selected_items.items():
            if k == kind and obj["id"] == item["id"]:
                self.selector.set(name)
                self.show_detail(name)
                return

    def access_metadata(self) -> dict:
        if not getattr(self.app, "bundled_access_valid", False):
            return {}
        try:
            return json.loads((Path(__file__).resolve().parents[3] / "data/access_research.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def invalidate_map(self) -> None:
        """Evita abrir una copia anterior a la actualización de datos o consulta."""
        self.path = None
        self.open_button.configure(state="disabled")

    def show_detail(self, selection: str) -> None:
        self.detail_label.configure(text=self.details.get(selection, "Sin elementos disponibles."))
        query = self.app.last_query
        charts.draw_network(self.preview.figure, self.app.data["city"], self.app.data["route"],
                            query if query and query.get("alcanzable") else None,
                            self.selected_items.get(selection), self.app.data["toll"], view=self.view)
        self.preview.redraw()

    def generate(self) -> Path | None:
        from .mapbuild import build_map
        try:
            if getattr(self.app, "map_mode", "graph") == "locality":
                from .mapbuild import build_locality_map
                query = getattr(self.app, "locality_query", None)
                if not query:
                    self.app.set_status("Primero calcula una ruta entre localidades.", error=True)
                    return None
                self.path = build_locality_map(self.folder / "pera_mapa.html", query)
            else:
                self.path = build_map(self.folder / "pera_mapa.html", self.app.data["city"], self.app.data["route"],
                                      self.app.data["toll"], self.app.last_query, self.access_metadata())
        except Exception as error:  # folium ausente o sin permisos de escritura
            self.app.set_status(f"No se pudo generar el mapa: {error}", error=True)
            return None
        self.open_button.configure(state="normal")
        self.app.set_status(f"Mapa generado: {self.path}")
        return self.path

    def open_browser(self) -> None:
        """Solo por clic del usuario."""
        path = self.path or self.generate()
        if path:
            webbrowser.open(path.as_uri())
