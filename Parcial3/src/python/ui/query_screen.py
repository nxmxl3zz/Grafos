"""Consulta A→B: cuatro tarjetas (distancia, tiempo, combustible, peajes) con camino y totales."""

from __future__ import annotations

from typing import Any
from pathlib import Path
import json

import customtkinter as ctk

from . import theme
from .format import compare_text, fmt_cop, fmt_horas, fmt_km, short_path
from .widgets import Card, CitySelector, button

ORDER = ("distancia", "tiempo", "combustible", "peajes", "total")


TOTALS = (("km", "Distancia"), ("horas", "Tiempo"), ("combustible", "Combustible"), ("peajes", "Peajes"))


def totals_labels(totals: dict) -> dict:
    return {"km": fmt_km(totals["km"]), "horas": fmt_horas(totals["horas"]),
            "combustible": fmt_cop(totals["combustible"]), "peajes": fmt_cop(totals["peajes"])}


class ResultCard(Card):
    def __init__(self, parent: Any, fonts: dict, criterion: str):
        super().__init__(parent, theme.CRITERIA_TITLES[criterion], fonts)
        self.criterion = criterion
        self.title_label.configure(text_color=theme.CRITERIA[criterion])
        self.path = ctk.CTkLabel(self.body, text="—", font=fonts["body"], text_color=theme.INK, anchor="w",
                                 justify="left", wraplength=420)
        self.path.pack(fill="x")
        self.legs = ctk.CTkLabel(self.body, text="", font=fonts["small"], text_color=theme.MUTED, anchor="w",
                                 justify="left", wraplength=420)
        self.legs.pack(fill="x", pady=(2, 8))
        self.totals = ctk.CTkFrame(self.body, fg_color="transparent")
        self.totals.pack(fill="x")
        self.totals.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="t")
        self.values: dict[str, ctk.CTkLabel] = {}
        for column, (key, caption) in enumerate(TOTALS):
            block = ctk.CTkFrame(self.totals, fg_color=theme.BG, corner_radius=8)
            block.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 4, 0))
            self.values[key] = ctk.CTkLabel(block, text="—", font=fonts["h1"], text_color=theme.INK, anchor="w")
            self.values[key].pack(fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(block, text=caption, font=fonts["small"], text_color=theme.MUTED, anchor="w").pack(
                fill="x", padx=10, pady=(0, 8))
        self.bind("<Configure>", lambda e: [w.configure(wraplength=max(e.width - 40, 200))
                                            for w in (self.path, self.legs)])

    def show(self, info: dict | None, city_name, base: dict | None = None, params: dict | None = None) -> None:
        if not info:
            self.path.configure(text="—")
            self.legs.configure(text="")
            for label in self.values.values():
                label.configure(text="—")
            return
        self.path.configure(text=short_path([city_name(c) for c in info["ciudades"]]))
        stops = max(len(info["ciudades"]) - 1, 0)
        note = compare_text(base, info["totales"]) if base and self.criterion != "distancia" else ""
        if params and params.get("consumo_km_gal"):
            gallons = info["totales"]["km"] / params["consumo_km_gal"]
            fuel = f"Combustible: {gallons:,.1f} gal × {fmt_cop(params['precio_gal'])}/gal".replace(",", ".")
            note = fuel + ("\n" + note if note else "")
        self.legs.configure(text=f"{stops} tramo{'s' if stops != 1 else ''}"
                                 + (f" · rutas {', '.join(info['rutas'])}" if info["rutas"] else "")
                                 + (f"\n{note}" if note else ""))
        for key, text in totals_labels(info["totales"]).items():
            self.values[key].configure(text=text)


def merge_via(first: dict, second: dict, a: str, b: str, via: str) -> dict:
    """Une A→V y V→B: el mejor camino por V para cada criterio es el mejor de cada mitad."""
    if not second.get("ok"):
        return second
    one, two = first["result"], second["result"]
    if not two.get("alcanzable"):
        return {"ok": True, "result": {"from": a, "to": b, "alcanzable": False}, "state": second.get("state")}
    criteria = {}
    for key, left in one["criterios"].items():
        right = two["criterios"][key]
        totals = {k: left["totales"][k] + right["totales"][k] for k in left["totales"]}
        totals["km"], totals["horas"] = round(totals["km"], 1), round(totals["horas"], 2)
        criteria[key] = {"ciudades": left["ciudades"] + right["ciudades"][1:], "rutas": left["rutas"] + right["rutas"],
                         "totales": totals}
    return {"ok": True, "state": second.get("state"),
            "result": {"from": a, "to": b, "via": via, "alcanzable": True, "criterios": criteria}}


class GraphQueryScreen(ctk.CTkFrame):
    def __init__(self, parent: Any, app: Any):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        fonts = app.fonts
        self.result: dict | None = None
        ctk.CTkLabel(self, text="Consulta de rutas", font=fonts["h1"], text_color=theme.INK, anchor="w").pack(
            fill="x", padx=2, pady=(0, 8))
        self.bar = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=10)
        self.bar.pack(fill="x", pady=(0, 10))
        self.bar.grid_columnconfigure((0, 2), weight=1)
        self.origin = self.destination = None
        content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True)
        self.message = ctk.CTkLabel(content, text="Elige origen y destino y pulsa Calcular.", font=fonts["body"],
                                    text_color=theme.MUTED, anchor="w", justify="left", wraplength=1050)
        self.message.pack(fill="x", padx=4, pady=(0, 8))
        content.bind("<Configure>", lambda event: self.message.configure(wraplength=max(event.width - 32, 200)))
        grid = ctk.CTkFrame(content, fg_color="transparent")
        grid.pack(fill="x", anchor="n")
        grid.grid_columnconfigure((0, 1), weight=1, uniform="q")
        self.cards: dict[str, ResultCard] = {}
        for i, key in enumerate(ORDER):
            self.cards[key] = ResultCard(grid, fonts, key)
            wide = key == "total"   # quinta tarjeta: ancho completo
            self.cards[key].grid(row=i // 2, column=0 if wide else i % 2, columnspan=2 if wide else 1, sticky="nsew",
                                 padx=(0 if i % 2 == 0 or wide else 5, 5 if i % 2 == 0 and not wide else 0),
                                 pady=(0 if i < 2 else 5, 5 if i < 4 else 0))
        self._build_selectors()

    def _build_selectors(self) -> None:
        fonts = self.app.fonts
        keep = (self.origin.city_id() if self.origin else None, self.destination.city_id() if self.destination else None,
                self.via.city_id() if getattr(self, 'via', None) else None)
        for child in self.bar.winfo_children():
            child.destroy()
        cities = self.app.data["city"]
        self.origin = CitySelector(self.bar, fonts, cities, only_active=True)
        self.destination = CitySelector(self.bar, fonts, cities, only_active=True)
        for column, text in ((0, "Origen (escribe para buscar)"), (2, "Destino (escribe para buscar)")):
            ctk.CTkLabel(self.bar, text=text, font=fonts["small"], text_color=theme.MUTED, anchor="w").grid(
                row=0, column=column, sticky="w", padx=(14 if column == 0 else 6, 6), pady=(10, 0))
        self.origin.grid(row=1, column=0, sticky="ew", padx=(14, 6), pady=(2, 14))
        ctk.CTkLabel(self.bar, text="→", font=fonts["h1"], text_color=theme.MUTED).grid(row=1, column=1)
        self.destination.grid(row=1, column=2, sticky="ew", padx=6, pady=(2, 14))
        self.swap = button(self.bar, "⇄", self.swap_cities, fonts, width=40)
        self.swap.grid(row=1, column=3, padx=(0, 6), pady=(2, 14))
        self.calculate = button(self.bar, "Calcular", self.run, fonts, primary=True, width=120)
        self.calculate.grid(row=1, column=4, padx=(0, 14), pady=(2, 14))
        ctk.CTkLabel(self.bar, text="Pasar por (opcional: elige la ruta obligando a pasar por esa ciudad)", font=fonts["small"],
                     text_color=theme.MUTED, anchor="w").grid(row=2, column=0, columnspan=3, sticky="w", padx=14)
        self.via = CitySelector(self.bar, fonts, cities, only_active=True)
        self.via.grid(row=3, column=0, sticky="ew", padx=(14, 6), pady=(2, 14))
        for selector, value in zip((self.origin, self.destination, self.via), keep):
            if value:
                selector.select(value)
        for selector in (self.origin, self.destination, self.via):
            selector._entry.bind("<Return>", lambda _e: self.run())

    def refresh(self) -> None:
        if self.result is not None and self.app.last_query is None:
            self.result = None
            self.show_message("Los datos cambiaron. Vuelve a calcular la ruta.")
            for card in self.cards.values():
                card.show(None, self.app.city_name)
        ids = tuple(c["id"] for c in self.app.data["city"] if c.get("activo", True))
        if ids != getattr(self, "_ids", None):
            self._ids = ids
            self._build_selectors()

    def swap_cities(self) -> None:
        a, b = self.origin.city_id(), self.destination.city_id()
        if b:
            self.origin.select(b)
        if a:
            self.destination.select(a)

    def run(self) -> None:
        a, b = self.origin.city_id(), self.destination.city_id()
        if not a or not b:
            self.show_message("Elige una ciudad de origen y una de destino de la lista.", error=True)
            return
        via = self.via.city_id() if self.via.get().strip() else None
        if self.via.get().strip() and not via:
            self.show_message("Elige una ciudad válida en «Pasar por» o déjalo vacío.", error=True)
            return
        response = self.app.api({"action": "query", "from": a, "to": b} if not via or via in (a, b)
                                else {"action": "query", "from": a, "to": via})
        if response is None:
            return
        if via and via not in (a, b) and response.get("ok") and response["result"].get("alcanzable"):
            second = self.app.api({"action": "query", "from": via, "to": b})
            if second is None:
                return
            response = merge_via(response, second, a, b, via)
        if not response.get("ok"):
            self.result = None
            self.app.last_query = None
            self.show_message(response.get("error", "Error desconocido"), error=True)
            for card in self.cards.values():
                card.show(None, self.app.city_name)
            return
        result = response["result"]
        self.result = self.app.last_query = result
        if not result.get("alcanzable"):
            message = f"Sin ruta registrada en esta red entre {self.app.city_name(a)} y {self.app.city_name(b)}."
            if getattr(self.app, "bundled_access_valid", False):
                try:
                    path = Path(__file__).resolve().parents[3] / "data" / "access_research.json"
                    cities = json.loads(path.read_text(encoding="utf-8"))["ciudades"]
                    for city_id in dict.fromkeys((a, b)):
                        if city_id in cities:
                            city = cities[city_id]
                            message += f"\n{city['nombre']}: {city['explicacion']}"
                except (OSError, ValueError, KeyError, TypeError):
                    pass
            self.show_message(message, error=True)
            for card in self.cards.values():
                card.show(None, self.app.city_name)
            return
        message = f"{self.app.city_name(a)} → {self.app.city_name(b)}"
        if via and via not in (a, b):
            message = f"{self.app.city_name(a)} → (por {self.app.city_name(via)}) → {self.app.city_name(b)}"
        if getattr(self.app, "bundled_access_valid", False) and "99001" in (a, b):
            message += "\nPuerto Carreño: acceso estacional; verifica el estado de la vía y posibles cargos de planchón."
        self.show_message(message)
        for key, card in self.cards.items():
            card.show(result["criterios"].get(key), self.app.city_name,
                      (result["criterios"].get("distancia") or {}).get("totales"), self.app.params)

    def show_message(self, text: str, error: bool = False) -> None:
        self.message.configure(text=text, text_color=theme.DANGER if error else theme.INK)


class QueryScreen(ctk.CTkFrame):
    """Consulta nacional y análisis del grafo editable como modos separados."""
    def __init__(self, parent: Any, app: Any):
        super().__init__(parent, fg_color="transparent")
        from .locality_screen import LocalityScreen
        self.app = app
        self.tabs = ctk.CTkTabview(self, command=self.mode_changed, fg_color="transparent")
        self.tabs.pack(fill="both", expand=True)
        self.tabs.add("Localidades de Colombia")
        self.tabs.add("Red de carreteras (grafos PERA)")
        self.local = LocalityScreen(self.tabs.tab("Localidades de Colombia"), app)
        self.local.pack(fill="both", expand=True)
        self.graph = GraphQueryScreen(self.tabs.tab("Red de carreteras (grafos PERA)"), app)
        self.graph.pack(fill="both", expand=True)
        self.app.map_mode = "locality"

    def mode_changed(self):
        self.local.invalidate()
        self.app.map_mode = "graph" if self.tabs.get() == "Red de carreteras (grafos PERA)" else "locality"
        self.refresh()

    def refresh(self):
        self.graph.refresh()
        self.local.refresh()
