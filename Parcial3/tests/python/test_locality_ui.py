"""Pruebas de estados de interfaz de localidades sin servidor gráfico."""
import queue
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src/python'))
from ui.locality_screen import LocalityScreen
from ui.widgets import LocalitySelector
from ui.mapbuild import build_locality_map


class LocalityUITest(unittest.TestCase):
    def test_enter_requires_highlight_and_down_does_not_select_place(self):
        box = Mock()
        box.curselection.return_value = ()
        widget = SimpleNamespace(matches=[{'id': '1'}], listbox=box, _choose=Mock())
        LocalitySelector._enter(widget)
        widget._choose.assert_not_called()
        LocalitySelector._down(widget)
        widget._choose.assert_not_called()
        box.selection_set.assert_called_with(0)
        box.curselection.return_value = (0,)
        LocalitySelector._enter(widget)
        widget._choose.assert_called_once()

    def test_invalidate_cancels_pending_and_clears_old_result(self):
        widget = SimpleNamespace(generation=3, app=SimpleNamespace(locality_query={'old': True}),
                                 future=Mock(), message=Mock(), calculate=Mock())
        LocalityScreen.invalidate(widget)
        self.assertEqual(widget.generation, 4)
        self.assertIsNone(widget.app.locality_query)
        widget.future.cancel.assert_called_once()
        self.assertIn('Selecciona', widget.message.configure.call_args.kwargs['text'])

    def test_stale_response_never_changes_ui(self):
        events = queue.Queue()
        events.put((1, {'candidatos': []}, None))
        widget = SimpleNamespace(events=events, generation=2, calculate=Mock(), message=Mock(),
                                 app=SimpleNamespace(locality_query=None), winfo_exists=lambda: False)
        LocalityScreen.poll(widget)
        widget.calculate.configure.assert_not_called()
        widget.message.configure.assert_not_called()
        self.assertIsNone(widget.app.locality_query)

    def test_worker_publishes_queue_only_and_latest_result_wins(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        main = threading.get_ident()
        class Label:
            def __init__(self): self.values = []
            def configure(self, **values):
                self_test.assertEqual(threading.get_ident(), main)
                self.values.append(values)
        self_test = self
        place = {'id': '20001000', 'nombre': 'Valledupar', 'municipio': 'Valledupar',
                 'departamento': 'Cesar', 'lat': 10., 'lon': -73.}
        dest = dict(place, id='08638000', nombre='Sabanalarga')
        result = {'origen': place, 'destino': dest, 'aviso': 'parcial', 'mejores': {'tiempo':'A1'},
                  'candidatos': [{'id':'A1','km':1.,'horas':1.,'combustible':10,'peajes_estimados':None,
                                  'snap_origen_m':1.,'snap_destino_m':1.}]}
        executor = ThreadPoolExecutor(max_workers=1)
        widget = SimpleNamespace(origin=SimpleNamespace(locality=lambda: place),
            destination=SimpleNamespace(locality=lambda: dest), app=SimpleNamespace(locality_query=None,
            map_mode=None, params={}, data={'toll': []}), generation=0, future=None,
            calculate=Label(), message=Label(), events=queue.Queue(), executor=executor,
            winfo_exists=lambda: False)
        widget.invalidate = lambda: LocalityScreen.invalidate(widget)
        try:
            with patch('locality_routing.consultar_localidades', return_value=result):
                LocalityScreen.run(widget)
                widget.future.result(timeout=5)
            widget.events.put((widget.generation - 1, None, 'stale failure'))
            LocalityScreen.poll(widget)
            self.assertIs(widget.app.locality_query['result'], result)
            self.assertNotIn('stale failure', widget.message.values[-1]['text'])
            self.assertIn('No disponible', widget.message.values[-1]['text'])
        finally:
            executor.shutdown()

    def test_road_map_uses_geometry_and_unknown_tolls(self):
        import tempfile
        origin = {'nombre': 'Valledupar', 'municipio': 'Valledupar', 'departamento': 'Cesar', 'lat': 10., 'lon': -73.}
        dest = {'nombre': 'Sabanalarga', 'municipio': 'Sabanalarga', 'departamento': 'Atlántico', 'lat': 11., 'lon': -75.}
        route = {'geometria': [[10., -73.], [10.5, -74.], [11., -75.]], 'km': 200, 'horas': 4,
                 'combustible': 50000, 'peajes_estimados': None, 'snap_origen_m': 40, 'snap_destino_m': 80,
                 'snap_origen': [10.01, -73.01], 'snap_destino': [11.01, -75.01]}
        with tempfile.TemporaryDirectory() as folder:
            path = build_locality_map(Path(folder) / 'map.html', {'route': route, 'result': {
                'origen': origin, 'destino': dest, 'aviso': 'Tarifas parciales'}})
            html = path.read_text()
            self.assertIn('10.5, -74.0', html)
            self.assertIn('Sabanalarga', html)
            self.assertIn('No disponible', html)
            self.assertIn('Ajuste vial origen', html)


if __name__ == '__main__':
    unittest.main()
