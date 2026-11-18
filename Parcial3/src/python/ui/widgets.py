"""Piezas reutilizables: tarjetas, botones, selector de ciudad y fuentes."""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from . import theme


def make_fonts(root: Any) -> dict:
    family = theme.pick_family(root)
    return {
        "h1": ctk.CTkFont(family=family, size=20, weight="bold"),
        "h2": ctk.CTkFont(family=family, size=14, weight="bold"),
        "body": ctk.CTkFont(family=family, size=13),
        "small": ctk.CTkFont(family=family, size=12),
        "kpi": ctk.CTkFont(family=family, size=24, weight="bold"),
        "mono": ctk.CTkFont(family="DejaVu Sans Mono", size=13),
        "family": family,
    }


class Card(ctk.CTkFrame):
    def __init__(self, parent: Any, title: str, fonts: dict):
        super().__init__(parent, fg_color=theme.CARD, corner_radius=10)
        self.title_label = ctk.CTkLabel(self, text=title, font=fonts["h2"], text_color=theme.INK, anchor="w")
        self.title_label.pack(fill="x", padx=14, pady=(10, 6))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=14, pady=(0, 12))


def button(parent: Any, text: str, command: Callable[[], None], fonts: dict, primary: bool = False,
           danger: bool = False, **kwargs: Any) -> ctk.CTkButton:
    fill = theme.ACCENT if primary else theme.DANGER if danger else theme.LINE
    hover = theme.ACCENT_HOVER if primary else "#c4443d" if danger else "#394659"
    return ctk.CTkButton(parent, text=text, command=command, font=fonts["body"], height=32,
                         fg_color=fill, hover_color=hover,
                         text_color="#ffffff" if primary or danger else theme.INK,
                         text_color_disabled="#7d8996", **kwargs)


class Kpi(ctk.CTkFrame):
    """Tarjeta con un valor grande y una etiqueta."""

    def __init__(self, parent: Any, fonts: dict, label: str, color: str = theme.INK):
        super().__init__(parent, fg_color=theme.CARD, corner_radius=10)
        self.value = ctk.CTkLabel(self, text="—", font=fonts["kpi"], text_color=color, anchor="w")
        self.value.pack(fill="x", padx=14, pady=(10, 0))
        self.caption = ctk.CTkLabel(self, text=label, font=fonts["small"], text_color=theme.MUTED, anchor="w")
        self.caption.pack(fill="x", padx=14, pady=(0, 10))

    def set(self, value: str) -> None:
        self.value.configure(text=value)


def city_label(city: dict) -> str:
    return f"{city['nombre']} ({city['id']})"


class CitySelector(ctk.CTkComboBox):
    """Combo con búsqueda: al escribir se filtran las ciudades por nombre, departamento o código."""

    def __init__(self, parent: Any, fonts: dict, cities: list[dict], only_active: bool = False, **kwargs: Any):
        super().__init__(parent, font=fonts["body"], dropdown_font=fonts["body"], height=34,
                         fg_color=theme.BG, border_color=theme.LINE, button_color=theme.LINE,
                         dropdown_fg_color=theme.PANEL, **kwargs)
        self.cities = [c for c in cities if c.get("activo", True) or not only_active]
        self.by_label = {city_label(c): c["id"] for c in self.cities}
        self.all_labels = list(self.by_label)
        self.configure(values=self.all_labels)
        self.set("")
        self._entry.bind("<KeyRelease>", self._filter, add="+")

    def _matches(self, needle: str) -> list[str]:
        needle = needle.strip().lower()
        out = []
        for city in self.cities:
            hay = f"{city['nombre']} {city.get('departamento', '')} {city['id']}".lower()
            if needle in hay:
                out.append(city_label(city))
        return out

    def _filter(self, _event: Any = None) -> None:
        found = self._matches(self.get())
        self.configure(values=found or self.all_labels)

    def city_id(self) -> str | None:
        """Id de la ciudad elegida (texto exacto o única coincidencia al escribir)."""
        text = self.get().strip()
        if text in self.by_label:
            return self.by_label[text]
        found = self._matches(text) if text else []
        return self.by_label[found[0]] if len(found) == 1 else None

    def select(self, city_id: str) -> None:
        for label, cid in self.by_label.items():
            if cid == city_id:
                self.set(label)
                return


class LocalitySelector(ctk.CTkFrame):
    """Campo con sugerencias locales y selección explícita de una identidad DANE."""
    def __init__(self, parent: Any, fonts: dict, records: list[dict], changed, **kwargs: Any):
        import tkinter as tk
        from locality_catalog import search_localities
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.records, self.search, self.changed = records, search_localities, changed
        self.selected = None
        self.matches = []
        self.entry = ctk.CTkEntry(self, font=fonts['body'], height=34, fg_color=theme.BG,
                                  border_color=theme.LINE, placeholder_text='Escribe una localidad')
        self.entry.pack(fill='x')
        self.listbox = tk.Listbox(self, height=4, bg=theme.PANEL, fg=theme.INK,
                                  selectbackground=theme.ACCENT, exportselection=False)
        self.entry.bind('<KeyRelease>', self._filter)
        self.entry.bind('<Down>', self._down)
        self.entry.bind('<Return>', self._enter)
        self.entry.bind('<Escape>', lambda e: self.listbox.pack_forget())
        self.listbox.bind('<ButtonRelease-1>', self._choose)
        self.listbox.bind('<Return>', self._choose)

    @staticmethod
    def label(item: dict) -> str:
        return f"{item['nombre']} — {item['municipio']}, {item['departamento']} · {item['id']}"

    def _filter(self, event=None):
        if event and event.keysym in ('Up', 'Down', 'Return', 'Escape', 'Tab'):
            return
        self.selected = None
        self.changed()
        text = self.entry.get().strip()
        self.matches = self.search(self.records, text, limit=20) if text else []
        self.listbox.delete(0, 'end')
        if text:
            for item in self.matches:
                self.listbox.insert('end', self.label(item))
            if not self.matches:
                self.listbox.insert('end', 'Sin coincidencias')
            self.listbox.pack(fill='x', pady=(2, 0))
        else:
            self.listbox.pack_forget()

    def _down(self, _event=None):
        if self.matches:
            self.listbox.focus_set()
            self.listbox.selection_set(0)
        return 'break'

    def _enter(self, _event=None):
        if self.listbox.curselection():
            self._choose()
        return 'break'

    def _choose(self, _event=None):
        selected = self.listbox.curselection()
        if selected and selected[0] < len(self.matches):
            self.select_locality(self.matches[selected[0]])
            self.entry.focus_set()
        return 'break'

    def locality(self):
        if self.selected and self.entry.get() == self.label(self.selected):
            return self.selected
        return None

    def select_locality(self, item):
        self.selected = item
        self.entry.delete(0, 'end')
        self.entry.insert(0, self.label(item) if item else '')
        self.listbox.pack_forget()
        self.changed()
