"""Rutas solicitadas entre localidades colombianas; no modifica el grafo académico."""
from __future__ import annotations

import json
import math
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import URLError
from urllib.request import Request, urlopen

OSRM = "https://router.project-osrm.org/route/v1/driving/"
MAX_SNAP_M = 2000
TOLL_RADIUS_KM = 1.0
AVISO = ("Las opciones son candidatas del proveedor, no óptimos de toda la red. "
         "Los peajes próximos y sus tarifas son una estimación parcial: pueden faltar, repetirse o corresponder a otra vía o sentido; "
         "no incluyen cargos internacionales, portuarios ni de ferry. Combustible estimado sobre toda la distancia; "
         "los tramos ferry identificados se descuentan; si no hay detalle se usa toda la distancia. Confirme condiciones y tarifas.")


class ErrorRuta(Exception):
    """No se pudo obtener una ruta fiable para los puntos elegidos."""


def _cache_file(url):
    import hashlib
    import os
    from pathlib import Path
    base = Path(os.environ.get("PERA_CACHE") or Path.home() / ".cache" / "pera-rutas")
    return base / (hashlib.sha256(url.encode()).hexdigest()[:32] + ".json")


def _fetch(url):
    """Consulta OSRM (2 intentos). Cada respuesta buena se guarda; sin red se reutiliza la ultima igual guardada."""
    last_error = None
    for _attempt in range(2):
        try:
            req = Request(url, headers={"User-Agent": "PERA-estudiantes/1.0"})
            with urlopen(req, timeout=12) as response:
                data = json.load(response)
            if data.get("code") == "Ok":
                try:
                    path = _cache_file(url)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data), encoding="utf-8")
                except OSError:
                    pass
            return data
        except (URLError, OSError, TimeoutError, ValueError) as error:
            last_error = error
    try:
        data = json.loads(_cache_file(url).read_text(encoding="utf-8"))
        data["_desde_cache"] = True
        return data
    except (OSError, ValueError):
        raise last_error


def _endpoint(item):
    try:
        lat, lon = float(item['lat']), float(item['lon'])
        if item.get('pais', 'CO') != 'CO' or not ( -4.3 <= lat <= 13.6 and -82.2 <= lon <= -66.8):
            raise ValueError
        if not item.get('id') or not item.get('nombre') or not math.isfinite(lat + lon):
            raise ValueError
        return lat, lon
    except (TypeError, KeyError, ValueError):
        raise ErrorRuta('Seleccione una localidad colombiana válida del catálogo.') from None


def _escalado(value, scale):
    return int((Decimal(str(value)) * scale).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _distance_segment(lat, lon, a, b):
    # Distancia aproximada a un segmento; longitud ajustada a la latitud del peaje.
    k = math.cos(math.radians(lat)) * 111.195
    ax, ay = (a[1] - lon) * k, (a[0] - lat) * 111.195
    bx, by = (b[1] - lon) * k, (b[0] - lat) * 111.195
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = max(0., min(1., -(ax * dx + ay * dy) / length2)) if length2 else 0.
    return math.hypot(ax + t * dx, ay + t * dy), t


def _tolls(geometry, tolls):
    matches = []
    for toll in tolls:
        if not toll.get('activo', True):
            continue
        try:
            lat, lon = float(toll['lat']), float(toll['lon'])
            if not math.isfinite(lat + lon):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        best = (float('inf'), 0.)
        for index, (a, b) in enumerate(zip(geometry, geometry[1:])):
            # Caja ampliada evita calcular proyecciones de segmentos lejanos.
            if not (min(a[0], b[0]) - .012 <= lat <= max(a[0], b[0]) + .012 and
                    min(a[1], b[1]) - .014 <= lon <= max(a[1], b[1]) + .014):
                continue
            dist, fraction = _distance_segment(lat, lon, a, b)
            if dist < best[0]:
                best = dist, index + fraction
        if best[0] <= TOLL_RADIUS_KM:
            matches.append((best[1], {**toll, 'distancia_m': round(best[0] * 1000)}))
    return [toll for _, toll in sorted(matches, key=lambda pair: pair[0])]


def consultar_localidades(origen, destino, peajes, consumo=40.0, precio=15886, fetcher=None, via=()):
    """Consulta hasta tres rutas OSRM y compara únicamente las alternativas recibidas.

    `fetcher(url)` devuelve el JSON decodificado; permite pruebas sin red. Peajes
    son coincidencias por proximidad y la suma es necesariamente incompleta.
    """
    a, b = _endpoint(origen), _endpoint(destino)
    vias = [_endpoint(v) for v in (via or ())][:2]
    try:
        cons10 = _escalado(consumo, 10)
        precio = int(precio)
        if cons10 <= 0 or precio < 0:
            raise ValueError
    except (ValueError, TypeError, ArithmeticError):
        raise ErrorRuta('Parámetros de combustible inválidos.') from None
    if origen['id'] == destino['id'] and not vias:
        if a != b:
            raise ErrorRuta('La localidad tiene coordenadas inconsistentes.')
        result = {'id': 'A1', 'geometria': [list(a)], 'km': 0.0, 'horas': 0.0, 'combustible': 0,
                  'peajes_estimados': 0, 'peajes': [], 'peajes_sin_tarifa': 0, 'snap_origen_m': 0, 'snap_destino_m': 0,
                  'snap_origen': list(a), 'snap_destino': list(b), 'km_conduccion': 0.0, 'km_ferry': 0.0, 'detalle_modos': True}
        return {'origen': origen, 'destino': destino, 'proveedor': 'OSRM', 'candidatos': [result],
                'mejores': {key: 'A1' for key in ('distancia', 'tiempo', 'combustible', 'peajes')}, 'aviso': AVISO}
    coords = ';'.join(f'{p[1]:.7f},{p[0]:.7f}' for p in [a, *vias, b])
    url = f"{OSRM}{coords}?alternatives={'false' if vias else '2'}&steps=true&geometries=geojson&overview=full"
    try:
        data = (fetcher or _fetch)(url)
        if data.get('code') == 'NoRoute':
            raise ErrorRuta('No se encontró ruta en la red del proveedor entre estas localidades.')
        if data.get('code') != 'Ok':
            raise ErrorRuta('El proveedor no pudo calcular la ruta solicitada.')
        waypoints = data['waypoints']
        snap_a, snap_b = float(waypoints[0]['distance']), float(waypoints[-1]['distance'])
        if len(waypoints) != len(vias) + 2:
            raise ValueError
        if not all(math.isfinite(float(w['distance'])) and 0 <= float(w['distance']) <= MAX_SNAP_M for w in waypoints):
            raise ErrorRuta('El punto más cercano de la red está a más de 2 km de la localidad seleccionada.')
        snap_points = []
        for waypoint in (waypoints[0], waypoints[-1]):
            lon, lat = map(float, waypoint['location'])
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
            snap_points.append([lat, lon])
        candidates = []
        for route in data['routes'][:3]:
            km, hours = float(route['distance']) / 1000, float(route['duration']) / 3600
            if not all(math.isfinite(x) and x >= 0 for x in (km, hours)):
                raise ValueError
            geometry = [[float(pt[1]), float(pt[0])] for pt in route['geometry']['coordinates']]
            if len(geometry) < 2 or any(not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180) for lat, lon in geometry):
                raise ValueError
            km10, horas100 = _escalado(km, 10), _escalado(hours, 100)
            steps = [step for leg in route.get('legs', []) for step in leg.get('steps', [])]
            valid_steps = bool(steps) and all(step.get('mode') in ('driving', 'ferry') and
                                              isinstance(step.get('distance'), (int, float)) and
                                              math.isfinite(step['distance']) and step['distance'] >= 0 for step in steps)
            valid_steps = valid_steps and abs(sum(s['distance'] for s in steps) - km * 1000) <= max(10, km * 10)
            ferry_km = sum(s['distance'] for s in steps if s['mode'] == 'ferry') / 1000 if valid_steps else None
            driving_km = max(0., km - ferry_km) if valid_steps else km
            driving10 = _escalado(driving_km, 10)
            fuel = (2 * driving10 * precio + cons10) // (2 * cons10)
            found = _tolls(geometry, peajes)
            known = [t['tarifa'] for t in found if isinstance(t.get('tarifa'), (int, float)) and math.isfinite(t['tarifa']) and t['tarifa'] >= 0]
            amount = sum(known) if known else None
            candidates.append({'id': f'A{len(candidates)+1}', 'geometria': geometry, 'km': km10 / 10,
                               'horas': horas100 / 100, 'combustible': fuel, 'km_conduccion': driving10 / 10,
                               'km_ferry': _escalado(ferry_km, 10) / 10 if ferry_km is not None else None,
                               'detalle_modos': valid_steps, 'peajes_estimados': amount,
                               'peajes': found, 'peajes_sin_tarifa': sum(1 for t in found if not isinstance(t.get('tarifa'), (int, float))),
                               'snap_origen_m': snap_a, 'snap_destino_m': snap_b,
                               'snap_origen': snap_points[0], 'snap_destino': snap_points[1]})
        if not candidates:
            raise ErrorRuta('El proveedor no devolvió rutas para estas localidades.')
        metrics = {'distancia': 'km', 'tiempo': 'horas', 'combustible': 'combustible', 'peajes': 'peajes_estimados'}
        best = {key: (min(candidates, key=lambda c: c[field])['id']
                      if all(c[field] is not None for c in candidates) else None)
                for key, field in metrics.items()}
        if any(c['peajes_sin_tarifa'] for c in candidates):
            best['peajes'] = None
        aviso = AVISO
        if data.get('_desde_cache'):
            aviso = ('SIN CONEXIÓN: se muestra el resultado guardado de la última consulta idéntica con internet; '
                     'puede no reflejar el estado actual de las vías. ') + AVISO
        return {'origen': origen, 'destino': destino, 'proveedor': 'OSRM', 'candidatos': candidates,
                'desde_cache': bool(data.get('_desde_cache')),
                'mejores': best, 'aviso': aviso, 'via': [dict(v) for v in (via or ())][:2]}
    except ErrorRuta:
        raise
    except (URLError, OSError, TimeoutError, ValueError, TypeError, KeyError, IndexError, ArithmeticError, AttributeError):
        raise ErrorRuta('No se pudo consultar el proveedor de rutas o su respuesta no es válida.') from None
