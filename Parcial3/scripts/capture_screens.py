#!/usr/bin/env python3
"""Captura las pantallas reales de la ventana para la documentacion (docs/screenshots/).

Abre la ventana REAL, por eso exige una pantalla virtual declarada de forma explicita:
    PERA_VIRTUAL_DISPLAY=1 DISPLAY=<virtual> .venv/bin/python scripts/capture_screens.py
Necesita ImageMagick (`import`) y, para la consulta de localidades, internet (o una respuesta guardada).
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "python"))
if os.environ.get("PERA_VIRTUAL_DISPLAY") != "1" or not os.environ.get("DISPLAY"):
    raise SystemExit("Se niega a abrir ventanas: declara una pantalla virtual con PERA_VIRTUAL_DISPLAY=1 y DISPLAY=<virtual>.")

from pera_backend import PythonBackend  # noqa: E402
from ui.app import App  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
DATA = ROOT / "data" / "pera_colombia.csv"
app = App(PythonBackend(), "Python", DATA)
app.geometry("1600x1000+0+0")
app.api({"action": "load", "path": str(DATA)})
app.reload()


def snap(name: str, steps: int = 8) -> None:
    for _ in range(steps):
        app.update()
        time.sleep(0.15)
    subprocess.run(["import", "-window", hex(app.winfo_id()), str(OUT / f"{name}.png")], check=True)


def query_tab(name: str):
    app.show("query")
    wrapper = app.screens["query"]
    wrapper.tabs.set(name)
    wrapper.mode_changed()
    return wrapper


app.show("dashboard"); snap("dashboard")
app.show("route"); snap("rutas")
graph = query_tab("Red de carreteras (grafos PERA)").graph
graph.origin.select("76001"); graph.destination.select("05001"); graph.run(); snap("consulta")
app.show("map"); snap("mapa")
from locality_catalog import load_catalog, search_localities  # noqa: E402
catalog = load_catalog()
local = query_tab("Localidades de Colombia").local
pick = lambda text, name: [r for r in search_localities(catalog, text) if r["nombre"] == name][0]
local.origin.select_locality(pick("Valledupar", "Valledupar"))
local.destination.select_locality(pick("Sabanalarga Atlántico", "Sabanalarga"))
local.run()
for _ in range(160):
    app.update(); time.sleep(0.25)
    if app.locality_query:
        break
snap("localidad")
app.show("map"); snap("mapa_localidad")
app.destroy()
print("capturas en", OUT)
