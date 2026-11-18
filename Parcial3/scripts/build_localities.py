#!/usr/bin/env python3
"""Build the bundled locality and toll snapshots from cached public DANE/INVIAS data.

DANE inputs: FeatureServer 305 (returnIdsOnly, then objectIds batches with
returnCentroid=true, returnGeometry=true, outSR=4326), plus layer 317 attributes.
Run after downloading these responses to noCommit/data-cache/localities/.
"""
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'noCommit/data-cache'
OUT = ROOT / 'data'
URL = 'https://portalgis.dane.gov.co/mparcgis/rest/services/Divipola/Serv_DIVIPOLA_MGN_2025/FeatureServer/305'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def download():
    """Refresh the small official snapshots; no all-pairs routing requests."""
    cache = CACHE / 'localities'
    cache.mkdir(parents=True, exist_ok=True)
    base = URL.rsplit('/', 1)[0]

    def fetch(url, params, path):
        request = Request(url + '/query?' + urlencode(params), headers={'User-Agent': 'PERA-localities/1.0'})
        with urlopen(request, timeout=60) as response:
            data = json.load(response)
        if 'error' in data:
            raise ValueError(str(data['error']))
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return data

    ids = fetch(URL, {'where': '1=1', 'returnIdsOnly': 'true', 'f': 'json'}, cache / 'ids.json')['objectIds']
    fetch(base + '/317', {'where': '1=1', 'outFields': '*', 'returnGeometry': 'false', 'f': 'json'}, cache / 'municipalities.json')
    for path in cache.glob('dane-batch-*.json'):
        path.unlink()
    for start in range(0, len(ids), 1000):
        fetch(URL, {'objectIds': ','.join(map(str, ids[start:start + 1000])),
                    'outFields': 'ZU_CDIVI,ZU_CNMBRE,MPIO_CDPMP,DPTO_CCDGO,CLAS_CCDGO',
                    'returnGeometry': 'true', 'returnCentroid': 'true', 'maxAllowableOffset': '0.0005',
                    'geometryPrecision': '5', 'outSR': '4326', 'f': 'json'}, cache / ('dane-batch-%d.json' % (start // 1000)))


def main():
    if '--download' in sys.argv:
        download()
    cache = CACHE / 'localities'
    expected = set(read(cache / 'ids.json')['objectIds'])
    admins = {f['attributes']['MPIO_CDPMP']: f['attributes'] for f in read(cache / 'municipalities.json')['features']}
    features = [f for p in sorted(cache.glob('dane-batch-*.json')) for f in read(p)['features']]
    places = []
    for f in features:
        a, point = f['attributes'], f['centroid']
        admin = admins[a['MPIO_CDPMP']]
        lat, lon = float(point['y']), float(point['x'])
        if not (-5 <= lat <= 14 and -82 <= lon <= -66):
            raise ValueError('Coordenadas inesperadas: ' + a['ZU_CDIVI'])
        places.append(dict(id=a['ZU_CDIVI'], nombre=a['ZU_CNMBRE'].title(),
                           municipio=admin['MPIO_CNMBRE'].title(), departamento=admin['DPTO_CNMBRE'].title(),
                           lat=lat, lon=lon, tipo='cabecera' if a['CLAS_CCDGO'] == '1' else 'centro_poblado'))
    if len(places) != len(expected) or len({p['id'] for p in places}) != len(expected):
        raise ValueError('La descarga es incompleta o hay IDs DIVIPOLA duplicados')
    places.sort(key=lambda p: p['id'])
    data = dict(version=1, fuente=URL, fecha_consulta='2026-11-17',
                nota='Centroides estadísticos DANE, aproximados; no garantizan acceso vial.', localidades=places)
    (OUT / 'localities_colombia.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')

    tolls = []
    for row in read(CACHE / 'peajes_68qj.json'):
        try:
            lon, lat = map(float, row['point']['coordinates'])
            name = row['nombre_peaje'].strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not (-5 <= lat <= 14 and -82 <= lon <= -66):
            continue
        try:
            fare = int(float(row['categoria_i']))
            if fare <= 0:
                fare = None
        except (KeyError, TypeError, ValueError):
            fare = None
        identity = '|'.join((str(row.get('c_digo_peaje', '')), name, str(lat), str(lon)))
        tolls.append(dict(id='INV-' + hashlib.sha256(identity.encode()).hexdigest()[:12], nombre=name,
                          lat=lat, lon=lon, tarifa=fare, activo=True))
    # Tarifa faltante en INVIAS: se completa solo con un nombre IDENTICO en la tabla ANI de categoria I (nunca por parecido).
    # Peajes marcados como no operativos o siniestrados se dejan inactivos (no suman costo).
    import re as _re
    import unicodedata as _ud
    norm = lambda t: _re.sub(r'[^a-z0-9]+', ' ', _ud.normalize('NFKD', t.casefold()).encode('ascii', 'ignore').decode()).strip()
    ani_path = ROOT / 'noCommit' / 'data-cache' / 'ani_tarifas_catI.json'
    ani = {norm(r['peaje']): int(r['valor']) for r in json.loads(ani_path.read_text(encoding='utf-8'))} if ani_path.exists() else {}
    for t in tolls:
        if _re.search(r'no operativo|siniestrad', t['nombre'], _re.I):
            t['activo'] = False
        elif t['tarifa'] is None and norm(t['nombre']) in ani:
            t['tarifa'], t['tarifa_fuente'] = ani[norm(t['nombre'])], 'ANI categoría I (INVIAS sin dato)'
    if len({t['id'] for t in tolls}) != len(tolls):
        raise ValueError('Identificador de peaje duplicado')
    tolls.sort(key=lambda t: t['id'])
    data = dict(fuente='https://www.datos.gov.co/Transporte/Peajes/68qj-5xux', fecha_consulta='2026-11-17',
                nota='Snapshot INVIAS: cobertura y tarifa sujetas a verificación.', peajes=tolls)
    (OUT / 'tolls_colombia.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print('localidades:', len(places), 'peajes:', len(tolls), 'tarifas sin dato:', sum(t['tarifa'] is None for t in tolls))


if __name__ == '__main__':
    main()
