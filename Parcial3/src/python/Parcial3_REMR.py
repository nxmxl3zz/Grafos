"""PERA UPC (Parcial 3): ventana CustomTkinter de rutas entre capitales de Colombia.

Ejecutar: python src/python/Parcial3_REMR.py [--python-backend] [--cpp-binary RUTA] [--data ARCHIVO]
El motor es el programa C++ (`build/pera_cpp --api`); si no existe se intenta compilar con
CMake y, si no se puede, se usa el motor Python (`pera_engine.py`).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pera_backend import ROOT, make_backend  # noqa: E402

DEFAULT_DATA = ROOT / "data" / "pera_colombia.csv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PERA: rutas, tiempos, combustible y peajes entre ciudades")
    parser.add_argument("--python-backend", action="store_true", help="usar el motor Python")
    parser.add_argument("--cpp-binary", help="ruta del ejecutable pera_cpp")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="archivo de datos (.csv)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    backend, note = make_backend(args.python_backend, args.cpp_binary, args.data)
    from ui.app import App
    App(backend, note, args.data).mainloop()


if __name__ == "__main__":
    main()
