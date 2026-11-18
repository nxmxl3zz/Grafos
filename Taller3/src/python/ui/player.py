"""Reproductor de pasos: temporizador, pausa, paso a paso y salto al final."""

from __future__ import annotations

from typing import Any, Callable

BASE_DELAY_MS = 900


class Player:
    """Reproduce una lista de pasos llamando a `on_step(step, ms)`; al final, `on_done()`."""

    def __init__(self, widget: Any, on_step: Callable[[dict, int], None],
                 on_skip: Callable[[dict], None], on_done: Callable[[], None]):
        self.widget, self.on_step, self.on_skip, self.on_done = widget, on_step, on_skip, on_done
        self.steps: list[dict] = []
        self.index = 0
        self.speed = 1.0
        self.paused = False       # pausa o modo paso a paso: espera "Siguiente"
        self.running = False
        self._job: str | None = None

    @property
    def delay(self) -> int:
        return int(BASE_DELAY_MS / self.speed)

    def play(self, steps: list[dict]) -> None:
        self.finish_now()
        self.steps, self.index, self.running = list(steps), 0, True
        if not self.paused:
            self._tick()

    def advance(self) -> None:
        """Un paso manual (con pausa o paso a paso)."""
        if self.running:
            self._cancel()
            self._tick()

    def set_paused(self, value: bool) -> None:
        self.paused = value
        if not value and self.running and self._job is None:
            self._schedule()
        elif value:
            self._cancel()

    def finish_now(self) -> None:
        """Termina de inmediato la animación en curso (registra los pasos que faltan)."""
        if not self.running:
            return
        self._cancel()
        for step in self.steps[self.index:]:
            self.on_skip(step)
        self.running = False
        self.on_done()

    def _cancel(self) -> None:
        if self._job is not None:
            self.widget.after_cancel(self._job)
            self._job = None

    def _schedule(self) -> None:
        self._job = self.widget.after(self.delay, self._tick)

    def _tick(self) -> None:
        self._job = None
        if self.index >= len(self.steps):
            self.running = False
            self.on_done()
            return
        step = self.steps[self.index]
        self.index += 1
        self.on_step(step, int(min(420, self.delay * 0.55)))
        if not self.paused:
            self._schedule()
