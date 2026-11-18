"""Utilidades comunes de la construccion de datos PERA (solo biblioteca estandar)."""
import json, math, os, time, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "noCommit", "data-cache")
UA = "pera-student-build/1.0 (university data structures project)"
_last = [0.0]


def polite_get(url, data=None, headers=None, min_gap=1.1, timeout=90):
    """GET/POST con pausa minima entre peticiones."""
    wait = min_gap - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    h = {"User-Agent": UA}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    _last[0] = time.time()
    return body


def cached_json(name, url, data=None, headers=None, offline=False):
    """Devuelve JSON desde noCommit/data-cache/<name>; si no existe lo descarga."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    if offline:
        raise SystemExit("falta en cache (modo sin red): " + name)
    body = polite_get(url, data, headers)
    obj = json.loads(body)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return obj


def hav(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def point_seg_km(lat, lon, a, b):
    """Distancia (km) de un punto al segmento a-b (lat,lon) con proyeccion plana local."""
    k = math.cos(math.radians(lat))
    px, py = 0.0, 0.0
    ax, ay = (a[1] - lon) * k * 111.195, (a[0] - lat) * 111.195
    bx, by = (b[1] - lon) * k * 111.195, (b[0] - lat) * 111.195
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(ax + t * dx - px, ay + t * dy - py), t


def min_dist_to_line(lat, lon, coords):
    """coords = [[lon,lat],...]. Devuelve (dist_km minima, posicion a lo largo en km)."""
    best, bestpos, acc = 1e9, 0.0, 0.0
    prev = None
    for c in coords:
        cur = (c[1], c[0])
        if prev is not None:
            seg = hav(prev[0], prev[1], cur[0], cur[1])
            d, t = point_seg_km(lat, lon, prev, cur)
            if d < best:
                best, bestpos = d, acc + t * seg
            acc += seg
        prev = cur
    return best, bestpos
