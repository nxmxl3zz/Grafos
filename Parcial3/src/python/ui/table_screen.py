"""Pantallas de tabla (ciudades, peajes y rutas): búsqueda, ordenar, crear, editar, eliminar, desactivar."""

from __future__ import annotations

from tkinter import messagebox, ttk
from typing import Any, Callable

import customtkinter as ctk

from . import forms, theme
from .format import es_num, fmt_horas, fmt_km
from .widgets import button

# (clave del item, encabezado, ancho, alineación, formateador o None)
Column = tuple[str, str, int, str, Callable[[Any, dict], str] | None]


def apply_tree_style(root: Any, family: str) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Pera.Treeview", background=theme.CARD, fieldbackground=theme.CARD, foreground=theme.INK,
                    rowheight=28, borderwidth=0, bordercolor=theme.CARD, lightcolor=theme.CARD,
                    darkcolor=theme.CARD, font=(family, 11))
    style.map("Pera.Treeview", background=[("selected", "#1d5c4c")], foreground=[("selected", "#ffffff")])
    style.configure("Pera.Treeview.Heading", background=theme.LINE, foreground=theme.INK, relief="flat",
                    font=(family, 11, "bold"), padding=6)
    style.map("Pera.Treeview.Heading", background=[("active", "#394659")])
    for orient in ("Vertical", "Horizontal"):
        style.configure(f"Pera.{orient}.TScrollbar", background=theme.LINE, troughcolor=theme.PANEL,
                        bordercolor=theme.PANEL, arrowcolor=theme.MUTED, lightcolor=theme.LINE,
                        darkcolor=theme.LINE)
        style.map(f"Pera.{orient}.TScrollbar", background=[("active", "#394659"), ("!active", theme.LINE)])


def state_text(item: dict) -> str:
    if not item.get("activo", True):
        return "Inactivo"
    if item.get("efectiva") is False:
        return "Sin efecto (ciudad inactiva)"
    return "Activo"


class TableScreen(ctk.CTkFrame):
    """Tabla genérica sobre un tipo de entidad (`city`, `toll` o `route`)."""

    kind = ""
    noun = ""
    plural = ""
    columns: list[Column] = []

    def __init__(self, parent: Any, app: Any):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        fonts = app.fonts
        self.sort_key, self.sort_desc = "id", False
        self.rows: dict[str, dict] = {}
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        self.top = top
        ctk.CTkLabel(top, text=self.plural, font=fonts["h1"], text_color=theme.INK).pack(side="left", padx=(2, 16))
        self.search = ctk.CTkEntry(top, placeholder_text="Buscar…", font=fonts["body"], height=34, width=260,
                                   fg_color=theme.CARD, border_color=theme.LINE)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda _e: self.render())
        self.count = ctk.CTkLabel(top, text="", font=fonts["small"], text_color=theme.MUTED)
        self.count.pack(side="left", padx=12)
        for text, command, style in (("Desactivar / Reactivar", self.toggle, {}), ("Eliminar", self.delete,
                                     dict(danger=True)), ("Editar", self.edit, {}),
                                     (f"Nuevo", self.new, dict(primary=True))):
            button(top, text, command, fonts, **style).pack(side="right", padx=(6, 0))
        holder = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=10)
        holder.pack(fill="both", expand=True)
        holder.grid_columnconfigure(0, weight=1)
        holder.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(holder, style="Pera.Treeview", show="headings", selectmode="browse",
                                 columns=[c[0] for c in self.columns])
        for key, heading, width, anchor, _fmt in self.columns:
            self.tree.heading(key, text=heading, anchor=anchor, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, minwidth=50, anchor=anchor, stretch=key in self.stretch_columns)
        scroll = ttk.Scrollbar(holder, orient="vertical", style="Pera.Vertical.TScrollbar", command=self.tree.yview)
        hscroll = ttk.Scrollbar(holder, orient="horizontal", style="Pera.Horizontal.TScrollbar",
                                command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=hscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        scroll.grid(row=0, column=1, sticky="ns", pady=6, padx=(0, 4))
        hscroll.grid(row=1, column=0, sticky="ew", padx=(6, 0), pady=(0, 4))
        self.tree.tag_configure("off", foreground="#6f7b8a")
        self.tree.bind("<Double-1>", lambda _e: self.edit())
        self.tree.bind("<Delete>", lambda _e: self.delete())

    stretch_columns: tuple[str, ...] = ("nombre",)

    # ---- datos ---------------------------------------------------------
    def items(self) -> list[dict]:
        return self.app.data[self.kind]

    def cell(self, item: dict, column: Column) -> str:
        key, _h, _w, _a, fmt = column
        if key == "estado":
            return state_text(item)
        value = item.get(key, "")
        return fmt(value, item) if fmt else str(value)

    def refresh(self) -> None:
        self.render()

    def render(self) -> None:
        needle = self.search.get().strip().lower()
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        shown = []
        for item in self.items():
            cells = [self.cell(item, c) for c in self.columns]
            if needle and needle not in " ".join(cells).lower():
                continue
            shown.append((item, cells))

        def sort_value(pair: tuple[dict, list[str]]):
            value = pair[0].get(self.sort_key, "")
            return (isinstance(value, str), value if not isinstance(value, (list, bool)) else str(value))

        shown.sort(key=sort_value, reverse=self.sort_desc)
        self.rows = {}
        for item, cells in shown:
            self.rows[item["id"]] = item
            off = not item.get("activo", True) or item.get("efectiva") is False
            self.tree.insert("", "end", iid=item["id"], values=cells, tags=("off",) if off else ())
        self.count.configure(text=f"{len(shown)} de {len(self.items())}")
        if selected and selected[0] in self.rows:
            self.tree.selection_set(selected[0])

    def sort_by(self, key: str) -> None:
        self.sort_desc = not self.sort_desc if key == self.sort_key else False
        self.sort_key = key
        self.render()

    def selected(self) -> dict | None:
        chosen = self.tree.selection()
        if not chosen:
            self.app.set_status(f"Selecciona {self.noun} en la tabla.", error=True)
            return None
        return self.rows.get(chosen[0])

    # ---- acciones ------------------------------------------------------
    def to_payload(self, values: dict) -> dict:
        raise NotImplementedError

    def open_form(self, values: dict | None, on_submit: Callable[[dict], str | None]):
        raise NotImplementedError

    def form_values(self, item: dict) -> dict:
        return dict(item)

    def new(self):
        return self.open_form(None, lambda v: self.save(None, v))

    def edit(self):
        item = self.selected()
        return self.open_form(self.form_values(item), lambda v: self.save(item["id"], v)) if item else None

    def save(self, item_id: str | None, values: dict) -> str | None:
        """Crea o actualiza; devuelve el mensaje de error del motor (el formulario lo muestra) o None."""
        payload = self.to_payload(values)
        if item_id is None:
            payload = {"action": "create", "kind": self.kind, **{k: v for k, v in payload.items() if v != "" or k != "id"}}
        else:
            payload.pop("id", None)
            payload = {"action": "update", "kind": self.kind, "id": item_id, **payload}
        response = self.app.api(payload)
        if response is None:
            return "No se pudo hablar con el motor."
        if not response.get("ok"):
            return response.get("error", "Error desconocido")
        self.app.reload()
        self.app.set_status(f"{self.noun.capitalize()} {'creado' if item_id is None else 'actualizado'}.")
        return None

    def delete(self) -> None:
        item = self.selected()
        if not item:
            return
        extra = " Se eliminarán también sus rutas." if self.kind == "city" else ""
        if not messagebox.askyesno("Eliminar", f"¿Eliminar {self.noun} {item['id']}?{extra}"):
            return
        response = self.app.api({"action": "delete", "kind": self.kind, "id": item["id"]})
        if response and response.get("ok"):
            gone = response["result"].get("rutas_eliminadas") or []
            self.app.reload()
            self.app.set_status(f"{self.noun.capitalize()} {item['id']} eliminado."
                                + (f" Rutas eliminadas: {len(gone)}." if gone else ""))
        elif response:
            self.app.set_status(response.get("error", "No se pudo eliminar."), error=True)

    def toggle(self) -> None:
        item = self.selected()
        if not item:
            return
        response = self.app.api({"action": "toggle", "kind": self.kind, "id": item["id"]})
        if response and response.get("ok"):
            self.app.reload()
            now = "reactivado" if response["result"].get("activo") else "desactivado"
            self.app.set_status(f"{self.noun.capitalize()} {item['id']} {now}.")
        elif response:
            self.app.set_status(response.get("error", "No se pudo cambiar el estado."), error=True)


def _num(decimals: int):
    return lambda v, _i: es_num(v, decimals)


class CityScreen(TableScreen):
    kind, noun, plural = "city", "la ciudad", "Ciudades"
    columns = [("id", "Código", 80, "w", None), ("nombre", "Nombre", 220, "w", None),
               ("departamento", "Departamento", 190, "w", None), ("lat", "Latitud", 90, "e", _num(4)),
               ("lon", "Longitud", 90, "e", _num(4)), ("grado", "Rutas", 70, "e", None),
               ("estado", "Estado", 150, "w", None)]
    stretch_columns = ("nombre", "departamento")

    def open_form(self, values, on_submit):
        return forms.city_form(self.app, values, on_submit)

    def to_payload(self, values: dict) -> dict:
        return forms.numbers(values, ("lat", "lon"))


class TollScreen(TableScreen):
    kind, noun, plural = "toll", "el peaje", "Peajes"
    columns = [("id", "Código", 80, "w", None), ("nombre", "Nombre", 260, "w", None),
               ("lat", "Latitud", 90, "e", _num(4)), ("lon", "Longitud", 90, "e", _num(4)),
               ("tarifa", "Tarifa (COP)", 120, "e", lambda v, _i: f"$ {es_num(v)}"),
               ("estado", "Estado", 120, "w", None)]

    def open_form(self, values, on_submit):
        return forms.toll_form(self.app, values, on_submit)

    def to_payload(self, values: dict) -> dict:
        return forms.numbers(values, ("lat", "lon", "tarifa"))


class RouteScreen(TableScreen):
    kind, noun, plural = "route", "la ruta", "Rutas"

    def __init__(self, parent: Any, app: Any):
        names = lambda cid, _i: app.city_name(cid)  # noqa: E731
        self.columns = [("id", "Código", 70, "w", None), ("origen", "Origen", 150, "w", names),
                        ("destino", "Destino", 150, "w", names), ("km", "Distancia", 100, "e", lambda v, _i: fmt_km(v)),
                        ("horas", "Tiempo", 80, "e", lambda v, _i: fmt_horas(v)),
                        ("peajes", "Peajes", 400, "w", lambda v, _i: self.toll_summary(v)),
                        ("combustible", "Combustible (COP)", 160, "e", lambda v, _i: f"$ {es_num(v)}"),
                        ("peajes_costo", "Peajes (COP)", 130, "e", lambda v, _i: f"$ {es_num(v)}"),
                        ("estado", "Estado", 190, "w", None)]
        super().__init__(parent, app)
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", pady=(8, 0))
        button(toolbar, "Ver peajes", self.show_tolls, app.fonts).pack(side="left")
        ctk.CTkLabel(toolbar, text="Selecciona una ruta y pulsa «Ver peajes» para ver todos sus peajes, IDs y tarifas.",
                     font=app.fonts["small"], text_color=theme.MUTED).pack(side="left", padx=10)

    def toll_summary(self, ids: list[str]) -> str:
        tolls = {t["id"]: t for t in self.app.data["toll"]}
        if not ids:
            return "—"
        names = [tolls[tid]["nombre"].removeprefix("Peaje ") if tid in tolls else tid for tid in ids]
        extra = f", +{len(names) - 2} más" if len(names) > 2 else ""
        return f"{len(ids)} · " + ", ".join(names[:2]) + extra

    def show_tolls(self) -> Any:
        route = self.selected()
        if not route:
            return
        dialog = ctk.CTkToplevel(self, fg_color=theme.PANEL)
        dialog.title("Peajes de la ruta")
        dialog.geometry("620x420")
        dialog.transient(self.app)
        title = f"{self.app.city_name(route['origen'])} → {self.app.city_name(route['destino'])} ({route['id']})"
        ctk.CTkLabel(dialog, text=title, font=self.app.fonts["h2"], text_color=theme.INK,
                     wraplength=570).pack(fill="x", padx=20, pady=(18, 8))
        details = ctk.CTkTextbox(dialog, font=self.app.fonts["body"], fg_color=theme.CARD,
                                 text_color=theme.INK, wrap="word")
        details.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        tolls = {t["id"]: t for t in self.app.data["toll"]}
        lines = []
        for tid in route.get("peajes", []):
            toll = tolls.get(tid)
            if toll is None:
                lines.append(f"{tid} · Información no disponible")
            else:
                inactive = " · Inactivo (no incluido en el costo)" if not toll.get("activo", True) else ""
                lines.append(f"{toll['nombre']} ({tid}) · $ {es_num(toll['tarifa'])} COP{inactive}")
        details.insert("1.0", "\n\n".join(lines) if lines else "Esta ruta no tiene peajes.")
        details.configure(state="disabled")
        ctk.CTkLabel(dialog, text=f"Costo de peajes activos: $ {es_num(route['peajes_costo'])} COP",
                     font=self.app.fonts["body"], text_color=theme.INK).pack(padx=20, pady=(0, 8))
        button(dialog, "Cerrar", dialog.destroy, self.app.fonts).pack(pady=(0, 16))
        return dialog

    stretch_columns = ("estado",)

    def open_form(self, values, on_submit):
        return forms.route_form(self.app, values, on_submit)

    def to_payload(self, values: dict) -> dict:
        return forms.numbers(values, ("km", "horas"))
