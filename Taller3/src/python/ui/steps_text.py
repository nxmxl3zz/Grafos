"""Texto en español de cada paso del contrato y nodos que se resaltan."""

from __future__ import annotations

ROTATION_NAMES = {
    "LL": "simple a la derecha",
    "RR": "simple a la izquierda",
    "LR": "doble izquierda-derecha",
    "RL": "doble derecha-izquierda",
}


def signed(value: int) -> str:
    return f"{value:+d}" if value else "0"


def describe(step: dict) -> tuple[str, str]:
    """Devuelve (texto, tipo de línea): info, rot, ok o warn."""
    t = step.get("t")
    if t == "compare":
        return f"Comparar {step['key']} con {step['with']}", "info"
    if t == "descend":
        return "Bajar por la " + ("izquierda" if step.get("dir") == "L" else "derecha"), "info"
    if t == "place":
        return f"Colocar {step['key']} como hoja (ubicación BST)", "ok"
    if t == "found":
        return f"Clave {step['key']} encontrada", "ok"
    if t == "notfound":
        return f"Clave {step['key']} no existe", "warn"
    if t == "replace":
        return f"Reemplazar {step['key']} por su sucesor {step['with']}", "info"
    if t == "remove":
        return f"Quitar el nodo {step['key']}", "warn"
    if t == "height":
        return f"Nodo {step['key']}: altura {step['h']}, balance {signed(step['bf'])}", "info"
    if t == "rotate":
        kind = step.get("type", "")
        return f"Rotación {kind} en {step['pivot']} ({ROTATION_NAMES.get(kind, '')})", "rot"
    if t == "toggle":
        return f"Nodo {step['key']} " + ("reactivado" if step.get("active") else "desactivado"), "ok"
    if t == "update":
        return f"Etiqueta del nodo {step['key']} modificada", "ok"
    return str(t), "info"


def highlight_of(step: dict) -> dict[int, str]:
    """Clave -> tipo de resaltado (ver theme.HIGHLIGHT)."""
    t = step.get("t")
    if t == "compare":
        return {step["with"]: "compare"}
    if t in ("place", "found", "remove"):
        return {step["key"]: t}
    if t == "replace":
        return {step["key"]: "remove", step["with"]: "place"}
    if t in ("toggle", "update"):
        return {step["key"]: "found"}
    if t == "height":
        return {step["key"]: "height"}
    if t == "rotate":
        return {step["pivot"]: "rotate"}
    return {}
