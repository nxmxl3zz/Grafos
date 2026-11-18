"""PAA UPC (Taller 3): ventana CustomTkinter para enseñar árboles AVL.

Ejecutar: python src/python/Taller3_REMR.py [--python-backend] [--cpp-binary RUTA] [--data ARCHIVO]
El motor es el programa C++ (`build/paa_cpp --api`); si no existe se intenta compilar con
CMake y, si no se puede, se usa el motor Python (`paa_engine.py`).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from paa_backend import ROOT, make_backend  # noqa: E402

DEFAULT_DATA = ROOT / "data" / "arbol_avl.txt"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PAA: aprendizaje de árboles AVL")
    parser.add_argument("--python-backend", action="store_true", help="usar el motor Python")
    parser.add_argument("--cpp-binary", help="ruta del ejecutable paa_cpp")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="archivo de datos del árbol")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    backend, note = make_backend(args.python_backend, args.cpp_binary, args.data)
    from ui.app import App
    App(backend, note, args.data).mainloop()


if __name__ == "__main__":
    main()
