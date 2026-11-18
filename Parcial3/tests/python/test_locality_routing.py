import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src/python'))
from locality_routing import consultar_localidades, ErrorRuta

A = {'id': '20001000', 'nombre': 'Valledupar', 'lat': 10., 'lon': -73.}
B = {'id': '08638000', 'nombre': 'Sabanalarga', 'lat': 10.1, 'lon': -73.1}

def response():
    return {'code': 'Ok', 'waypoints': [{'distance': 5, 'location': [-73.,10.]}, {'distance': 10, 'location': [-73.1,10.1]}], 'routes': [
        {'distance': 100000, 'duration': 7200, 'geometry': {'coordinates': [[-73,10],[-73.1,10.1]]}},
        {'distance': 120000, 'duration': 6000, 'geometry': {'coordinates': [[-73,10],[-73.1,10.1]]}}]}

class RoutingTest(unittest.TestCase):
    def test_candidates_and_approximate_tolls(self):
        toll = {'id': 't1', 'nombre': 'Ejemplo', 'lat': 10.05, 'lon': -73.05, 'tarifa': 12300}
        out = consultar_localidades(A, B, [toll], fetcher=lambda url: response())
        self.assertEqual(out['candidatos'][0]['geometria'][0], [10.,-73.])
        self.assertEqual(out['candidatos'][0]['combustible'], 39715)
        self.assertEqual(out['candidatos'][0]['peajes_estimados'], 12300)
        self.assertEqual(out['mejores']['distancia'], 'A1')
        self.assertEqual(out['mejores']['tiempo'], 'A2')
        self.assertIn('estimación parcial', out['aviso'])
    def test_empty_or_unknown_tolls_not_misrepresented(self):
        toll = {'id':'t', 'nombre':'Sin tarifa', 'lat':10.05, 'lon':-73.05, 'tarifa':None}
        c = consultar_localidades(A, B, [toll], fetcher=lambda url: response())['candidatos'][0]
        self.assertIsNone(c['peajes_estimados'])
        self.assertEqual(c['peajes_sin_tarifa'], 1)
        no_tolls = consultar_localidades(A, B, [], fetcher=lambda url: response())
        self.assertIsNone(no_tolls['candidatos'][0]['peajes_estimados'])
        self.assertIsNone(no_tolls['mejores']['peajes'])
        self.assertIsNone(c['peajes'][0]['tarifa'])
    def test_ferry_distance_excluded_from_fuel(self):
        d = response()
        d['routes'][0]['legs'] = [{'steps': [{'mode':'driving','distance':80000}, {'mode':'ferry','distance':20000}]}]
        c = consultar_localidades(A, B, [], fetcher=lambda url: d)['candidatos'][0]
        self.assertEqual((c['km_conduccion'], c['km_ferry'], c['combustible']), (80.0, 20.0, 31772))
        self.assertTrue(c['detalle_modos'])
        self.assertFalse(consultar_localidades(A, B, [], fetcher=lambda url: response())['candidatos'][0]['detalle_modos'])

    def test_identical_locality_never_fetches(self):
        out = consultar_localidades(A, A, [], fetcher=lambda url: self.fail('unexpected network'))
        self.assertEqual(out['candidatos'][0]['km'], 0)
    def test_no_route_snap_and_bad_input(self):
        with self.assertRaises(ErrorRuta): consultar_localidades(A,B,[],fetcher=lambda url: {'code':'NoRoute'})
        d=response(); d['waypoints'][0]['distance']=2001
        with self.assertRaises(ErrorRuta): consultar_localidades(A,B,[],fetcher=lambda url: d)
        with self.assertRaises(ErrorRuta): consultar_localidades({**A,'pais':'US'},B,[],fetcher=lambda url: response())
        with self.assertRaises(ErrorRuta): consultar_localidades(A,B,[],fetcher=lambda url: {})
        d=response(); d['routes'][0]['geometry']['coordinates'][0]=[-73, 100]
        with self.assertRaises(ErrorRuta): consultar_localidades(A,B,[],fetcher=lambda url: d)

if __name__ == '__main__': unittest.main()


class ViaTest(unittest.TestCase):
    def test_via_is_in_url_and_disables_alternatives(self):
        from locality_routing import consultar_localidades
        urls = []

        def fetcher(url):
            urls.append(url)
            return {'code': 'Ok', 'waypoints': [{'distance': 5, 'location': [-73.2, 10.4]}, {'distance': 3, 'location': [-73.1, 9.1]},
                                                 {'distance': 4, 'location': [-74.9, 10.6]}],
                    'routes': [{'distance': 500000, 'duration': 30000, 'geometry': {'coordinates': [[-73.2, 10.4], [-74.9, 10.6]]},
                                'legs': [{'steps': [{'mode': 'driving', 'distance': 500000}]}]}]}
        place = lambda i, lat, lon: {'id': i, 'nombre': i, 'municipio': i, 'departamento': 'X', 'lat': lat, 'lon': lon, 'pais': 'CO'}
        result = consultar_localidades(place('a', 10.4, -73.2), place('b', 10.6, -74.9), [], fetcher=fetcher,
                                       via=[place('v', 9.1, -73.1)])
        self.assertIn('-73.1000000,9.1000000', urls[0])
        self.assertIn('alternatives=false', urls[0])
        self.assertEqual(result['via'][0]['id'], 'v')
        self.assertEqual(result['candidatos'][0]['km'], 500.0)


class CacheTest(unittest.TestCase):
    def test_offline_uses_saved_answer_and_says_so(self):
        import os
        import tempfile
        from unittest import mock
        import locality_routing as lr
        good = {'code': 'Ok', 'waypoints': [{'distance': 5, 'location': [-73.2, 10.4]}, {'distance': 3, 'location': [-74.9, 10.6]}],
                'routes': [{'distance': 300000, 'duration': 18000, 'geometry': {'coordinates': [[-73.2, 10.4], [-74.9, 10.6]]},
                            'legs': [{'steps': [{'mode': 'driving', 'distance': 300000}]}]}]}
        place = lambda i, lat, lon: {'id': i, 'nombre': i, 'municipio': i, 'departamento': 'X', 'lat': lat, 'lon': lon, 'pais': 'CO'}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {'PERA_CACHE': tmp}):
            class Resp:
                def __enter__(s): return s
                def __exit__(s, *a): return False
                def read(s, *a): return __import__('json').dumps(good).encode()
            with mock.patch.object(lr, 'urlopen', return_value=Resp()):
                online = lr.consultar_localidades(place('a', 10.4, -73.2), place('b', 10.6, -74.9), [])
            self.assertFalse(online['desde_cache'])
            from urllib.error import URLError
            with mock.patch.object(lr, 'urlopen', side_effect=URLError('sin red')):
                offline = lr.consultar_localidades(place('a', 10.4, -73.2), place('b', 10.6, -74.9), [])
                self.assertTrue(offline['desde_cache'])
                self.assertIn('SIN CONEXIÓN', offline['aviso'])
                with self.assertRaises(lr.ErrorRuta):      # una consulta nunca vista y sin red falla con mensaje claro
                    lr.consultar_localidades(place('a', 10.4, -73.2), place('c', 9.0, -74.0), [])
