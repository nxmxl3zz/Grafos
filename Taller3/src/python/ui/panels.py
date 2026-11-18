"""Paneles de la ventana: operaciones, animación, bitácora y recorridos."""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from . import theme


class Card(ctk.CTkFrame):
    def __init__(self, parent: Any, title: str, fonts: dict):
        super().__init__(parent, fg_color=theme.CARD, corner_radius=10)
        ctk.CTkLabel(self, text=title, font=fonts["h2"], text_color=theme.INK, anchor="w").pack(
            fill="x", padx=14, pady=(10, 6))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=14, pady=(0, 12))


def button(parent: Any, text: str, command: Callable[[], None], fonts: dict, primary: bool = False,
           danger: bool = False) -> ctk.CTkButton:
    fill = theme.ACCENT if primary else theme.DANGER if danger else theme.LINE
    hover = theme.ACCENT_HOVER if primary else "#c4443d" if danger else "#394659"
    return ctk.CTkButton(parent, text=text, command=command, font=fonts["body"], height=32,
                         fg_color=fill, hover_color=hover, text_color="#ffffff" if primary or danger else theme.INK)


class OperationsPanel(Card):
    """Clave, etiqueta y botones de operación."""

    def __init__(self, parent: Any, fonts: dict, run: Callable[[str], None]):
        super().__init__(parent, "Operaciones", fonts)
        self.key = ctk.CTkEntry(self.body, placeholder_text="Clave (entero)", font=fonts["body"], height=34)
        self.label = ctk.CTkEntry(self.body, placeholder_text="Etiqueta (texto)", font=fonts["body"], height=34)
        self.key.pack(fill="x", pady=(0, 6))
        self.label.pack(fill="x", pady=(0, 10))
        grid = ctk.CTkFrame(self.body, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1), weight=1, uniform="ops")
        actions = [("Insertar", "insert", dict(primary=True)), ("Eliminar", "delete", dict(danger=True)),
                   ("Buscar", "search", {}), ("Desactivar / Reactivar", "toggle", {}),
                   ("Modificar etiqueta", "update", {})]
        self.buttons = []
        for i, (text, action, style) in enumerate(actions):
            b = button(grid, text, lambda a=action: run(a), fonts, **style)
            b.grid(row=i // 2, column=i % 2, columnspan=2 if i == 3 or i == 4 else 1,
                   sticky="ew", padx=2, pady=2)
            self.buttons.append(b)
        for entry in (self.key, self.label):
            entry.bind("<Return>", lambda _e: run("insert"))

    def read(self) -> tuple[str, str]:
        return self.key.get().strip(), self.label.get().strip()

    def clear_key(self) -> None:
        self.key.delete(0, "end")
        self.key.focus_set()


class AnimationPanel(Card):
    """Velocidad, pausa y paso a paso."""

    def __init__(self, parent: Any, fonts: dict, on_speed: Callable[[float], None],
                 on_pause: Callable[[bool], None], on_next: Callable[[], None]):
        super().__init__(parent, "Animación", fonts)
        self.on_pause = on_pause
        self.speed_label = ctk.CTkLabel(self.body, text="Velocidad: 1,0x", font=fonts["small"],
                                        text_color=theme.MUTED, anchor="w")
        self.speed_label.pack(fill="x")
        self.slider = ctk.CTkSlider(self.body, from_=0.25, to=4.0, number_of_steps=15,
                                    progress_color=theme.ACCENT, button_color=theme.ACCENT,
                                    button_hover_color=theme.ACCENT_HOVER, command=self._speed)
        self.slider.set(1.0)
        self.slider.pack(fill="x", pady=(2, 10))
        self.on_speed = on_speed
        self.step_mode = ctk.CTkSwitch(self.body, text="Paso a paso", font=fonts["body"],
                                       progress_color=theme.ACCENT, command=self._changed)
        self.step_mode.pack(anchor="w", pady=(0, 8))
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x")
        row.grid_columnconfigure((0, 1), weight=1, uniform="anim")
        self.pause_button = button(row, "Pausa", self._toggle_pause, fonts)
        self.pause_button.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.next_button = button(row, "Siguiente paso", on_next, fonts)
        self.next_button.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        self._paused_by_user = False
        self.fonts = fonts

    def _speed(self, value: float) -> None:
        self.speed_label.configure(text=f"Velocidad: {value:.2f}x".replace(".", ","))
        self.on_speed(value)

    def _toggle_pause(self) -> None:
        self._paused_by_user = not self._paused_by_user
        self.pause_button.configure(text="Continuar" if self._paused_by_user else "Pausa")
        self._changed()

    def _changed(self) -> None:
        self.on_pause(self._paused_by_user or bool(self.step_mode.get()))


class LogPanel(Card):
    """Bitácora de pasos en español."""

    def __init__(self, parent: Any, fonts: dict):
        super().__init__(parent, "Bitácora", fonts)
        self.text = ctk.CTkTextbox(self.body, font=fonts["small"], fg_color=theme.BG, text_color=theme.INK,
                                   wrap="word", border_width=0)
        self.text.pack(fill="both", expand=True)
        for tag, color in (("rot", theme.WARN), ("ok", "#5be39a"), ("warn", "#ff8a80"),
                           ("info", theme.INK), ("head", theme.BLUE)):
            self.text.tag_config(tag, foreground=color)
        self.text.configure(state="disabled")

    def add(self, text: str, kind: str = "info") -> None:
        self.text.configure(state="normal")
        self.text.insert("end", text + "\n", kind)
        self.text.configure(state="disabled")
        self.text.see("end")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


class TraversalsPanel(ctk.CTkFrame):
    """Recorridos pre, in y post orden, siempre visibles."""

    NAMES = (("pre", "Preorden"), ("in", "Inorden"), ("post", "Postorden"))

    def __init__(self, parent: Any, fonts: dict):
        super().__init__(parent, fg_color=theme.CARD, corner_radius=10)
        self.grid_columnconfigure(1, weight=1)
        self.values: dict[str, ctk.CTkLabel] = {}
        for row, (key, name) in enumerate(self.NAMES):
            ctk.CTkLabel(self, text=name, font=fonts["h2"], text_color=theme.ACCENT, width=90,
                         anchor="w").grid(row=row, column=0, sticky="nw", padx=(14, 6), pady=4)
            label = ctk.CTkLabel(self, text="—", font=fonts["mono"], text_color=theme.INK, anchor="w",
                                 justify="left", wraplength=700)
            label.grid(row=row, column=1, sticky="ew", padx=(0, 14), pady=4)
            self.values[key] = label
        self.bind("<Configure>", lambda e: [v.configure(wraplength=max(e.width - 140, 200))
                                            for v in self.values.values()])

    def show(self, traversals: dict) -> None:
        for key, label in self.values.items():
            keys = traversals.get(key, [])
            label.configure(text="  ".join(str(k) for k in keys) if keys else "—")
