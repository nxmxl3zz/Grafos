"""Formato en español: miles con punto, decimales con coma."""

from __future__ import annotations


def es_num(value: float, decimals: int = 0) -> str:
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def fmt_km(value: float) -> str:
    return f"{es_num(value, 1)} km"


def fmt_horas(hours: float) -> str:
    minutes = round(hours * 60)
    return f"{minutes // 60}:{minutes % 60:02d} h"


def fmt_cop(value: float) -> str:
    return f"$ {es_num(value)}"


def to_number(text: str):
    """Convierte '4,7' o '16000' a número; si no se puede devuelve el texto (el motor lo valida)."""
    clean = str(text).strip().replace(",", ".")
    try:
        number = float(clean)
    except ValueError:
        return str(text).strip()
    return int(number) if number.is_integer() and "." not in clean else number


def _signed(value: float, text: str) -> str:
    return ("+" if value > 0 else "−" if value < 0 else "±") + text


def compare_text(base: dict, other: dict) -> str:
    """Diferencia de una alternativa frente a la ruta más corta (totales del motor); vacío si son iguales."""
    dk, dh = other["km"] - base["km"], other["horas"] - base["horas"]
    df, dt = other["combustible"] - base["combustible"], other["peajes"] - base["peajes"]
    if abs(dk) < 0.05 and abs(dh) < 0.01 and df == 0 and dt == 0:
        return ""
    return ("Frente a la más corta: " + _signed(dk, fmt_km(abs(dk))) + " · " + _signed(dh, fmt_horas(abs(dh)))
            + " · combustible " + _signed(df, fmt_cop(abs(df))) + " · peajes " + _signed(dt, fmt_cop(abs(dt)))
            + " · costo total (combustible + peajes) " + _signed(df + dt, fmt_cop(abs(df + dt))))


def short_path(names: list[str], head: int = 5, tail: int = 3) -> str:
    """Cadena de ciudades; si es larga se recorta al inicio y al final con el número de tramos."""
    if len(names) <= head + tail + 1:
        return " → ".join(names)
    return " → ".join(names[:head]) + f" → … ({len(names) - head - tail} ciudades) … → " + " → ".join(names[-tail:])
