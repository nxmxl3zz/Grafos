"""Etapa 1: descarga (con cache) de rutas OSRM entre pares candidatos de capitales."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pera_common import *
from cities import CITIES

OSRM = "https://router.project-osrm.org/route/v1/driving/{},{};{},{}?overview=full&geometries=geojson&alternatives=false&steps=false"
MAX_HAV = 550.0   # km en linea recta: candidatos = todos los pares de capitales a <= 550 km
EXTRA_CARRENO = ["85001", "50001", "95001", "81001"]
ISOLATED_CHECK = ["88001", "91001", "94001", "97001"]


def city_coords():
    wd = cached_json("wikidata_capitals.json",
                     "https://query.wikidata.org/sparql?" + urllib.parse.urlencode(
                         {"query": open(os.path.join(CACHE, "wikidata_query.rq"), encoding="utf-8").read()}),
                     headers={"Accept": "application/sparql-results+json"})
    co = {}
    for b in wd["results"]["bindings"]:
        code = b["code"]["value"]
        lon, lat = map(float, b["co"]["value"][6:-1].split())
        if code == "91001" and lat > -4.0:   # punto duplicado de Wikidata (area, no la ciudad)
            continue
        co[code] = (lat, lon)
    return co


SMALL = {"De", "Del", "La", "Las", "Los", "Y", "El"}
ALIAS = {"Guadalajara De Buga": "Buga", "Villa De San Diego De Ubaté": "Ubaté", "San Andrés De Tumaco": "Tumaco",
         "Santa Cruz De Mompox": "Mompox", "Cartagena De Indias": "Cartagena", "San José De Cúcuta": "Cúcuta",
         "San Juan De Pasto": "Pasto", "Santiago De Cali": "Cali", "San Vicente Del Caguán": "San Vicente del Caguán"}


def pretty(name):
    name = ALIAS.get(name, name)
    return " ".join(w if i == 0 or w not in SMALL else w.lower() for i, w in enumerate(name.split()))


def town_nodes():
    """Todas las cabeceras municipales de Colombia (DIVIPOLA) que no son ya capitales del archivo:
    {codigo_municipal: (nombre, departamento, lat, lon)}. Los nombres repetidos llevan el departamento entre parentesis."""
    from collections import Counter
    records = json.load(open(os.path.join(ROOT, "data", "localities_colombia.json"), encoding="utf-8"))["localidades"]
    capitals = {c[0] for c in CITIES}
    seats = [r for r in records if r["tipo"] == "cabecera" and r["id"][:5] not in capitals]
    # capitales excluidas a proposito (sin carretera ni peajes): tampoco entran como nodos sueltos
    skip = {"88001", "91001", "94001", "97001"}
    seats = [r for r in seats if r["id"][:5] not in skip]
    names = Counter(pretty(r["municipio"]) for r in seats)
    out = {}
    for r in seats:
        n = pretty(r["municipio"])
        if names[n] > 1:
            n += " (" + pretty(r["departamento"]) + ")"
        out[r["id"][:5]] = (n, pretty(r["departamento"]), r["lat"], r["lon"])
    return out


def route_path(a, b):
    return "route_%s_%s.json" % (a, b)


def get_route(co, a, b, offline=False):
    la, loa = co[a]; lb, lob = co[b]
    url = OSRM.format(loa, la, lob, lb)
    return cached_json(route_path(a, b), url, offline=offline)


def candidate_pairs(co):
    ids = [c[0] for c in CITIES]
    iso = set(ISOLATED_CHECK)
    main = [i for i in ids if i not in iso]
    pairs = []
    for i, a in enumerate(main):
        for b in main[i + 1:]:
            if hav(*co[a], *co[b]) <= MAX_HAV:
                pairs.append((a, b))
    for x in ISOLATED_CHECK:   # solo verificacion: 3 capitales continentales mas cercanas
        near = sorted(main, key=lambda m: hav(*co[x], *co[m]))[:3]
        pairs += [tuple(sorted((x, m))) for m in near]
    pairs += [tuple(sorted(("99001", m))) for m in EXTRA_CARRENO]   # Puerto Carreño: solo se acepta si OSRM encuentra ruta
    return sorted(set(pairs))


def knn_pairs(co, ids, k=6, max_km=320.0, only=None):
    """Cada nodo con sus k vecinos mas cercanos (hasta max_km): el grafo se arma con tramos, no con saltos largos."""
    pairs = set()
    for a in (only or ids):
        near = sorted((b for b in ids if b != a), key=lambda b: hav(*co[a], *co[b]))[:k]
        pairs |= {tuple(sorted((a, b))) for b in near if hav(*co[a], *co[b]) <= max_km}
    pairs |= {tuple(sorted(("99001", m))) for m in EXTRA_CARRENO}
    return sorted(pairs)


if __name__ == "__main__":
    co = city_coords()
    ps = candidate_pairs(co)
    print(len(ps), "pares")
    for k, (a, b) in enumerate(ps):
        try:
            get_route(co, a, b)
        except Exception as e:
            print("fallo", a, b, e, flush=True)
        if k % 20 == 0:
            print(k, flush=True)
