"""Misma secuencia de solicitudes en el motor C++ y en el Python; compara respuestas y archivos guardados.

Uso: python3 -I tests/integration/check_interop.py build/pera_cpp [archivo.csv ...]
Sin archivos extra usa tests/fixtures/mini.csv; con archivos, además consulta pares de ciudades de cada uno.
"""
import json
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src", "python"))
from pera_engine import Engine  # noqa: E402

TOL = 1e-9


class Cpp:
    def __init__(self, exe):
        self.p = subprocess.Popen([exe, "--api"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  text=True, encoding="utf-8")

    def handle(self, req):
        self.p.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError("el motor C++ no respondió a %r" % req)
        return json.loads(line)

    def close(self):
        self.handle({"action": "shutdown"})
        self.p.wait(timeout=5)


def same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= TOL
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def norm(r):
    r = json.loads(json.dumps(r))
    if r.get("ok"):
        res = r.get("result")
        if isinstance(res, dict):
            res.pop("backend", None)
            res.pop("path", None)
    return r


def mini_sequence(path):
    s = [{"action": "ping"}, {"action": "load", "path": path}, {"action": "state"}, {"action": "params"},
         {"action": "list", "kind": "city"}, {"action": "list", "kind": "toll"}, {"action": "list", "kind": "route"},
         {"action": "get", "kind": "route", "id": "R002"}, {"action": "get", "kind": "city", "id": "99999"}]
    for a, b in (("11001", "50001"), ("11001", "73001"), ("15001", "73001"), ("11001", "91001"),
                 ("11001", "11001"), ("11001", "00000"), ("91001", "11001")):
        s.append({"action": "query", "from": a, "to": b})
    s += [{"action": "stats"},
          {"action": "create", "kind": "route", "origen": "50001", "destino": "11001", "km": "90", "horas": "2.3"},  # inversa
          {"action": "create", "kind": "route", "origen": "11001", "destino": "11001", "km": "1", "horas": "1"},
          {"action": "create", "kind": "route", "origen": "15001", "destino": "73001", "km": "280.5", "horas": "5.5",
           "peajes": "P001|P004"},
          {"action": "create", "kind": "route", "origen": "11001", "destino": "XXXX", "km": "1", "horas": "1"},
          {"action": "create", "kind": "toll", "nombre": "Peaje Nuevo", "lat": "4.5", "lon": "-74.0", "tarifa": "15000"},
          {"action": "create", "kind": "city", "id": "20001", "nombre": "Valle;dupar", "departamento": "Cesar",
           "lat": "10.46314", "lon": "-73.25322"},
          {"action": "create", "kind": "city", "id": "20001", "nombre": "Repetida", "departamento": "Cesar",
           "lat": "1", "lon": "1"},
          {"action": "create", "kind": "route", "origen": "20001", "destino": "15001", "km": "700", "horas": "11",
           "peajes": "P006"},
          {"action": "update", "kind": "route", "id": "R001", "km": "150.4", "peajes": "P001|P006"},
          {"action": "update", "kind": "toll", "id": "P004", "tarifa": "25000"},
          {"action": "toggle", "kind": "toll", "id": "P004"}, {"action": "query", "from": "11001", "to": "50001"},
          {"action": "toggle", "kind": "toll", "id": "P004"},
          {"action": "toggle", "kind": "city", "id": "15001"}, {"action": "query", "from": "11001", "to": "50001"},
          {"action": "toggle", "kind": "city", "id": "15001"},
          {"action": "set_params", "consumo_km_gal": "35", "precio_gal": "15500"},
          {"action": "query", "from": "11001", "to": "73001"}, {"action": "stats"},
          {"action": "delete", "kind": "toll", "id": "P001"}, {"action": "delete", "kind": "toll", "id": "P999"},
          {"action": "delete", "kind": "city", "id": "11001"}, {"action": "stats"}, {"action": "list", "kind": "route"}]
    s += [{"action": "undo"}] * 14 + [{"action": "stats"}, {"action": "list", "kind": "route"}]
    s += [{"action": "reset"}, {"action": "undo"}, {"action": "stats"}, {"action": "query", "from": "1", "to": "2"},
          {"action": "bogus"}, {"action": "list", "kind": "nada"}]
    return s


def real_sequence(path, rnd_seed=3):
    s = [{"action": "load", "path": path}, {"action": "stats"}, {"action": "params"},
         {"action": "list", "kind": "city"}, {"action": "list", "kind": "toll"}, {"action": "list", "kind": "route"}]
    ids = None
    return s, ids


def run(cpp, py, seq, label, save_path_cpp=None, save_path_py=None):
    bad = 0
    for i, req in enumerate(seq):
        a, b = norm(cpp.handle(req)), norm(py.handle(req))
        if not same(a, b):
            bad += 1
            if bad <= 6:
                print("DIFERENCIA [%s] #%d %s" % (label, i, json.dumps(req, ensure_ascii=False)[:160]))
                for k in sorted(set(a) | set(b)):
                    if not same(a.get(k), b.get(k)):
                        print("  campo %r:\n    cpp=%s\n    py =%s" % (k, json.dumps(a.get(k), ensure_ascii=False)[:300],
                                                                   json.dumps(b.get(k), ensure_ascii=False)[:300]))
    return bad


def main():
    exe = sys.argv[1]
    extra = sys.argv[2:]
    tmp = tempfile.mkdtemp()
    mini = os.path.join(ROOT, "tests", "fixtures", "mini.csv")
    cpp, py = Cpp(exe), Engine()
    bad = run(cpp, py, mini_sequence(mini), "mini")
    # guardado byte a byte tras operaciones
    for eng, name in ((cpp, "c"), (py, "p")):
        eng.handle({"action": "load", "path": mini})
        eng.handle({"action": "create", "kind": "toll", "nombre": "Peaje; Raro\n", "lat": "1", "lon": "2", "tarifa": "100"})
        eng.handle({"action": "toggle", "kind": "route", "id": "R003"})
        eng.handle({"action": "save", "path": os.path.join(tmp, name + ".csv")})
    a = open(os.path.join(tmp, "c.csv"), "rb").read()
    b = open(os.path.join(tmp, "p.csv"), "rb").read()
    if a != b:
        bad += 1
        print("DIFERENCIA: los archivos guardados no coinciden")
    # ida y vuelta idéntica del fixture
    for eng, name in ((cpp, "c"), (py, "p")):
        eng.handle({"action": "load", "path": mini})
        eng.handle({"action": "save", "path": os.path.join(tmp, name + "_rt.csv")})
    if open(os.path.join(tmp, "c_rt.csv"), "rb").read() != open(mini, "rb").read():
        bad += 1
        print("DIFERENCIA: C++ no reproduce mini.csv al guardar")
    if open(os.path.join(tmp, "p_rt.csv"), "rb").read() != open(mini, "rb").read():
        bad += 1
        print("DIFERENCIA: Python no reproduce mini.csv al guardar")
    # archivos corruptos: error en ambos y estado intacto
    for text in ("garbage\n", "C;1;a;b;1;2;1\nR;R1;1;2;3;4;;1\n", "K;foo;1\n", "C;1;a;b;1;2;7\n"):
        p = os.path.join(tmp, "bad.csv")
        open(p, "w", encoding="utf-8").write(text)
        cpp.handle({"action": "load", "path": mini}); py.handle({"action": "load", "path": mini})
        ra, rb = cpp.handle({"action": "load", "path": p}), py.handle({"action": "load", "path": p})
        if ra["ok"] or rb["ok"] or not same(cpp.handle({"action": "stats"}), py.handle({"action": "stats"})):
            bad += 1
            print("DIFERENCIA con archivo corrupto %r" % text[:30])
    # datos reales
    for path in extra:
        cpp.handle({"action": "load", "path": path}); py.handle({"action": "load", "path": path})
        cities = [c["id"] for c in py.handle({"action": "list", "kind": "city"})["result"]["items"]]
        rnd = random.Random(11)
        seq = [{"action": "stats"}, {"action": "params"}, {"action": "list", "kind": "route"},
               {"action": "list", "kind": "toll"}, {"action": "list", "kind": "city"}]
        seq += [{"action": "query", "from": rnd.choice(cities), "to": rnd.choice(cities)} for _ in range(300)]
        bad += run(cpp, py, seq, os.path.basename(path))
        eng_files = []
        for eng, name in ((cpp, "rc"), (py, "rp")):
            eng.handle({"action": "save", "path": os.path.join(tmp, name + ".csv")})
            eng_files.append(open(os.path.join(tmp, name + ".csv"), "rb").read())
        if eng_files[0] != eng_files[1]:
            bad += 1
            print("DIFERENCIA: guardado de datos reales")
    cpp.close()
    print("OK" if bad == 0 else "%d diferencias" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
