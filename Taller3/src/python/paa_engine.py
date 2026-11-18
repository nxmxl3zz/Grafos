"""Motor AVL autonomo de PAA (solo biblioteca estandar, Python >= 3.10).

Implementa el mismo contrato de pasos y el mismo protocolo JSON que el motor
C++ (`paa_cpp --api`). Uso como biblioteca: `Engine().handle({...}) -> dict`.
Uso como proceso: `python3 paa_engine.py --api [--data ruta]` (una linea JSON
por solicitud por stdin, una linea JSON por respuesta por stdout).

Convenciones del contrato:
- `rotate.pivot` es la clave del nodo desbalanceado (el que se rota), tal como
  era ANTES de la rotacion; `rotate.type` es el caso: LL (rotacion simple a la
  derecha), RR (simple a la izquierda), LR (doble izq-der), RL (doble der-izq).
- Tras la fase de busqueda/colocacion, cada nodo del camino (de abajo hacia
  arriba) emite `height{key,h,bf}` con su altura y factor ya recalculados; si
  |bf| > 1 le sigue `rotate`. El `tree` de cada paso es el arbol justo despues
  de ese paso (la altura almacenada se actualiza en el paso `height`).
- `search` de una clave ausente NO es error: responde ok con `found=false` y el
  paso `notfound`. `delete`/`toggle`/`update` de clave ausente si son error.
"""
import json
import os
import sys
import tempfile

PROTOCOL = "1"
INT_MIN, INT_MAX = -(2 ** 31), 2 ** 31 - 1


MAX_NODES = 20000   # tope de nodos al cargar un archivo (misma regla que el motor C++)


class Node:
    __slots__ = ("key", "label", "active", "h", "left", "right")

    def __init__(self, key, label, active=1):
        self.key = key
        self.label = label
        self.active = active
        self.h = 1
        self.left = None
        self.right = None


def _h(n):
    return n.h if n else 0


def _bf(n):
    return _h(n.left) - _h(n.right)


def _fix(n):
    n.h = 1 + max(_h(n.left), _h(n.right))


def _snap(n):
    if n is None:
        return None
    return {"k": n.key, "l": n.label, "a": 1 if n.active else 0, "h": n.h,
            "bf": _bf(n), "L": _snap(n.left), "R": _snap(n.right)}


class AvlError(Exception):
    pass


class AvlTree:
    """Arbol AVL con registro opcional de pasos (record=False para pruebas masivas)."""

    def __init__(self, record=True):
        self.root = None
        self.size = 0
        self.record = record
        self.steps = []

    # ---- utilidades
    def _emit(self, t, **kw):
        if self.record:
            kw["t"] = t
            kw["tree"] = _snap(self.root)
            self.steps.append(kw)

    def clear(self):
        self.root = None
        self.size = 0
        self.steps = []

    def snapshot(self):
        return _snap(self.root)

    def _find(self, key):
        n = self.root
        while n is not None and n.key != key:
            n = n.left if key < n.key else n.right
        return n

    def traversals(self):
        pre, ino, post = [], [], []
        stack = []
        n = self.root
        # pre-orden
        if n:
            stack = [n]
            while stack:
                x = stack.pop()
                pre.append(x.key)
                if x.right:
                    stack.append(x.right)
                if x.left:
                    stack.append(x.left)
        # in-orden
        stack, x = [], self.root
        while stack or x:
            while x:
                stack.append(x)
                x = x.left
            x = stack.pop()
            ino.append(x.key)
            x = x.right
        # post-orden (inverso de raiz-der-izq)
        if self.root:
            stack = [self.root]
            while stack:
                x = stack.pop()
                post.append(x.key)
                if x.left:
                    stack.append(x.left)
                if x.right:
                    stack.append(x.right)
            post.reverse()
        return {"pre": pre, "in": ino, "post": post}

    # ---- rotaciones
    def _rot_right(self, y):
        x = y.left
        y.left, x.right = x.right, y
        _fix(y)
        _fix(x)
        return x

    def _rot_left(self, x):
        y = x.right
        x.right, y.left = y.left, x
        _fix(x)
        _fix(y)
        return y

    def _rebalance(self, n):
        """Recalcula n (emite height) y rota si hace falta; devuelve la nueva raiz."""
        _fix(n)
        bf = _bf(n)
        self._emit("height", key=n.key, h=n.h, bf=bf)
        if bf > 1:
            kind = "LL" if _bf(n.left) >= 0 else "LR"
        elif bf < -1:
            kind = "RR" if _bf(n.right) <= 0 else "RL"
        else:
            return n
        pivot = n.key
        if kind == "LL":
            n = self._rot_right(n)
        elif kind == "RR":
            n = self._rot_left(n)
        elif kind == "LR":
            n.left = self._rot_left(n.left)
            n = self._rot_right(n)
        else:
            n.right = self._rot_right(n.right)
            n = self._rot_left(n)
        return n, kind, pivot

    def _balance_path(self, path, links):
        """path: nodos de la raiz al padre del cambio; links: lado por el que se baja."""
        for i in range(len(path) - 1, -1, -1):
            n = path[i]
            res = self._rebalance(n)
            if isinstance(res, tuple):
                new, kind, pivot = res
                self._attach(path, links, i, new)
                self._emit("rotate", type=kind, pivot=pivot)
            else:
                self._attach(path, links, i, res)

    def _attach(self, path, links, i, new):
        if i == 0:
            self.root = new
        elif links[i - 1] == "L":
            path[i - 1].left = new
        else:
            path[i - 1].right = new

    # ---- operaciones
    def insert(self, key, label):
        path, links = [], []
        n = self.root
        while n is not None:
            if key == n.key:
                raise AvlError("La clave %d ya existe" % key)
            self._emit("compare", key=key, **{"with": n.key})
            d = "L" if key < n.key else "R"
            self._emit("descend", dir=d)
            path.append(n)
            links.append(d)
            n = n.left if d == "L" else n.right
        new = Node(key, label)
        if not path:
            self.root = new
        elif links[-1] == "L":
            path[-1].left = new
        else:
            path[-1].right = new
        self.size += 1
        self._emit("place", key=key)
        self._balance_path(path, links)

    def delete(self, key):
        path, links = [], []
        n = self.root
        while n is not None and n.key != key:
            self._emit("compare", key=key, **{"with": n.key})
            d = "L" if key < n.key else "R"
            self._emit("descend", dir=d)
            path.append(n)
            links.append(d)
            n = n.left if d == "L" else n.right
        if n is None:
            if self.record:
                self.steps = []
            raise AvlError("La clave %d no existe" % key)
        self._emit("compare", key=key, **{"with": n.key})
        if n.left is not None and n.right is not None:
            path.append(n)
            links.append("R")
            self._emit("descend", dir="R")
            s = n.right
            while s.left is not None:
                path.append(s)
                links.append("L")
                self._emit("descend", dir="L")
                s = s.left
            n.key, n.label, n.active = s.key, s.label, s.active
            # `replace.key` es la clave original del nodo, `with` la del sucesor.
            old = key
            self._emit("replace", key=old, **{"with": s.key})
            n = s  # ahora se quita el sucesor (a lo sumo un hijo derecho)
            key = s.key
        child = n.left if n.left is not None else n.right
        if not path:
            self.root = child
        elif links[-1] == "L":
            path[-1].left = child
        else:
            path[-1].right = child
        self.size -= 1
        self._emit("remove", key=key)
        self._balance_path(path, links)

    def search(self, key):
        n = self.root
        while n is not None:
            self._emit("compare", key=key, **{"with": n.key})
            if key == n.key:
                self._emit("found", key=key)
                return n
            d = "L" if key < n.key else "R"
            self._emit("descend", dir=d)
            n = n.left if d == "L" else n.right
        self._emit("notfound", key=key)
        return None

    def _walk(self, key):
        n = self.root
        while n is not None:
            self._emit("compare", key=key, **{"with": n.key})
            if key == n.key:
                return n
            d = "L" if key < n.key else "R"
            self._emit("descend", dir=d)
            n = n.left if d == "L" else n.right
        return None

    def toggle(self, key):
        n = self._walk(key)
        if n is None:
            raise AvlError("La clave %d no existe" % key)
        n.active = 0 if n.active else 1
        self._emit("toggle", key=key, active=bool(n.active))
        return n

    def update(self, key, label):
        n = self._walk(key)
        if n is None:
            raise AvlError("La clave %d no existe" % key)
        n.label = label
        self._emit("update", key=key)
        return n

    def load_entries(self, entries):
        """Reconstruye el arbol desde [(key, label, active)] en pre-orden.

        La insercion BST plana en pre-orden reproduce exactamente la forma
        guardada (insertar con rotaciones no, porque los prefijos no son AVL).
        Si el archivo no describe un AVL valido, se reinserta con balanceo.
        """
        if len(entries) > MAX_NODES:
            raise AvlError("El archivo tiene demasiados nodos (maximo %d)" % MAX_NODES)
        root, seen = None, set()
        for key, label, act in entries:
            if key in seen:
                raise AvlError("clave duplicada %d" % key)
            seen.add(key)
            node = Node(key, label, act)
            if root is None:
                root = node
                continue
            n = root
            while True:
                nxt = n.left if key < n.key else n.right
                if nxt is None:
                    break
                n = nxt
            if key < n.key:
                n.left = node
            else:
                n.right = node
        valid, order, stack = True, [], ([root] if root else [])
        while stack:  # pre-orden; alturas en orden inverso
            x = stack.pop()
            order.append(x)
            stack.extend(c for c in (x.left, x.right) if c)
        for x in reversed(order):
            _fix(x)
            if abs(_bf(x)) > 1:
                valid = False
        if valid:
            self.root, self.size = root, len(order)
            return
        self.clear()
        for key, label, act in entries:
            self.insert(key, label)
            if not act:
                self._find(key).active = 0
        self.steps = []

    def preorder_nodes(self):
        out, stack = [], ([self.root] if self.root else [])
        while stack:
            x = stack.pop()
            out.append(x)
            if x.right:
                stack.append(x.right)
            if x.left:
                stack.append(x.left)
        return out


def _clean(label):
    return label.replace("\r", " ").replace("\n", " ").replace(";", " ")


def _parse_file(path):
    """Lee el archivo y devuelve un AvlTree nuevo, o lanza AvlError."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
    except OSError as e:
        raise AvlError("No se pudo leer el archivo: %s" % (e.strerror or e))
    except UnicodeDecodeError:
        raise AvlError("El archivo no es UTF-8 valido")
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        raise AvlError("El archivo esta vacio")
    entries, seen = [], set()
    for i, line in enumerate(lines, 1):
        first = line.find(";")
        last = line.rfind(";")
        if first < 0 or last == first:
            raise AvlError("Linea %d mal formada" % i)
        ks, label, act = line[:first], line[first + 1:last], line[last + 1:]
        try:
            key = int(ks)
        except ValueError:
            raise AvlError("Linea %d: clave no entera" % i)
        if not INT_MIN <= key <= INT_MAX:
            raise AvlError("Linea %d: clave fuera de rango" % i)
        if act not in ("0", "1"):
            raise AvlError("Linea %d: el estado debe ser 0 o 1" % i)
        if key in seen:
            raise AvlError("Linea %d: clave duplicada %d" % (i, key))
        seen.add(key)
        entries.append((key, label, int(act)))
    tmp = AvlTree(record=False)
    tmp.load_entries(entries)
    return tmp


class Engine:
    def __init__(self, data_path=None):
        self.tree = AvlTree()
        self.dirty = False
        self.data_path = data_path
        self.shutdown_requested = False
        self.history = []  # copias previas del arbol, para deshacer

    def _state(self):
        return {"dirty": self.dirty, "size": self.tree.size}

    def _err(self, msg):
        return {"ok": False, "error": msg, "state": self._state()}

    def _ok(self, result=None, steps=None):
        return {"ok": True, "result": result if result is not None else {},
                "steps": steps if steps is not None else [],
                "tree": self.tree.snapshot(),
                "traversals": self.tree.traversals(),
                "state": self._state()}

    @staticmethod
    def _key(req):
        k = req.get("key")
        if isinstance(k, bool) or not isinstance(k, int):
            raise AvlError("La clave debe ser un entero")
        if not INT_MIN <= k <= INT_MAX:
            raise AvlError("La clave esta fuera del rango de 32 bits")
        return k

    @staticmethod
    def _label(req):
        lab = req.get("label", "")
        if not isinstance(lab, str):
            raise AvlError("La etiqueta debe ser texto")
        return lab

    def _path(self, req):
        p = req.get("path") or self.data_path
        if not isinstance(p, str) or not p:
            raise AvlError("Falta la ruta del archivo")
        return p

    def handle(self, request):
        try:
            if not isinstance(request, dict):
                raise AvlError("La solicitud debe ser un objeto JSON")
            action = request.get("action")
            fn = getattr(self, "_do_" + action, None) if isinstance(action, str) else None
            if fn is None:
                raise AvlError("Accion desconocida: %s" % (action,))
            self.tree.steps = []
            mutating = action in ("insert", "delete", "toggle", "update")
            before = self._entries() if mutating else None
            response = fn(request)
            if mutating and response.get("ok"):
                self.history.append(before)
                del self.history[:-200]
            return response
        except AvlError as e:
            return self._err(str(e))
        except Exception as e:  # nunca propagar al proceso
            return self._err("Error interno: %s" % e)

    def _entries(self):
        return [(n.key, n.label, n.active) for n in self.tree.preorder_nodes()]

    def _do_undo(self, r):
        if not self.history:
            raise AvlError("No hay nada que deshacer")
        self.tree.load_entries(self.history.pop())
        self.dirty = True
        return self._ok()

    def _do_ping(self, r):
        return self._ok({"backend": "python", "protocol": PROTOCOL})

    def _do_state(self, r):
        return self._ok()

    def _do_traversals(self, r):
        return self._ok()

    def _do_shutdown(self, r):
        self.shutdown_requested = True
        return self._ok()

    def _do_reset(self, r):
        self.tree.clear()
        self.dirty = False
        return self._ok()

    def _do_insert(self, r):
        key, label = self._key(r), self._label(r)
        self.tree.insert(key, label)
        self.dirty = True
        return self._ok({"key": key}, self.tree.steps)

    def _do_delete(self, r):
        key = self._key(r)
        self.tree.delete(key)
        self.dirty = True
        return self._ok({"key": key}, self.tree.steps)

    def _do_search(self, r):
        key = self._key(r)
        n = self.tree.search(key)
        res = {"key": key, "found": n is not None}
        if n is not None:
            res.update(label=n.label, active=bool(n.active))
        return self._ok(res, self.tree.steps)

    def _do_toggle(self, r):
        n = self.tree.toggle(self._key(r))
        self.dirty = True
        return self._ok({"key": n.key, "active": bool(n.active)}, self.tree.steps)

    def _do_update(self, r):
        key = self._key(r)
        if "label" not in r:
            raise AvlError("Falta la etiqueta")
        n = self.tree.update(key, self._label(r))
        self.dirty = True
        return self._ok({"key": key}, self.tree.steps)

    def _do_save(self, r):
        path = self._path(r)
        lines = ["%d;%s;%d\n" % (n.key, _clean(n.label), 1 if n.active else 0)
                 for n in self.tree.preorder_nodes()]
        d = os.path.dirname(os.path.abspath(path))
        tmp = None
        try:
            os.makedirs(d, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=d, prefix=".paa_", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(lines)
            os.replace(tmp, path)
        except OSError as e:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)
            raise AvlError("No se pudo guardar: %s" % (e.strerror or e))
        self.dirty = False
        return self._ok({"path": path, "size": self.tree.size})

    def _do_load(self, r):
        new = _parse_file(self._path(r))  # el arbol actual no se toca si falla
        new.record = True
        self.tree = new
        self.dirty = False
        return self._ok({"size": new.size})


def serve(engine, inp, out):
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            resp = engine._err("JSON invalido")
        else:
            resp = engine.handle(req)
        out.write(json.dumps(resp, ensure_ascii=False, separators=(",", ":")) + "\n")
        out.flush()
        if engine.shutdown_requested:
            break


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    data = None
    if "--data" in argv:
        i = argv.index("--data")
        if i + 1 >= len(argv):
            sys.stderr.write("Falta la ruta tras --data\n")
            return 2
        data = argv[i + 1]
    if "--api" not in argv:
        sys.stderr.write("Uso: paa_engine.py --api [--data ruta]\n")
        return 2
    for s in (sys.stdin, sys.stdout):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    serve(Engine(data), sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
