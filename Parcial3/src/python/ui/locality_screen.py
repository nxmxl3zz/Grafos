"""Consulta vial nacional: catálogo local y cálculo en segundo plano."""
from __future__ import annotations

import json
from pathlib import Path
import queue
from concurrent.futures import ThreadPoolExecutor
import customtkinter as ctk
from . import theme
from .format import fmt_cop, fmt_horas, fmt_km
from .widgets import LocalitySelector, button


class LocalityScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        from locality_catalog import load_catalog
        self.app = app
        self.app.locality_query = None
        self.generation = 0
        self.events = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pera-route")
        self.future = None
        self.bind("<Destroy>", self._destroy, add="+")
        self.signature = None
        try:
            self.records = load_catalog()
            self.catalog_error = None
        except (OSError, ValueError, KeyError) as error:
            self.records = []
            self.catalog_error = str(error)
        fonts = app.fonts
        ctk.CTkLabel(self, text="Ruta entre localidades", font=fonts['h1'], text_color=theme.INK,
                     anchor="w").pack(fill="x", pady=(0, 6))
        bar = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=10)
        bar.pack(fill='x')
        bar.grid_columnconfigure((0, 1), weight=1, uniform='locality')
        for column, title in enumerate(('Origen', 'Destino')):
            ctk.CTkLabel(bar, text=title, font=fonts['small'], text_color=theme.MUTED).grid(
                row=0, column=column, sticky='w', padx=12, pady=(8, 0))
        self.origin = LocalitySelector(bar, fonts, self.records, self.invalidate)
        self.destination = LocalitySelector(bar, fonts, self.records, self.invalidate)
        self.origin.grid(row=1, column=0, sticky='ew', padx=12, pady=(2, 8))
        self.destination.grid(row=1, column=1, sticky='ew', padx=12, pady=(2, 8))
        ctk.CTkLabel(bar, text='Pasar por (opcional: fuerza la ruta por esa localidad)', font=fonts['small'],
                     text_color=theme.MUTED).grid(row=2, column=0, columnspan=2, sticky='w', padx=12)
        self.via = LocalitySelector(bar, fonts, self.records, self.invalidate)
        self.via.grid(row=3, column=0, sticky='ew', padx=12, pady=(2, 8))
        self.calculate = button(bar, 'Calcular', self.run, fonts, primary=True, width=120)
        self.calculate.grid(row=1, column=3, padx=(6, 12), pady=(2, 8))
        self.swap = button(bar, '⇄', self.swap_places, fonts, width=40)
        self.swap.grid(row=1, column=2, pady=(2, 8))
        content = ctk.CTkScrollableFrame(self, fg_color='transparent')
        content.pack(fill='both', expand=True)
        self.stats = ctk.CTkFrame(content, fg_color='transparent')
        self.stats.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform='s')
        self.stat_values = {}
        self.stat_captions = {}
        for column, (key, caption) in enumerate((('km', 'Distancia'), ('horas', 'Tiempo'),
                                                 ('combustible', 'Combustible'), ('peajes', 'Peajes (estimación parcial)'))):
            block = ctk.CTkFrame(self.stats, fg_color=theme.CARD, corner_radius=8)
            block.grid(row=0, column=column, sticky='ew', padx=(0 if column == 0 else 4, 0))
            self.stat_values[key] = ctk.CTkLabel(block, text='—', font=fonts['h1'], text_color=theme.INK, anchor='w')
            self.stat_values[key].pack(fill='x', padx=10, pady=(8, 0))
            self.stat_captions[key] = ctk.CTkLabel(block, text=caption, font=fonts['small'], text_color=theme.MUTED, anchor='w')
            self.stat_captions[key].pack(fill='x', padx=10, pady=(0, 8))
        self.chooser = ctk.CTkSegmentedButton(content, values=['—'], command=self.choose_option, font=fonts['small'])
        self.options = {}
        self.message = ctk.CTkLabel(content, text='Escribe y selecciona origen y destino de la lista.',
                                    font=fonts['body'], text_color=theme.INK, anchor='w', justify='left',
                                    wraplength=850)
        self.message.pack(fill='x', pady=12, padx=4)
        content.bind('<Configure>', lambda e: self.message.configure(wraplength=max(e.width - 30, 200)))
        if self.catalog_error:
            self.message.configure(text='No se pudo cargar el catálogo de localidades: ' + self.catalog_error)
        self.poll_id = self.after(100, self.poll)

    def _destroy(self, event):
        if event.widget is self:
            self.generation += 1
            if getattr(self, "poll_id", None):
                self.after_cancel(self.poll_id)
            if self.future:
                self.future.cancel()
            self.executor.shutdown(wait=False, cancel_futures=True)

    def invalidate(self):
        self.generation += 1
        self.app.locality_query = None
        if self.future:
            self.future.cancel()
        if getattr(self, 'stats', None) is not None:
            self.stats.pack_forget()
        if getattr(self, 'chooser', None) is not None:
            self.chooser.pack_forget()
        if hasattr(self, 'message'):
            self.message.configure(text='Selecciona origen y destino (capitales, municipios o centros poblados) y pulsa Calcular. '
                                                  'Ejemplo: Valledupar → Sabanalarga (Atlántico). Calcular consulta el servicio de rutas '
                                                  'OSRM y necesita internet; sin conexión usa la pestaña «Red de carreteras (grafos PERA)».')
        if hasattr(self, 'calculate'):
            self.calculate.configure(state='normal')

    def refresh(self):
        sig = (tuple(sorted(self.app.params.items())), tuple((t['id'], t.get('tarifa'), t.get('activo'))
                                                            for t in self.app.data['toll']))
        if self.signature is not None and sig != self.signature:
            self.invalidate()
            self.message.configure(text='Los datos cambiaron. Vuelve a calcular la ruta.')
        self.signature = sig

    def swap_places(self):
        origin, destination = self.origin.locality(), self.destination.locality()
        self.origin.select_locality(destination)
        self.destination.select_locality(origin)

    def run(self):
        origin, destination = self.origin.locality(), self.destination.locality()
        if not origin or not destination:
            self.message.configure(text='Selecciona una localidad válida en cada lista.')
            return
        self.invalidate()
        generation = self.generation
        self.app.map_mode = 'locality'
        self.calculate.configure(state='disabled')
        self.message.configure(text='Calculando ruta vial…')
        params = dict(self.app.params)
        try:
            toll_file = Path(__file__).resolve().parents[3] / 'data/tolls_colombia.json'
            tolls = json.loads(toll_file.read_text(encoding='utf-8'))['peajes']
        except (OSError, ValueError, KeyError) as error:
            self.calculate.configure(state='normal')
            self.message.configure(text=f'No se pudo cargar el catálogo de peajes: {error}')
            return
        origin, destination = dict(origin), dict(destination)
        origin['pais'] = destination['pais'] = 'CO'
        via_selector = getattr(self, 'via', None)
        via_item = via_selector.locality() if via_selector else None
        if via_selector and via_selector.entry.get().strip() and not via_item:
            self.calculate.configure(state='normal')
            self.message.configure(text='Selecciona una localidad válida en «Pasar por» o déjalo vacío.')
            return
        vias = [dict(via_item, pais='CO')] if via_item else []

        def work():
            try:
                from locality_routing import consultar_localidades
                result = consultar_localidades(origin, destination, tolls,
                                               consumo=params.get('consumo_km_gal', 40),
                                               precio=params.get('precio_gal', 15886), via=vias)
                self.events.put((generation, result, None))
            except Exception as error:
                self.events.put((generation, None, str(error)))
        self.future = self.executor.submit(work)

    def choose_option(self, tag):
        route = self.options.get(tag)
        if route:
            render_route(self, self.current_result, route)

    def poll(self):
        try:
            while True:
                generation, result, error = self.events.get_nowait()
                if generation != self.generation:
                    continue
                self.calculate.configure(state='normal')
                if error:
                    self.message.configure(text=f'No se pudo calcular la ruta: {error}')
                    continue
                candidates = result.get('candidatos') or []
                if not candidates:
                    self.message.configure(text='El servicio no devolvió una ruta vial para estas localidades.')
                    continue
                chosen_id = (result.get('mejores') or {}).get('tiempo')
                route = next((c for c in candidates if c['id'] == chosen_id), candidates[0])
                setup_options(self, result, candidates, route)
                render_route(self, result, route)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.poll_id = self.after(100, self.poll)


def setup_options(screen, result, candidates, fastest):
    """Selector de alternativas: el usuario elige la vía que quiere ver y costear."""
    chooser = getattr(screen, 'chooser', None)
    if chooser is None:
        return
    screen.options = {}
    for index, item in enumerate(candidates, 1):
        tag = f"Opción {index}: {fmt_km(item['km'])} · {fmt_horas(item['horas'])}"
        screen.options[tag] = item
        if item is fastest:
            screen.fastest_tag = tag
    screen.current_result = result
    if len(candidates) > 1:
        chooser.configure(values=list(screen.options))
        chooser.set(screen.fastest_tag)
        chooser.pack(fill='x', padx=4, pady=(8, 0), before=screen.message)
    else:
        chooser.pack_forget()


def render_route(self, result, route):
    """Muestra una alternativa concreta: tarjetas, texto y mapa (app.locality_query)."""
    self.app.locality_query = {'result': result, 'route': route}
    toll_value = route.get('peajes_estimados')
    toll_text = f"{fmt_cop(toll_value)} COP (estimación parcial)" if toll_value is not None else 'No disponible'
    tolls = route.get('peajes') or []
    toll_lines = ', '.join(f"{t['nombre']}: {fmt_cop(t['tarifa'])} COP" if t.get('tarifa') is not None
                           else f"{t['nombre']}: sin tarifa" for t in tolls)
    params = getattr(self.app, 'params', None) or {}
    price, cons = params.get('precio_gal', 15886), params.get('consumo_km_gal', 40)
    gallons = route.get('km_conduccion', route['km']) / cons if cons else 0
    stats = getattr(self, 'stats', None)
    if stats is not None:
        values = {'km': fmt_km(route['km']), 'horas': fmt_horas(route['horas']),
                  'combustible': fmt_cop(route['combustible']),
                  'peajes': fmt_cop(toll_value) if toll_value is not None else 'No disponible'}
        for key, text in values.items():
            self.stat_values[key].configure(text=text)
        self.stat_captions['combustible'].configure(
            text=f"Combustible ({gallons:,.1f} gal × {fmt_cop(price)}/gal)".replace(',', '.'))
        chooser = getattr(self, 'chooser', None)
        anchor = chooser if chooser is not None and chooser.winfo_manager() else self.message
        stats.pack(fill='x', padx=4, pady=(8, 0), before=anchor)
    via = result.get('via') or []
    via_text = ' · vía ' + ', '.join(LocalitySelector.label(v) for v in via) if via else ''
    self.message.configure(text=(f"{LocalitySelector.label(result['origen'])} → {LocalitySelector.label(result['destino'])}{via_text}\n"
        f"{fmt_km(route['km'])} · {fmt_horas(route['horas'])} · "
        f"combustible {fmt_cop(route['combustible'])} COP · peajes {toll_text}\n"
        f"Ajuste a la vía: origen {route['snap_origen_m']:.0f} m; destino {route['snap_destino_m']:.0f} m.\n"
        f"{result.get('aviso', '')}\nPeajes: catálogo nacional independiente del grafo editable.\n"
        f"Peajes próximos detectados: {toll_lines or 'ninguno confirmado'}"))
