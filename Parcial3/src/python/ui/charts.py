"""Figuras de matplotlib con el tema oscuro (sin pyplot: no se acumulan figuras abiertas)."""

from __future__ import annotations

from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator

from . import theme
from .format import es_num

def _is_cap(city_id: str) -> bool:
    """Capitales: código DANE terminado en 001 (Agua de Dios, 25001, es municipio, no capital)."""
    return city_id.endswith("001") and city_id != "25001"


UNITS = {"distancia": "km", "tiempo": "horas", "combustible": "COP", "peajes": "COP"}
TITLES = {"distancia": "Distancia de las rutas", "tiempo": "Tiempo de las rutas",
          "combustible": "Combustible por ruta", "peajes": "Peajes por ruta"}


def new_figure(width: float = 9.0, height: float = 5.0) -> Figure:
    return Figure(figsize=(width, height), dpi=100, facecolor=theme.PANEL)


def style(ax, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_facecolor(theme.CARD)
    ax.set_title(title, color=theme.INK, fontsize=11, fontweight="bold", loc="left", pad=8)
    ax.set_xlabel(xlabel, color=theme.MUTED, fontsize=9)
    ax.set_ylabel(ylabel, color=theme.MUTED, fontsize=9)
    ax.tick_params(colors=theme.MUTED, labelsize=8, length=3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(theme.LINE)
    ax.grid(color=theme.LINE, linewidth=0.6, alpha=0.7)
    ax.set_axisbelow(True)


def es_formatter(decimals: int = 0) -> FuncFormatter:
    return FuncFormatter(lambda value, _pos: es_num(value, decimals))


def empty(ax, title: str) -> None:
    style(ax, title)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.text(0.5, 0.5, "Sin datos", color=theme.MUTED, ha="center", va="center", transform=ax.transAxes)


def draw_histograms(fig: Figure, grafos: dict) -> None:
    fig.clear()
    fig.subplots_adjust(left=0.08, right=0.98, top=0.93, bottom=0.09, hspace=0.42, wspace=0.18)
    for ax, key in zip(fig.subplots(2, 2).flat, UNITS):
        graph = grafos.get(key) or {}
        hist = graph.get("hist") or {}
        limits, counts = hist.get("limites") or [], hist.get("cuentas") or []
        if not graph.get("n") or len(limits) != len(counts) + 1:
            empty(ax, TITLES[key])
            continue
        widths = [limits[i + 1] - limits[i] for i in range(len(counts))]
        widths = [w if w > 0 else max(abs(limits[0]) * 0.1, 1.0) for w in widths]
        ax.bar(limits[:-1], counts, width=widths, align="edge", color=theme.CRITERIA[key],
               edgecolor=theme.PANEL, linewidth=0.8)
        style(ax, TITLES[key], UNITS[key], "Rutas")
        logy = False
        if counts and max(counts) > 20 * max(1, sorted(counts)[len(counts) // 2]):
            ax.set_yscale("symlog", linthresh=10)   # distribuciones muy sesgadas: la escala logarítmica deja ver la cola
            ax.set_ylabel("Rutas (escala log)", color=theme.MUTED, fontsize=9)
            top = [t for t in (0, 10, 100, 1000, 10000) if t <= max(counts)]
            ax.set_yticks(top)
            ax.set_yticklabels([es_num(t) for t in top])
            logy = True
        ax.xaxis.set_major_locator(MaxNLocator(5))
        if not logy:
            ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
        ax.xaxis.set_major_formatter(es_formatter(1 if key == "tiempo" else 0))
        mean = graph.get("media")
        if mean is not None:
            ax.axvline(mean, color=theme.INK, linestyle="--", linewidth=1)
            ax.text(1.0, 1.03, f"media {es_num(mean, 1 if key == 'tiempo' else 0)} {UNITS[key]}", color=theme.MUTED,
                    fontsize=8, ha="right", va="bottom", transform=ax.transAxes)


def _barh(ax, labels: list[str], values: list[float], color: str, title: str, xlabel: str,
          decimals: int = 0) -> None:
    if not labels:
        empty(ax, title)
        return
    positions = range(len(labels))
    ax.barh(positions, values, color=color, height=0.7)
    ax.set_yticks(list(positions), labels)
    ax.invert_yaxis()
    style(ax, title, xlabel)
    ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_formatter(es_formatter(decimals))
    ax.xaxis.set_major_locator(MaxNLocator(integer=decimals == 0, nbins=5))
    top = max(values) or 1
    for pos, value in zip(positions, values):
        ax.text(value + top * 0.01, pos, es_num(value, decimals), va="center", color=theme.INK, fontsize=7)
    ax.set_xlim(0, top * 1.15)


def short(text: str, limit: int = 22) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def draw_bars(fig: Figure, stats: dict, criterion: str, city_name) -> None:
    fig.clear()
    grid = fig.add_gridspec(2, 2, left=0.17, right=0.97, top=0.94, bottom=0.07, hspace=0.42, wspace=0.62)
    departments = (stats.get("peajes_por_departamento") or [])[:10]
    _barh(fig.add_subplot(grid[0, 0]), [short(d["departamento"]) for d in departments],
          [d["cantidad"] for d in departments], theme.WARN, "Peajes por departamento", "Peajes")
    degrees = [g for g in (stats.get("grados") or [])][:12]
    _barh(fig.add_subplot(grid[0, 1]), [short(g["nombre"]) for g in degrees], [g["grado"] for g in degrees],
          theme.BLUE, "Rutas por ciudad (grado)", "Rutas")
    top = (stats.get("top_rutas") or {}).get(criterion) or []
    decimals = 1 if criterion in ("distancia", "tiempo") else 0
    ax = fig.add_subplot(grid[1, :])
    _barh(ax, [f"{short(city_name(r['origen']), 14)} – {short(city_name(r['destino']), 14)}" for r in top],
          [r["valor"] for r in top], theme.CRITERIA[criterion],
          f"Rutas con mayor valor ({UNITS[criterion]})", UNITS[criterion], decimals)


def _mid(points: list) -> tuple[float, float]:
    return points[len(points) // 2][1], points[len(points) // 2][0]


def _t(text: str) -> str:
    """Matplotlib interpreta pares de '$' como matemáticas: se escapan."""
    return text.replace("$", r"\$")


def _wrap(text: str, width: int = 56) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width=width) or [""]


def _panel(fig: Figure, blocks: list[list[tuple[str, str, bool]]]) -> None:
    """Panel de texto a la derecha: bloques de líneas (texto, color, negrita)."""
    from matplotlib.offsetbox import AnchoredOffsetbox, TextArea, VPacker
    boxes = []
    for block in blocks:
        for text, color, bold in block:
            boxes.append(TextArea(_t(text), textprops=dict(color=color, fontsize=9.5,
                                                              fontweight="bold" if bold else "normal")))
        boxes.append(TextArea(" ", textprops=dict(fontsize=4)))
    pack = VPacker(children=boxes, align="left", pad=0, sep=2)
    panel = fig.add_axes([0.55, 0.02, 0.44, 0.93])
    panel.axis("off")
    panel.add_artist(AnchoredOffsetbox(loc="upper left", child=pack, pad=0.2, frameon=False,
                                       bbox_to_anchor=(0, 1), bbox_transform=panel.transAxes, borderpad=0))


def draw_network(fig: Figure, cities: list[dict], routes: list[dict], query: dict | None,
                 selected: tuple[str, dict] | None = None, tolls: list[dict] | None = None,
                 view: tuple | None = None) -> None:
    """Mapa de la red (límites departamentales, trazado vial, peajes) y panel con tarifas, tiempos y costos."""
    from . import geodata
    from .format import compare_text, fmt_cop, fmt_horas, fmt_km
    fig.clear()
    ax = fig.add_axes([0.06, 0.0, 0.48, 0.97])
    ax.set_facecolor(theme.PANEL)
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ax.spines.values():
        side.set_visible(False)
    ax.set_aspect("equal", adjustable="box", anchor="W")
    for dep in geodata.departments():
        for ring in dep["anillos"]:
            ax.fill([p[1] for p in ring], [p[0] for p in ring], facecolor=theme.CARD, edgecolor=theme.LINE,
                    linewidth=0.6, zorder=0)
    ax.set_xlim(-79.4, -66.6)
    ax.set_ylim(-4.4, 12.7)
    by_id = {c["id"]: c for c in cities}
    toll_by_id = {t["id"]: t for t in (tolls or [])}
    route_by_id = {r["id"]: r for r in routes}
    from matplotlib.collections import LineCollection
    dense = len(routes) > 600
    good, bad = [], []
    for route in routes:
        pts = geodata.route_points(route, by_id)
        if len(pts) >= 2:
            (good if route.get("efectiva", True) else bad).append([(p[1], p[0]) for p in pts])
    if good:
        ax.add_collection(LineCollection(good, colors="#5b6b7d", linewidths=0.6 if dense else 1.1, alpha=0.9, zorder=1))
    if bad:
        ax.add_collection(LineCollection(bad, colors="#6a4a4a", linewidths=1.0, linestyles=":", alpha=0.9, zorder=1))
    live = [t for t in (tolls or []) if t.get("activo", True)]
    ax.scatter([t["lon"] for t in live], [t["lat"] for t in live], s=6 if dense else 8, color=theme.WARN, alpha=0.6, zorder=2)
    widths = {"distancia": 6.0, "tiempo": 4.5, "combustible": 3.2, "peajes": 2.0, "total": 2.6}
    blocks: list[list[tuple[str, str, bool]]] = []
    criteria = (query or {}).get("criterios") or {}
    if criteria:
        blocks.append([(f"{by_id.get(query['from'], {}).get('nombre', query['from'])} → "
                        f"{by_id.get(query['to'], {}).get('nombre', query['to'])}", theme.INK, True)])
    groups: dict[tuple, list[str]] = {}
    for key, info in criteria.items():
        groups.setdefault((tuple(info["rutas"]), tuple(info["ciudades"])), []).append(key)
    for key, info in criteria.items():
        same = groups[(tuple(info["rutas"]), tuple(info["ciudades"]))]
        if same[0] != key:
            continue  # rutas idénticas: un solo bloque, con todos los criterios en el título
        names: list[str] = []
        for rid in info.get("rutas", []):
            route = route_by_id.get(rid)
            if not route:
                continue
            pts = geodata.route_points(route, by_id)
            if len(pts) >= 2:
                ax.plot([p[1] for p in pts], [p[0] for p in pts], color=theme.CRITERIA[key], linewidth=widths.get(key, 3) * 0.7,
                        alpha=0.95, zorder=3, solid_capstyle="round")
                if len(info["rutas"]) <= 3 and ("distancia" in same or len(same) == 1 and key != "peajes"):
                    x, y = _mid(pts)
                    ax.annotate(f"{fmt_km(route['km'])} · {fmt_horas(route['horas'])}", (x, y), color=theme.INK, fontsize=7,
                                xytext=(8, 0), textcoords="offset points", zorder=8,
                                bbox=dict(boxstyle="round,pad=0.2", fc=theme.PANEL, ec=theme.CRITERIA[key], lw=0.8))
            for tid in route.get("peajes", []):
                toll = toll_by_id.get(tid)
                if toll and toll["nombre"] not in names:
                    names.append(f"{toll['nombre']} {fmt_cop(toll['tarifa'])}")
                    ax.scatter([toll["lon"]], [toll["lat"]], s=30, color=theme.WARN, edgecolors=theme.BG, zorder=4)
        t = info["totales"]
        tail = [(f"{fmt_km(t['km'])} · {fmt_horas(t['horas'])} · combustible {fmt_cop(t['combustible'])} · "
                 f"peajes {fmt_cop(t['peajes'])}", theme.INK, False)]
        base = (criteria.get("distancia") or {}).get("totales")
        if base and "distancia" not in same:
            note = compare_text(base, t)
            if note:
                tail += [(line, theme.DANGER if t["km"] > base["km"] * 1.5 else theme.MUTED, False) for line in _wrap(note)]
        from .format import short_path
        route_line = short_path([by_id[c]["nombre"] if c in by_id else c for c in info["ciudades"]])
        tail += [(line, theme.MUTED, False) for line in _wrap(route_line)]
        if names:
            shown = names[:8] + ([f"+{len(names) - 8} más"] if len(names) > 8 else [])
            tail += [(line, theme.WARN, False) for line in _wrap("Peajes: " + ", ".join(shown))]
        title = " · ".join(theme.CRITERIA_TITLES[k].replace("Menor ", "").replace("costo en ", "").replace("costo total (combustible + peajes)", "costo total") for k in same)
        blocks.append([("Menor " + title if len(same) > 1 else theme.CRITERIA_TITLES[key], theme.CRITERIA[key], True)] + tail)
    if selected:
        kind, item = selected
        if kind == "route":
            pts = geodata.route_points(item, by_id)
            a, b = by_id.get(item["origen"]), by_id.get(item["destino"])
            if len(pts) >= 2:
                ax.plot([p[1] for p in pts], [p[0] for p in pts], color="#ffffff", linewidth=3.2, linestyle="--", zorder=8)
            ts = [toll_by_id[i] for i in item.get("peajes", []) if i in toll_by_id]
            for toll in ts:
                ax.scatter([toll["lon"]], [toll["lat"]], s=34, color=theme.WARN, edgecolors="#ffffff", zorder=9)
                ax.annotate(fmt_cop(toll["tarifa"]), (toll["lon"], toll["lat"]), color="#ffffff", fontsize=6.5,
                            xytext=(4, -9), textcoords="offset points", zorder=9)
            head = f"Ruta {item['id']}: {a['nombre'] if a else '?'} – {b['nombre'] if b else '?'}"
            lines = [(head, "#ffffff", True),
                     (f"{fmt_km(item['km'])} · {fmt_horas(item['horas'])} · combustible {fmt_cop(item['combustible'])} · "
                      f"peajes {fmt_cop(item['peajes_costo'])}", theme.INK, False)]
            lines += [(line, theme.WARN, False) for line in
                      _wrap("Peajes: " + (", ".join(f"{x['nombre']} {fmt_cop(x['tarifa'])}" for x in ts) or "ninguno"))]
            if not geodata.is_road(item):
                lines.append(("Ruta editada: segmento recto entre ciudades, no trazado vial.", theme.MUTED, False))
            blocks.append(lines)
        elif kind == "toll":
            ax.scatter([item["lon"]], [item["lat"]], marker="*", s=220, color=theme.WARN, edgecolors="#ffffff",
                       linewidths=1, zorder=9)
            state = "activo" if item.get("activo", True) else "inactivo"
            blocks.append([(f"Peaje {item['id']}: {item['nombre']}", "#ffffff", True),
                           (f"Tarifa categoría I: {fmt_cop(item['tarifa'])} COP · {state}", theme.INK, False)])
    if not blocks:
        blocks.append([("Red de rutas y peajes", theme.INK, True),
                       ("Naranja: peajes. Haz una consulta o elige una ruta o un peaje para ver tiempos, costos y tarifas aquí.",
                        theme.MUTED, False)])
    capitals = [c for c in cities if _is_cap(c["id"])]
    towns_ = [c for c in cities if not _is_cap(c["id"])]
    ax.scatter([c["lon"] for c in towns_], [c["lat"] for c in towns_], s=3 if dense else 9, color=theme.MUTED,
               edgecolors="none" if dense else theme.BG, linewidths=0.5, zorder=5)
    ax.scatter([c["lon"] for c in capitals], [c["lat"] for c in capitals], s=26, color=theme.ACCENT, edgecolors=theme.BG,
               linewidths=0.8, zorder=5)
    on_path = set()
    for info in criteria.values():
        on_path.update(info.get("ciudades", []))
    if selected and selected[0] == "route":
        on_path.update((selected[1]["origen"], selected[1]["destino"]))
    zoomed = bool(view) and (view[0][1] - view[0][0]) < 5.5
    for c in cities:
        if _is_cap(c["id"]) or c["id"] in on_path or zoomed:
            ax.annotate(c["nombre"], (c["lon"], c["lat"]), color=theme.INK if _is_cap(c["id"]) else theme.MUTED,
                        fontsize=6.5 if _is_cap(c["id"]) else 6, xytext=(4, -8), textcoords="offset points", zorder=6)
    if view:  # zoom/desplazamiento del usuario
        ax.set_xlim(*view[0])
        ax.set_ylim(*view[1])
    _panel(fig, blocks)


def draw_locality_route(fig: Figure, query: dict, view: tuple | None = None) -> None:
    """Geometría vial real del servicio sobre los límites departamentales; peajes con tarifa y resumen de costos."""
    from . import geodata
    from .format import fmt_cop, fmt_horas, fmt_km
    fig.clear()
    ax = fig.add_axes([0.01, 0.01, 0.98, 0.93])
    ax.set_facecolor(theme.PANEL)
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ax.spines.values():
        side.set_visible(False)
    for dep in geodata.departments():
        for ring in dep["anillos"]:
            ax.fill([p[1] for p in ring], [p[0] for p in ring], facecolor=theme.CARD, edgecolor=theme.LINE,
                    linewidth=0.6, zorder=0)
    route, result = query["route"], query["result"]
    points = route["geometria"]
    xs, ys = [], []
    if points:
        xs, ys = [p[1] for p in points], [p[0] for p in points]
        ax.plot(xs, ys, color=theme.BLUE, linewidth=2.4, zorder=3, solid_capstyle="round")
    tolls = route.get("peajes") or []
    if tolls:
        ax.scatter([t["lon"] for t in tolls], [t["lat"] for t in tolls], s=34, color=theme.WARN, marker="^",
                   edgecolors=theme.BG, zorder=4)
        for t in tolls:
            if t.get("tarifa") is not None:
                ax.annotate(fmt_cop(t["tarifa"]), (t["lon"], t["lat"]), color=theme.WARN, fontsize=7, xytext=(4, 4),
                            textcoords="offset points", zorder=7)
    for key in ("snap_origen", "snap_destino"):
        point = route.get(key)
        if point:
            ax.scatter([point[1]], [point[0]], s=22, color=theme.BLUE, zorder=4)
    for title, item in (("Origen", result["origen"]), ("Destino", result["destino"])):
        ax.scatter([item["lon"]], [item["lat"]], s=60, color=theme.ACCENT, edgecolors="#ffffff", zorder=5)
        ax.annotate(title + ": " + item["nombre"], (item["lon"], item["lat"]), color=theme.INK, xytext=(6, 6),
                    textcoords="offset points", fontsize=9, fontweight="bold", zorder=8)
        xs.append(item["lon"]); ys.append(item["lat"])
    if xs:
        pad = max((max(xs) - min(xs)), (max(ys) - min(ys)), 0.5) * 0.12
        ax.set_xlim(min(xs) - pad, max(xs) + pad)
        ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_aspect("equal", adjustable="datalim")
    if view:
        ax.set_xlim(*view[0])
        ax.set_ylim(*view[1])
    toll_total = route.get("peajes_estimados")
    toll_text = f"{fmt_cop(toll_total)} (estimación parcial)" if toll_total is not None else "no disponible"
    box = (f"{fmt_km(route['km'])} · {fmt_horas(route['horas'])}\ncombustible {fmt_cop(route['combustible'])} · peajes {toll_text}")
    ax.text(0.015, 0.985, _t(box), transform=ax.transAxes, va="top", ha="left", color=theme.INK, fontsize=9,
            bbox=dict(boxstyle="round,pad=0.4", fc=theme.PANEL, ec=theme.LINE), zorder=10)
