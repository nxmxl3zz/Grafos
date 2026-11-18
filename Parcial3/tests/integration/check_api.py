"""Prueba de integración del protocolo --api del motor C++ (uso: check_api.py <binario>)."""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MINI = os.path.join(ROOT, "tests", "fixtures", "mini.csv")


def main():
    binary = sys.argv[1]
    p = subprocess.Popen([binary, "--api"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         text=True, encoding="utf-8")

    def raw(line):
        p.stdin.write(line + "\n")
        p.stdin.flush()
        out = p.stdout.readline()
        assert out, "sin respuesta para %r" % line
        return json.loads(out)

    def call(**req):
        return raw(json.dumps(req))

    def ok(r):
        assert r["ok"] is True, r
        assert set(r) == {"ok", "result", "state"}, r
        assert set(r["state"]) == {"dirty", "ciudades", "peajes", "rutas"}, r
        return r

    def err(r, text):
        assert r["ok"] is False and r["error"] == text, r
        assert "state" in r
        return r

    r = ok(call(action="ping"))
    assert r["result"] == {"backend": "cpp", "protocol": "1"}
    assert r["state"] == {"dirty": False, "ciudades": 0, "peajes": 0, "rutas": 0}

    r = ok(call(action="load", path=MINI))
    assert r["result"] == {"path": MINI, "ciudades": 5, "peajes": 5, "rutas": 6}
    assert r["state"] == {"dirty": False, "ciudades": 5, "peajes": 5, "rutas": 6}

    # carga y guardado reproducen el archivo byte a byte
    out = os.path.join(tempfile.mkdtemp(), "sub", "a.csv")
    ok(call(action="save", path=out))
    assert open(out, "rb").read() == open(MINI, "rb").read()

    # consultas esperadas del plan
    q = ok(call(action="query", **{"from": "11001", "to": "50001"}))["result"]
    assert q["from"] == "11001" and q["to"] == "50001" and q["alcanzable"] is True
    c = q["criterios"]
    assert set(c) == {"distancia", "tiempo", "combustible", "peajes", "total"}
    for k in ("distancia", "tiempo", "combustible"):
        assert c[k]["ciudades"] == ["11001", "50001"] and c[k]["rutas"] == ["R003"], (k, c[k])
        assert c[k]["totales"] == {"km": 86.0, "horas": 2.2, "combustible": 34400, "peajes": 20000}
    assert c["peajes"]["ciudades"] == ["11001", "15001", "50001"] and c["peajes"]["rutas"] == ["R001", "R004"]
    t = c["peajes"]["totales"]
    assert t["km"] == 377.0 and abs(t["horas"] - 8.25) < 1e-9 and t["combustible"] == 150800 and t["peajes"] == 12900
    q = ok(call(action="query", **{"from": "11001", "to": "91001"}))["result"]
    assert q["alcanzable"] is False and "criterios" not in q
    q = ok(call(action="query", **{"from": "11001", "to": "11001"}))["result"]
    assert q["alcanzable"] is True and q["criterios"]["tiempo"]["ciudades"] == ["11001"]
    assert q["criterios"]["tiempo"]["rutas"] == [] and q["criterios"]["tiempo"]["totales"]["km"] == 0
    err(call(action="query", **{"from": "11001", "to": "00000"}), "La ciudad 00000 no existe")

    # listas e items
    items = ok(call(action="list", kind="route"))["result"]["items"]
    assert [i["id"] for i in items] == ["R001", "R002", "R003", "R004", "R005", "R006"]
    r2 = items[1]
    assert r2["peajes"] == ["P002", "P003", "P005"] and r2["peajes_costo"] == 25200 and r2["efectiva"] is True
    assert items[5]["efectiva"] is False and items[5]["activo"] is False
    cities = ok(call(action="list", kind="city"))["result"]["items"]
    assert [i["id"] for i in cities] == ["11001", "15001", "50001", "73001", "91001"]
    assert cities[0]["grado"] == 3 and cities[4]["grado"] == 0
    assert ok(call(action="get", kind="toll", id="P005"))["result"]["activo"] is False

    # parámetros
    assert ok(call(action="params"))["result"] == {"consumo_km_gal": 40.0, "precio_gal": 16000, "velocidad_kmh": 55}
    r = ok(call(action="set_params", precio_gal=20000))
    assert r["result"]["precio_gal"] == 20000 and r["state"]["dirty"] is True
    q = ok(call(action="query", **{"from": "11001", "to": "50001"}))["result"]
    assert q["criterios"]["distancia"]["totales"]["combustible"] == 43000
    ok(call(action="undo"))
    assert ok(call(action="params"))["result"]["precio_gal"] == 16000

    # integridad
    err(call(action="create", kind="route", origen="50001", destino="11001", km=10, horas=1),
        "La ruta entre 50001 y 11001 ya existe")
    err(call(action="create", kind="route", origen="11001", destino="11001", km=10, horas=1),
        "Una ruta necesita dos ciudades distintas")
    err(call(action="create", kind="route", origen="11001", destino="91001", km=10, horas=1, peajes="P404"),
        "El peaje P404 no existe")
    err(call(action="create", kind="city", id="11001", nombre="x", departamento="y", lat=1, lon=1),
        "La ciudad 11001 ya existe")
    err(call(action="create", kind="city", nombre="x", departamento="y", lat=1, lon=1), "Campo inválido: id")
    err(call(action="update", kind="city", id="11001", lat="x"), "Campo inválido: lat")
    err(call(action="update", kind="city", id="11001", lat=91), "Campo inválido: lat")
    err(call(action="get", kind="route", id="R999"), "La ruta R999 no existe")
    err(call(action="get", kind="barco", id="1"), "Campo inválido: kind")
    err(call(action="nada"), "Acción desconocida: nada")
    err(call(action="undo"), "No hay nada que deshacer")

    r = ok(call(action="create", kind="route", origen="11001", destino="91001", km=100.5, horas=2, peajes=["P001"]))
    assert r["result"]["id"] == "R007" and r["result"]["km"] == 100.5 and r["result"]["peajes"] == ["P001"]
    q = ok(call(action="query", **{"from": "11001", "to": "91001"}))["result"]
    assert q["alcanzable"] is True and q["criterios"]["distancia"]["rutas"] == ["R007"]
    r = ok(call(action="create", kind="toll", nombre="Peaje; nuevo", lat=4.5, lon=-74.1, tarifa=9000))
    assert r["result"]["id"] == "P006" and r["result"]["tarifa"] == 9000
    r = ok(call(action="toggle", kind="toll", id="P006"))
    assert r["result"]["activo"] is False
    r = ok(call(action="update", kind="route", id="R007", km=90, origen="73001"))
    assert r["result"]["origen"] == "73001" and r["result"]["km"] == 90.0
    r = ok(call(action="delete", kind="toll", id="P003"))
    assert r["result"] == {"id": "P003"}
    assert ok(call(action="get", kind="route", id="R002"))["result"]["peajes"] == ["P002", "P005"]
    r = ok(call(action="delete", kind="city", id="11001"))
    assert r["result"] == {"id": "11001", "rutas_eliminadas": ["R001", "R002", "R003"]}
    assert r["state"]["ciudades"] == 4 and r["state"]["rutas"] == 4
    for _ in range(6):  # borrar ciudad, borrar peaje, update, toggle, crear peaje, crear ruta
        ok(call(action="undo"))
    s = ok(call(action="state"))["state"]
    assert s == {"dirty": True, "ciudades": 5, "peajes": 5, "rutas": 6}, s
    ok(call(action="save", path=out))
    assert open(out, "rb").read() == open(MINI, "rb").read()

    # estadísticas
    st = ok(call(action="stats"))["result"]
    assert st["conteos"] == {"ciudades": 5, "ciudades_activas": 5, "peajes": 5, "peajes_activos": 4, "rutas": 6,
                             "rutas_activas": 5, "rutas_efectivas": 5, "componentes": 2}
    d = st["grafos"]["distancia"]
    assert d["n"] == 5 and d["min"] == 86.0 and d["max"] == 350.0 and abs(d["total"] - 1008.0) < 1e-9
    assert len(d["hist"]["limites"]) == 11 and len(d["hist"]["cuentas"]) == 10 and sum(d["hist"]["cuentas"]) == 5
    assert st["grados"][0] == {"id": "11001", "nombre": "Bogotá D.C.", "grado": 3}
    assert st["top_rutas"]["distancia"][0]["id"] == "R005" and len(st["top_rutas"]["distancia"]) == 5
    assert st["peajes_por_departamento"][0]["departamento"] == "Bogotá D.C."

    # desactivar ciudad
    ok(call(action="toggle", kind="city", id="15001"))
    err(call(action="query", **{"from": "15001", "to": "50001"}), "Ciudad inactiva: 15001")
    q = ok(call(action="query", **{"from": "11001", "to": "50001"}))["result"]
    assert q["criterios"]["peajes"]["rutas"] == ["R003"]

    # carga con error: estado intacto
    bad = os.path.join(tempfile.mkdtemp(), "bad.csv")
    open(bad, "w", encoding="utf-8").write("C;1;a;b;4.0;-74.0;1\nR;R1;1;2;1.0;1.00;;1\n")
    r = call(action="load", path=bad)
    assert r["ok"] is False and r["error"].startswith("Archivo inválido: línea 2")
    assert r["state"]["ciudades"] == 5
    assert call(action="load", path=bad + ".no")["ok"] is False
    ok(call(action="reset"))
    assert ok(call(action="state"))["state"] == {"dirty": False, "ciudades": 0, "peajes": 0, "rutas": 0}
    err(call(action="undo"), "No hay nada que deshacer")  # reset borra el historial

    assert raw("{no json")["ok"] is False
    assert raw("[1]")["error"] == "La solicitud debe ser un objeto JSON"
    ok(call(action="shutdown"))
    p.wait(timeout=5)
    print("OK")


main()
