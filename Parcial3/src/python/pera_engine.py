"""Motor PERA autonomo (solo biblioteca estandar, Python >= 3.10).

Mismo contrato de archivo y protocolo JSON que el motor C++ (`pera_cpp --api`).
Biblioteca: `Engine().handle({...}) -> dict`. Proceso:
`python3 pera_engine.py --api [--data ruta]` (una linea JSON por solicitud por
stdin, una linea JSON por respuesta por stdout; termina tras `shutdown`).

Aritmetica entera: km_x10, consumo_x10, horas_x100 y pesos. Tres grafos como
listas de adyacencia (G_distancia, G_combustible, G_peajes) mas G_tiempo (las
horas viajan en la misma ruta); se reconstruyen desde las tablas tras cada
cambio, asi que siempre estan sincronizados. Solo contienen rutas efectivas
(activas y con ambas ciudades activas).
"""
import heapq
import json
import os
import re
import sys
import tempfile
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

PROTOCOL = "1"
HISTORY_MAX = 200
KINDS = ("city", "toll", "route")
NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")
INT_RE = re.compile(r"^\d+$")


class PeraError(Exception):
    pass


class InvalidFile(PeraError):
    def __init__(self, msg):
        super().__init__("Archivo inválido: " + msg)


# ---------------------------------------------------------------- numeros
def _scaled(v, scale, field):
    """Valor (str/int/float) -> entero escalado, redondeo de mitades hacia arriba."""
    if isinstance(v, bool) or v is None:
        raise PeraError("Campo inválido: %s" % field)
    try:
        d = Decimal(str(v).strip() if isinstance(v, str) else repr(v))
    except InvalidOperation:
        raise PeraError("Campo inválido: %s" % field)
    if not d.is_finite():
        raise PeraError("Campo inválido: %s" % field)
    return int((d * scale).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _ranged(v, scale, field, lo, hi):
    n = _scaled(v, scale, field)
    if not lo <= n <= hi:
        raise PeraError("Campo inválido: %s" % field)
    return n


def _bool(v, field):
    if isinstance(v, bool):
        return v
    if v in (1, "1", "true", "True"):
        return True
    if v in (0, "0", "false", "False"):
        return False
    raise PeraError("Campo inválido: %s" % field)


def _text(v, field):
    if isinstance(v, bool) or not isinstance(v, (str, int, float)):
        raise PeraError("Campo inválido: %s" % field)
    return str(v)


def _ident(v, field="id"):
    s = _text(v, field).strip() if v is not None else ""
    if not s or any(c in s for c in ";|\r\n"):
        raise PeraError("Campo inválido: %s" % field)
    return s


def _half_up(num, den):
    """num/den (den > 0) redondeado a entero, mitades hacia arriba."""
    return (2 * num + den) // (2 * den)


def _fuel(km10, cons10, precio):
    return (2 * km10 * precio + cons10) // (2 * cons10)


def _fmt(n, scale):
    """Entero escalado -> float exacto en 1/scale (para JSON)."""
    return n / scale


# ---------------------------------------------------------------- grafos
LIM = 4 * 10 ** 18   # tope de los pesos compuestos (cabe en un entero de 64 bits con margen)


class Graph:
    """Lista de adyacencia: adj[ciudad] = [(id_ruta, vecino, peso)] por id de ruta ascendente."""

    def __init__(self, cities):
        self.adj = {c: [] for c in cities}

    def add_edge(self, rid, a, b, w):
        self.adj[a].append((rid, b, w))
        self.adj[b].append((rid, a, w))

    def sort(self):
        for lst in self.adj.values():
            lst.sort(key=lambda t: t[0])

    def dijkstra(self, src, dst):
        """(ciudades, rutas) del camino optimo o None. Cola ordenada por (costo, id de ciudad)."""
        dist = {src: 0}
        prev = {}
        heap = [(0, src)]
        done = set()
        while heap:
            d, u = heapq.heappop(heap)
            if u in done:
                continue
            done.add(u)
            if u == dst:
                break
            for rid, v, w in self.adj[u]:
                nd = d + w
                if nd < dist.get(v, nd + 1):  # relajacion estrictamente mejor
                    dist[v] = nd
                    prev[v] = (u, rid)
                    heapq.heappush(heap, (nd, v))
        if dst not in done:
            return None
        cities, routes = [dst], []
        while cities[-1] != src:
            u, rid = prev[cities[-1]]
            cities.append(u)
            routes.append(rid)
        cities.reverse()
        routes.reverse()
        return cities, routes


# ---------------------------------------------------------------- datos
class Data:
    def __init__(self):
        self.cities = {}   # id -> {nombre, depto, lat, lon, activo}
        self.tolls = {}    # id -> {nombre, lat, lon, tarifa, activo}
        self.routes = {}   # id -> {o, d, km10, h100, peajes, activo}
        self.cons10 = 400
        self.precio = 16000
        self.vel = 55

    def clone(self):
        n = Data()
        n.cities = {k: dict(v) for k, v in self.cities.items()}
        n.tolls = {k: dict(v) for k, v in self.tolls.items()}
        n.routes = {k: dict(v, peajes=list(v["peajes"])) for k, v in self.routes.items()}
        n.cons10, n.precio, n.vel = self.cons10, self.precio, self.vel
        return n

    # --- derivados
    def efectiva(self, r):
        return bool(r["activo"] and self.cities[r["o"]]["activo"] and self.cities[r["d"]]["activo"])

    def fuel(self, r):
        return _fuel(r["km10"], self.cons10, self.precio)

    def toll_cost(self, r):
        return sum(self.tolls[t]["tarifa"] for t in r["peajes"] if self.tolls[t]["activo"])

    def degree(self, cid):
        return sum(1 for r in self.routes.values() if (r["o"] == cid or r["d"] == cid) and self.efectiva(r))

    # --- serializacion deterministica
    def dumps(self):
        out = ["# PERA v1\n", "K;consumo_km_gal;%d.%d\n" % divmod(self.cons10, 10),
               "K;precio_gal;%d\n" % self.precio, "K;velocidad_kmh;%d\n" % self.vel]
        clean = lambda s: s.replace("\r", " ").replace("\n", " ").replace(";", " ")
        for i in sorted(self.cities):
            c = self.cities[i]
            out.append("C;%s;%s;%s;%.5f;%.5f;%d\n" % (i, clean(c["nombre"]), clean(c["depto"]),
                                                       c["lat"], c["lon"], 1 if c["activo"] else 0))
        for i in sorted(self.tolls):
            t = self.tolls[i]
            out.append("P;%s;%s;%.5f;%.5f;%d;%d\n" % (i, clean(t["nombre"]), t["lat"], t["lon"],
                                                      t["tarifa"], 1 if t["activo"] else 0))
        for i in sorted(self.routes):
            r = self.routes[i]
            out.append("R;%s;%s;%s;%d.%d;%d.%02d;%s;%d\n" % (
                i, r["o"], r["d"], *divmod(r["km10"], 10), *divmod(r["h100"], 100),
                "|".join(r["peajes"]), 1 if r["activo"] else 0))
        return "".join(out)


def _file_num(s, scale, lo, hi, what, ln):
    if not NUM_RE.match(s):
        raise InvalidFile("línea %d: %s no es un número" % (ln, what))
    n = _scaled(s, scale, what)
    if not lo <= n <= hi:
        raise InvalidFile("línea %d: %s fuera de rango" % (ln, what))
    return n


def _file_coord(s, lim, what, ln):
    if not NUM_RE.match(s):
        raise InvalidFile("línea %d: %s no es un número" % (ln, what))
    v = float(s)
    if not -lim <= v <= lim:
        raise InvalidFile("línea %d: %s fuera de rango" % (ln, what))
    return v


def _file_act(s, ln):
    if s not in ("0", "1"):
        raise InvalidFile("línea %d: activo debe ser 0 o 1" % ln)
    return s == "1"


def parse_text(text):
    """Texto del archivo -> Data nueva, o InvalidFile."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    d = Data()
    pending = []  # rutas: se validan al final (el orden de lineas no importa)
    seen_k = set()
    for ln, line in enumerate(lines, 1):
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split(";")
        kind = f[0]
        if kind == "K":
            if len(f) != 3:
                raise InvalidFile("línea %d mal formada" % ln)
            if f[1] in seen_k:
                raise InvalidFile("línea %d: parámetro repetido %s" % (ln, f[1]))
            seen_k.add(f[1])
            if f[1] == "consumo_km_gal":
                d.cons10 = _file_num(f[2], 10, 1, 10 ** 6, "consumo_km_gal", ln)
            elif f[1] == "precio_gal":
                if not INT_RE.match(f[2]):
                    raise InvalidFile("línea %d: precio_gal no es entero" % ln)
                d.precio = _file_num(f[2], 1, 0, 10 ** 9, "precio_gal", ln)
            elif f[1] == "velocidad_kmh":
                if not INT_RE.match(f[2]):
                    raise InvalidFile("línea %d: velocidad_kmh no es entera" % ln)
                d.vel = _file_num(f[2], 1, 1, 10 ** 4, "velocidad_kmh", ln)
            else:
                raise InvalidFile("línea %d: parámetro desconocido %s" % (ln, f[1]))
        elif kind == "C":
            if len(f) != 7:
                raise InvalidFile("línea %d mal formada" % ln)
            if not f[1]:
                raise InvalidFile("línea %d: id vacío" % ln)
            if f[1] in d.cities:
                raise InvalidFile("línea %d: ciudad repetida %s" % (ln, f[1]))
            d.cities[f[1]] = {"nombre": f[2], "depto": f[3], "lat": _file_coord(f[4], 90, "lat", ln),
                              "lon": _file_coord(f[5], 180, "lon", ln), "activo": _file_act(f[6], ln)}
        elif kind == "P":
            if len(f) != 7:
                raise InvalidFile("línea %d mal formada" % ln)
            if not f[1]:
                raise InvalidFile("línea %d: id vacío" % ln)
            if f[1] in d.tolls:
                raise InvalidFile("línea %d: peaje repetido %s" % (ln, f[1]))
            if not INT_RE.match(f[5]):
                raise InvalidFile("línea %d: tarifa no es entera" % ln)
            d.tolls[f[1]] = {"nombre": f[2], "lat": _file_coord(f[3], 90, "lat", ln),
                             "lon": _file_coord(f[4], 180, "lon", ln),
                             "tarifa": _file_num(f[5], 1, 0, 10 ** 9, "tarifa", ln), "activo": _file_act(f[6], ln)}
        elif kind == "R":
            if len(f) != 8:
                raise InvalidFile("línea %d mal formada" % ln)
            if not f[1]:
                raise InvalidFile("línea %d: id vacío" % ln)
            if f[1] in d.routes or any(p[0] == f[1] for p in pending):
                raise InvalidFile("línea %d: ruta repetida %s" % (ln, f[1]))
            km10 = _file_num(f[4], 10, 1, 10 ** 7, "km", ln)
            h100 = _file_num(f[5], 100, 1, 10 ** 6, "horas", ln)
            tolls = f[6].split("|") if f[6] else []
            if len(set(tolls)) != len(tolls) or "" in tolls:
                raise InvalidFile("línea %d: lista de peajes inválida" % ln)
            pending.append((f[1], {"o": f[2], "d": f[3], "km10": km10, "h100": h100, "peajes": tolls,
                                   "activo": _file_act(f[7], ln)}, ln))
        else:
            raise InvalidFile("línea %d: tipo de registro desconocido" % ln)
    pairs = set()
    for rid, r, ln in pending:
        if r["o"] == r["d"]:
            raise InvalidFile("línea %d: ruta %s con origen = destino" % (ln, rid))
        for c in (r["o"], r["d"]):
            if c not in d.cities:
                raise InvalidFile("línea %d: ruta %s con ciudad inexistente %s" % (ln, rid, c))
        for t in r["peajes"]:
            if t not in d.tolls:
                raise InvalidFile("línea %d: ruta %s con peaje inexistente %s" % (ln, rid, t))
        pair = frozenset((r["o"], r["d"]))
        if pair in pairs:
            raise InvalidFile("línea %d: ruta repetida entre %s y %s" % (ln, r["o"], r["d"]))
        pairs.add(pair)
        d.routes[rid] = r
    return d


# ---------------------------------------------------------------- motor
class Engine:
    def __init__(self, data_path=None):
        self.data_path = data_path
        self.data = Data()
        self.dirty = False
        self.history = []  # textos serializados previos
        self.shutdown_requested = False
        self._rebuild()

    # ---- grafos
    def _rebuild(self):
        d = self.data
        self.G_distancia = Graph(d.cities)
        self.G_tiempo = Graph(d.cities)
        self.G_combustible = Graph(d.cities)
        self.G_peajes = Graph(d.cities)
        self.G_total = Graph(d.cities)
        # Desempate lexicografico (costo, km): peso = costo * M + km10 con M > suma de TODOS los km10, de modo que ningun
        # camino simple puede cambiar el orden por costo. Si el producto desbordara, se usa solo el costo (igual en el motor C++).
        eff = [r for r in d.routes.values() if d.efectiva(r)]
        self.tie_m = sum(r["km10"] for r in eff) + 1
        if (sum(d.fuel(r) + d.toll_cost(r) for r in eff) + 1) * self.tie_m >= LIM:
            self.tie_m = 0
        m = self.tie_m
        wt = (lambda c, km: c * m + km) if m else (lambda c, km: c)
        for rid, r in d.routes.items():
            if d.efectiva(r):
                self.G_distancia.add_edge(rid, r["o"], r["d"], r["km10"])
                self.G_tiempo.add_edge(rid, r["o"], r["d"], r["h100"])
                self.G_combustible.add_edge(rid, r["o"], r["d"], d.fuel(r))
                # peajes y total: a igual costo gana el camino mas corto
                self.G_peajes.add_edge(rid, r["o"], r["d"], wt(d.toll_cost(r), r["km10"]))
                self.G_total.add_edge(rid, r["o"], r["d"], wt(d.fuel(r) + d.toll_cost(r), r["km10"]))
        for g in (self.G_distancia, self.G_tiempo, self.G_combustible, self.G_peajes, self.G_total):
            g.sort()

    # ---- respuestas
    def _state(self):
        d = self.data
        return {"dirty": self.dirty, "ciudades": len(d.cities), "peajes": len(d.tolls), "rutas": len(d.routes)}

    def _err(self, msg):
        return {"ok": False, "error": msg, "state": self._state()}

    def _ok(self, result=None):
        return {"ok": True, "result": {} if result is None else result, "state": self._state()}

    # ---- items
    def _city_item(self, i):
        c = self.data.cities[i]
        return {"id": i, "nombre": c["nombre"], "departamento": c["depto"], "lat": c["lat"], "lon": c["lon"],
                "activo": c["activo"], "grado": self.data.degree(i)}

    def _toll_item(self, i):
        t = self.data.tolls[i]
        return {"id": i, "nombre": t["nombre"], "lat": t["lat"], "lon": t["lon"], "tarifa": t["tarifa"],
                "activo": t["activo"]}

    def _route_item(self, i):
        d = self.data
        r = d.routes[i]
        return {"id": i, "origen": r["o"], "destino": r["d"], "km": _fmt(r["km10"], 10),
                "horas": _fmt(r["h100"], 100), "peajes": list(r["peajes"]), "activo": r["activo"],
                "efectiva": d.efectiva(r), "combustible": d.fuel(r), "peajes_costo": d.toll_cost(r)}

    def _item(self, kind, i):
        return {"city": self._city_item, "toll": self._toll_item, "route": self._route_item}[kind](i)

    def _table(self, kind):
        if kind not in KINDS:
            raise PeraError("Campo inválido: kind")
        return {"city": self.data.cities, "toll": self.data.tolls, "route": self.data.routes}[kind]

    @staticmethod
    def _missing(kind, i):
        return PeraError({"city": "La ciudad %s no existe", "toll": "El peaje %s no existe",
                          "route": "La ruta %s no existe"}[kind] % i)

    def _existing(self, req):
        kind = req.get("kind")
        tab = self._table(kind)
        i = _text(req.get("id"), "id") if req.get("id") is not None else ""
        if i not in tab:
            raise self._missing(kind, i)
        return kind, i, tab

    # ---- despacho
    def handle(self, request):
        try:
            if not isinstance(request, dict):
                raise PeraError("La solicitud debe ser un objeto JSON")
            action = request.get("action")
            name = action if isinstance(action, str) else ""
            fn = getattr(self, "_do_" + name, None) if re.match(r"^[a-z_]+$", name) else None
            if fn is None:
                raise PeraError("Acción desconocida: %s" % name)
            mutating = name in ("create", "update", "delete", "toggle", "set_params")
            before = self.data.dumps() if mutating else None
            response = fn(request)
            if mutating:
                self.history.append(before)
                del self.history[:-HISTORY_MAX]
                self.dirty = True
                response["state"] = self._state()
            return response
        except PeraError as e:
            self._rebuild_if_needed()
            return self._err(str(e))
        except Exception as e:  # nunca propagar al proceso
            self._rebuild_if_needed()
            return self._err("Error interno: %s" % e)

    def _rebuild_if_needed(self):
        pass  # los cambios solo se aplican tras validar; no hay estado a medias

    # ---- acciones simples
    def _do_ping(self, r):
        return self._ok({"backend": "python", "protocol": PROTOCOL})

    def _do_state(self, r):
        return self._ok()

    def _do_shutdown(self, r):
        self.shutdown_requested = True
        return self._ok()

    def _do_reset(self, r):
        self.data = Data()
        self.history = []
        self.dirty = False
        self._rebuild()
        return self._ok()

    def _do_params(self, r):
        return self._ok(self._params())

    def _params(self):
        d = self.data
        return {"consumo_km_gal": _fmt(d.cons10, 10), "precio_gal": d.precio, "velocidad_kmh": d.vel}

    def _do_set_params(self, r):
        d = self.data
        cons, precio, vel = d.cons10, d.precio, d.vel
        if "consumo_km_gal" in r:
            cons = _ranged(r["consumo_km_gal"], 10, "consumo_km_gal", 1, 10 ** 6)
        if "precio_gal" in r:
            precio = self._whole(r["precio_gal"], "precio_gal", 0, 10 ** 9)
        if "velocidad_kmh" in r:
            vel = self._whole(r["velocidad_kmh"], "velocidad_kmh", 1, 10 ** 4)
        d.cons10, d.precio, d.vel = cons, precio, vel
        self._rebuild()
        return self._ok(self._params())

    @staticmethod
    def _whole(v, field, lo, hi):
        n = _scaled(v, 1, field)
        if _scaled(v, 1000, field) != n * 1000:
            raise PeraError("Campo inválido: %s" % field)
        if not lo <= n <= hi:
            raise PeraError("Campo inválido: %s" % field)
        return n

    def _path(self, r):
        p = r.get("path") or self.data_path
        if not isinstance(p, str) or not p:
            raise PeraError("Falta la ruta del archivo")
        return p

    def _do_save(self, r):
        path = self._path(r)
        text = self.data.dumps()
        d = os.path.dirname(os.path.abspath(path))
        tmp = None
        try:
            os.makedirs(d, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=d, prefix=".pera_", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            os.replace(tmp, path)
        except OSError as e:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)
            raise PeraError("No se pudo guardar: %s" % (e.strerror or e))
        self.dirty = False
        return self._ok({"path": path, "ciudades": len(self.data.cities), "peajes": len(self.data.tolls),
                         "rutas": len(self.data.routes)})

    def _do_load(self, r):
        path = self._path(r)
        try:
            with open(path, encoding="utf-8", newline="") as f:
                text = f.read()
        except OSError as e:
            raise InvalidFile("no se pudo leer (%s)" % (e.strerror or e))
        except UnicodeDecodeError:
            raise InvalidFile("no es UTF-8")
        new = parse_text(text)  # si falla, el estado actual no se toca
        self.data = new
        self.history = []
        self.dirty = False
        self._rebuild()
        return self._ok({"path": path, "ciudades": len(new.cities), "peajes": len(new.tolls),
                         "rutas": len(new.routes)})

    def _do_undo(self, r):
        if not self.history:
            raise PeraError("No hay nada que deshacer")
        self.data = parse_text(self.history.pop())
        self.dirty = True
        self._rebuild()
        return self._ok()

    # ---- CRUD
    def _do_list(self, r):
        kind = r.get("kind")
        tab = self._table(kind)
        return self._ok({"items": [self._item(kind, i) for i in sorted(tab)]})

    def _do_get(self, r):
        kind, i, _ = self._existing(r)
        return self._ok(self._item(kind, i))

    def _next_id(self, tab, prefix):
        n = 0
        for k in tab:
            m = re.match(r"^%s(\d+)$" % prefix, k)
            if m:
                n = max(n, int(m.group(1)))
        return "%s%03d" % (prefix, n + 1)

    def _do_create(self, r):
        kind = r.get("kind")
        tab = self._table(kind)
        i = r.get("id")
        if kind == "city":
            if i is None or str(i).strip() == "":
                raise PeraError("Campo inválido: id")
            i = _ident(i)
        elif i is None or str(i).strip() == "":
            i = self._next_id(tab, "P" if kind == "toll" else "R")
        else:
            i = _ident(i)
        if i in tab:
            raise PeraError({"city": "La ciudad %s ya existe", "toll": "El peaje %s ya existe",
                             "route": "La ruta %s ya existe"}[kind] % i)
        rec = self._build(kind, r, None, i)
        tab[i] = rec
        self._rebuild()
        return self._ok(self._item(kind, i))

    def _do_update(self, r):
        kind, i, tab = self._existing(r)
        rec = self._build(kind, r, tab[i], i)
        tab[i] = rec
        self._rebuild()
        return self._ok(self._item(kind, i))

    def _build(self, kind, r, old, i):
        """Registro nuevo (create: old=None, campos requeridos) o copia de old con los campos enviados."""
        def get(name, conv, default):
            if name in r:
                return conv(r[name])
            if old is not None:
                return old[{"depto": "depto", "o": "o", "d": "d"}.get(name, name)]
            return default

        if kind == "city":
            return {"nombre": get("nombre", lambda v: _text(v, "nombre"), ""),
                    "depto": self._pick(r, old, "departamento", "depto", lambda v: _text(v, "departamento"), ""),
                    "lat": self._coord(r, old, "lat", 90), "lon": self._coord(r, old, "lon", 180),
                    "activo": self._pick(r, old, "activo", "activo", lambda v: _bool(v, "activo"), True)}
        if kind == "toll":
            return {"nombre": get("nombre", lambda v: _text(v, "nombre"), ""),
                    "lat": self._coord(r, old, "lat", 90), "lon": self._coord(r, old, "lon", 180),
                    "tarifa": self._pick(r, old, "tarifa", "tarifa",
                                         lambda v: _ranged(v, 1, "tarifa", 0, 10 ** 9), 0),
                    "activo": self._pick(r, old, "activo", "activo", lambda v: _bool(v, "activo"), True)}
        # ruta
        if old is None:
            for need in ("origen", "destino", "km", "horas"):
                if r.get(need) is None:
                    raise PeraError("Campo inválido: %s" % need)
        o = self._pick(r, old, "origen", "o", lambda v: _ident(v, "origen"), None)
        dd = self._pick(r, old, "destino", "d", lambda v: _ident(v, "destino"), None)
        km10 = self._pick(r, old, "km", "km10", lambda v: _ranged(v, 10, "km", 1, 10 ** 7), None)
        h100 = self._pick(r, old, "horas", "h100", lambda v: _ranged(v, 100, "horas", 1, 10 ** 6), None)
        tolls = self._pick(r, old, "peajes", "peajes", self._toll_list, [])
        act = self._pick(r, old, "activo", "activo", lambda v: _bool(v, "activo"), True)
        if o == dd:
            raise PeraError("Una ruta necesita dos ciudades distintas")
        for c in (o, dd):
            if c not in self.data.cities:
                raise PeraError("La ciudad %s no existe" % c)
        for t in tolls:
            if t not in self.data.tolls:
                raise PeraError("El peaje %s no existe" % t)
        for rid, x in self.data.routes.items():
            if rid != i and {x["o"], x["d"]} == {o, dd}:
                raise PeraError("La ruta entre %s y %s ya existe" % (o, dd))
        return {"o": o, "d": dd, "km10": km10, "h100": h100, "peajes": list(tolls), "activo": act}

    @staticmethod
    def _pick(r, old, name, key, conv, default):
        if name in r:
            return conv(r[name])
        return old[key] if old is not None else default

    @staticmethod
    def _toll_list(v):
        if isinstance(v, list):
            items = [str(x) for x in v]
        elif v is None or v == "":
            items = []
        elif isinstance(v, str):
            items = v.split("|")
        else:
            raise PeraError("Campo inválido: peajes")
        items = [x.strip() for x in items]
        if "" in items or len(set(items)) != len(items):
            raise PeraError("Campo inválido: peajes")
        return items

    @staticmethod
    def _coord(r, old, name, lim):
        if name in r:
            v = _scaled(r[name], 100000, name)
            if abs(v) > lim * 100000:
                raise PeraError("Campo inválido: %s" % name)
            return float(Decimal(v) / 100000)
        return old[name] if old is not None else 0.0

    def _do_delete(self, r):
        kind, i, tab = self._existing(r)
        d = self.data
        if kind == "city":
            gone = sorted(k for k, x in d.routes.items() if i in (x["o"], x["d"]))
            for k in gone:
                del d.routes[k]
            del tab[i]
            res = {"id": i, "rutas_eliminadas": gone}
        else:
            del tab[i]
            if kind == "toll":
                for x in d.routes.values():
                    if i in x["peajes"]:
                        x["peajes"].remove(i)
            res = {"id": i}
        self._rebuild()
        return self._ok(res)

    def _do_toggle(self, r):
        kind, i, tab = self._existing(r)
        tab[i]["activo"] = not tab[i]["activo"]
        self._rebuild()
        return self._ok(self._item(kind, i))

    # ---- consulta
    def _do_query(self, r):
        d = self.data
        a, b = (_text(r.get(k), k) if r.get(k) is not None else "" for k in ("from", "to"))
        for c in (a, b):
            if c not in d.cities:
                raise PeraError("La ciudad %s no existe" % c)
            if not d.cities[c]["activo"]:
                raise PeraError("Ciudad inactiva: %s" % c)
        res = {"from": a, "to": b, "alcanzable": True}
        if a == b:
            zero = {"km": 0.0, "horas": 0.0, "combustible": 0, "peajes": 0}
            res["criterios"] = {k: {"ciudades": [a], "rutas": [], "totales": dict(zero)}
                                for k in ("distancia", "tiempo", "combustible", "peajes", "total")}
            return self._ok(res)
        crit = {}
        for name, g in (("distancia", self.G_distancia), ("tiempo", self.G_tiempo),
                        ("combustible", self.G_combustible), ("peajes", self.G_peajes), ("total", self.G_total)):
            p = g.dijkstra(a, b)
            if p is None:
                return self._ok({"from": a, "to": b, "alcanzable": False})
            cities, routes = p
            rs = [d.routes[x] for x in routes]
            crit[name] = {"ciudades": cities, "rutas": routes, "totales": {
                "km": _fmt(sum(x["km10"] for x in rs), 10), "horas": _fmt(sum(x["h100"] for x in rs), 100),
                "combustible": sum(d.fuel(x) for x in rs), "peajes": sum(d.toll_cost(x) for x in rs)}}
        res["criterios"] = crit
        return self._ok(res)

    # ---- estadisticas
    def _do_stats(self, r):
        d = self.data
        eff = sorted((k for k, x in d.routes.items() if d.efectiva(x)))
        conteos = {"ciudades": len(d.cities), "ciudades_activas": sum(1 for c in d.cities.values() if c["activo"]),
                   "peajes": len(d.tolls), "peajes_activos": sum(1 for t in d.tolls.values() if t["activo"]),
                   "rutas": len(d.routes), "rutas_activas": sum(1 for x in d.routes.values() if x["activo"]),
                   "rutas_efectivas": len(eff), "componentes": self._components()}
        crit = {"distancia": (lambda x: x["km10"], 10), "tiempo": (lambda x: x["h100"], 100),
                "combustible": (d.fuel, 1), "peajes": (d.toll_cost, 1)}
        grafos, top = {}, {}
        for name, (fn, sc) in crit.items():
            vals = {k: fn(d.routes[k]) for k in eff}
            grafos[name] = self._summary(sorted(vals.values()), sc)
            order = sorted(eff, key=lambda k: (-vals[k], k))[:5]
            top[name] = [{"id": k, "origen": d.routes[k]["o"], "destino": d.routes[k]["d"],
                          "valor": self._num(vals[k], sc)} for k in order]
        pairs = {}
        for k in eff:
            x = d.routes[k]
            deps = {d.cities[x["o"]]["depto"], d.cities[x["d"]]["depto"]}
            for t in x["peajes"]:
                if d.tolls[t]["activo"]:
                    for dep in deps:
                        pairs[(dep, t)] = True
        per = {}
        for dep, t in pairs:
            c = per.setdefault(dep, [0, 0])
            c[0] += 1
            c[1] += d.tolls[t]["tarifa"]
        peajes_dep = [{"departamento": k, "cantidad": v[0], "tarifa_total": v[1]}
                      for k, v in sorted(per.items(), key=lambda kv: (-kv[1][0], kv[0]))]
        grados = sorted(((d.degree(i), i) for i in d.cities), key=lambda t: (-t[0], t[1]))
        return self._ok({"conteos": conteos, "grafos": grafos, "peajes_por_departamento": peajes_dep,
                         "grados": [{"id": i, "nombre": d.cities[i]["nombre"], "grado": g} for g, i in grados],
                         "top_rutas": top})

    @staticmethod
    def _num(v, sc):
        return v if sc == 1 else v / sc

    def _summary(self, vals, sc):
        n = len(vals)
        out = lambda v: self._num(v, sc)
        if n == 0:
            return {"n": 0, "min": out(0), "max": out(0), "media": 0.0, "mediana": 0.0, "total": out(0),
                    "hist": {"limites": [0.0] * 11, "cuentas": [0] * 10}}
        lo, hi, tot = vals[0], vals[-1], sum(vals)
        media = _half_up(tot * 100, n * sc) / 100
        mediana = vals[n // 2] / sc if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / (2 * sc)
        cuentas = [0] * 10
        for v in vals:
            cuentas[0 if hi == lo else min(9, (v - lo) * 10 // (hi - lo))] += 1
        limites = [_half_up((lo * 10 + (hi - lo) * i) * 100, 10 * sc) / 100 for i in range(11)]
        return {"n": n, "min": out(lo), "max": out(hi), "media": media, "mediana": mediana, "total": out(tot),
                "hist": {"limites": limites, "cuentas": cuentas}}

    def _components(self):
        d = self.data
        adj = self.G_distancia.adj
        seen, n = set(), 0
        for c in sorted(d.cities):
            if not d.cities[c]["activo"] or c in seen:
                continue
            n += 1
            stack = [c]
            seen.add(c)
            while stack:
                u = stack.pop()
                for _, v, _ in adj[u]:
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
        return n


def serve(engine, inp, out):
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            resp = engine._err("JSON inválido")
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
        sys.stderr.write("Uso: pera_engine.py --api [--data ruta]\n")
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
