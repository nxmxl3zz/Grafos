import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))


class MergeViaTest(unittest.TestCase):
    def test_merge_via_with_real_engine(self):
        from pera_engine import Engine
        from ui.query_screen import merge_via
        e = Engine()
        e.handle({"action": "load", "path": str(ROOT / "data" / "pera_colombia.csv")})
        a, v, b = "76001", "73001", "05001"       # Cali, por Ibagué, a Medellín
        one = e.handle({"action": "query", "from": a, "to": v})
        two = e.handle({"action": "query", "from": v, "to": b})
        merged = merge_via(one, two, a, b, v)["result"]
        self.assertEqual(merged["via"], v)
        crit = merged["criterios"]["distancia"]
        self.assertEqual(crit["ciudades"][0], a)
        self.assertEqual(crit["ciudades"][-1], b)
        self.assertIn(v, crit["ciudades"])
        direct = e.handle({"action": "query", "from": a, "to": b})["result"]["criterios"]["distancia"]["totales"]["km"]
        self.assertGreaterEqual(crit["totales"]["km"], direct)       # forzar la ciudad nunca acorta
        self.assertEqual(set(merged["criterios"]), {"distancia", "tiempo", "combustible", "peajes", "total"})


if __name__ == "__main__":
    unittest.main()
