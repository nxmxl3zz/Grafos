"""Ventana principal de PERA: barra lateral, pantallas, menús y diálogo inicial."""

from __future__ import annotations

import hashlib
import json

from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
from typing import Any

import customtkinter as ctk

from . import forms, theme
from .dashboard import Dashboard
from .map_screen import MapScreen
from .query_screen import QueryScreen
from .table_screen import CityScreen, RouteScreen, TollScreen, apply_tree_style
from .widgets import button, make_fonts

NAV = (("dashboard", "Resumen"), ("city", "Ciudades"), ("toll", "Peajes"), ("route", "Rutas"),
       ("query", "Consulta"), ("map", "Mapa"))


class App(ctk.CTk):
    def __init__(self, backend: Any, note: str, data_path: Path):
        super().__init__()
        self.backend, self.data_path = backend, data_path
        self.bundled_access_valid = False
        ctk.set_appearance_mode("dark")
        self.title("PERA — Rutas entre ciudades de Colombia")
        self.geometry("1360x820")
        self.minsize(1180, 700)
        self.configure(fg_color=theme.BG)
        self.fonts = make_fonts(self)
        apply_tree_style(self, self.fonts["family"])
        self.data: dict[str, list[dict]] = {"city": [], "toll": [], "route": []}
        self.names: dict[str, str] = {}
        self.params: dict = {}
        self.last_query: dict | None = None
        self.dirty = False
        self.current = ""
        self._build_menu()
        self._build_layout(note)
        self.protocol("WM_DELETE_WINDOW", self.close)
        for sequence, command in (("<Control-s>", self.save_file), ("<Control-o>", self.open_file),
                                  ("<Control-n>", self.new_data)):
            self.bind(sequence, lambda _e, c=command: c())
        self.bind("<Control-z>", self._ctrl_z)
        self.reload()
        self.show("dashboard")
        self.set_status("Listo")
        self.after(150, self.startup_dialog)

    # ---- construcción -------------------------------------------------
    def _menu(self, parent: tk.Menu | None = None) -> tk.Menu:
        return tk.Menu(parent, tearoff=0, bg=theme.PANEL, fg=theme.INK, activebackground=theme.ACCENT, bd=0)

    def _build_menu(self) -> None:
        menubar = self._menu(self)
        file = self._menu(menubar)
        file.add_command(label="Nuevo (vacío)", accelerator="Ctrl+N", command=self.new_data)
        file.add_command(label="Abrir…", accelerator="Ctrl+O", command=self.open_file)
        file.add_command(label="Guardar…", accelerator="Ctrl+S", command=self.save_file)
        file.add_separator()
        file.add_command(label="Salir", command=self.close)
        menubar.add_cascade(label="Archivo", menu=file)
        edit = self._menu(menubar)
        edit.add_command(label="Deshacer", accelerator="Ctrl+Z", command=self.undo)
        edit.add_command(label="Parámetros de combustible…", command=self.edit_params)
        menubar.add_cascade(label="Editar", menu=edit)
        self.configure(menu=menubar)

    def _build_layout(self, note: str) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        side = ctk.CTkFrame(self, fg_color=theme.PANEL, corner_radius=0, width=210)
        side.grid(row=0, column=0, rowspan=2, sticky="ns")
        side.grid_propagate(False)
        ctk.CTkLabel(side, text="PERA", font=self.fonts["kpi"], text_color=theme.ACCENT, anchor="w").pack(
            fill="x", padx=18, pady=(18, 0))
        ctk.CTkLabel(side, text="Rutas entre ciudades", font=self.fonts["small"], text_color=theme.MUTED,
                     anchor="w").pack(fill="x", padx=18, pady=(0, 16))
        self.nav: dict[str, ctk.CTkButton] = {}
        for key, label in NAV:
            self.nav[key] = ctk.CTkButton(side, text=label, anchor="w", height=38, font=self.fonts["body"],
                                          fg_color="transparent", hover_color=theme.LINE, text_color=theme.INK,
                                          corner_radius=8, command=lambda k=key: self.show(k))
            self.nav[key].pack(fill="x", padx=10, pady=2)
        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=10, pady=12)
        self.params_label = ctk.CTkLabel(bottom, text="", font=self.fonts["small"], text_color=theme.MUTED,
                                         anchor="w", justify="left")
        self.params_label.pack(fill="x", padx=4, pady=(0, 6))
        button(bottom, "Parámetros…", self.edit_params, self.fonts).pack(fill="x")
        ctk.CTkLabel(bottom, text=f"Motor: {self.backend.name}", font=self.fonts["small"], text_color=theme.MUTED,
                     anchor="w").pack(fill="x", padx=4, pady=(8, 0))

        host = ctk.CTkFrame(self, fg_color="transparent")
        host.grid(row=0, column=1, sticky="nsew", padx=14, pady=(12, 4))
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(0, weight=1)
        self.screens: dict[str, Any] = {
            "dashboard": Dashboard(host, self), "city": CityScreen(host, self), "toll": TollScreen(host, self),
            "route": RouteScreen(host, self), "query": QueryScreen(host, self), "map": MapScreen(host, self)}
        for screen in self.screens.values():
            screen.grid(row=0, column=0, sticky="nsew")
        self.status = ctk.CTkLabel(self, text=note, font=self.fonts["small"], text_color=theme.WARN if note else
                                   theme.MUTED, anchor="w")
        self.status.grid(row=1, column=1, sticky="ew", padx=16, pady=(0, 8))

    # ---- motor y datos -----------------------------------------------
    def api(self, payload: dict) -> dict | None:
        """Envía una solicitud y devuelve la respuesta completa (o None si el motor falla)."""
        try:
            response = self.backend.request(payload)
        except Exception as error:  # el motor C++ puede morir; no se cierra la ventana
            messagebox.showerror("Motor", f"Error del motor: {error}")
            return None
        if response.get("ok") and payload.get("action") in {"add", "create", "update", "delete", "toggle", "set_params", "undo", "reset", "load"}:
            self.last_query = None
            self.bundled_access_valid = False
        self._mark(response)
        if response.get("ok") and payload.get("action") in {"load", "reset", "create", "update", "delete", "toggle", "undo", "set_params"}:
            query_screen = self.screens.get("query") if hasattr(self, "screens") else None
            if query_screen and hasattr(query_screen, "local"):
                query_screen.local.invalidate()
        return response

    def _mark(self, response: dict) -> None:
        state = response.get("state") or {}
        self.dirty = bool(state.get("dirty", self.dirty))
        counts = f" ({state['ciudades']} ciudades, {state['rutas']} rutas)" if "ciudades" in state else ""
        self.title("PERA — Rutas de Colombia" + counts + (" *" if self.dirty else ""))

    def set_status(self, text: str, error: bool = False) -> None:
        self.status.configure(text=text, text_color=theme.DANGER if error else theme.MUTED)

    def city_name(self, city_id: str) -> str:
        return self.names.get(city_id, city_id)

    def reload(self) -> None:
        """Vuelve a leer ciudades, peajes, rutas y parámetros del motor y refresca la pantalla visible."""
        for kind in self.data:
            response = self.api({"action": "list", "kind": kind})
            if response and response.get("ok"):
                self.data[kind] = response["result"]["items"]
        self.names = {c["id"]: c["nombre"] for c in self.data["city"]}
        response = self.api({"action": "params"})
        if response and response.get("ok"):
            self.params = response["result"]
            p = self.params
            self.params_label.configure(text=f"{p['consumo_km_gal']} km/gal · ${int(p['precio_gal']):,} /gal".replace(",", "."))
        if self.current:
            self.screens[self.current].refresh()

    def show(self, key: str) -> None:
        self.current = key
        for name, button_ in self.nav.items():
            button_.configure(fg_color=theme.ACCENT if name == key else "transparent",
                              text_color="#ffffff" if name == key else theme.INK)
        self.screens[key].tkraise()
        self.screens[key].refresh()

    # ---- edición -----------------------------------------------------
    def _ctrl_z(self, event: Any) -> str | None:
        if isinstance(event.widget, (tk.Entry, tk.Text)) or "entry" in str(event.widget).lower():
            return None  # Ctrl+Z dentro de un campo de texto lo maneja el propio campo
        self.undo()
        return "break"

    def undo(self) -> None:
        response = self.api({"action": "undo"})
        if not response:
            return
        if not response.get("ok"):
            self.set_status(response.get("error", "No hay nada que deshacer"), error=True)
            return
        self.reload()
        self.set_status("Última acción deshecha")

    def edit_params(self):
        def submit(values: dict) -> str | None:
            payload = {"action": "set_params", **forms.numbers(values, tuple(values))}
            response = self.api(payload)
            if response is None:
                return "No se pudo hablar con el motor."
            if not response.get("ok"):
                return response.get("error", "Error desconocido")
            self.last_query = None  # los costos cambiaron: la consulta anterior ya no vale
            self.reload()
            self.set_status("Parámetros actualizados.")
            return None
        return forms.params_form(self, {k: self.params.get(k, "") for k in
                                        ("consumo_km_gal", "precio_gal", "velocidad_kmh")}, submit)

    # ---- archivo -----------------------------------------------------
    def confirm_discard(self) -> bool:
        return not self.dirty or messagebox.askyesno("Cambios sin guardar", "Hay cambios sin guardar. ¿Descartarlos?")

    def new_data(self) -> None:
        if not self.confirm_discard():
            return
        response = self.api({"action": "reset"})
        if response and response.get("ok"):
            self.last_query = None
            self.reload()
            self.set_status("Datos nuevos (vacíos).")

    def load_path(self, path: Path) -> bool:
        response = self.api({"action": "load", "path": str(path)})
        if not response:
            return False
        if not response.get("ok"):
            messagebox.showerror("Abrir", response.get("error", "No se pudo abrir el archivo."))
            return False
        self.last_query = None
        bundled = Path(__file__).resolve().parents[3] / "data" / "pera_colombia.csv"
        try:
            metadata = json.loads((bundled.parent / "access_research.json").read_text(encoding="utf-8"))
            self.bundled_access_valid = (Path(path).resolve() == bundled.resolve() and
                                         hashlib.sha256(bundled.read_bytes()).hexdigest() == metadata["csv_sha256"])
        except (OSError, ValueError, KeyError, TypeError):
            self.bundled_access_valid = False
        self.reload()
        self.set_status(f"Archivo cargado: {path.name}")
        return True

    def open_file(self) -> None:
        if not self.confirm_discard():
            return
        path = filedialog.askopenfilename(title="Abrir datos", filetypes=[("Datos PERA", "*.csv"), ("Todos", "*")],
                                          initialdir=str(self.data_path.parent))
        if path:
            self.load_path(Path(path))

    def save_file(self) -> None:
        path = filedialog.asksaveasfilename(title="Guardar datos", defaultextension=".csv",
                                            initialfile=self.data_path.name, initialdir=str(self.data_path.parent),
                                            filetypes=[("Datos PERA", "*.csv")])
        if not path:
            return
        response = self.api({"action": "save", "path": path})
        if response and response.get("ok"):
            bundled = Path(__file__).resolve().parents[3] / "data" / "pera_colombia.csv"
            if Path(path).resolve() != bundled.resolve():
                self.bundled_access_valid = False
            self.set_status(f"Guardado en {Path(path).name}")
        elif response:
            messagebox.showerror("Guardar", response.get("error", "No se pudo guardar."))

    # ---- inicio y cierre ---------------------------------------------
    def startup_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self, fg_color=theme.PANEL)
        dialog.title("Bienvenido a PERA")
        dialog.geometry("440x220")
        dialog.resizable(False, False)
        dialog.transient(self)
        ctk.CTkLabel(dialog, text="¿Cómo quieres empezar?", font=self.fonts["h1"], text_color=theme.INK).pack(
            pady=(22, 4))
        ctk.CTkLabel(dialog, text=f"Datos guardados: {self.data_path.name}", font=self.fonts["small"],
                     text_color=theme.MUTED).pack(pady=(0, 16))

        def choose(load: bool) -> None:
            dialog.destroy()
            if not load:
                return
            if not self.data_path.is_file():
                self.set_status(f"No existe {self.data_path.name}; se empieza vacío.", error=True)
            else:
                self.load_path(self.data_path)

        button(dialog, "Cargar datos", lambda: choose(True), self.fonts, primary=True).pack(fill="x", padx=40, pady=4)
        button(dialog, "Empezar vacío", lambda: choose(False), self.fonts).pack(fill="x", padx=40, pady=4)
        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(False))
        dialog.after(120, lambda: (dialog.grab_set(), dialog.focus_set()))

    def close(self) -> None:
        if not self.confirm_discard():
            return
        self.backend.close()
        self.destroy()
