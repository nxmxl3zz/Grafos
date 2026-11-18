#!/usr/bin/env python3
"""Construye data/pera_colombia.csv (formato PERA v1) a partir de fuentes reales.

Uso:  python3 scripts/build_data.py            (usa la cache; descarga lo que falte)
      python3 scripts/build_data.py --offline  (falla si falta algo en la cache)

Fuentes (todas en noCommit/data-cache/):
  - Wikidata (P7325 = codigo DANE, P625 = coordenadas)    -> wikidata_capitals.json
  - OSRM demo (router.project-osrm.org), perfil driving    -> route_<A>_<B>.json
  - datos.gov.co 68qj-5xux "Peajes" (INVIAS)               -> peajes_68qj.json
  - datos.gov.co 7gj8-j6i3 "Tarifas de Peajes ANI"          -> ani_tarifas_catI.json (verificacion cruzada)
"""
import glob, json, os, re, sys, time, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pera_common import *
from cities import CITIES
import fetch_routes as fr

OFFLINE = "--offline" in sys.argv
OUT = os.path.join(ROOT, "data", "pera_colombia.csv")
NEAR_CAPITAL_KM = 4.0     # rechazar ruta que pasa a <= 4 km de un tercer nodo (capital o ciudad intermedia)
TOLL_KM = 1.0             # un peaje pertenece a la ruta si esta a <= 1 km de su geometria
MIN_AVG_KMH = 25.0        # umbral heuristico: candidatos lentos requieren revision manual
MAX_SNAP_KM = 10.0        # si OSRM "ajusta" una capital a una via a mas de 10 km: sin carretera
PARAMS = {"consumo_km_gal": 40.0, "precio_gal": 15886, "velocidad_kmh": 55}

# Adyacencia entre departamentos (capitales) segun el mapa politico de Colombia. Bogota D.C. se trata como
# Cundinamarca. Candidatos = pares con departamentos vecinos + corredores conocidos (CORREDORES).
ADY = {
 "Antioquia": ["Córdoba", "Bolívar", "Santander", "Boyacá", "Caldas", "Risaralda", "Chocó", "Sucre"],
 "Atlántico": ["Bolívar", "Magdalena"],
 "Bogotá D.C.": ["Boyacá", "Meta", "Tolima", "Huila", "Caldas"],
 "Bolívar": ["Atlántico", "Magdalena", "Cesar", "Santander", "Antioquia", "Córdoba", "Sucre"],
 "Boyacá": ["Santander", "Norte de Santander", "Arauca", "Casanare", "Meta", "Bogotá D.C.", "Antioquia", "Caldas"],
 "Caldas": ["Antioquia", "Risaralda", "Tolima", "Bogotá D.C.", "Boyacá"],
 "Caquetá": ["Huila", "Putumayo", "Cauca", "Meta", "Guaviare"],
 "Casanare": ["Boyacá", "Arauca", "Vichada", "Meta"],
 "Cauca": ["Valle del Cauca", "Huila", "Tolima", "Caquetá", "Putumayo", "Nariño"],
 "Cesar": ["Magdalena", "La Guajira", "Norte de Santander", "Santander", "Bolívar"],
 "Chocó": ["Antioquia", "Risaralda", "Valle del Cauca", "Córdoba"],
 "Córdoba": ["Antioquia", "Bolívar", "Sucre", "Chocó"],
 "Huila": ["Tolima", "Bogotá D.C.", "Meta", "Caquetá", "Cauca"],
 "La Guajira": ["Magdalena", "Cesar"],
 "Magdalena": ["Atlántico", "Bolívar", "Cesar", "La Guajira"],
 "Meta": ["Bogotá D.C.", "Boyacá", "Casanare", "Vichada", "Guaviare", "Caquetá", "Huila"],
 "Nariño": ["Cauca", "Putumayo"],
 "Norte de Santander": ["Santander", "Boyacá", "Cesar", "Arauca"],
 "Quindío": ["Risaralda", "Valle del Cauca", "Tolima"],
 "Risaralda": ["Caldas", "Antioquia", "Chocó", "Valle del Cauca", "Quindío", "Tolima"],
 "Santander": ["Antioquia", "Bolívar", "Cesar", "Norte de Santander", "Boyacá"],
 "Sucre": ["Córdoba", "Bolívar", "Antioquia"],
 "Tolima": ["Bogotá D.C.", "Caldas", "Risaralda", "Quindío", "Valle del Cauca", "Cauca", "Huila"],
 "Valle del Cauca": ["Chocó", "Risaralda", "Quindío", "Tolima", "Cauca"],
 "Arauca": ["Norte de Santander", "Boyacá", "Casanare", "Vichada"],
 "Putumayo": ["Nariño", "Cauca", "Caquetá"],
 "Guaviare": ["Meta", "Caquetá", "Vichada"],
 "Vichada": ["Casanare", "Meta", "Guaviare", "Arauca"],
}
# Corredores troncales entre departamentos no vecinos (ruta 45/50/55, Ruta del Sol, Troncal del Caribe...).
CORREDORES = [("11001", "05001"), ("11001", "68001"), ("08001", "47001"), ("08001", "13001")]


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def clean_name(s):
    s = re.sub(r"\s+", " ", s.replace(";", ",")).strip()
    letters = [ch for ch in s if ch.isalpha()]
    if letters and sum(ch.isupper() or ch == "l" for ch in letters) / len(letters) > 0.8 and (s.isupper() or "ll)" in s):
        s = s.title()
    s = re.sub(r"\b(Ii|Iii|Ll)\b", lambda m: {"Ii": "II", "Iii": "III", "Ll": "II"}[m.group(1)], s)
    return s


def main():
    co = fr.city_coords()
    towns = fr.town_nodes()
    nodes = list(CITIES) + [(cid, t[0], t[1]) for cid, t in sorted(towns.items())]
    for cid, t in towns.items():
        co[cid] = (t[2], t[3])
    nm = {c[0]: c[1] for c in nodes}
    ids = [c[0] for c in nodes]
    log = []
    routes = []   # dict por ruta aceptada
    tried = set()
    near_ids = sorted(ids, key=lambda i: co[i])

    def process(a, b):
        if (a, b) in tried:
            return
        tried.add((a, b))
        r = None
        for attempt in range(3):
            try:
                r = fr.get_route(co, a, b, OFFLINE)
                break
            except SystemExit:
                raise
            except Exception as e:
                err = e
                time.sleep(3)
        if r is None:
            log.append("SIN RUTA  %s-%s (%s)" % (nm[a], nm[b], err)); return
        if r.get("code") != "Ok":
            log.append("SIN RUTA  %s-%s (%s)" % (nm[a], nm[b], r.get("code"))); return
        rt = r["routes"][0]; g = rt["geometry"]["coordinates"]
        if max(w["distance"] for w in r["waypoints"]) / 1000 > MAX_SNAP_KM:
            log.append("REVISION PENDIENTE %s-%s (punto ajustado a >%d km)" % (nm[a], nm[b], MAX_SNAP_KM)); return
        if rt["distance"] / 1000 / (rt["duration"] / 3600) < MIN_AVG_KMH:
            log.append("REVISION PENDIENTE %s-%s (%.0f km/h medios; umbral heuristico, no prueba ausencia de carretera)" % (nm[a], nm[b], rt["distance"] / 1000 / (rt["duration"] / 3600))); return
        routes.append({"a": a, "b": b, "km": rt["distance"] / 1000.0, "h": rt["duration"] / 3600.0, "geom": g})

    cand = fr.knn_pairs(co, ids)
    for k_, (a, b) in enumerate(cand):
        process(a, b)
        if k_ % 200 == 0:
            print("  %d / %d candidatos, %d rutas" % (k_, len(cand), len(routes)), flush=True)
    # nodos sin ninguna ruta: se prueban sus vecinos mas cercanos hasta engancharlos (o declararlos sin carretera)
    for wave, k in enumerate((12, 24)):
        deg = {}
        for r in routes:
            deg[r["a"]] = deg.get(r["a"], 0) + 1; deg[r["b"]] = deg.get(r["b"], 0) + 1
        lonely = [i for i in ids if deg.get(i, 0) == 0]
        print("  ola %d: %d nodos sin ruta" % (wave + 1, len(lonely)), flush=True)
        for a, b in fr.knn_pairs(co, ids, k=k, max_km=400.0, only=lonely):
            process(a, b)
    def components(rs):
        adj = {}
        for r in rs:
            adj.setdefault(r["a"], set()).add(r["b"]); adj.setdefault(r["b"], set()).add(r["a"])
        seen, comps = set(), []
        for s0 in adj:
            if s0 in seen:
                continue
            comp, stack = set(), [s0]
            while stack:
                u = stack.pop()
                if u in comp:
                    continue
                comp.add(u); stack.extend(adj[u] - comp)
            seen |= comp; comps.append(comp)
        return comps

    # puentes: cada componente pequena intenta engancharse a la principal por sus nodos mas cercanos (hasta 3 rondas)
    for rnd in range(3):
        comps = components(routes)
        main_c = max(comps, key=len)
        small = [c for c in comps if c is not main_c]
        if not small:
            break
        pairs = set()
        for comp in small:
            best = sorted(((hav(*co[x], *co[y]), x, y) for x in comp for y in main_c))[: 6 * (rnd + 1)]
            pairs |= {tuple(sorted((x, y))) for _, x, y in best if _ <= 250}
        print("  puentes ronda %d: %d componentes pequenas, %d pares" % (rnd + 1, len(small), len(pairs)), flush=True)
        for a, b in sorted(pairs):
            process(a, b)
    # Se conservan TODAS las carreteras candidatas y se quitan solo las redundantes: un tramo se descarta si ya hay otro camino
    # (de los que se conservan) que no es mas largo que el tramo x 1.03. Asi la conexidad nunca se pierde.
    import heapq
    routes.sort(key=lambda r: -r["km"])
    adjw = {}
    for r in routes:
        adjw.setdefault(r["a"], {})[r["b"]] = r["km"]; adjw.setdefault(r["b"], {})[r["a"]] = r["km"]
    kept = []
    for r in routes:
        a, b, lim = r["a"], r["b"], r["km"] * 1.03
        del adjw[a][b]; del adjw[b][a]
        dist, heap, found = {a: 0.0}, [(0.0, a)], False
        while heap:
            dd, u = heapq.heappop(heap)
            if dd > dist.get(u, 1e18) or dd > lim:
                continue
            if u == b:
                found = True; break
            for v, w in adjw[u].items():
                nd = dd + w
                if nd <= lim and nd < dist.get(v, 1e18):
                    dist[v] = nd; heapq.heappush(heap, (nd, v))
        if found:
            continue                                   # redundante: hay un camino equivalente
        adjw[a][b] = r["km"]; adjw[b][a] = r["km"]
        kept.append(r)
    log.append("TRAMOS REDUNDANTES DESCARTADOS (camino alterno <= 1.03 x): %d de %d" % (len(routes) - len(kept), len(routes)))
    routes = kept
    comps = components(routes)
    main_c = max(comps, key=len)
    dropped = [i for i in ids if i not in main_c]
    routes = [r for r in routes if r["a"] in main_c and r["b"] in main_c]
    nodes = [c for c in nodes if c[0] in main_c]
    log.append("NODOS SIN CARRETERA EN LA RED PRINCIPAL (%d): %s" % (len(dropped), ", ".join(nm[i] for i in dropped)))
    print("  componentes %d; principal %d nodos; fuera %d" % (len(comps), len(main_c), len(dropped)), flush=True)
    dep = {c[0]: c[2] for c in nodes}
    # peajes
    raw = json.load(open(os.path.join(CACHE, "peajes_68qj.json"), encoding="utf-8"))
    ani = {}
    for x in json.load(open(os.path.join(CACHE, "ani_tarifas_catI.json"), encoding="utf-8")):
        ani[norm(x["peaje"])] = int(x["valor"])
    tolls = []
    for x in raw:
        try:
            # los campos latitud/longitud de la fuente estan danados en varias filas (longitud = latitud);
            # se usa la geometria 'point' (lon, lat) del mismo registro.
            tar = int(float(x["categoria_i"])); lon, lat = x["point"]["coordinates"]
        except (KeyError, ValueError, TypeError):
            continue
        if tar <= 0:
            continue
        tolls.append({"name": clean_name(x["nombre_peaje"]), "lat": lat, "lon": lon, "tar": tar,
                      "resp": (x.get("responsable") or "").strip(), "sector": x.get("sector", ""), "sentido": x.get("sentido", "")})
    # nombres repetidos en la fuente (p. ej. dos "Supía" en lugares distintos): se agrega el sector
    seen = {}
    for t in tolls:
        seen.setdefault(norm(t["name"]), []).append(t)
    for group in seen.values():
        if len(group) > 1 and len({(round(t["lat"], 2), round(t["lon"], 2)) for t in group}) > 1:
            for t in group:
                if t["sector"]:
                    t["name"] += " (" + t["sector"].strip() + ")"
    used = {}   # indice peaje -> True
    for rt in routes:
        lst = []
        for i, t in enumerate(tolls):
            d, pos = min_dist_to_line(t["lat"], t["lon"], rt["geom"])
            if d <= TOLL_KM:
                lst.append((pos, i, d))
        lst.sort()
        rt["tolls"] = [(i, d) for _, i, d in lst]
        for _, i, _ in lst:
            used[i] = True
    order = sorted(used, key=lambda i: (norm(tolls[i]["name"]), tolls[i]["lat"]))
    pid = {i: "P%03d" % (k + 1) for k, i in enumerate(order)}
    routes.sort(key=lambda r: (r["a"], r["b"]))
    for k, r in enumerate(routes):
        r["id"] = "R%03d" % (k + 1)
    # escritura determinista
    L = ["# PERA v1"]
    L.append("K;consumo_km_gal;%.1f" % PARAMS["consumo_km_gal"])
    L.append("K;precio_gal;%d" % PARAMS["precio_gal"])
    L.append("K;velocidad_kmh;%d" % PARAMS["velocidad_kmh"])
    for cid, name, d in sorted(nodes):
        lat, lon = co[cid]
        L.append("C;%s;%s;%s;%.5f;%.5f;1" % (cid, name, d, lat, lon))
    for i in sorted(order, key=lambda i: pid[i]):
        t = tolls[i]
        L.append("P;%s;Peaje %s;%.5f;%.5f;%d;1" % (pid[i], t["name"], t["lat"], t["lon"], t["tar"]))
    for r in routes:
        L.append("R;%s;%s;%s;%.1f;%.2f;%s;1" % (r["id"], r["a"], r["b"], r["km"], r["h"], "|".join(pid[i] for i, _ in r["tolls"])))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    # informe para el README (no se publica en el CSV)
    rep = []
    rep.append("## Registro de decisiones de rutas\n")
    rep.append("El umbral de velocidad es heuristico; descartar un candidato no prueba ausencia de acceso. Pares fuera de la seleccion requieren revision independiente.\n")
    rep += ["- " + s for s in log]
    rep.append("\n## Candidatos en cache no evaluados por filtros de seleccion\n")
    selected = set(cand)
    for filename in sorted(glob.glob(os.path.join(CACHE, "route_*_*.json"))):
        parts = os.path.basename(filename).removesuffix(".json").split("_")
        if len(parts) != 3 or tuple(parts[1:]) in selected:
            continue
        a, b = parts[1:]
        if a not in nm or b not in nm:
            continue
        with open(filename, encoding="utf-8") as cached:
            data = json.load(cached)
        route = (data.get("routes") or [None])[0]
        if route and route.get("duration", 0) > 0:
            avg = route["distance"] / route["duration"] * 3.6
            rep.append("- %s–%s: no seleccionado; %.1f km/h estimados; requiere revision de modo y acceso." % (nm[a], nm[b], avg))
        else:
            rep.append("- %s–%s: no seleccionado; respuesta OSRM %s." % (nm[a], nm[b], data.get("code", "sin codigo")))
    rep.append("\n## Peajes\n")
    rep.append("| id | peaje | tarifa cat. I | responsable | verificacion ANI | rutas |")
    rep.append("|---|---|---|---|---|---|")
    for i in sorted(order, key=lambda i: pid[i]):
        t = tolls[i]
        on = [r["id"] for r in routes if any(j == i for j, _ in r["tolls"])]
        a = ani.get(norm(t["name"]))
        v = "coincide" if a == t["tar"] else ("difiere (ANI %d)" % a if a else "no figura en ANI")
        rep.append("| %s | %s | %d | %s | %s | %s |" % (pid[i], t["name"], t["tar"], t["resp"] or "(sin dato)", v, ", ".join(on)))
    rep.append("\n## Rutas\n")
    rep.append("| id | origen | destino | km | horas | peajes |")
    rep.append("|---|---|---|---|---|---|")
    for r in routes:
        rep.append("| %s | %s | %s | %.1f | %.2f | %d |" % (r["id"], nm[r["a"]], nm[r["b"]], r["km"], r["h"], len(r["tolls"])))
    with open(os.path.join(CACHE, "informe_build.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")
    print("nodos %d, peajes %d, rutas %d -> %s" % (len(nodes), len(order), len(routes), OUT))
    for s in log:
        print(" ", s)


if __name__ == "__main__":
    main()
