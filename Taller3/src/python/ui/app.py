"""Ventana principal de PAA."""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from . import theme
from .panels import AnimationPanel, LogPanel, OperationsPanel, TraversalsPanel, button
from .player import Player
from .steps_text import describe, highlight_of
from .tree_canvas import TreeCanvas

INT_MIN, INT_MAX = -2**31, 2**31 - 1


def traversals_of(node: dict | None) -> dict:
    """Recorridos de un snapshot (para mostrarlos en cada paso de la animación)."""
    pre: list[int] = []
    ino: list[int] = []
    post: list[int] = []

    def walk(n: dict | None) -> None:
        if not n:
            return
        pre.append(n["k"])
        walk(n.get("L"))
        ino.append(n["k"])
        walk(n.get("R"))
        post.append(n["k"])

    walk(node)
    return {"pre": pre, "in": ino, "post": post}
ACTION_TITLES = {"insert": "Insertar", "delete": "Eliminar", "search": "Buscar",
                 "toggle": "Desactivar / Reactivar", "update": "Modificar etiqueta"}


class App(ctk.CTk):
    def __init__(self, backend: Any, note: str, data_path: Path):
        super().__init__()
        self.backend, self.data_path = backend, data_path
        ctk.set_appearance_mode("dark")
        self.title("PAA — Programa de Aprendizaje de Árboles AVL")
        self.geometry("1280x780")
        self.minsize(1100, 680)
        self.configure(fg_color=theme.BG)
        family = theme.pick_family(self)
        self.fonts = {
            "h1": ctk.CTkFont(family=family, size=20, weight="bold"),
            "h2": ctk.CTkFont(family=family, size=14, weight="bold"),
            "body": ctk.CTkFont(family=family, size=13),
            "small": ctk.CTkFont(family=family, size=12),
            "mono": ctk.CTkFont(family="DejaVu Sans Mono", size=13),
        }
        self.final_tree: dict | None = None
        self.final_traversals: dict = {}
        self.dirty = False
        self._build_menu()
        self._build_layout(family)
        self.player = Player(self, self._on_step, self._on_skip, self._on_done)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Control-s>", lambda _e: self.save_file())
        self.bind("<Control-o>", lambda _e: self.open_file())
        self.bind("<Control-n>", lambda _e: self.new_tree())
        self.bind("<Control-z>", lambda _e: self.undo())
        self.log.add(f"Motor: {backend.name}", "head")
        if note:
            self.log.add(note, "warn")
        self.set_status("Listo")
        self.after(150, self.startup_dialog)

    # ---- construcción -------------------------------------------------
    def _build_menu(self) -> None:
        import tkinter as tk
        menubar = tk.Menu(self, bg=theme.PANEL, fg=theme.INK, activebackground=theme.ACCENT, bd=0)
        menu = tk.Menu(menubar, tearoff=0, bg=theme.PANEL, fg=theme.INK, activebackground=theme.ACCENT)
        menu.add_command(label="Nuevo", accelerator="Ctrl+N", command=self.new_tree)
        menu.add_command(label="Abrir…", accelerator="Ctrl+O", command=self.open_file)
        menu.add_command(label="Guardar…", accelerator="Ctrl+S", command=self.save_file)
        menu.add_separator()
        menu.add_command(label="Salir", command=self.close)
        menubar.add_cascade(label="Archivo", menu=menu)
        edit = tk.Menu(menubar, tearoff=0, bg=theme.PANEL, fg=theme.INK, activebackground=theme.ACCENT)
        edit.add_command(label="Deshacer", accelerator="Ctrl+Z", command=self.undo)
        menubar.add_cascade(label="Editar", menu=edit)
        self.configure(menu=menubar)

    def _build_layout(self, family: str) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(self, fg_color="transparent", width=290)
        left.grid(row=0, column=0, sticky="ns", padx=(12, 6), pady=12)
        ctk.CTkLabel(left, text="PAA · Árboles AVL", font=self.fonts["h1"], text_color=theme.INK,
                     anchor="w").pack(fill="x", pady=(0, 10))
        self.ops = OperationsPanel(left, self.fonts, self.run_action)
        self.ops.pack(fill="x", pady=(0, 10))
        self.anim = AnimationPanel(left, self.fonts, self._set_speed, self._set_paused,
                                   lambda: self.player.advance())
        self.anim.pack(fill="x")
        self.status = ctk.CTkLabel(left, text="", font=self.fonts["small"], text_color=theme.MUTED,
                                   anchor="w", justify="left", wraplength=270)
        self.status.pack(fill="x", pady=(12, 0))

        center = ctk.CTkFrame(self, fg_color="transparent")
        center.grid(row=0, column=1, sticky="nsew", padx=6, pady=12)
        center.grid_columnconfigure(0, weight=1)
        center.grid_rowconfigure(0, weight=1)
        frame = ctk.CTkFrame(center, fg_color=theme.PANEL, corner_radius=10)
        frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.canvas = TreeCanvas(frame, family)
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self.traversals = TraversalsPanel(center, self.fonts)
        self.traversals.grid(row=1, column=0, sticky="ew")

        self.log = LogPanel(self, self.fonts)
        self.log.grid(row=0, column=2, sticky="ns", padx=(6, 12), pady=12)
        self.log.configure(width=330)
        self.log.grid_propagate(False)

    # ---- motor -------------------------------------------------------
    def request(self, payload: dict) -> dict | None:
        try:
            return self.backend.request(payload)
        except Exception as error:  # el motor C++ puede morir; no se cierra la ventana
            messagebox.showerror("Motor", f"Error del motor: {error}")
            return None

    def set_status(self, text: str, error: bool = False) -> None:
        self.status.configure(text=text, text_color=theme.DANGER if error else theme.MUTED)

    def _mark(self, response: dict) -> None:
        state = response.get("state") or {}
        self.dirty = bool(state.get("dirty", self.dirty))
        size = state.get("size")
        suffix = " *" if self.dirty else ""
        self.title("PAA — Árboles AVL" + (f" ({size} nodos)" if size is not None else "") + suffix)

    # ---- operaciones -------------------------------------------------
    def run_action(self, action: str) -> None:
        raw_key, label = self.ops.read()
        try:
            key = int(raw_key)
            if not INT_MIN <= key <= INT_MAX:
                raise ValueError
        except ValueError:
            self.set_status("La clave debe ser un entero de 32 bits.", error=True)
            self.ops.key.focus_set()
            return
        if action in ("insert", "update") and not label and action == "update":
            self.set_status("Escribe la nueva etiqueta.", error=True)
            return
        payload: dict[str, Any] = {"action": action, "key": key}
        if action in ("insert", "update"):
            payload["label"] = label
        self.player.finish_now()
        response = self.request(payload)
        if response is None:
            return
        self.log.add(f"▶ {ACTION_TITLES[action]} {key}", "head")
        self._mark(response)
        if not response.get("ok"):
            error = response.get("error", "error desconocido")
            self.log.add(error, "warn")
            self.set_status(error, error=True)
            return
        self.set_status(ACTION_TITLES[action] + ": en curso…")
        self.final_tree = response.get("tree")
        self.final_traversals = response.get("traversals", {})
        self.ops.clear_key()
        self.player.play(response.get("steps", []))

    # ---- animación ---------------------------------------------------
    def _set_speed(self, value: float) -> None:
        self.player.speed = value

    def _set_paused(self, value: bool) -> None:
        self.player.set_paused(value)
        if value and self.player.running:
            self.set_status("En pausa: pulsa «Siguiente paso».")

    def _on_step(self, step: dict, ms: int) -> None:
        text, kind = describe(step)
        self.log.add("  " + text, kind)
        self.canvas.show(step.get("tree"), highlight_of(step), ms)
        self.traversals.show(traversals_of(step.get("tree")))

    def _on_skip(self, step: dict) -> None:
        self.log.add("  " + describe(step)[0], describe(step)[1])
        self.traversals.show(traversals_of(step.get("tree")))

    def _on_done(self) -> None:
        self.canvas.show(self.final_tree, {}, 250)
        self.traversals.show(self.final_traversals)
        self.set_status("Listo")

    def show_state(self, response: dict) -> None:
        """Muestra de golpe el árbol de una respuesta (abrir, nuevo, cargar)."""
        self.player.finish_now()
        self.final_tree = response.get("tree")
        self.final_traversals = response.get("traversals", {})
        self.canvas.pos = {}
        self.canvas.show(self.final_tree)
        self.traversals.show(self.final_traversals)
        self._mark(response)

    def undo(self) -> None:
        self.player.finish_now()
        response = self.request({"action": "undo"})
        if not response:
            return
        if not response.get("ok"):
            self.set_status(response.get("error", "Nada que deshacer"), error=True)
            return
        self.show_state(response)
        self.log.add("↶ Deshacer", "head")
        self.set_status("Última operación deshecha")

    # ---- archivo -----------------------------------------------------
    def confirm_discard(self) -> bool:
        return not self.dirty or messagebox.askyesno("Cambios sin guardar", "Hay cambios sin guardar. ¿Descartarlos?")

    def new_tree(self) -> None:
        if not self.confirm_discard():
            return
        response = self.request({"action": "reset"})
        if response and response.get("ok"):
            self.show_state(response)
            self.log.clear()
            self.log.add("Árbol nuevo (vacío)", "head")

    def load_path(self, path: Path) -> bool:
        response = self.request({"action": "load", "path": str(path)})
        if not response:
            return False
        if not response.get("ok"):
            messagebox.showerror("Abrir", response.get("error", "No se pudo abrir el archivo."))
            return False
        self.show_state(response)
        self.log.add(f"Archivo cargado: {path.name}", "head")
        return True

    def open_file(self) -> None:
        if not self.confirm_discard():
            return
        path = filedialog.askopenfilename(title="Abrir árbol", filetypes=[("Árbol AVL", "*.txt"), ("Todos", "*")],
                                          initialdir=str(self.data_path.parent))
        if path:
            self.load_path(Path(path))

    def save_file(self) -> None:
        path = filedialog.asksaveasfilename(title="Guardar árbol", defaultextension=".txt",
                                            initialfile=self.data_path.name,
                                            initialdir=str(self.data_path.parent),
                                            filetypes=[("Árbol AVL", "*.txt")])
        if not path:
            return
        response = self.request({"action": "save", "path": path})
        if response and response.get("ok"):
            self._mark(response)
            self.log.add(f"Guardado en {Path(path).name}", "ok")
        elif response:
            messagebox.showerror("Guardar", response.get("error", "No se pudo guardar."))

    # ---- inicio y cierre ---------------------------------------------
    def startup_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self, fg_color=theme.PANEL)
        dialog.title("Bienvenido a PAA")
        dialog.geometry("420x210")
        dialog.resizable(False, False)
        dialog.transient(self)
        ctk.CTkLabel(dialog, text="¿Cómo quieres empezar?", font=self.fonts["h1"], text_color=theme.INK).pack(pady=(22, 4))
        ctk.CTkLabel(dialog, text=f"Datos guardados: {self.data_path.name}", font=self.fonts["small"],
                     text_color=theme.MUTED).pack(pady=(0, 16))

        def choose(load: bool) -> None:
            dialog.destroy()
            if load:
                if not self.data_path.is_file():
                    self.set_status(f"No existe {self.data_path.name}; se empieza vacío.", error=True)
                else:
                    self.load_path(self.data_path)
            self.ops.key.focus_set()

        button(dialog, "Cargar datos", lambda: choose(True), self.fonts, primary=True).pack(fill="x", padx=40, pady=4)
        button(dialog, "Empezar vacío", lambda: choose(False), self.fonts).pack(fill="x", padx=40, pady=4)
        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(False))
        dialog.after(120, lambda: (dialog.grab_set(), dialog.focus_set()))

    def close(self) -> None:
        if not self.confirm_discard():
            return
        self.backend.close()
        self.destroy()
