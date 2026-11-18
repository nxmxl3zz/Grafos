"""Prueba de humo de la ventana: necesita una pantalla (real o virtual); se omite si no hay.

Abre ventanas reales, por eso NO corre salvo que se declare explicitamente una pantalla virtual:
    PERA_VIRTUAL_DISPLAY=1 DISPLAY=<virtual> .venv/bin/python tests/python/test_window_smoke.py
Sin PERA_VIRTUAL_DISPLAY=1 se omite, aunque DISPLAY apunte al escritorio del usuario.
Con PERA_SMOKE_CPP=1 usa el motor C++ (build/pera_cpp) en lugar del Python.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))
MINI = ROOT / "tests" / "fixtures" / "mini.csv"


class FormatTests(unittest.TestCase):
    def test_spanish_formats(self):
        from ui.format import fmt_cop, fmt_horas, fmt_km, to_number
        self.assertEqual(fmt_km(86.0), "86,0 km")
        self.assertEqual(fmt_km(1234.5), "1.234,5 km")
        self.assertEqual(fmt_horas(2.2), "2:12 h")
        self.assertEqual(fmt_horas(8.25), "8:15 h")
        self.assertEqual(fmt_cop(34400), "$ 34.400")
        self.assertEqual(to_number("4,7"), 4.7)
        self.assertEqual(to_number("16000"), 16000)
        self.assertEqual(to_number("abc"), "abc")


@unittest.skipUnless(os.environ.get("DISPLAY") and os.environ.get("PERA_VIRTUAL_DISPLAY") == "1",
                     "ventanas reales: exige PERA_VIRTUAL_DISPLAY=1 con una pantalla virtual")
class WindowSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pera_backend import make_backend
        from ui import app as appmod
        cls.appmod = appmod
        cls.tmp = Path(tempfile.mkdtemp())
        backend, note = make_backend(not os.environ.get("PERA_SMOKE_CPP"), None, MINI)
        with mock.patch.object(appmod.App, "startup_dialog", lambda self: None):
            cls.app = appmod.App(backend, note, MINI)
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        cls.app.dirty = False
        cls.app.close()

    def setUp(self):
        a = self.app
        a.dirty = False
        self.assertTrue(a.load_path(MINI))
        a.update()

    def test_screens_render(self):
        a = self.app
        for key in ("dashboard", "city", "toll", "route", "query", "map"):
            a.show(key)
            a.update()
        a.show("city")
        self.assertEqual(len(a.screens["city"].tree.get_children()), 5)
        a.show("route")
        self.assertEqual(len(a.screens["route"].tree.get_children()), 6)

    def test_query_cards(self):
        a = self.app
        a.show("query")
        wrapper = a.screens["query"]
        wrapper.tabs.set("Red de carreteras (grafos PERA)")
        wrapper.mode_changed()
        q = wrapper.graph
        q.origin.select("11001")
        q.destination.select("50001")
        q.run()
        a.update()
        self.assertEqual(q.cards["distancia"].values["km"].cget("text"), "86,0 km")
        self.assertEqual(q.cards["distancia"].values["horas"].cget("text"), "2:12 h")
        self.assertEqual(q.cards["combustible"].values["combustible"].cget("text"), "$ 34.400")
        self.assertIn("Bogotá D.C. → Tunja → Villavicencio", q.cards["peajes"].path.cget("text"))
        self.assertEqual(q.cards["peajes"].values["km"].cget("text"), "377,0 km")
        q.origin.select("11001")
        q.destination.select("91001")
        q.run()
        self.assertIn("Sin ruta registrada en esta red", q.message.cget("text"))

    def test_map_file_never_opened(self):
        a = self.app
        a.show("query")
        wrapper = a.screens["query"]
        wrapper.tabs.set("Red de carreteras (grafos PERA)")
        wrapper.mode_changed()
        q = wrapper.graph
        q.origin.select("11001")
        q.destination.select("50001")
        q.run()
        a.show("map")
        with mock.patch("webbrowser.open") as opened:
            path = a.screens["map"].generate()
            opened.assert_not_called()
        self.assertTrue(path.is_file())
        html = path.read_text(encoding="utf-8")
        self.assertIn("Menor distancia", html)
        self.assertIn("Villavicencio", html)

    def test_crud_validation_undo_and_params(self):
        a = self.app
        cities = a.screens["city"]
        dialog = cities.new()
        dialog.fields["id"].set_value("11001")  # ya existe
        for key, value in (("nombre", "Otra"), ("departamento", "X"), ("lat", "4,5"), ("lon", "-74")):
            dialog.fields[key].set_value(value)
        self.assertFalse(dialog.submit())
        self.assertIn("ya existe", dialog.error.cget("text"))
        dialog.fields["id"].set_value("68001")
        self.assertTrue(dialog.submit())
        a.update()
        self.assertEqual(len(a.data["city"]), 6)
        # ruta con dos ciudades y peajes
        dialog = a.screens["route"].new()
        dialog.fields["origen"].set_value("68001")
        dialog.fields["destino"].set_value("15001")
        dialog.fields["km"].set_value("120,5")
        dialog.fields["horas"].set_value("2,5")
        dialog.fields["peajes"].set_value(["P001", "P004"])
        self.assertTrue(dialog.submit())
        route = a.data["route"][-1]
        self.assertEqual((route["km"], route["peajes"]), (120.5, ["P001", "P004"]))
        dialog = a.screens["route"].new()
        for key, value in (("origen", "68001"), ("destino", "68001"), ("km", "1"), ("horas", "1")):
            dialog.fields[key].set_value(value)
        self.assertFalse(dialog.submit())
        self.assertIn("dos ciudades distintas", dialog.error.cget("text"))
        dialog.destroy()
        # desactivar, eliminar y deshacer
        a.show("toll")
        toll = a.screens["toll"]
        toll.tree.selection_set("P001")
        toll.toggle()
        self.assertFalse(next(t for t in a.data["toll"] if t["id"] == "P001")["activo"])
        a.undo()
        self.assertTrue(next(t for t in a.data["toll"] if t["id"] == "P001")["activo"])
        a.show("city")
        cities.tree.selection_set("68001")
        with mock.patch.object(self.appmod.messagebox, "askyesno", return_value=True):
            cities.delete()
        self.assertEqual(len(a.data["city"]), 5)
        a.undo()
        self.assertEqual(len(a.data["city"]), 6)
        # parámetros
        dialog = a.edit_params()
        dialog.fields["precio_gal"].set_value("20000")
        self.assertTrue(dialog.submit())
        self.assertEqual(a.params["precio_gal"], 20000)
        dialog = a.edit_params()
        dialog.fields["consumo_km_gal"].set_value("-3")
        self.assertFalse(dialog.submit())
        dialog.destroy()

    def test_save_open_and_bad_file(self):
        a = self.app
        target = self.tmp / "salida.csv"
        with mock.patch.object(self.appmod.filedialog, "asksaveasfilename", return_value=str(target)):
            a.save_file()
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_text(encoding="utf-8"), MINI.read_text(encoding="utf-8"))
        bad = self.tmp / "mal.csv"
        bad.write_text("esto no es un archivo\n", encoding="utf-8")
        with mock.patch.object(self.appmod.messagebox, "showerror") as err:
            self.assertFalse(a.load_path(bad))
            err.assert_called_once()
        self.assertEqual(len(a.data["city"]), 5)
        a.new_data()
        self.assertEqual(len(a.data["city"]), 0)
        a.show("dashboard")
        a.update()


if __name__ == "__main__":
    unittest.main()
