"""Formularios modales: ciudad, peaje, ruta y parámetros. El motor valida; aquí solo se muestra su mensaje."""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from . import theme
from .format import es_num, to_number
from .widgets import CitySelector, button


class EntryField(ctk.CTkEntry):
    def __init__(self, parent: Any, fonts: dict, readonly: bool = False, **_: Any):
        super().__init__(parent, font=fonts["body"], height=34, fg_color=theme.BG, border_color=theme.LINE)
        self.readonly = readonly

    def get_value(self) -> str:
        return self.get().strip()

    def set_value(self, value: Any) -> None:
        self.configure(state="normal")
        self.delete(0, "end")
        self.insert(0, "" if value is None else str(value))
        if self.readonly:
            self.configure(state="disabled")


class CityField(CitySelector):
    def get_value(self) -> str:
        return self.city_id() or ""

    def set_value(self, value: Any) -> None:
        self.select(str(value))


class TollPicker(ctk.CTkFrame):
    """Selección múltiple de peajes con búsqueda; conserva el orden en que se marcan."""

    def __init__(self, parent: Any, fonts: dict, tolls: list[dict], **_: Any):
        super().__init__(parent, fg_color="transparent")
        self.fonts, self.tolls = fonts, tolls
        self.selected: list[str] = []
        self.search = ctk.CTkEntry(self, font=fonts["body"], height=30, fg_color=theme.BG,
                                   border_color=theme.LINE, placeholder_text="Buscar peaje…")
        self.search.pack(fill="x", pady=(0, 4))
        self.search.bind("<KeyRelease>", lambda _e: self._render())
        self.box = ctk.CTkScrollableFrame(self, fg_color=theme.BG, height=130, corner_radius=6)
        self.box.pack(fill="both", expand=True)
        self.summary = ctk.CTkLabel(self, text="", font=fonts["small"], text_color=theme.MUTED, anchor="w")
        self.summary.pack(fill="x", pady=(4, 0))
        self.vars: dict[str, ctk.BooleanVar] = {}
        self._render()

    def _toggle(self, toll_id: str) -> None:
        on = self.vars[toll_id].get()
        if on and toll_id not in self.selected:
            self.selected.append(toll_id)
        elif not on and toll_id in self.selected:
            self.selected.remove(toll_id)
        self._summary()

    def _summary(self) -> None:
        self.summary.configure(text=f"Seleccionados: {', '.join(self.selected) or 'ninguno'}")

    def _render(self) -> None:
        for child in self.box.winfo_children():
            child.destroy()
        needle = self.search.get().strip().lower()
        self.vars = {}
        for toll in self.tolls:
            if needle and needle not in f"{toll['id']} {toll['nombre']}".lower():
                continue
            var = ctk.BooleanVar(value=toll["id"] in self.selected)
            self.vars[toll["id"]] = var
            suffix = "" if toll.get("activo", True) else " (inactivo)"
            ctk.CTkCheckBox(self.box, text=f"{toll['id']} · {toll['nombre']} · $ {es_num(toll['tarifa'])}{suffix}",
                            variable=var, font=self.fonts["small"], fg_color=theme.ACCENT,
                            hover_color=theme.ACCENT_HOVER, command=lambda i=toll["id"]: self._toggle(i)
                            ).pack(anchor="w", pady=2)
        self._summary()

    def get_value(self) -> str:
        return "|".join(self.selected)

    def set_value(self, value: Any) -> None:
        ids = value if isinstance(value, list) else [v for v in str(value).split("|") if v]
        self.selected = list(ids)
        self._render()


# (clave, etiqueta, clase de campo, opciones)
Spec = tuple[str, str, type, dict]


class FormDialog(ctk.CTkToplevel):
    """Ventana modal con campos. `on_submit(valores)` devuelve un mensaje de error o None si salió bien."""

    def __init__(self, app: Any, title: str, specs: list[Spec], on_submit: Callable[[dict], str | None],
                 values: dict | None = None, height: int | None = None, show: bool = True):
        super().__init__(app, fg_color=theme.PANEL)
        self.app, self.on_submit = app, on_submit
        self.title(title)
        self.resizable(False, False)
        self.transient(app)
        fonts = app.fonts
        ctk.CTkLabel(self, text=title, font=fonts["h1"], text_color=theme.INK, anchor="w").pack(
            fill="x", padx=24, pady=(18, 8))
        self.fields: dict[str, Any] = {}
        for key, label, cls, options in specs:
            ctk.CTkLabel(self, text=label, font=fonts["small"], text_color=theme.MUTED, anchor="w").pack(
                fill="x", padx=24, pady=(6, 0))
            field = cls(self, fonts, **options)
            field.pack(fill="x", padx=24)
            self.fields[key] = field
        for key, value in (values or {}).items():
            if key in self.fields:
                self.fields[key].set_value(value)
        self.error = ctk.CTkLabel(self, text="", font=fonts["small"], text_color=theme.DANGER, anchor="w",
                                  justify="left", wraplength=380)
        self.error.pack(fill="x", padx=24, pady=(8, 0))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(8, 18))
        row.grid_columnconfigure((0, 1), weight=1, uniform="f")
        button(row, "Cancelar", self.destroy, fonts).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        button(row, "Guardar", self.submit, fonts, primary=True).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.bind("<Return>", lambda _e: self.submit())
        self.bind("<Escape>", lambda _e: self.destroy())
        if show:
            self.after(120, self._modal)

    def _modal(self) -> None:
        try:
            self.grab_set()
            self.focus_set()
        except Exception:  # la ventana pudo cerrarse antes
            pass

    def values(self) -> dict:
        return {key: field.get_value() for key, field in self.fields.items()}

    def submit(self) -> bool:
        message = self.on_submit(self.values())
        if message:
            self.error.configure(text=message)
            return False
        self.destroy()
        return True


def city_form(app: Any, values: dict | None, on_submit: Callable[[dict], str | None]) -> FormDialog:
    editing = values is not None
    specs: list[Spec] = [
        ("id", "Código DANE (5 dígitos)", EntryField, {"readonly": editing}),
        ("nombre", "Nombre", EntryField, {}),
        ("departamento", "Departamento", EntryField, {}),
        ("lat", "Latitud (grados)", EntryField, {}),
        ("lon", "Longitud (grados)", EntryField, {}),
    ]
    return FormDialog(app, "Editar ciudad" if editing else "Nueva ciudad", specs, on_submit, values)


def toll_form(app: Any, values: dict | None, on_submit: Callable[[dict], str | None]) -> FormDialog:
    editing = values is not None
    specs: list[Spec] = [
        ("id", "Código (vacío = automático)", EntryField, {"readonly": editing}),
        ("nombre", "Nombre", EntryField, {}),
        ("lat", "Latitud (grados)", EntryField, {}),
        ("lon", "Longitud (grados)", EntryField, {}),
        ("tarifa", "Tarifa categoría I (COP)", EntryField, {}),
    ]
    return FormDialog(app, "Editar peaje" if editing else "Nuevo peaje", specs, on_submit, values)


def route_form(app: Any, values: dict | None, on_submit: Callable[[dict], str | None]) -> FormDialog:
    editing = values is not None
    cities = app.data["city"]
    specs: list[Spec] = [
        ("origen", "Ciudad de origen", CityField, {"cities": cities}),
        ("destino", "Ciudad de destino", CityField, {"cities": cities}),
        ("km", "Distancia (km)", EntryField, {}),
        ("horas", "Duración (horas, p. ej. 2,75)", EntryField, {}),
        ("peajes", "Peajes en la ruta", TollPicker, {"tolls": app.data["toll"]}),
    ]
    return FormDialog(app, "Editar ruta" if editing else "Nueva ruta", specs, on_submit, values)


# Consumo típico en km por galón (valores de referencia, editables). Los peajes del modelo son de categoría I (automóvil).
VEHICLE_PRESETS = {"Automóvil pequeño (50 km/gal)": 50, "Automóvil mediano (40 km/gal)": 40,
                   "Camioneta / SUV (28 km/gal)": 28, "Campero o pickup diésel pesado (20 km/gal)": 20}


def params_form(app: Any, values: dict, on_submit: Callable[[dict], str | None]) -> FormDialog:
    specs: list[Spec] = [
        ("consumo_km_gal", "Consumo (km por galón)", EntryField, {}),
        ("precio_gal", "Precio del galón (COP)", EntryField, {}),
        ("velocidad_kmh", "Velocidad por defecto (km/h)", EntryField, {}),
    ]
    dialog = FormDialog(app, "Parámetros de combustible", specs, on_submit, values)
    first = dialog.winfo_children()[1]   # primer campo del formulario: el selector va antes
    preset = ctk.CTkComboBox(dialog, values=list(VEHICLE_PRESETS), font=app.fonts["body"], state="readonly",
                             dropdown_font=app.fonts["body"], height=34, fg_color=theme.BG, border_color=theme.LINE,
                             button_color=theme.LINE, dropdown_fg_color=theme.PANEL,
                             command=lambda name: dialog.fields["consumo_km_gal"].set_value(VEHICLE_PRESETS[name]))
    preset.set("Elegir tipo de vehículo (rellena el consumo)")
    ctk.CTkLabel(dialog, text="Vehículo de referencia · los peajes del modelo son de categoría I (automóvil)",
                 font=app.fonts["small"], text_color=theme.MUTED, anchor="w").pack(fill="x", padx=24, pady=(6, 0), before=first)
    preset.pack(fill="x", padx=24, before=first)
    return dialog


def numbers(values: dict, keys: tuple[str, ...]) -> dict:
    """Copia de `values` con las claves numéricas convertidas (acepta coma decimal)."""
    out = dict(values)
    for key in keys:
        if key in out:
            out[key] = to_number(out[key])
    return out
