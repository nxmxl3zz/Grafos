"""Coverage metadata and invalidation must follow the loaded, unmodified dataset."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))


class AccessMetadataTest(unittest.TestCase):
    def test_bundled_manifest_and_sources(self):
        metadata = json.loads((ROOT / "data/access_research.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["csv_sha256"], hashlib.sha256((ROOT / "data/pera_colombia.csv").read_bytes()).hexdigest())
        self.assertEqual(set(metadata["ciudades"]), {"88001", "91001", "94001", "97001", "99001"})
        for city in metadata["ciudades"].values():
            self.assertTrue(city["explicacion"])
            self.assertTrue(all(source["url"].startswith("https://") for source in city["fuentes"]))

    def test_mutations_invalidate_results_and_metadata(self):
        from ui.app import App
        for action in ("create", "update", "delete", "toggle", "set_params", "undo", "reset", "load"):
            app = Mock()
            app.backend.request.return_value = {"ok": True}
            app.last_query = {"old": 1}
            app.bundled_access_valid = True
            App.api(app, {"action": action})
            self.assertIsNone(app.last_query, action)
            self.assertFalse(app.bundled_access_valid, action)
        for action in ("query", "list", "save"):
            app = Mock()
            app.backend.request.return_value = {"ok": True}
            app.last_query = {"old": 1}
            app.bundled_access_valid = True
            App.api(app, {"action": action})
            self.assertEqual(app.last_query, {"old": 1}, action)
            self.assertTrue(app.bundled_access_valid, action)

    def test_loading_scope_and_save_as(self):
        from ui.app import App
        app = Mock()
        app.api.return_value = {"ok": True}
        bundled = ROOT / "data/pera_colombia.csv"
        self.assertTrue(App.load_path(app, bundled))
        self.assertTrue(app.bundled_access_valid)
        with tempfile.TemporaryDirectory() as folder:
            other = Path(folder) / "copy.csv"
            other.write_bytes(bundled.read_bytes())
            self.assertTrue(App.load_path(app, other))
            self.assertFalse(app.bundled_access_valid)
            self.assertTrue(App.load_path(app, bundled))
            app.data_path = bundled
            with patch("ui.app.filedialog.asksaveasfilename", return_value=str(other)):
                App.save_file(app)
            self.assertFalse(app.bundled_access_valid)

    def test_failed_mutation_preserves_query_and_metadata(self):
        from ui.app import App
        app = Mock()
        app.backend.request.return_value = {"ok": False, "error": "invalid"}
        app.last_query = {"old": 1}
        app.bundled_access_valid = True
        App.api(app, {"action": "update", "kind": "toll"})
        self.assertEqual(app.last_query, {"old": 1})
        self.assertTrue(app.bundled_access_valid)

    def test_reachable_carreno_shows_seasonal_notice(self):
        from ui.query_screen import GraphQueryScreen
        screen = Mock()
        screen.origin.city_id.return_value = "50001"
        screen.destination.city_id.return_value = "99001"
        screen.app.bundled_access_valid = True
        screen.app.api.return_value = {"ok": True, "result": {"alcanzable": True, "criterios": {}}}
        screen.cards = {}
        GraphQueryScreen.run(screen)
        message = screen.show_message.call_args.args[0]
        self.assertIn("estacional", message)
        self.assertIn("planchón", message)
        screen.app.bundled_access_valid = False
        GraphQueryScreen.run(screen)
        self.assertNotIn("estacional", screen.show_message.call_args.args[0])

    def test_refresh_clears_previously_displayed_totals(self):
        from ui.query_screen import GraphQueryScreen
        screen = Mock()
        screen.result = {"old": 1}
        screen.app.last_query = None
        screen.app.data = {"city": []}
        screen._ids = ()
        card = Mock()
        screen.cards = {"distancia": card}
        GraphQueryScreen.refresh(screen)
        self.assertIsNone(screen.result)
        card.show.assert_called_once_with(None, screen.app.city_name)
        screen.show_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
