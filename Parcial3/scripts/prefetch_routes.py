#!/usr/bin/env python3
"""Descarga en paralelo (2 hilos, < 1 peticion/s en total, para respetar el servicio publico OSRM) las rutas candidatas que faltan en la cache.

Uso: python3 scripts/prefetch_routes.py   y luego   python3 scripts/build_data.py --offline
"""
import os, sys, time, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pera_common import CACHE, UA
import fetch_routes as fr
import json

co = fr.city_coords()
towns = fr.town_nodes()
for cid, t in towns.items():
    co[cid] = (t[2], t[3])
from cities import CITIES
ids = [c[0] for c in CITIES] + sorted(towns)
pairs = [p for p in fr.knn_pairs(co, ids) if not os.path.exists(os.path.join(CACHE, fr.route_path(*p)))]
print(len(pairs), "rutas por descargar", flush=True)
lock = threading.Lock()
last = [0.0]
done = [0]
fails = [0]


def fetch(pair):
    a, b = pair
    for attempt in range(4):
        with lock:                      # separacion minima global entre peticiones: 1.2 s => < 1 por segundo
            wait = 1.2 - (time.time() - last[0])
            if wait > 0:
                time.sleep(wait)
            last[0] = time.time()
        try:
            (la, loa), (lb, lob) = co[a], co[b]
            req = urllib.request.Request(fr.OSRM.format(loa, la, lob, lb), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            json.loads(body)
            tmp = os.path.join(CACHE, fr.route_path(a, b) + ".part")
            with open(tmp, "wb") as f:
                f.write(body)
            os.replace(tmp, os.path.join(CACHE, fr.route_path(a, b)))
            break
        except Exception:
            time.sleep(4 * (attempt + 1))
    else:
        with lock:
            fails[0] += 1
    with lock:
        done[0] += 1
        if done[0] % 100 == 0:
            print("  %d / %d (fallos %d)" % (done[0], len(pairs), fails[0]), flush=True)


with ThreadPoolExecutor(2) as ex:
    list(ex.map(fetch, pairs))
print("listo:", done[0], "intentadas,", fails[0], "fallos")
