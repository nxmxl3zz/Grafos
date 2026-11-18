import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src/python'))
from locality_catalog import load_catalog, search_localities


class LocalityCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.places = load_catalog()

    def test_ambiguity_and_department_filter(self):
        results = search_localities(self.places, 'sabanalarga', 100)
        seats = {x['departamento']: x for x in results if x['nombre'] == 'Sabanalarga' and x['tipo'] == 'cabecera'}
        self.assertTrue({'Atlántico', 'Antioquia', 'Casanare'} <= set(seats))
        selected = search_localities(self.places, 'sabanalarga atlantico', 20)
        self.assertEqual(selected[0]['id'], '08638000')
        self.assertAlmostEqual(selected[0]['lat'], 10.63208, places=4)

    def test_representative_seat_and_count_limit(self):
        self.assertEqual(len(self.places), 8420)
        self.assertEqual(search_localities(self.places, 'pamplona norte santander')[0]['id'], '54518000')
        self.assertEqual(search_localities(self.places, 'valledupar cesar')[0]['id'], '20001000')
        self.assertEqual(len(search_localities(self.places, 'san', 5)), 5)
        self.assertEqual(search_localities(self.places, '', 5), [])

    def test_tolls_snapshot(self):
        tolls = json.loads((ROOT / 'data/tolls_colombia.json').read_text(encoding='utf-8'))['peajes']
        self.assertEqual(len(tolls), 179)
        self.assertEqual(len({x['id'] for x in tolls}), len(tolls))
        self.assertTrue(any(x['tarifa'] is None for x in tolls))


if __name__ == '__main__':
    unittest.main()
