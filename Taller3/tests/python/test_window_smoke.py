"""Prueba de humo de la ventana: necesita una pantalla (real o virtual); se omite si no hay.

Se ejecuta con una pantalla virtual, nunca sobre el escritorio del usuario:
    python3 tests/python/test_window_smoke.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))


@unittest.skipUnless(os.environ.get("DISPLAY"), "sin pantalla")
class WindowSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from paa_backend import make_backend
        from ui import app as appmod
        cls.appmod = appmod
        cls.tmp = Path(tempfile.mkdtemp())
        cls.data = cls.tmp / "arbol.txt"
        backend, note = make_backend(not os.environ.get("PAA_SMOKE_CPP"), None, cls.data)
        with mock.patch.object(appmod.App, "startup_dialog", lambda self: None):
            cls.app = appmod.App(backend, note, cls.data)
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        cls.app.player.finish_now()
        cls.app.destroy()

    def op(self, action, key, label=""):
        a = self.app
        a.ops.key.delete(0, "end"); a.ops.label.delete(0, "end")
        a.ops.key.insert(0, str(key))
        if label:
            a.ops.label.insert(0, label)
        a.run_action(action)
        a.player.finish_now()
        a.update()

    def test_flow(self):
        a = self.app
        for k in (10, 20, 30):
            self.op("insert", k, "n%d" % k)
        self.assertEqual(a.final_traversals["pre"], [20, 10, 30])
        self.assertIn("20", a.traversals.values["pre"].cget("text"))
        # guardar (el cuadro de archivo se sustituye por una ruta fija)
        with mock.patch.object(self.appmod.filedialog, "asksaveasfilename", return_value=str(self.data)):
            a.save_file()
        self.assertTrue(self.data.is_file())
        self.assertEqual(self.data.read_text(encoding="utf-8").splitlines()[0], "20;n20;1")
        # deshacer, nuevo, abrir
        a.undo(); a.update()
        self.assertEqual(a.final_traversals["pre"], [10, 20])
        a.dirty = False
        a.new_tree(); a.update()
        self.assertIsNone(a.final_tree)
        with mock.patch.object(self.appmod.filedialog, "askopenfilename", return_value=str(self.data)):
            a.open_file()
        self.assertEqual(a.final_traversals["pre"], [20, 10, 30])
        # cargar desde el camino del diálogo inicial y archivo corrupto
        self.assertTrue(a.load_path(self.data))
        bad = self.tmp / "mal.txt"
        bad.write_text("esto no es un arbol\n", encoding="utf-8")
        with mock.patch.object(self.appmod.messagebox, "showerror") as err:
            self.assertFalse(a.load_path(bad))
            err.assert_called_once()
        self.assertEqual(a.final_traversals["pre"], [20, 10, 30])  # el árbol sigue intacto
        # operación que falla: duplicado
        self.op("insert", 20)
        self.assertIn("ya existe", a.status.cget("text"))


class TraversalsOfSnapshot(unittest.TestCase):
    def test_pure(self):
        from ui.app import traversals_of
        t = {"k": 2, "L": {"k": 1}, "R": {"k": 3}}
        self.assertEqual(traversals_of(t), {"pre": [2, 1, 3], "in": [1, 2, 3], "post": [1, 3, 2]})
        self.assertEqual(traversals_of(None), {"pre": [], "in": [], "post": []})


if __name__ == "__main__":
    unittest.main()
