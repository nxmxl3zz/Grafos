"""Geometría solo para dibujar: trazado vial de cada ruta (OSRM, simplificado) y límites departamentales."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import json

DATA = Path(__file__).resolve().parents[3] / "data"


@lru_cache(maxsize=None)
def _load(name: str):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def departments() -> list[dict]:
    return _load("colombia_departments.json") or []


def route_points(route: dict, by_id: dict) -> list[list[float]]:
    """[lat, lon] del trazado vial si la ruta sigue siendo la original; si no, segmento recto entre las ciudades."""
    geometry = (_load("route_geometry.json") or {}).get(route["id"])
    if geometry and geometry["a"] == route["origen"] and geometry["b"] == route["destino"]:
        return geometry["pts"]
    a, b = by_id.get(route["origen"]), by_id.get(route["destino"])
    return [[a["lat"], a["lon"]], [b["lat"], b["lon"]]] if a and b else []


def is_road(route: dict) -> bool:
    geometry = (_load("route_geometry.json") or {}).get(route["id"])
    return bool(geometry and geometry["a"] == route["origen"] and geometry["b"] == route["destino"])
