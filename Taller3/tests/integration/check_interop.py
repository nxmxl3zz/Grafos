"""Misma secuencia de operaciones en el motor C++ y en el motor Python; compara todo.

Uso: python3 -I tests/integration/check_interop.py build/paa_cpp
"""
import json
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src", "python"))
from paa_engine import Engine  # noqa: E402


class Cpp:
    def __init__(self, exe, data):
        self.p = subprocess.Popen([exe, "--api", "--data", data], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True, encoding="utf-8")

    def handle(self, req):
        self.p.stdin.write(json.dumps(req) + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())

    def close(self):
        self.handle({"action": "shutdown"})
        self.p.wait(timeout=5)


def norm(resp):
    r = dict(resp)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error")}
    r.pop("result", None) if False else None
    res = dict(r.get("result", {}))
    res.pop("backend", None)
    res.pop("path", None)
    r["result"] = res
    return r


def build_sequence():
    seq = []
    for k in (10, 20, 30, 25, 5, 4, 3, -7, 0, 2147483647, -2147483648):
        seq.append({"action": "insert", "key": k, "label": f"n{k}"})
    seq += [{"action": "insert", "key": 10, "label": "dup"},
            {"action": "search", "key": 25}, {"action": "search", "key": 999},
            {"action": "toggle", "key": 25}, {"action": "toggle", "key": 25},
            {"action": "update", "key": 5, "label": "cinco"},
            {"action": "delete", "key": 20}, {"action": "delete", "key": 999},
            {"action": "delete", "key": 10}, {"action": "delete", "key": 4},
            {"action": "traversals"}, {"action": "state"}]
    rnd = random.Random(7)
    keys = rnd.sample(range(-500, 500), 120)
    seq += [{"action": "insert", "key": k, "label": ""} for k in keys]
    seq += [{"action": "delete", "key": k} for k in rnd.sample(keys, 70)]
    seq += [{"action": "toggle", "key": k} for k in rnd.sample(keys, 10)]
    seq += [{"action": "undo"}] * 15  # deshacer toggles, borrados e inserciones
    seq += [{"action": "reset"}, {"action": "undo"}, {"action": "insert", "key": 1}, {"action": "undo"},
            {"action": "undo"}, {"action": "traversals"}]  # deshacer hasta vacío y más allá
    return seq


def main():
    exe = sys.argv[1]
    tmp = tempfile.mkdtemp()
    cpp_data, py_data = os.path.join(tmp, "c.txt"), os.path.join(tmp, "p.txt")
    cpp, py = Cpp(exe, cpp_data), Engine(py_data)
    bad = 0
    seq = build_sequence() + [{"action": "save", "path": cpp_data}]
    for i, req in enumerate(seq):
        a = cpp.handle(req)
        b = py.handle(dict(req, path=py_data) if req["action"] == "save" else req)
        na, nb = norm(a), norm(b)
        if na != nb:
            bad += 1
            if bad <= 5:
                print(f"DIFERENCIA en #{i} {req}")
                for key in sorted(set(na) | set(nb)):
                    if na.get(key) != nb.get(key):
                        print(f"  campo '{key}':")
                        if key == "steps":
                            sa, sb = na[key], nb[key]
                            for j in range(max(len(sa), len(sb))):
                                x = sa[j] if j < len(sa) else None
                                y = sb[j] if j < len(sb) else None
                                if x != y:
                                    print(f"    paso {j}: cpp={json.dumps(x)[:200]}\n           py ={json.dumps(y)[:200]}")
                                    break
                        else:
                            print(f"    cpp={json.dumps(na.get(key))[:200]}\n    py ={json.dumps(nb.get(key))[:200]}")
    # persistencia cruzada: el archivo de C++ debe cargarse igual en Python y viceversa
    py.handle({"action": "save", "path": py_data})
    with open(cpp_data, encoding="utf-8") as f1, open(py_data, encoding="utf-8") as f2:
        if f1.read() != f2.read():
            bad += 1
            print("DIFERENCIA: los archivos guardados no coinciden")
    cpp2, py2 = Cpp(exe, cpp_data), Engine(cpp_data)
    ra = cpp2.handle({"action": "load", "path": py_data})
    rb = py2.handle({"action": "load", "path": cpp_data})
    if ra.get("tree") != rb.get("tree") or ra.get("tree") != cpp.handle({"action": "traversals"}).get("tree"):
        bad += 1
        print("DIFERENCIA: carga cruzada")
    cpp.close(); cpp2.close()
    print("OK" if bad == 0 else f"{bad} diferencias")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
