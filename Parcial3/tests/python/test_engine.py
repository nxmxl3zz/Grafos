"""Pruebas del motor Python PERA (pera_engine). Desde la raiz del proyecto:
    python3 -I tests/python/test_engine.py
"""
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "src", "python")
MINI = os.path.join(ROOT, "tests", "fixtures", "mini.csv")
sys.path.insert(0, SRC)

import pera_engine  # noqa: E402
from pera_engine import Engine  # noqa: E402

BOG, TUN, IBA, VIL, LET = "11001", "15001", "73001", "50001", "91001"


def mini_sorted_bytes():
    """mini.csv tal cual, pero con las lineas C/P/R en orden de id (el guardado es ordenado por contrato;
    el fixture trae 73001 antes de 50001)."""
    with open(MINI, "rb") as f:
        lines = f.read().decode("utf-8").splitlines(True)
    head = [x for x in lines if x[0] in "#K"]
    body = sorted((x for x in lines if x[0] in "CPR"), key=lambda x: ("CPR".index(x[0]), x.split(";")[1]))
    return "".join(head + body).encode("utf-8")


def mini():
    e = Engine()
    r = e.handle({"action": "load", "path": MINI})
    assert r["ok"], r
    return e


def ok(e, **req):
    r = e.handle(req)
    assert r["ok"], r
    return r["result"]


def err(e, **req):
    r = e.handle(req)
    assert not r["ok"], r
    return r["error"]


def city(e, id_, **kw):
    d = dict(action="create", kind="city", id=id_, nombre=id_, departamento="D", lat=1.0, lon=2.0)
    d.update(kw)
    return e.handle(d)


def route(e, o, d, km=10, horas=1, **kw):
    q = dict(action="create", kind="route", origen=o, destino=d, km=km, horas=horas)
    q.update(kw)
    return e.handle(q)


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.e = mini()

    def crit(self, a, b):
        return ok(self.e, action="query", **{"from": a, "to": b})["criterios"]

    def test_bogota_villavicencio(self):
        c = self.crit(BOG, VIL)
        for k in ("distancia", "tiempo", "combustible"):
            self.assertEqual(c[k]["ciudades"], [BOG, VIL])
            self.assertEqual(c[k]["rutas"], ["R003"])
            self.assertEqual(c[k]["totales"], {"km": 86.0, "horas": 2.2, "combustible": 34400, "peajes": 20000})
        p = c["peajes"]
        self.assertEqual(p["ciudades"], [BOG, TUN, VIL])
        self.assertEqual(p["rutas"], ["R001", "R004"])
        self.assertEqual(p["totales"], {"km": 377.0, "horas": 8.25, "combustible": 150800, "peajes": 12900})

    def test_alcanzable_flag_and_echo(self):
        r = ok(self.e, action="query", **{"from": BOG, "to": VIL})
        self.assertTrue(r["alcanzable"])
        self.assertEqual((r["from"], r["to"]), (BOG, VIL))

    def test_leticia_isolated(self):
        r = ok(self.e, action="query", **{"from": BOG, "to": LET})
        self.assertFalse(r["alcanzable"])
        self.assertNotIn("criterios", r)

    def test_inactive_toll_not_added(self):
        c = self.crit(BOG, IBA)
        self.assertEqual(c["distancia"]["rutas"], ["R002"])
        self.assertEqual(c["distancia"]["totales"]["peajes"], 25200)

    def test_inactive_route_ignored(self):
        c = self.crit(TUN, IBA)
        self.assertEqual(c["distancia"]["rutas"], ["R001", "R002"])
        self.assertEqual(c["distancia"]["totales"]["km"], 342.0)

    def test_same_city(self):
        c = self.crit(BOG, BOG)
        for k in ("distancia", "tiempo", "combustible", "peajes"):
            self.assertEqual(c[k]["ciudades"], [BOG])
            self.assertEqual(c[k]["rutas"], [])
            self.assertEqual(c[k]["totales"], {"km": 0, "horas": 0, "combustible": 0, "peajes": 0})

    def test_errors(self):
        self.assertEqual(err(self.e, action="query", **{"from": "99999", "to": BOG}), "La ciudad 99999 no existe")
        ok(self.e, action="toggle", kind="city", id=TUN)
        self.assertEqual(err(self.e, action="query", **{"from": TUN, "to": BOG}), "Ciudad inactiva: " + TUN)
        self.assertEqual(err(self.e, action="query", **{"from": BOG, "to": TUN}), "Ciudad inactiva: " + TUN)

    def test_inactive_city_in_middle_detours(self):
        ok(self.e, action="toggle", kind="city", id=BOG)
        c = self.crit(TUN, IBA)  # R006 inactiva, Bogota inactiva, via Villavicencio
        self.assertEqual(c["distancia"]["rutas"], ["R004", "R005"])
        self.assertEqual(c["distancia"]["ciudades"], [TUN, VIL, IBA])

    def test_tie_break_deterministic(self):
        e = Engine()
        for c in "ABCD":
            self.assertTrue(city(e, c)["ok"])
        for rid, o, d in (("R001", "A", "C"), ("R002", "A", "B"), ("R003", "B", "D"), ("R004", "C", "D")):
            self.assertTrue(route(e, o, d, id=rid)["ok"])
        # A-C y A-B cuestan igual: sale primero B (id de ciudad menor), D se fija por B
        r = ok(e, action="query", **{"from": "A", "to": "D"})["criterios"]["distancia"]
        self.assertEqual(r["ciudades"], ["A", "B", "D"])
        self.assertEqual(r["rutas"], ["R002", "R003"])

    def test_fuel_params_change(self):
        ok(self.e, action="set_params", consumo_km_gal=20, precio_gal=10000, velocidad_kmh=60)
        self.assertEqual(ok(self.e, action="params"), {"consumo_km_gal": 20.0, "precio_gal": 10000, "velocidad_kmh": 60})
        self.assertEqual(self.crit(BOG, VIL)["distancia"]["totales"]["combustible"], 43000)
        # redondeo mitades hacia arriba: 86.0/ 40.0 * 16000 exacto; 147.0 km a 40 -> 58800
        r = ok(self.e, action="get", kind="route", id="R001")
        self.assertEqual(r["combustible"], 73500)


class CrudTests(unittest.TestCase):
    def setUp(self):
        self.e = mini()

    def test_counts_state(self):
        r = self.e.handle({"action": "state"})
        self.assertEqual(r["state"], {"dirty": False, "ciudades": 5, "peajes": 5, "rutas": 6})
        self.assertEqual(ok(self.e, action="ping"), {"backend": "python", "protocol": "1"})

    def test_list_and_get_items(self):
        items = ok(self.e, action="list", kind="city")["items"]
        self.assertEqual([i["id"] for i in items], sorted([BOG, TUN, VIL, IBA, LET]))
        self.assertEqual(ok(self.e, action="get", kind="city", id=BOG),
                         {"id": BOG, "nombre": "Bogotá D.C.", "departamento": "Bogotá D.C.",
                          "lat": 4.711, "lon": -74.0721, "activo": True, "grado": 3})
        self.assertEqual(ok(self.e, action="get", kind="toll", id="P005"),
                         {"id": "P005", "nombre": "Peaje Inactivo", "lat": 4.4, "lon": -74.6,
                          "tarifa": 9000, "activo": False})
        self.assertEqual(ok(self.e, action="get", kind="route", id="R002"),
                         {"id": "R002", "origen": BOG, "destino": IBA, "km": 195.0, "horas": 3.6,
                          "peajes": ["P002", "P003", "P005"], "activo": True, "efectiva": True,
                          "combustible": 78000, "peajes_costo": 25200})
        self.assertFalse(ok(self.e, action="get", kind="route", id="R006")["efectiva"])

    def test_reverse_duplicate_rejected(self):
        self.assertEqual(route(self.e, TUN, BOG)["error"], "La ruta entre %s y %s ya existe" % (TUN, BOG))
        # tambien con la ruta inactiva R006
        self.assertEqual(route(self.e, IBA, TUN)["error"], "La ruta entre %s y %s ya existe" % (IBA, TUN))

    def test_route_validation(self):
        self.assertEqual(route(self.e, BOG, BOG)["error"], "Una ruta necesita dos ciudades distintas")
        self.assertEqual(route(self.e, BOG, "0")["error"], "La ciudad 0 no existe")
        self.assertEqual(route(self.e, LET, BOG, peajes="PXXX")["error"], "El peaje PXXX no existe")
        self.assertEqual(route(self.e, LET, BOG, km="abc")["error"], "Campo inválido: km")
        self.assertEqual(route(self.e, LET, BOG, id="R001")["error"], "La ruta R001 ya existe")

    def test_create_assigns_ids(self):
        r = route(self.e, LET, BOG, km="500.5", horas="12.25", peajes="P001|P002")
        self.assertTrue(r["ok"])
        self.assertEqual(r["result"]["id"], "R007")
        self.assertEqual(r["result"]["km"], 500.5)
        self.assertEqual(r["result"]["combustible"], 200200)
        self.assertEqual(r["result"]["peajes_costo"], 24700)
        t = ok(self.e, action="create", kind="toll", nombre="Nuevo", lat=1, lon=2, tarifa=5000)
        self.assertEqual(t["id"], "P006")
        self.assertTrue(t["activo"])
        self.assertEqual(self.e.handle({"action": "state"})["state"]["rutas"], 7)

    def test_city_requires_id_and_unique(self):
        self.assertEqual(err(self.e, action="create", kind="city", nombre="X"), "Campo inválido: id")
        self.assertEqual(city(self.e, BOG)["error"], "La ciudad %s ya existe" % BOG)
        self.assertEqual(err(self.e, action="get", kind="city", id="1"), "La ciudad 1 no existe")
        self.assertEqual(err(self.e, action="get", kind="toll", id="P9"), "El peaje P9 no existe")
        self.assertEqual(err(self.e, action="get", kind="route", id="R9"), "La ruta R9 no existe")
        self.assertEqual(err(self.e, action="list", kind="x"), "Campo inválido: kind")
        self.assertEqual(err(self.e, action="zzz"), "Acción desconocida: zzz")

    def test_delete_city_cascades(self):
        r = ok(self.e, action="delete", kind="city", id=VIL)
        self.assertEqual(r, {"id": VIL, "rutas_eliminadas": ["R003", "R004", "R005"]})
        st = self.e.handle({"action": "state"})["state"]
        self.assertEqual((st["ciudades"], st["rutas"]), (4, 3))
        self.assertTrue(st["dirty"])

    def test_delete_toll_removes_from_routes(self):
        self.assertEqual(ok(self.e, action="delete", kind="toll", id="P001"), {"id": "P001"})
        self.assertEqual(ok(self.e, action="get", kind="route", id="R001")["peajes"], [])
        c = ok(self.e, action="query", **{"from": BOG, "to": TUN})["criterios"]
        self.assertEqual(c["peajes"]["totales"]["peajes"], 0)

    def test_delete_route_and_missing(self):
        self.assertEqual(ok(self.e, action="delete", kind="route", id="R003"), {"id": "R003"})
        c = ok(self.e, action="query", **{"from": BOG, "to": VIL})["criterios"]
        self.assertEqual(c["distancia"]["rutas"], ["R001", "R004"])
        self.assertEqual(err(self.e, action="delete", kind="route", id="R003"), "La ruta R003 no existe")

    def test_toggle_city_makes_routes_not_effective(self):
        r = ok(self.e, action="toggle", kind="city", id=BOG)
        self.assertFalse(r["activo"])
        self.assertFalse(ok(self.e, action="get", kind="route", id="R001")["efectiva"])
        self.assertTrue(ok(self.e, action="get", kind="route", id="R001")["activo"])
        self.assertEqual(ok(self.e, action="get", kind="city", id=BOG)["grado"], 0)
        r = ok(self.e, action="toggle", kind="city", id=BOG)
        self.assertTrue(ok(self.e, action="get", kind="route", id="R001")["efectiva"])
        r = ok(self.e, action="toggle", kind="route", id="R006")
        self.assertTrue(r["activo"] and r["efectiva"])

    def test_update(self):
        r = ok(self.e, action="update", kind="route", id="R003", km="100.0", peajes="")
        self.assertEqual((r["km"], r["peajes"], r["horas"], r["combustible"]), (100.0, [], 2.2, 40000))
        r = ok(self.e, action="update", kind="city", id=LET, nombre="Leticia X", id_="ignorado")
        self.assertEqual(r["nombre"], "Leticia X")
        r = ok(self.e, action="update", kind="toll", id="P004", tarifa=1)
        self.assertEqual(r["tarifa"], 1)
        self.assertEqual(err(self.e, action="update", kind="route", id="R003", destino=BOG),
                         "Una ruta necesita dos ciudades distintas")
        self.assertEqual(err(self.e, action="update", kind="route", id="R003", destino=TUN),
                         "La ruta entre %s y %s ya existe" % (BOG, TUN))
        self.assertEqual(err(self.e, action="update", kind="toll", id="P004", tarifa="x"), "Campo inválido: tarifa")

    def test_graph_sync_with_update(self):
        ok(self.e, action="update", kind="route", id="R003", km=1000)
        c = ok(self.e, action="query", **{"from": BOG, "to": VIL})["criterios"]
        self.assertEqual(c["distancia"]["rutas"], ["R001", "R004"])
        ok(self.e, action="update", kind="toll", id="P001", tarifa=99999)
        self.assertEqual(ok(self.e, action="get", kind="route", id="R001")["peajes_costo"], 99999)
        c = ok(self.e, action="query", **{"from": BOG, "to": TUN})["criterios"]
        self.assertEqual(c["peajes"]["rutas"], ["R003", "R004"])
        self.assertEqual(c["peajes"]["totales"]["peajes"], 20000)

    def test_internal_graphs_are_adjacency_lists(self):
        g = self.e.G_distancia
        self.assertEqual([(rid, n, w) for rid, n, w in g.adj[BOG]],
                         [("R001", TUN, 1470), ("R002", IBA, 1950), ("R003", VIL, 860)])
        self.assertEqual(g.adj[LET], [])
        self.assertEqual(self.e.G_combustible.adj[BOG][0], ("R001", TUN, 58800))
        rid, to, w = self.e.G_peajes.adj[BOG][1]
        self.assertEqual((rid, to, divmod(w, self.e.tie_m)), ("R002", IBA, (25200, 1950)))


class UndoTests(unittest.TestCase):
    def setUp(self):
        self.e = mini()
        self.base = self.snap()

    def snap(self):
        return (json.dumps([ok(self.e, action="list", kind=k)["items"] for k in ("city", "toll", "route")],
                           sort_keys=True), json.dumps(ok(self.e, action="params")))

    def check_undo(self, **req):
        ok(self.e, **req)
        self.assertNotEqual(self.snap(), self.base)
        r = self.e.handle({"action": "undo"})
        self.assertTrue(r["ok"])
        self.assertTrue(r["state"]["dirty"])
        self.assertEqual(self.snap(), self.base)
        # los grafos tambien se restauran
        c = ok(self.e, action="query", **{"from": BOG, "to": VIL})["criterios"]
        self.assertEqual(c["distancia"]["rutas"], ["R003"])

    def test_undo_each(self):
        self.check_undo(action="create", kind="city", id="1", nombre="x", departamento="y", lat=1, lon=1)
        self.check_undo(action="create", kind="toll", nombre="x", lat=1, lon=1, tarifa=1)
        self.check_undo(action="create", kind="route", origen=LET, destino=BOG, km=1, horas=1)
        self.check_undo(action="update", kind="route", id="R003", km=900)
        self.check_undo(action="delete", kind="city", id=VIL)
        self.check_undo(action="delete", kind="toll", id="P004")
        self.check_undo(action="delete", kind="route", id="R003")
        self.check_undo(action="toggle", kind="city", id=VIL)
        self.check_undo(action="set_params", consumo_km_gal=10, precio_gal=1, velocidad_kmh=1)

    def test_undo_empty_and_not_recorded_failures(self):
        self.assertEqual(err(self.e, action="undo"), "No hay nada que deshacer")
        self.e.handle({"action": "delete", "kind": "route", "id": "R999"})
        self.assertEqual(err(self.e, action="undo"), "No hay nada que deshacer")

    def test_undo_limit_200(self):
        for i in range(210):
            ok(self.e, action="toggle", kind="city", id=LET)
        n = 0
        while self.e.handle({"action": "undo"})["ok"]:
            n += 1
        self.assertEqual(n, 200)

    def test_save_clears_dirty_then_undo_dirty(self):
        ok(self.e, action="toggle", kind="city", id=LET)
        with tempfile.TemporaryDirectory() as d:
            ok(self.e, action="save", path=os.path.join(d, "x.csv"))
            self.assertFalse(self.e.handle({"action": "state"})["state"]["dirty"])
        self.assertTrue(self.e.handle({"action": "undo"})["state"]["dirty"])


class PersistenceTests(unittest.TestCase):
    def test_round_trip_byte_identical(self):
        # un archivo ya ordenado se reproduce byte a byte
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "sorted.csv")
            with open(src, "wb") as f:
                f.write(mini_sorted_bytes())
            e0 = Engine()
            ok(e0, action="load", path=src)
            ok(e0, action="save", path=os.path.join(d, "again.csv"))
            with open(src, "rb") as a, open(os.path.join(d, "again.csv"), "rb") as b:
                self.assertEqual(a.read(), b.read())
        e = mini()
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "out.csv")
            ok(e, action="save", path=p)
            with open(p, "rb") as b:
                self.assertEqual(mini_sorted_bytes(), b.read())
            e2 = Engine()
            ok(e2, action="load", path=p)
            p2 = os.path.join(d, "out2.csv")
            ok(e2, action="save", path=p2)
            with open(p, "rb") as a, open(p2, "rb") as b:
                self.assertEqual(a.read(), b.read())

    def write(self, d, text, name="f.csv"):
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return p

    def test_corrupt_leaves_state_intact(self):
        e = mini()
        before = ok(e, action="list", kind="route")
        bad = {
            "linea": "# PERA v1\nC;1;x\n",
            "ciudad repetida": "C;1;a;d;1;1;1\nC;1;b;d;1;1;1\n",
            "ruta sin ciudad": "C;1;a;d;1;1;1\nR;R1;1;2;1.0;1.0;;1\n",
            "peaje inexistente": "C;1;a;d;1;1;1\nC;2;b;d;1;1;1\nR;R1;1;2;1.0;1.0;P9;1\n",
            "origen=destino": "C;1;a;d;1;1;1\nR;R1;1;1;1.0;1.0;;1\n",
            "par repetido": "C;1;a;d;1;1;1\nC;2;b;d;1;1;1\nR;R1;1;2;1.0;1.0;;1\nR;R2;2;1;1.0;1.0;;1\n",
            "rango": "C;1;a;d;99;1;1\n",
            "numero": "K;precio_gal;abc\n",
            "activo": "C;1;a;d;1;1;2\n",
            "tipo": "Z;1\n",
            "peaje repetido": "P;P1;a;1;1;1;1\nP;P1;b;1;1;1;1\n",
        }
        with tempfile.TemporaryDirectory() as d:
            for name, text in bad.items():
                r = e.handle({"action": "load", "path": self.write(d, text)})
                self.assertFalse(r["ok"], name)
                self.assertTrue(r["error"].startswith("Archivo inválido: "), (name, r["error"]))
                self.assertEqual(ok(e, action="list", kind="route"), before, name)
            r = e.handle({"action": "load", "path": os.path.join(d, "nope.csv")})
            self.assertFalse(r["ok"])
            with open(os.path.join(d, "bin.csv"), "wb") as f:
                f.write(b"\xff\xfe\x00")
            self.assertFalse(e.handle({"action": "load", "path": os.path.join(d, "bin.csv")})["ok"])
            self.assertEqual(e.handle({"action": "state"})["state"]["ciudades"], 5)

    def test_empty_file_valid(self):
        e = mini()
        with tempfile.TemporaryDirectory() as d:
            ok(e, action="load", path=self.write(d, ""))
            self.assertEqual(e.handle({"action": "state"})["state"], {"dirty": False, "ciudades": 0, "peajes": 0, "rutas": 0})
            self.assertEqual(ok(e, action="params"), {"consumo_km_gal": 40.0, "precio_gal": 16000, "velocidad_kmh": 55})
            ok(e, action="save", path=os.path.join(d, "o.csv"))
            with open(os.path.join(d, "o.csv"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "# PERA v1\nK;consumo_km_gal;40.0\nK;precio_gal;16000\nK;velocidad_kmh;55\n")
            ok(e, action="load", path=self.write(d, "# solo comentario\n\n"))
            st = ok(e, action="stats")
            self.assertEqual(st["conteos"]["componentes"], 0)

    def test_crlf_and_unsorted_input_saved_sorted(self):
        text = ("# PERA v1\r\nK;precio_gal;1000\r\n\r\nC;2;b;d;1;1;1\r\nC;1;a;d;1.5;-1;0\r\n"
                "R;R2;1;2;12.34;1.005;;1\r\n")
        e = Engine()
        with tempfile.TemporaryDirectory() as d:
            ok(e, action="load", path=self.write(d, text))
            ok(e, action="save", path=os.path.join(d, "o.csv"))
            with open(os.path.join(d, "o.csv"), encoding="utf-8", newline="") as f:
                self.assertEqual(f.read(),
                                 "# PERA v1\nK;consumo_km_gal;40.0\nK;precio_gal;1000\nK;velocidad_kmh;55\n"
                                 "C;1;a;d;1.50000;-1.00000;0\nC;2;b;d;1.00000;1.00000;1\n"
                                 "R;R2;1;2;12.3;1.01;;1\n")

    def test_accents_and_semicolon_names(self):
        e = Engine()
        self.assertTrue(city(e, "Ñandú-ü", nombre="Ñ;a\nb")["ok"])
        self.assertTrue(city(e, "Z", nombre="é")["ok"])
        self.assertEqual(ok(e, action="get", kind="city", id="Ñandú-ü")["id"], "Ñandú-ü")
        self.assertEqual(err(e, action="create", kind="city", id="a;b"), "Campo inválido: id")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "o.csv")
            ok(e, action="save", path=p)
            with open(p, encoding="utf-8") as f:
                self.assertIn("C;Ñandú-ü;Ñ a b;D;1.00000;2.00000;1\n", f.read())
            e2 = Engine()
            ok(e2, action="load", path=p)
            self.assertEqual(ok(e2, action="get", kind="city", id="Ñandú-ü")["nombre"], "Ñ a b")

    def test_reset_and_load_state(self):
        e = mini()
        ok(e, action="toggle", kind="city", id=LET)
        r = e.handle({"action": "reset"})
        self.assertEqual(r["state"], {"dirty": False, "ciudades": 0, "peajes": 0, "rutas": 0})
        self.assertEqual(ok(e, action="params")["precio_gal"], 16000)
        ok(e, action="load", path=MINI)
        self.assertFalse(e.handle({"action": "state"})["state"]["dirty"])


class StatsTests(unittest.TestCase):
    def setUp(self):
        self.s = ok(mini(), action="stats")

    def test_conteos(self):
        self.assertEqual(self.s["conteos"], {"ciudades": 5, "ciudades_activas": 5, "peajes": 5, "peajes_activos": 4,
                                             "rutas": 6, "rutas_activas": 5, "rutas_efectivas": 5, "componentes": 2})

    def g(self, k):
        return self.s["grafos"][k]

    def hist(self, k, counts, lo, hi):
        h = self.g(k)["hist"]
        self.assertEqual(h["cuentas"], counts)
        self.assertEqual(len(h["limites"]), 11)
        self.assertAlmostEqual(h["limites"][0], lo)
        self.assertAlmostEqual(h["limites"][10], hi)

    def test_distancia(self):
        g = self.g("distancia")
        self.assertEqual((g["n"], g["min"], g["max"], g["total"]), (5, 86.0, 350.0, 1008.0))
        self.assertAlmostEqual(g["media"], 201.6)
        self.assertAlmostEqual(g["mediana"], 195.0)
        self.hist("distancia", [1, 0, 1, 0, 1, 1, 0, 0, 0, 1], 86.0, 350.0)
        self.assertAlmostEqual(g["hist"]["limites"][1], 112.4)

    def test_tiempo(self):
        g = self.g("tiempo")
        self.assertEqual((g["n"], g["min"], g["max"]), (5, 2.2, 7.0))
        self.assertAlmostEqual(g["total"], 21.05)
        self.assertAlmostEqual(g["media"], 4.21)
        self.assertAlmostEqual(g["mediana"], 3.6)
        self.hist("tiempo", [1, 1, 1, 0, 0, 0, 1, 0, 0, 1], 2.2, 7.0)

    def test_combustible(self):
        g = self.g("combustible")
        self.assertEqual((g["n"], g["min"], g["max"], g["total"]), (5, 34400, 140000, 403200))
        self.assertAlmostEqual(g["media"], 80640)
        self.assertAlmostEqual(g["mediana"], 78000)
        self.hist("combustible", [1, 0, 1, 0, 1, 1, 0, 0, 0, 1], 34400, 140000)

    def test_peajes(self):
        g = self.g("peajes")
        self.assertEqual((g["n"], g["min"], g["max"], g["total"]), (5, 0, 25200, 58100))
        self.assertAlmostEqual(g["media"], 11620)
        self.assertAlmostEqual(g["mediana"], 12900)
        self.hist("peajes", [2, 0, 0, 0, 0, 1, 0, 1, 0, 1], 0, 25200)

    def test_even_median_and_equal_values(self):
        e = Engine()
        for c in "ABC":
            city(e, c)
        route(e, "A", "B", km=10, horas=1)
        route(e, "B", "C", km=20, horas=1)
        g = ok(e, action="stats")["grafos"]
        self.assertAlmostEqual(g["distancia"]["mediana"], 15.0)
        self.assertEqual(g["tiempo"]["hist"]["cuentas"], [2, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(g["tiempo"]["hist"]["limites"], [1.0] * 11)

    def test_empty_stats(self):
        s = ok(Engine(), action="stats")
        self.assertEqual(s["grafos"]["distancia"]["n"], 0)
        self.assertEqual(s["grafos"]["distancia"]["hist"]["cuentas"], [0] * 10)
        self.assertEqual(s["peajes_por_departamento"], [])
        self.assertEqual(s["grados"], [])

    def test_grados(self):
        self.assertEqual([(x["id"], x["grado"]) for x in self.s["grados"]],
                         [(BOG, 3), (VIL, 3), (TUN, 2), (IBA, 2), (LET, 0)])
        self.assertEqual(self.s["grados"][0]["nombre"], "Bogotá D.C.")

    def test_peajes_por_departamento(self):
        self.assertEqual(self.s["peajes_por_departamento"], [
            {"departamento": "Bogotá D.C.", "cantidad": 4, "tarifa_total": 58100},
            {"departamento": "Tolima", "cantidad": 2, "tarifa_total": 25200},
            {"departamento": "Boyacá", "cantidad": 1, "tarifa_total": 12900},
            {"departamento": "Meta", "cantidad": 1, "tarifa_total": 20000}])

    def test_top_rutas(self):
        t = self.s["top_rutas"]
        def ids(k):
            return [x["id"] for x in t[k]]
        self.assertEqual(ids("distancia"), ["R005", "R004", "R002", "R001", "R003"])
        self.assertEqual(ids("tiempo"), ["R005", "R004", "R002", "R001", "R003"])
        self.assertEqual(ids("combustible"), ["R005", "R004", "R002", "R001", "R003"])
        self.assertEqual(ids("peajes"), ["R002", "R003", "R001", "R004", "R005"])
        self.assertEqual(t["distancia"][0], {"id": "R005", "origen": IBA, "destino": VIL, "valor": 350.0})
        self.assertEqual(t["tiempo"][4]["valor"], 2.2)
        self.assertEqual(t["peajes"][1]["valor"], 20000)

    def test_stats_follow_effectiveness(self):
        e = mini()
        ok(e, action="toggle", kind="city", id=VIL)
        s = ok(e, action="stats")
        self.assertEqual(s["conteos"]["rutas_efectivas"], 2)
        self.assertEqual(s["conteos"]["ciudades_activas"], 4)
        self.assertEqual(s["conteos"]["componentes"], 2)  # {B,T,I} y Leticia; la inactiva no cuenta


def grid_engine(n, rnd):
    e = Engine()
    for i in range(n):
        for j in range(n):
            assert city(e, "%03d%03d" % (i, j), departamento="D%d" % (i % 5))["ok"]
    k = 0
    for i in range(n):
        for j in range(n):
            for di, dj in ((0, 1), (1, 0)):
                a, b = i + di, j + dj
                if a < n and b < n:
                    k += 1
                    r = route(e, "%03d%03d" % (i, j), "%03d%03d" % (a, b), km="%.1f" % rnd.uniform(1, 50),
                              horas="%.2f" % rnd.uniform(0.1, 2), id="R%05d" % k)
                    assert r["ok"], r
    return e


class DijkstraTests(unittest.TestCase):
    def test_vs_floyd_warshall(self):
        rnd = random.Random(7)
        n = 4
        e = grid_engine(n, rnd)
        for t in range(3):  # peajes en algunas rutas
            ok(e, action="create", kind="toll", nombre="t", lat=0, lon=0, tarifa=rnd.randint(1000, 9000))
        ok(e, action="update", kind="route", id="R00003", peajes="P001|P002")
        ok(e, action="update", kind="route", id="R00010", peajes="P003")
        ok(e, action="toggle", kind="route", id="R00005")
        routes = ok(e, action="list", kind="route")["items"]
        ids = [c["id"] for c in ok(e, action="list", kind="city")["items"]]
        pos = {c: i for i, c in enumerate(ids)}
        inf = float("inf")
        fields = {"distancia": lambda r: round(r["km"] * 10), "tiempo": lambda r: round(r["horas"] * 100),
                  "combustible": lambda r: r["combustible"], "peajes": lambda r: r["peajes_costo"]}
        totkey = {"distancia": "km", "tiempo": "horas", "combustible": "combustible", "peajes": "peajes"}
        scale = {"distancia": 10, "tiempo": 100, "combustible": 1, "peajes": 1}
        for crit, fn in fields.items():
            m = [[inf] * len(ids) for _ in ids]
            for i in range(len(ids)):
                m[i][i] = 0
            for r in routes:
                if r["efectiva"]:
                    a, b = pos[r["origen"]], pos[r["destino"]]
                    m[a][b] = m[b][a] = min(m[a][b], fn(r))
            for k in range(len(ids)):
                for i in range(len(ids)):
                    for j in range(len(ids)):
                        if m[i][k] + m[k][j] < m[i][j]:
                            m[i][j] = m[i][k] + m[k][j]
            for i in range(len(ids)):
                for j in range(len(ids)):
                    q = ok(e, action="query", **{"from": ids[i], "to": ids[j]})
                    self.assertTrue(q["alcanzable"])
                    tot = q["criterios"][crit]["totales"][totkey[crit]]
                    self.assertEqual(round(tot * scale[crit]), m[i][j], (crit, ids[i], ids[j]))

    def test_large_grid(self):
        n = 20  # 400 ciudades
        e = grid_engine(n, random.Random(3))
        t = time.time()
        q = ok(e, action="query", **{"from": "000000", "to": "019019"})
        self.assertLess(time.time() - t, 2.0)
        self.assertTrue(q["alcanzable"])
        for c in q["criterios"].values():
            self.assertEqual(len(c["ciudades"]), len(c["rutas"]) + 1)
            self.assertEqual(c["ciudades"][0], "000000")
        self.assertEqual(ok(e, action="stats")["conteos"]["componentes"], 1)


class ApiProcessTests(unittest.TestCase):
    def run_api(self, lines, extra=()):
        p = subprocess.run([sys.executable, "-I", os.path.join(SRC, "pera_engine.py"), "--api", *extra],
                           input=lines.encode("utf-8"), capture_output=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        return [json.loads(x) for x in p.stdout.decode("utf-8").splitlines()]

    def test_api_session(self):
        out = self.run_api('{"action":"ping"}\nno es json\n[1]\n{"action":"state"}\n'
                           '{"action":"shutdown"}\n{"action":"ping"}\n', ["--data", MINI])
        self.assertEqual(len(out), 5)
        self.assertEqual(out[0]["result"], {"backend": "python", "protocol": "1"})
        self.assertFalse(out[1]["ok"])
        self.assertFalse(out[2]["ok"])
        self.assertEqual(out[3]["state"]["ciudades"], 0)  # --data solo fija la ruta por defecto
        self.assertTrue(out[4]["ok"])

    def test_api_default_path_and_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.csv")
            out = self.run_api('{"action":"load","path":%s}\n{"action":"get","kind":"city","id":"11001"}\n'
                               '{"action":"save"}\n' % json.dumps(MINI) + '{"action":"shutdown"}\n', ["--data", p])
            self.assertEqual(out[1]["result"]["nombre"], "Bogotá D.C.")
            self.assertTrue(out[2]["ok"])
            with open(p, "rb") as a:
                self.assertEqual(a.read(), mini_sorted_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=1)
