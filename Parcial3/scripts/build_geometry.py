#!/usr/bin/env python3
"""Construye data/route_geometry.json y data/colombia_departments.json (solo para dibujar los mapas).

  - Geometria vial de cada ruta del CSV: tomada de las respuestas OSRM en la cache, simplificada (Douglas-Peucker, ~1 km).
  - Limites departamentales: Natural Earth 10m admin-1 (dominio publico), simplificados; sin San Andres.
No cambia el CSV ni los costos: los km y horas siguen siendo los del CSV.
"""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pera_common import ROOT, CACHE

TOL = 0.008  # grados (~0.9 km)


def simplify(pts, tol=TOL):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts); keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        (x1, y1), (x2, y2) = pts[i], pts[j]
        dx, dy = x2 - x1, y2 - y1
        n = math.hypot(dx, dy) or 1e-12
        far, k = 0.0, -1
        for m in range(i + 1, j):
            d = abs(dy * (pts[m][0] - x1) - dx * (pts[m][1] - y1)) / n
            if d > far:
                far, k = d, m
        if far > tol:
            keep[k] = True; stack += [(i, k), (k, j)]
    return [p for p, k in zip(pts, keep) if k]


def simplify_ring(ring, tol):
    """Anillo cerrado: se parte en el punto mas lejano al inicio para que Douglas-Peucker no colapse."""
    k = max(range(len(ring)), key=lambda i: (ring[i][0] - ring[0][0]) ** 2 + (ring[i][1] - ring[0][1]) ** 2)
    return simplify(ring[:k + 1], tol)[:-1] + simplify(ring[k:], tol)


def main():
    routes = {}
    for line in open(os.path.join(ROOT, "data", "pera_colombia.csv"), encoding="utf-8"):
        f = line.rstrip("\n").split(";")
        if f[0] != "R":
            continue
        rid, a, b = f[1], f[2], f[3]
        data = json.load(open(os.path.join(CACHE, "route_%s_%s.json" % (a, b)), encoding="utf-8"))
        g = data["routes"][0]["geometry"]["coordinates"]
        routes[rid] = {"a": a, "b": b, "pts": [[round(y, 4), round(x, 4)] for x, y in simplify([(x, y) for x, y in g])]}
    with open(os.path.join(ROOT, "data", "route_geometry.json"), "w", encoding="utf-8") as out:
        json.dump(routes, out, separators=(",", ":"), sort_keys=True)
    deps = []
    for ft in json.load(open(os.path.join(CACHE, "ne_colombia_adm1.json"), encoding="utf-8"))["features"]:
        if not ft["name"] or ft["name"].startswith("San Andr"):
            continue
        geo = ft["geometry"]
        polys = geo["coordinates"] if geo["type"] == "MultiPolygon" else [geo["coordinates"]]
        rings = []
        for poly in polys:
            ring = simplify_ring([(x, y) for x, y in poly[0]], 0.01)
            if len(ring) >= 4:
                rings.append([[round(y, 3), round(x, 3)] for x, y in ring])
        deps.append({"nombre": ft["name"], "anillos": rings})
    with open(os.path.join(ROOT, "data", "colombia_departments.json"), "w", encoding="utf-8") as out:
        json.dump(deps, out, ensure_ascii=False, separators=(",", ":"))
    print("rutas con geometria %d, puntos %d; departamentos %d" % (len(routes), sum(len(r["pts"]) for r in routes.values()), len(deps)))


if __name__ == "__main__":
    main()
