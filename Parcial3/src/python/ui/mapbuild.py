"""Mapa Folium (HTML) de ciudades, rutas efectivas y peajes; resalta la última consulta por criterio."""

from __future__ import annotations

from html import escape as html_escape
from pathlib import Path

from . import geodata, theme
from .format import fmt_cop, fmt_horas, fmt_km

INACTIVE = "#7a8696"


def escape(value: str, quote: bool = True) -> str:
    """Escapa HTML y delimitadores de las plantillas JavaScript que usa Folium."""
    return html_escape(value, quote=quote).replace("\\", "&#92;").replace("`", "&#96;").replace("$", "&#36;")


VENDOR = Path(__file__).resolve().parents[3] / "data" / "vendor"
_INLINE = {"leaflet.js": "leaflet.js", "jquery-3.7.1.min.js": "jquery.min.js", "bootstrap.bundle.min.js": "bootstrap.bundle.min.js",
           "leaflet.css": "leaflet.css", "bootstrap.min.css": "bootstrap.min.css"}


def _data_uri(name: str) -> str:
    import base64
    return "data:image/png;base64," + base64.b64encode((VENDOR / name).read_bytes()).decode()


def make_offline(path: Path) -> None:
    """Incrusta Leaflet/Bootstrap/jQuery en el HTML y elimina todo recurso externo: se abre sin internet."""
    import re
    html = path.read_text(encoding="utf-8")

    def script(match):
        name = _INLINE.get(match.group(1).rsplit("/", 1)[-1])
        if not name:
            return ""
        return "<script>" + (VENDOR / name).read_text(encoding="utf-8").replace("</script", "<\\/script") + "</script>"

    def style(match):
        name = _INLINE.get(match.group(1).rsplit("/", 1)[-1])
        if not name:
            return ""
        css = (VENDOR / name).read_text(encoding="utf-8")
        for image in ("layers-2x.png", "layers.png", "marker-icon.png"):
            css = css.replace(f"url(images/{image})", f"url({_data_uri(image)})")
        return "<style>" + css + "</style>"

    html = re.sub(r'<script src="(https?://[^"]+)"></script>', script, html)
    html = re.sub(r'<link rel="stylesheet" href="(https?://[^"]+)"\s*/?>', style, html)
    path.write_text(html, encoding="utf-8")


def add_backdrop(fmap, folium) -> None:
    """Fondo sin internet: límites departamentales; los mosaicos de OpenStreetMap quedan como capa opcional."""
    fmap.get_root().header.add_child(folium.Element(
        "<style>.leaflet-container{background:#cfdbe6!important}.leaflet-tooltip{font-size:10px;padding:0 3px;line-height:1.25;box-shadow:none}</style>"))
    layer = folium.FeatureGroup(name="Límites departamentales (sin internet)")
    for dep in geodata.departments():
        for ring in dep["anillos"]:
            folium.Polygon(ring, color="#8795a5", weight=1, fill=True, fill_color="#eef1ec", fill_opacity=1,
                           interactive=False).add_to(layer)
    layer.add_to(fmap)
    folium.TileLayer("OpenStreetMap", name="Mapa base en línea (OpenStreetMap, requiere internet)",
                     overlay=True, show=False).add_to(fmap)


def build_map(path: Path, cities: list[dict], routes: list[dict], tolls: list[dict],
              query: dict | None = None, access: dict | None = None) -> Path:
    import folium

    by_id = {c["id"]: c for c in cities}
    active = [c for c in cities if c.get("activo", True)] or cities
    center = [sum(c["lat"] for c in active) / len(active), sum(c["lon"] for c in active) / len(active)] \
        if active else [4.6, -74.1]
    fmap = folium.Map(location=center, zoom_start=6, tiles=None, control_scale=True)
    add_backdrop(fmap, folium)

    route_objects = {}
    toll_objects = {}
    layer_routes = folium.FeatureGroup(name="Rutas efectivas")
    layer_off = folium.FeatureGroup(name="Rutas inactivas", show=False)
    for route in routes:
        a, b = by_id.get(route["origen"]), by_id.get(route["destino"])
        if not a or not b:
            continue
        effective = route.get("efectiva", True)
        tip = (f"{route['id']}: {a['nombre']} – {b['nombre']} · {fmt_km(route['km'])} · {fmt_horas(route['horas'])}"
               f" · combustible {fmt_cop(route['combustible'])} COP · peajes {fmt_cop(route['peajes_costo'])} COP")
        line = folium.PolyLine(geodata.route_points(route, by_id), color="#5b6b7d" if effective else INACTIVE,
                        weight=2, opacity=0.8, dash_array=None if effective else "6 6",
                        tooltip=escape(tip), popup=folium.Popup(escape(tip), max_width=350)).add_to(layer_routes if effective else layer_off)
        route_objects[route["id"]] = (line, layer_routes if effective else layer_off)
    layer_routes.add_to(fmap)
    layer_off.add_to(fmap)

    access_cities = (access or {}).get("ciudades", {})
    layer_cities = folium.FeatureGroup(name="Ciudades")
    for city in cities:
        access_info = access_cities.get(city["id"], {})
        city_detail = f"{city['nombre']} · {city['departamento']} · {city.get('grado', 0)} rutas"
        if access_info:
            city_detail += f" · {access_info['estado']}. {access_info['explicacion']}"
        folium.CircleMarker([city["lat"], city["lon"]], radius=6, weight=2, fill=True, fill_opacity=0.9,
                            color=theme.ACCENT if city.get("activo", True) else INACTIVE,
                            fill_color=theme.ACCENT if city.get("activo", True) else INACTIVE,
                            tooltip=escape(f"{city['nombre']} ({city['departamento']})"),
                            popup=folium.Popup(escape(city_detail), max_width=400)
                            ).add_to(layer_cities)
    layer_cities.add_to(fmap)

    layer_tolls = folium.FeatureGroup(name="Peajes", show=True)
    for toll in tolls:
        marker = folium.CircleMarker([toll["lat"], toll["lon"]], radius=4, weight=1, fill=True, fill_opacity=0.9,
                            color=theme.WARN if toll.get("activo", True) else INACTIVE,
                            fill_color=theme.WARN if toll.get("activo", True) else INACTIVE,
                            tooltip=escape(f"{toll['nombre']} · {fmt_cop(toll['tarifa'])} COP"),
                            popup=folium.Popup(escape(f"{toll['nombre']} · {fmt_cop(toll['tarifa'])} COP · {'Activo' if toll.get('activo', True) else 'Inactivo'}"), max_width=350)).add_to(layer_tolls)
        toll_objects[toll["id"]] = (marker, layer_tolls)
    layer_tolls.add_to(fmap)

    route_by_id = {r["id"]: r for r in routes}
    toll_by_id = {t["id"]: t for t in tolls}
    widths = {"distancia": 9, "tiempo": 7, "combustible": 5, "peajes": 3, "total": 4}
    labelled = set()
    for key, info in ((query or {}).get("criterios") or {}).items():
        totals = info["totales"]
        tip = (f"{theme.CRITERIA_TITLES[key]}: {fmt_km(totals['km'])} · {fmt_horas(totals['horas'])} · "
               f"combustible {fmt_cop(totals['combustible'])} COP · peajes {fmt_cop(totals['peajes'])} COP")
        group = folium.FeatureGroup(name=theme.CRITERIA_TITLES[key])
        drawn = False
        for rid in info.get("rutas", []):
            route = route_by_id.get(rid)
            if route:
                folium.PolyLine(geodata.route_points(route, by_id), color=theme.CRITERIA[key], weight=widths.get(key, 5),
                                opacity=0.9, tooltip=escape(tip), popup=folium.Popup(escape(tip), max_width=350)).add_to(group)
                drawn = True
                if key == next(iter(query["criterios"])):  # tarifas visibles solo en el primer criterio: evita amontonar
                    labelled.update(route.get("peajes", []))
        if not drawn:
            points = [[by_id[i]["lat"], by_id[i]["lon"]] for i in info["ciudades"] if i in by_id]
            if len(points) >= 2:
                folium.PolyLine(points, color=theme.CRITERIA[key], weight=6, opacity=0.9, tooltip=escape(tip),
                                popup=folium.Popup(escape(tip), max_width=350)).add_to(group)
        group.add_to(fmap)
    if labelled:  # peajes de las rutas consultadas: tarifa siempre visible
        layer_labels = folium.FeatureGroup(name="Tarifas de la consulta")
        for tid in labelled:
            toll = toll_by_id.get(tid)
            if toll:
                folium.CircleMarker([toll["lat"], toll["lon"]], radius=6, weight=2, color="#ffffff", fill=True,
                                    fill_color=theme.WARN, fill_opacity=1,
                                    tooltip=folium.Tooltip(escape(f"{fmt_cop(toll['tarifa'])}"), permanent=True,
                                                           direction="right")).add_to(layer_labels)
        layer_labels.add_to(fmap)

    # Selectores siempre visibles: evitan llenar el país con etiquetas superpuestas.
    choices = []
    for route in routes:
        a, b = by_id.get(route["origen"]), by_id.get(route["destino"])
        if a and b:
            state = "efectiva" if route.get("efectiva", True) else "inactiva"
            title = f"Ruta {route['id']}: {a['nombre']} – {b['nombre']} ({state})"
            detail = (f"{title} · {fmt_km(route['km'])} · {fmt_horas(route['horas'])} · "
                      f"combustible {fmt_cop(route['combustible'])} COP · peajes {fmt_cop(route['peajes_costo'])} COP")
            choices.append((title, detail, *route_objects[route["id"]], "route"))
    for toll in tolls:
        state = "activo" if toll.get("activo", True) else "inactivo"
        title = f"Peaje {toll['nombre']} ({state})"
        choices.append((title, f"{title} · tarifa {fmt_cop(toll['tarifa'])} COP", *toll_objects[toll["id"]], "toll"))
    options = ''.join(f'<option value="{index}" data-detail="{escape(detail, quote=True)}">{escape(title)}</option>'
                      for index, (title, detail, _obj, _layer, _kind) in enumerate(choices))
    initial = choices[0][1] if choices else "Sin rutas ni peajes registrados."
    if query and query.get("alcanzable"):
        lines = []
        for key, info in (query.get("criterios") or {}).items():
            t = info['totales']
            lines.append(f"{theme.CRITERIA_TITLES[key]}: {fmt_km(t['km'])} · {fmt_horas(t['horas'])} · "
                         f"combustible {fmt_cop(t['combustible'])} COP · peajes {fmt_cop(t['peajes'])} COP")
        summary = '<br>'.join(escape(line) for line in lines) or 'Sin resultados por criterio.'
    elif query:
        summary = 'Sin ruta registrada en esta red para la última consulta.'
    else:
        summary = 'Sin consulta reciente.'
    if access and query:
        for city_id in (query.get('from'), query.get('to')):
            info = access_cities.get(city_id)
            if info:
                summary += '<br>' + escape(f"{info['nombre']}: {info['estado']}. {info['explicacion']}")
    panel = f"""<div style="position:absolute;z-index:1000;bottom:20px;left:10px;background:white;
      padding:10px;max-width:380px;max-height:40%;overflow:auto;box-shadow:0 1px 5px #888;font:13px sans-serif">
      <strong>Detalle de la red</strong><br>Trazado vial aproximado (OSRM simplificado); las rutas editadas se dibujan como segmento recto. Servicios estacionales y tarifas de transporte no modeladas requieren confirmación.<br>
      <label for="pera-detail">Seleccione una ruta o peaje:</label><br>
      <select id="pera-detail" style="max-width:100%;width:100%" onchange="document.getElementById('pera-value').textContent=this.selectedOptions[0].dataset.detail;window.peraSelect(Number(this.value))">
      {options or '<option>Sin elementos</option>'}</select>
      <div id="pera-value">{escape(initial)}</div>
      <strong>Última consulta</strong><div>{summary}</div></div>"""
    fmap.get_root().html.add_child(folium.Element(panel))
    # Solo referencias generadas por Folium y enteros llegan al JavaScript; los textos
    # editables permanecen escapados en atributos HTML, nunca como código.
    refs = ",".join(f"{{item:{obj.get_name()},layer:{layer.get_name()},route:{str(kind == 'route').lower()}}}"
                    for _title, _detail, obj, layer, kind in choices)
    js = f"""window.peraSelect = function(index) {{
      const choices = [{refs}], selected = choices[index];
      if (!selected) return;
      const map = {fmap.get_name()};
      if (!map.hasLayer(selected.layer)) selected.layer.addTo(map);
      if (selected.route) map.fitBounds(selected.item.getBounds(), {{padding:[60,60], maxZoom:10}});
      else map.setView(selected.item.getLatLng(), 10);
      selected.item.openPopup();
    }};"""
    fmap.get_root().script.add_child(folium.Element(js))

    if len(active) > 1:  # encuadra todas las ciudades activas, no un zoom fijo
        fmap.fit_bounds([[min(c["lat"] for c in active), min(c["lon"] for c in active)],
                         [max(c["lat"] for c in active), max(c["lon"] for c in active)]], padding=(30, 30))
    folium.LayerControl(collapsed=False).add_to(fmap)
    path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(path))
    make_offline(path)
    return path


def build_locality_map(path: Path, query: dict) -> Path:
    """Mapa de la geometría vial devuelta para localidades, separado del grafo."""
    import folium
    result, route = query['result'], query['route']
    points = route['geometria']
    origin, destination = result['origen'], result['destino']
    center = [origin['lat'], origin['lon']]
    fmap = folium.Map(location=center, zoom_start=7, tiles=None, control_scale=True)
    add_backdrop(fmap, folium)
    if len(points) >= 2:
        folium.PolyLine(points, color=theme.BLUE, weight=5, opacity=.9).add_to(fmap)
    for title, place in (('Origen', origin), ('Destino', destination)):
        name = f"{title}: {place['nombre']} — {place['municipio']}, {place['departamento']}"
        folium.Marker([place['lat'], place['lon']], tooltip=escape(name),
                      popup=folium.Popup(escape(name))).add_to(fmap)
    for title, key in (('Ajuste vial origen', 'snap_origen'), ('Ajuste vial destino', 'snap_destino')):
        point = route.get(key)
        if point:
            folium.CircleMarker(point, radius=4, color=theme.BLUE, fill=True,
                                tooltip=escape(title)).add_to(fmap)
    toll_layer = folium.FeatureGroup(name='Peajes próximos (paso no confirmado)')
    for item in route.get('peajes', []):
        state = 'activo' if item.get('activo', True) else 'inactivo'
        value = f"{fmt_cop(item['tarifa'])} COP" if item.get('tarifa') is not None else 'sin tarifa'
        text = f"{item['nombre']} · {value} · {state} · próximo a la ruta; paso no confirmado"
        folium.CircleMarker([item['lat'], item['lon']], radius=5, color=theme.WARN if item.get('activo', True) else INACTIVE,
                            fill=True, tooltip=escape(text), popup=folium.Popup(escape(text))).add_to(toll_layer)
    toll_layer.add_to(fmap)
    folium.LayerControl().add_to(fmap)
    toll = route.get('peajes_estimados')
    toll_text = f"{fmt_cop(toll)} COP (estimación parcial)" if toll is not None else 'No disponible'
    details = (f"{fmt_km(route['km'])} · {fmt_horas(route['horas'])} · combustible "
               f"{fmt_cop(route['combustible'])} COP · peajes {toll_text}. "
               f"Ajuste a la vía: origen {route['snap_origen_m']:.0f} m; "
               f"destino {route['snap_destino_m']:.0f} m. {result.get('aviso', '')}")
    nearby = ', '.join(f"{t['nombre']}: {fmt_cop(t['tarifa'])} COP" if t.get('tarifa') is not None else f"{t['nombre']}: sin tarifa" for t in route.get('peajes', []))
    details += f" Peajes próximos detectados: {nearby or 'ninguno confirmado'}. Catálogo nacional independiente del grafo editable."
    panel = f'''<div style="position:absolute;z-index:1000;bottom:20px;left:10px;background:white;
    padding:10px;max-width:380px;max-height:40%;overflow:auto;box-shadow:0 1px 5px #888;font:13px sans-serif">
    <strong>Ruta vial OSRM: {escape(origin['nombre'])}, {escape(origin['municipio'])}, {escape(origin['departamento'])} → {escape(destination['nombre'])}, {escape(destination['municipio'])}, {escape(destination['departamento'])}</strong><br>{escape(details)}</div>'''
    fmap.get_root().html.add_child(folium.Element(panel))
    bounds = list(points) + [[origin['lat'], origin['lon']], [destination['lat'], destination['lon']]]
    if len(bounds) > 1:
        fmap.fit_bounds(bounds, padding=(30, 30))
    path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(path))
    make_offline(path)
    return path
