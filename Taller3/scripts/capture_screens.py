#!/usr/bin/env python3
"""Captura las pantallas reales de PAA para el README (docs/screenshots/), sobre una COPIA de los datos.

Abre la ventana REAL: exige una pantalla virtual declarada de forma explicita:
    PERA_VIRTUAL_DISPLAY=1 DISPLAY=<virtual> python3 scripts/capture_screens.py
Necesita CustomTkinter e ImageMagick (`import`).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "python"))
if os.environ.get("PERA_VIRTUAL_DISPLAY") != "1" or not os.environ.get("DISPLAY"):
    raise SystemExit("Se niega a abrir ventanas: declara una pantalla virtual con PERA_VIRTUAL_DISPLAY=1 y DISPLAY=<virtual>.")

from paa_backend import make_backend  # noqa: E402
from ui.app import App  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix="paa-shots-"))
data = work / "arbol_avl.txt"
shutil.copy(ROOT / "data" / "arbol_avl.txt", data)
App.startup_dialog = lambda self: None
backend, note = make_backend(False, None, data)
app = App(backend, note, data)
app.geometry("1280x780+0+0")
app.load_path(data)


def wait(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.05)


def snap(name: str) -> None:
    wait(0.4)
    subprocess.run(["import", "-window", hex(app.winfo_id()), str(OUT / f"{name}.png")], check=True)


def do(action: str, key: int, label: str = "") -> None:
    app.ops.key.delete(0, "end"); app.ops.key.insert(0, str(key))
    app.ops.label.delete(0, "end"); app.ops.label.insert(0, label)
    app.run_action(action)


snap("arbol")
do("insert", 5, "Nueva hoja")
wait(1.6); snap("rotacion")
app.player.finish_now(); snap("equilibrado")
do("insert", 55, "Sin rotación"); app.player.finish_now(); snap("insertar")
app.destroy()
shutil.rmtree(work, ignore_errors=True)
print("capturas en", OUT)
