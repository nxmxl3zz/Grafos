"""Adaptador del motor: proceso hijo C++ (`pera_cpp --api`) o motor Python.

Ambos exponen `request(dict) -> dict` y `close()`. El protocolo es una línea JSON por
solicitud y por respuesta (ver `noCommit/PLAN.md`, sección «Protocolo»).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT = 15.0


class BackendError(RuntimeError):
    pass


class PythonBackend:
    name = "Python"

    def __init__(self, data: Path | None = None):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from pera_engine import Engine
        self.engine = Engine()

    def request(self, payload: dict) -> dict:
        return self.engine.handle(payload)

    def close(self) -> None:
        pass


class CppBackend:
    name = "C++"

    def __init__(self, binary: Path):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen([str(binary), "--api"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     bufsize=1, creationflags=flags)
        self._lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        reply = self.request({"action": "ping"})
        if not reply.get("ok") or str(reply.get("result", {}).get("protocol")) != "1":
            self.close()
            raise BackendError("el motor C++ no habla el protocolo 1")

    def _pump(self) -> None:
        for line in self.proc.stdout:
            self._lines.put(line)
        self._lines.put("")

    def request(self, payload: dict) -> dict:
        if self.proc.poll() is not None:
            raise BackendError("el motor C++ terminó")
        try:
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            line = self._lines.get(timeout=TIMEOUT)
        except (OSError, queue.Empty) as error:
            raise BackendError(f"sin respuesta del motor C++: {error}") from error
        if not line:
            raise BackendError("el motor C++ cerró la conexión")
        return json.loads(line)

    def close(self) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write('{"action":"shutdown"}\n')
                self.proc.stdin.flush()
                self.proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()


def find_binary(explicit: str | None) -> Path | None:
    """Binario C++ indicado, el compilado en build/ o el incluido para Windows."""
    names = ("pera_cpp.exe", "pera_cpp") if os.name == "nt" else ("pera_cpp",)
    candidates = [Path(explicit)] if explicit else []
    for name in names:
        candidates += [ROOT / "build" / name, ROOT / "build" / "Release" / name]
    if os.name == "nt":
        candidates.append(ROOT / "bin" / "windows" / "pera_cpp.exe")
    return next((c for c in candidates if c.is_file()), None)


def build_cpp() -> bool:
    """Intenta compilar con CMake una sola vez; False si no hay CMake o falla."""
    if not shutil.which("cmake") or not (ROOT / "CMakeLists.txt").is_file():
        return False
    try:
        for step in (["cmake", "-S", ".", "-B", "build"], ["cmake", "--build", "build"]):
            subprocess.run(step, cwd=ROOT, check=True, capture_output=True, timeout=300)
    except (subprocess.SubprocessError, OSError):
        return False
    return True


def make_backend(python_only: bool = False, cpp_binary: str | None = None,
                 data: Path | None = None) -> tuple[PythonBackend | CppBackend, str]:
    """Devuelve (motor, nota). La nota explica un respaldo si lo hubo, o es ''.

    `data` no se usa aquí: la ventana pide `load` al motor tras el diálogo inicial.
    """
    if python_only:
        return PythonBackend(data), ""
    note = ""
    binary = find_binary(cpp_binary)
    if binary is None and not cpp_binary:
        binary = find_binary(None) if build_cpp() else None
    if binary is None:
        note = "No se encontró el motor C++; se usa el motor Python."
    else:
        try:
            return CppBackend(binary), ""
        except (BackendError, OSError, ValueError) as error:
            note = f"El motor C++ no arrancó ({error}); se usa el motor Python."
    return PythonBackend(data), note
