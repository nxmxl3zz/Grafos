"""Comprueba los datos visibles del mapa sin abrir una ventana ni un navegador."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src' / 'python'))
from pera_engine import Engine
from ui.mapbuild import build_map


class MapBuildTest(unittest.TestCase):
    def test_details_and_query_states(self):
        engine = Engine()
        def call(**request):
            response = engine.handle(request)
            self.assertTrue(response['ok'], response)
            return response['result']
        call(action='load', path=str(ROOT / 'tests/fixtures/mini.csv'))
        cities, routes, tolls = [call(action='list', kind=k)['items'] for k in ('city', 'route', 'toll')]
        tolls[0]['nombre'] = '<Peaje & prueba>` ${alert(1)} </script> \"x\"'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'map.html'
            for destination, expected in [('50001', '86,0 km'), ('11001', '0,0 km'),
                                          ('91001', 'Sin ruta registrada')]:
                query = call(action='query', **{'from': '11001', 'to': destination})
                build_map(path, cities, routes, tolls, query)
                html = path.read_text()
                self.assertIn(expected, html)
                self.assertIn('&lt;Peaje &amp; prueba&gt;', html)
                self.assertNotIn('<Peaje & prueba>', html)
                self.assertNotIn('${alert(1)}', html)
                self.assertIn('&#96; &#36;{alert(1)} &lt;/script&gt;', html)
                self.assertIn('&quot;x&quot;', html)
                self.assertIn('combustible', html)
                self.assertIn(' COP', html)
                self.assertNotIn('Seleccione…</option>', html)
                self.assertIn('id="pera-value">Ruta', html)
                self.assertIn('window.peraSelect', html)
                self.assertIn('selected.layer.addTo(map)', html)
                self.assertIn('selected.item.openPopup()', html)
                self.assertIn('selected.item.getBounds()', html)
                self.assertIn('Trazado vial aproximado', html)
            build_map(path, [], [], [], None)
            self.assertIn('Sin consulta reciente', path.read_text())

class MapScreenTest(unittest.TestCase):
    def test_refresh_invalidates_and_preserves_selection(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from ui.map_screen import MapScreen
        engine = Engine()
        def call(**request):
            return engine.handle(request)['result']
        call(action='load', path=str(ROOT / 'tests/fixtures/mini.csv'))
        data = {k: call(action='list', kind=k)['items'] for k in ('city', 'route', 'toll')}
        app = SimpleNamespace(last_query=call(action='query', **{'from': '11001', 'to': '50001'}),
                              data=data, city_name=lambda city: city)
        selector = Mock()
        selector.get.return_value = 'Peaje P001 · Andes (activo)'
        screen = SimpleNamespace(app=app, path=Path('/tmp/old.html'), open_button=Mock(), info=Mock(),
                                 selector=selector, detail_label=Mock(), note=Mock(), preview=SimpleNamespace(figure=Mock(), redraw=Mock()))
        screen.access_metadata = lambda: {'ciudades': {'50001': {'nombre': 'Destino', 'estado': 'Estacional', 'explicacion': 'Verificar transporte'}}}
        screen.invalidate_map = lambda: MapScreen.invalidate_map(screen)
        screen.show_detail = lambda name: MapScreen.show_detail(screen, name)
        # Use an actual option, whose text is derived from the engine fixture.
        toll = data['toll'][0]
        selected = f"Peaje {toll['id']} · {toll['nombre']} ({'activo' if toll.get('activo', True) else 'inactivo'})"
        selector.get.return_value = selected
        with patch('ui.map_screen.charts.draw_network') as draw:
            MapScreen.refresh(screen)
        self.assertIsNone(screen.path)
        screen.open_button.configure.assert_called_with(state='disabled')
        selector.set.assert_called_with(selected)
        self.assertIn('COP', screen.detail_label.configure.call_args.kwargs['text'])
        self.assertEqual(draw.call_args.args[-2][0], 'toll')
        text = screen.info.configure.call_args.kwargs['text']
        self.assertIn('Estacional', text)
        app.last_query = {'from': '11001', 'to': '50001', 'alcanzable': False}
        with patch('ui.map_screen.charts.draw_network'):
            MapScreen.refresh(screen)
        self.assertIn('Verificar transporte', screen.info.configure.call_args.kwargs['text'])
        for criterion in ('distancia', 'tiempo', 'combustible', 'peajes'):
            self.assertIn(criterion, text.lower())


if __name__ == '__main__':
    unittest.main()
