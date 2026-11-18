"""Genera la especificación técnica de PERA (Parcial 3, grafos) en formato DOCX.

Uso (necesita python-docx, Pillow y graphviz `dot`):
    python scripts/build_technical_spec.py
Salida: docs/especificacion_tecnica.docx
"""

from __future__ import annotations

from pathlib import Path
import os
import re
import subprocess
import tempfile

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/especificacion_tecnica.docx"
FONT = "/usr/share/fonts/TTF/DejaVuSansCondensed.ttf"
BOLD_FONT = "/usr/share/fonts/TTF/DejaVuSansCondensed-Bold.ttf"
NAVY = (25, 52, 78)
PALE = (232, 239, 246)
GRAY = (90, 103, 115)
WARN = (252, 228, 214)
INACTIVE = (225, 225, 225)
WIDTH = 1400  # ancho base de los diagramas; se inserta a ~16 cm, texto >= 8 pt


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(BOLD_FONT if bold else FONT, size)


def text_width(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont) -> int:
    return int(draw.textlength(text, font=f))


def center_text(draw, cx: int, y: int, text: str, f, fill=NAVY) -> None:
    draw.text((cx - text_width(draw, text, f) // 2, y), text, font=f, fill=fill)


def arrow_head(draw, end, direction, size=16, fill=NAVY) -> None:
    x, y = end
    dx, dy = direction
    px, py = -dy, dx
    draw.polygon([(x, y), (x - dx * size + px * size * 0.5, y - dy * size + py * size * 0.5),
                  (x - dx * size - px * size * 0.5, y - dy * size - py * size * 0.5)], fill=fill)


def line_arrow(draw, start, end, width=3, dashed=False, fill=NAVY) -> None:
    (x1, y1), (x2, y2) = start, end
    length = max(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, 1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    if dashed:
        pos = 0.0
        while pos < length - 16:
            seg = min(12, length - 16 - pos)
            draw.line((x1 + ux * pos, y1 + uy * pos, x1 + ux * (pos + seg), y1 + uy * (pos + seg)),
                      fill=fill, width=width)
            pos += 22
    else:
        draw.line((start, (x2 - ux * 10, y2 - uy * 10)), fill=fill, width=width)
    arrow_head(draw, end, (ux, uy), 15, fill)


def box(draw, xy, lines, fill=PALE, size=26) -> None:
    draw.rounded_rectangle(xy, radius=14, fill=fill, outline=NAVY, width=3)
    left, top, right, bottom = xy
    height = len(lines) * (size + 10)
    y = top + (bottom - top - height) // 2 + 3
    for i, line in enumerate(lines):
        center_text(draw, (left + right) // 2, y, line, font(size, i == 0))
        y += size + 10

# --------------------------------------------------------------- casos de uso

def actor(draw, cx: int, top: int, name: str) -> None:
    draw.ellipse((cx - 22, top, cx + 22, top + 44), outline=NAVY, width=4)
    draw.line((cx, top + 44, cx, top + 120), fill=NAVY, width=4)
    draw.line((cx - 40, top + 70, cx + 40, top + 70), fill=NAVY, width=4)
    draw.line((cx, top + 120, cx - 32, top + 175), fill=NAVY, width=4)
    draw.line((cx, top + 120, cx + 32, top + 175), fill=NAVY, width=4)
    lines = name.split("\n")
    for i, line in enumerate(lines):
        center_text(draw, cx, top + 185 + i * 30, line, font(24, True))


def usecase(draw, cx: int, cy: int, text: str, w=470, h=70) -> tuple[int, int, int, int]:
    xy = (cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)
    draw.ellipse(xy, fill=PALE, outline=NAVY, width=3)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        center_text(draw, cx, cy - len(lines) * 15 + 2 + i * 28, line, font(23, True))
    return xy


# ------------------------------------------------------------------ secuencia

def sequence_figure(path: Path, lifelines: list[str], messages: list[tuple], frames=()) -> None:
    """Mensajes: (origen, destino, texto, tipo) con tipo 'call' o 'ret'; origen == destino es un autollamado.
    Marcos: (inicio, fin, etiqueta) con índices de mensaje (base 0)."""
    step, first = 84, 180
    height = first + len(messages) * step + 40
    canvas = Image.new("RGB", (WIDTH, height), "white")
    draw = ImageDraw.Draw(canvas)
    span = WIDTH // len(lifelines)
    xs = [span // 2 + i * span for i in range(len(lifelines))]
    f = font(22)
    for x, name in zip(xs, lifelines):
        lines = name.split("\n")
        box(draw, (x - span // 2 + 20, 20, x + span // 2 - 20, 100), lines, size=22)
        for y in range(104, height - 15, 22):
            draw.line((x, y, x, min(y + 11, height - 15)), fill=GRAY, width=2)
    for start, end, label in frames:
        y1, y2 = first + start * step - 38, first + end * step + step - 30
        draw.rectangle((24, y1, WIDTH - 24, y2), outline=(140, 150, 160), width=2)
        draw.rectangle((24, y1, 24 + text_width(draw, label, font(21)) + 20, y1 + 30), fill=PALE, outline=(140, 150, 160), width=2)
        draw.text((34, y1 + 2), label, font=font(21), fill=NAVY)
    for i, (a, b, text, *rest) in enumerate(messages):
        kind = rest[0] if rest else "call"
        y = first + i * step + 36
        label = f"{i + 1}. {text}"
        if a == b:
            x = xs[a]
            draw.line((x, y - 12, x + 52, y - 12, x + 52, y + 14, x + 4, y + 14), fill=NAVY, width=3)
            arrow_head(draw, (x + 2, y + 14), (-1, 0), 12)
            tw = text_width(draw, label, f)
            lx = x - 20 - tw if a == len(lifelines) - 1 else x + 64
            draw.rectangle((lx - 4, y - 18, lx + tw + 4, y + 10), fill="white")
            draw.text((lx, y - 16), label, font=f, fill=NAVY)
            continue
        sign = 1 if xs[b] > xs[a] else -1
        line_arrow(draw, (xs[a], y), (xs[b], y), dashed=(kind == "ret"), width=3)
        tw = text_width(draw, label, f)
        left = min(xs[a], xs[b]) + (abs(xs[b] - xs[a]) - tw) // 2
        draw.rectangle((left - 4, y - 33, left + tw + 4, y - 5), fill="white")
        draw.text((left, y - 33), label, font=f, fill=NAVY)
    canvas.save(path)

# --------------------------------------------------------------------- estados

DOT_HEAD = ('digraph G {{ rankdir={rank}; bgcolor="white"; nodesep=0.7; ranksep=0.9; pad=0.2;\n'
            ' node [fontname="DejaVu Sans", fontsize=19, shape=box, style="rounded,filled", fillcolor="#E8EFF6", color="#19344E", fontcolor="#19344E", penwidth=1.6];\n'
            ' edge [fontname="DejaVu Sans", fontsize=17, color="#19344E", fontcolor="#19344E", penwidth=1.5];\n')


def state_diagram(path: Path, body: str, rank="LR") -> None:
    source = DOT_HEAD.format(rank=rank) + body + "\n}\n"
    subprocess.run(["dot", "-Tpng", "-Gdpi=170", "-o", str(path)], input=source.encode(), check=True)


INITIAL = ' {name} [label="", shape=circle, width=0.25, style=filled, fillcolor="#19344E"];\n'
FINAL = ' {name} [label="", shape=doublecircle, width=0.3, style=filled, fillcolor="#19344E"];\n'



# ---------------------------------------------------------------- utilidades docx

def shade(cell, color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), color)
    tc_pr.append(shd)


def borders(cell) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    edges = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        item = OxmlElement("w:" + edge)
        item.set(qn("w:val"), "single")
        item.set(qn("w:sz"), "4")
        item.set(qn("w:color"), "BFC8D0")
        edges.append(item)
    tc_pr.append(edges)


def margins(cell) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    cell_mar = OxmlElement("w:tcMar")
    for edge, value in (("top", "70"), ("left", "100"), ("bottom", "70"), ("right", "100")):
        node = OxmlElement("w:" + edge)
        node.set(qn("w:w"), value)
        node.set(qn("w:type"), "dxa")
        cell_mar.append(node)
    tc_pr.append(cell_mar)


def add_table(doc, headers, rows, widths, center_first=False, mono_cols=()) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for col_index, width in enumerate(widths):
        table.columns[col_index].width = Cm(width)
    for row_index, values in enumerate([headers] + rows):
        row = table.rows[0] if row_index == 0 else table.add_row()
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        for col_index, value in enumerate(values):
            cell = row.cells[col_index]
            cell.width = Cm(widths[col_index])
            cell.text = str(value)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            borders(cell)
            margins(cell)
            if row_index == 0:
                shade(cell, "1C3955")
            elif row_index % 2 == 0:
                shade(cell, "F3F7FA")
            for par in cell.paragraphs:
                par.paragraph_format.space_after = Pt(0)
                par.paragraph_format.line_spacing = 1.05
                if col_index == 0 and center_first:
                    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in par.runs:
                    run.font.name = "DejaVu Sans Mono" if col_index in mono_cols and row_index else "Liberation Sans"
                    run.font.size = Pt(8.2 if col_index in mono_cols and row_index else 8.8)
                    if row_index == 0:
                        run.font.bold = True
                        run.font.color.rgb = RGBColor(255, 255, 255)
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    tr_pr.append(repeat)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def paragraph(doc, text: str, style: str | None = None):
    return doc.add_paragraph(text, style=style)


def bullet(doc, text: str) -> None:
    doc.add_paragraph(text, style="List Bullet")


def heading(doc, text: str, level: int = 1) -> None:
    doc.add_heading(text, level=level)


def code_block(doc, text: str) -> None:
    for line in text.strip("\n").split("\n"):
        par = doc.add_paragraph()
        par.paragraph_format.space_after = Pt(0)
        par.paragraph_format.line_spacing = 1.0
        par.paragraph_format.left_indent = Cm(0.3)
        run = par.add_run(line if line else " ")
        run.font.name = "DejaVu Sans Mono"
        run.font.size = Pt(7.8)
        ppr = par._p.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:fill"), "F1F4F7")
        ppr.append(shd)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


_FIGURES = [0]


def figure(doc, path: Path, caption: str, width_cm: float = 16.4) -> None:
    _FIGURES[0] += 1
    caption = f"Figura {_FIGURES[0]}. " + re.sub(r"^Figura \d+\. ", "", caption)
    image = doc.add_paragraph()
    image.alignment = WD_ALIGN_PARAGRAPH.CENTER
    image.paragraph_format.keep_with_next = True
    image.add_run().add_picture(str(path), width=Cm(width_cm))
    label = doc.add_paragraph(caption)
    label.alignment = WD_ALIGN_PARAGRAPH.CENTER
    label.style = "Caption"


def setup(doc) -> None:
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(1.8)
    section.left_margin = section.right_margin = Cm(2.1)
    normal = doc.styles["Normal"]
    normal.font.name = "Liberation Sans"
    normal.font.size = Pt(9.6)
    normal.font.color.rgb = RGBColor(25, 25, 25)
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.12
    for name, size, above, below in (("Title", 20, 0, 10), ("Heading 1", 13.5, 14, 6), ("Heading 2", 11, 10, 4)):
        style = doc.styles[name]
        style.font.name = "Liberation Sans"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(25, 52, 78)
        style.paragraph_format.space_before = Pt(above)
        style.paragraph_format.space_after = Pt(below)
        style.paragraph_format.keep_with_next = True
        ppr = style.element.get_or_add_pPr()
        for border in ppr.findall(qn("w:pBdr")):
            ppr.remove(border)
    subtitle = doc.styles["Subtitle"]
    subtitle.font.name = "Liberation Sans"
    subtitle.font.size = Pt(9)
    subtitle.font.italic = False
    subtitle.font.color.rgb = RGBColor(90, 103, 115)
    doc.styles["Caption"].font.name = "Liberation Sans"
    doc.styles["Caption"].font.size = Pt(8.5)
    doc.styles["Caption"].font.color.rgb = RGBColor(70, 70, 70)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.style.font.name = "Liberation Sans"
    footer.style.font.size = Pt(8)
    footer.style.font.color.rgb = RGBColor(90, 90, 90)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)



# ------------------------------------------------------------ figuras del modelo

CITIES = {  # nombre corto, posición dentro del panel del grafo
    "B": ("Bogotá", 100, 170), "T": ("Tunja", 330, 55), "I": ("Ibagué", 330, 285),
    "V": ("Villavicencio", 560, 170), "L": ("Leticia", 590, 290),
}
ROUTES = [  # id, a, b, km, horas, combustible, peajes, activa, posición de la etiqueta (0..1)
    ("R001", "B", "T", "147,0", "2,75", "58.800", "12.900", True, 0.5),
    ("R002", "B", "I", "195,0", "3,60", "78.000", "25.200", True, 0.5),
    ("R003", "B", "V", "86,0", "2,20", "34.400", "20.000", True, 0.3),
    ("R004", "T", "V", "230,0", "5,50", "92.000", "0", True, 0.5),
    ("R005", "I", "V", "350,0", "7,00", "140.000", "0", True, 0.5),
    ("R006", "T", "I", "300,0", "6,00", "-", "-", False, 0.4),
]


def graph_panel(draw, ox, oy, mode) -> None:
    pos = {k: (ox + x, oy + y) for k, (_, x, y) in CITIES.items()}
    for rid, a, b, km, hh, fuel, toll, active, t in ROUTES:
        (x1, y1), (x2, y2) = pos[a], pos[b]
        if active:
            draw.line((x1, y1, x2, y2), fill=NAVY, width=4)
            value = {"d": f"{rid}  {km} km", "c": f"{rid}  {fuel}", "p": f"{rid}  {toll}"}[mode]
        else:
            pos_d = max(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, 1)
            ux, uy = (x2 - x1) / pos_d, (y2 - y1) / pos_d
            for s in range(0, int(pos_d) - 10, 24):
                draw.line((x1 + ux * s, y1 + uy * s, x1 + ux * (s + 12), y1 + uy * (s + 12)), fill=(160, 160, 160), width=3)
            value = f"{rid} inactiva"
        lx, ly = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        f = font(19)
        w = text_width(draw, value, f)
        if not active:
            lx += w // 2 + 10
        draw.rectangle((lx - w // 2 - 4, ly - 14, lx + w // 2 + 4, ly + 12), fill="white")
        draw.text((lx - w // 2, ly - 13), value, font=f, fill=(140, 140, 140) if not active else NAVY)
    for key, (name, _, _) in CITIES.items():
        x, y = pos[key]
        w = max(text_width(draw, name, font(21, True)) + 22, 70)
        fill = INACTIVE if key == "L" else PALE
        draw.rounded_rectangle((x - w // 2, y - 20, x + w // 2, y + 20), radius=10, fill=fill, outline=NAVY, width=3)
        center_text(draw, x, y - 13, name, font(21, True))


def adjacency_text(draw, x, y, mode) -> None:
    short = {"B": "Bogotá", "T": "Tunja", "I": "Ibagué", "V": "Villavic.", "L": "Leticia"}
    adj = {k: [] for k in short}
    for rid, a, b, km, hh, fuel, toll, active, _ in ROUTES:
        if not active:
            continue
        w = {"d": km, "c": fuel, "p": toll}[mode]
        adj[a].append(f"({short[b]}, {rid}, {w})")
        adj[b].append(f"({short[a]}, {rid}, {w})")
    f, fb = font(19), font(19, True)
    yy = y
    for k in short:
        items = adj[k] or ["(sin vecinos)"]
        draw.text((x, yy), short[k], font=fb, fill=NAVY)
        for j in range(0, len(items), 2):
            draw.text((x + 110, yy), ("→ " if j == 0 else "   ") + " ".join(items[j:j + 2]), font=f, fill=NAVY)
            yy += 32
        yy += 6


def graphs_figure(path: Path) -> None:
    rows = [("d", "G_distancia (km)"), ("c", "G_combustible (COP)"), ("p", "G_peajes (COP)")]
    row_h = 345
    canvas = Image.new("RGB", (WIDTH, 20 + row_h * 3), "white")
    draw = ImageDraw.Draw(canvas)
    for i, (mode, title) in enumerate(rows):
        top = 10 + i * row_h
        draw.text((20, top), title, font=font(26, True), fill=NAVY)
        graph_panel(draw, 20, top + 25, mode)
        draw.text((730, top + 40), "Lista de adyacencia (vecino, ruta, peso)", font=font(20, True), fill=GRAY)
        adjacency_text(draw, 730, top + 80, mode)
        if i < 2:
            draw.line((20, top + row_h - 8, WIDTH - 20, top + row_h - 8), fill=(200, 208, 216), width=2)
    canvas.save(path)


def entity_figure(path: Path) -> None:
    canvas = Image.new("RGB", (WIDTH, 560), "white")
    draw = ImageDraw.Draw(canvas)

    def cls(xy, title, fields):
        left, top, right, bottom = xy
        draw.rounded_rectangle(xy, radius=12, fill=PALE, outline=NAVY, width=3)
        center_text(draw, (left + right) // 2, top + 8, title, font(27, True))
        draw.line((left, top + 50, right, top + 50), fill=NAVY, width=3)
        for i, text in enumerate(fields):
            draw.text((left + 18, top + 62 + i * 34), text, font=font(22), fill=NAVY)

    cls((20, 30, 430, 330), "Ciudad (vértice)",
        ["id : cadena (DANE, 5 dígitos)", "nombre : texto", "departamento : texto", "lat, lon : decimal",
         "activo : booleano", "grado : derivado"])
    cls((500, 30, 900, 360), "Ruta (arista)",
        ["id : R###", "origen, destino : ciudades", "km_x10 : entero", "horas_x100 : entero",
         "peajes : lista de ids P###", "activo : booleano", "efectiva : derivado"])
    cls((970, 30, 1380, 330), "Peaje",
        ["id : P###", "nombre : texto", "lat, lon : decimal", "tarifa : pesos (cat. I)", "activo : booleano"])
    draw.line((430, 140, 500, 140), fill=NAVY, width=3)
    draw.text((436, 104), "0..n", font=font(20), fill=GRAY)
    draw.text((470, 148), "2", font=font(22, True), fill=NAVY)
    draw.line((900, 140, 970, 140), fill=NAVY, width=3)
    draw.text((904, 104), "0..n", font=font(20), fill=GRAY)
    draw.text((934, 148), "0..n", font=font(20), fill=GRAY)
    box(draw, (20, 395, 680, 540), ["Parámetros de combustible", "consumo_x10 (km por galón x 10)",
                                    "precio_gal (COP)  ·  velocidad_kmh"], WARN, size=22)
    box(draw, (730, 395, 1380, 540), ["Pesos derivados de la ruta", "combustible = redondeo(km / consumo x precio)",
                                      "peajes = suma de tarifas de sus peajes activos"], size=22)
    canvas.save(path)


def architecture_figure(path: Path) -> None:
    canvas = Image.new("RGB", (WIDTH, 610), "white")
    draw = ImageDraw.Draw(canvas)
    box(draw, (20, 60, 270, 190), ["Usuario"], size=27)
    box(draw, (350, 30, 760, 220), ["Ventana Python", "CustomTkinter", "tablas, consulta,", "dashboard, mapa"], size=24)
    box(draw, (880, 30, 1380, 220), ["Motor C++ (pera_cpp)", "modo --api", "grafos, Dijkstra,", "estadísticas"], size=24)
    line_arrow(draw, (275, 125), (345, 125))
    line_arrow(draw, (765, 85), (875, 85))
    line_arrow(draw, (875, 165), (765, 165))
    draw.text((775, 38), "JSON", font=font(22), fill=GRAY)
    draw.text((765, 172), "stdin/stdout", font=font(20), fill=GRAY)
    box(draw, (350, 330, 760, 520), ["Motor Python", "autónomo", "(mismo contrato)"], WARN, size=24)
    line_arrow(draw, (555, 225), (555, 325), dashed=True)
    draw.text((570, 262), "si C++ no arranca", font=font(21), fill=GRAY)
    box(draw, (880, 330, 1380, 520), ["data/pera_colombia.csv", "líneas K, C, P y R", "texto UTF-8, separador ;"], size=24)
    line_arrow(draw, (1130, 225), (1130, 325))
    line_arrow(draw, (765, 425), (875, 425), dashed=True)
    for i, t in enumerate(["Dos programas que", "funcionan solos: C++", "con consola y menú;", "Python con su motor."]):
        draw.text((20, 330 + i * 32), t, font=font(23, True), fill=NAVY)
    canvas.save(path)


def dashboard_figure(path: Path) -> None:
    canvas = Image.new("RGB", (WIDTH, 640), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((20, 20, 1380, 620), radius=12, outline=NAVY, width=3)
    draw.rectangle((20, 20, 250, 620), fill=PALE, outline=NAVY, width=3)
    for i, name in enumerate(["Resumen", "Ciudades", "Peajes", "Rutas", "Consulta", "Mapa"]):
        draw.text((45, 50 + i * 52), name, font=font(24, i == 0), fill=NAVY)
    for i, name in enumerate(["Ciudades", "Peajes", "Rutas efectivas", "Componentes"]):
        x = 280 + i * 275
        draw.rounded_rectangle((x, 40, x + 255, 120), radius=10, fill="white", outline=NAVY, width=2)
        center_text(draw, x + 127, 52, name, font(20), GRAY)
        center_text(draw, x + 127, 80, "n", font(26, True))

    def bars(x, y, w, h, title, heights, color=(70, 110, 150)):
        draw.rectangle((x, y, x + w, y + h), outline=(160, 170, 180), width=2)
        draw.text((x + 10, y + 6), title, font=font(19, True), fill=NAVY)
        k = len(heights)
        bw = (w - 30) / k
        for j, v in enumerate(heights):
            bx = x + 15 + j * bw
            draw.rectangle((bx + 2, y + h - 12 - v * (h - 60), bx + bw - 2, y + h - 12), fill=color)

    hist = [0.2, 0.5, 0.8, 1.0, 0.7, 0.45, 0.3, 0.2, 0.1, 0.05]
    bars(280, 140, 520, 215, "Histograma de distancia", hist)
    bars(830, 140, 520, 215, "Histograma de tiempo", hist[::-1][:5] + hist[:5])
    bars(280, 375, 520, 215, "Histograma de combustible", [0.1, 0.4, 0.9, 1.0, 0.6, 0.3, 0.25, 0.1, 0.1, 0.05])
    bars(830, 375, 250, 215, "Peajes por depto.", [1.0, 0.8, 0.6, 0.5, 0.3, 0.2], (190, 120, 60))
    bars(1100, 375, 250, 215, "Rutas más caras", [1.0, 0.9, 0.8, 0.7, 0.6], (190, 120, 60))
    canvas.save(path)


# --------------------------------------------------------------- casos de uso

def use_case_general(path: Path) -> None:
    names = ["Cargar datos o\niniciar sin datos", "Guardar datos", "Gestionar ciudades", "Gestionar peajes",
             "Gestionar rutas", "Editar parámetros\nde combustible", "Consultar costos entre\ndos ciudades",
             "Ver resumen estadístico\n(consola C++)", "Ver dashboard (Python)", "Ver mapa Folium (bono)", "Deshacer"]
    step = 96
    height = 150 + len(names) * step
    canvas = Image.new("RGB", (WIDTH, height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((300, 20, 1090, height - 15), radius=10, outline=NAVY, width=3)
    draw.text((318, 30), "Sistema PERA (ventana Python + motor de grafos)", font=font(24, True), fill=GRAY)
    centers = {}
    for i, name in enumerate(names):
        cy = 120 + i * step
        centers[name] = (695, cy)
        usecase(draw, 695, cy, name, w=470, h=76)
    mid = height // 2
    actor(draw, 110, mid - 110, "Usuario\n(estudiante)")
    for name, (cx, cy) in centers.items():
        line_arrow(draw, (190, mid - 20), (cx - 240, cy), width=2)
    actor(draw, 1260, 70, "Archivo\npera_colombia.csv")
    actor(draw, 1260, 480, "Motor de grafos\n(C++ / Python)")
    for name in names[:2]:
        cx, cy = centers[name]
        line_arrow(draw, (1200, 130), (cx + 240, cy), width=2)
    for name in names[2:]:
        cx, cy = centers[name]
        line_arrow(draw, (1190, 540), (cx + 240, cy), width=2)
    canvas.save(path)


def use_case_detail(path: Path) -> None:
    canvas = Image.new("RGB", (WIDTH, 700), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((250, 15, WIDTH - 20, 685), radius=10, outline=NAVY, width=3)
    draw.text((268, 25), "Detalle de consulta, ruta y ciudad", font=font(24, True), fill=GRAY)
    usecase(draw, 520, 110, "Consultar costos\nentre dos ciudades", 380, 84)
    usecase(draw, 520, 380, "Crear o modificar ruta", 380, 70)
    usecase(draw, 520, 600, "Eliminar ciudad", 380, 70)
    usecase(draw, 1080, 110, "Ejecutar Dijkstra por\ncinco criterios", 440, 84)
    usecase(draw, 1080, 250, "Informar que no hay ruta registrada", 440, 70)
    usecase(draw, 1080, 380, "Validar ciudades, ruta\núnica y peajes", 440, 84)
    usecase(draw, 1080, 600, "Eliminar sus rutas y\nactualizar grafos", 440, 84)
    actor(draw, 100, 250, "Usuario")
    line_arrow(draw, (150, 310), (335, 125), width=2)
    line_arrow(draw, (150, 330), (335, 380), width=2)
    line_arrow(draw, (150, 350), (335, 590), width=2)
    line_arrow(draw, (710, 110), (855, 110), width=2, dashed=True)
    line_arrow(draw, (710, 380), (855, 380), width=2, dashed=True)
    line_arrow(draw, (710, 600), (855, 600), width=2, dashed=True)
    for y in (88, 358, 578):
        draw.text((730, y), "<<include>>", font=font(20), fill=NAVY)
    line_arrow(draw, (900, 215), (640, 145), width=2, dashed=True)
    draw.text((760, 160), "<<extend>>", font=font(20), fill=NAVY)
    draw.text((900, 290), "[origen y destino sin camino]", font=font(20), fill=GRAY)
    canvas.save(path)


# ------------------------------------------------------------------ secuencia

LIFE4 = ["Usuario", "Ventana\nPython", "Motor\nC++ / Python", "Grafos\n(listas de adyacencia)"]


def sequence_query(path: Path) -> None:
    sequence_figure(path, LIFE4, [
        (0, 1, "Elige origen y destino, Consultar"),
        (1, 2, "query {from, to}"),
        (2, 2, "validar: existen y están activas"),
        (2, 3, "dijkstra por criterio (x 4)"),
        (3, 3, "relajar aristas efectivas por (costo, id)"),
        (3, 2, "ciudades y rutas del camino", "ret"),
        (2, 2, "sumar km, horas, combustible, peajes"),
        (2, 1, "alcanzable, criterios", "ret"),
        (1, 0, "cinco tarjetas y camino", "ret"),
        (2, 1, "alcanzable:false (sin camino registrado)", "ret"),
        (1, 0, "mensaje informativo", "ret"),
    ], frames=[(0, 8, "alt [hay camino]"), (9, 10, "[sin camino]")])


def sequence_route(path: Path) -> None:
    sequence_figure(path, LIFE4, [
        (0, 1, "Formulario: ciudades, km, horas, peajes"),
        (1, 2, "create {kind:route, origen, destino, ...}"),
        (2, 2, "ciudades distintas y existentes"),
        (2, 2, "ruta A-B no repetida (ambos sentidos)"),
        (2, 2, "peajes de la lista existentes"),
        (2, 2, "guardar copia para deshacer"),
        (2, 3, "insertar arista en los tres grafos"),
        (3, 3, "pesos: km, combustible, suma de tarifas activas"),
        (2, 1, "ok:true, ruta {efectiva, combustible, peajes_costo}", "ret"),
        (1, 0, "tabla actualizada, dirty = verdadero", "ret"),
        (2, 1, "ok:false, error (ciudad, peaje o ruta)", "ret"),
        (1, 0, "mensaje; los grafos quedan intactos", "ret"),
    ], frames=[(2, 9, "alt [validación correcta]"), (10, 11, "[validación falla]")])


def sequence_persist(path: Path) -> None:
    sequence_figure(path, ["Usuario", "Ventana\nPython", "Motor\nC++ / Python", "Grafos", "Archivo\n.csv"], [
        (0, 1, "Archivo > Abrir"),
        (1, 2, "load {path}"),
        (2, 4, "leer líneas"),
        (4, 2, "K, C, P, R", "ret"),
        (2, 3, "validar y construir grafos temporales"),
        (2, 1, "ok:true, state (dirty:false)", "ret"),
        (2, 1, "ok:false, Archivo inválido: ...", "ret"),
        (0, 1, "Archivo > Guardar"),
        (1, 2, "save {path}"),
        (2, 4, "escribir K, C, P, R ordenados por id"),
        (2, 1, "ok:true, dirty:false", "ret"),
        (0, 1, "Editar > Deshacer (Ctrl+Z)"),
        (1, 2, "undo"),
        (2, 3, "restaurar la copia anterior"),
        (2, 1, "ok:true, dirty:true (o error)", "ret"),
    ], frames=[(0, 6, "carga atómica: si algo falla, el estado queda intacto"), (7, 10, "guardado"), (11, 14, "deshacer")])


# --------------------------------------------------------------------- estados

def states_entity(path: Path) -> None:
    state_diagram(path, INITIAL.format(name="i") + FINAL.format(name="f") + '''
 Activo; Inactivo [fillcolor="#E1E1E1"];
 i -> Activo [label="crear"];
 Activo -> Inactivo [label="desactivar"];
 Inactivo -> Activo [label="reactivar"];
 Activo -> Activo [label="modificar"];
 Inactivo -> Inactivo [label="modificar"];
 Activo -> f [label="eliminar"];
 Inactivo -> f [label="eliminar"];
''', rank="TB")


def states_route(path: Path) -> None:
    state_diagram(path, INITIAL.format(name="i") + FINAL.format(name="f") + '''
 Efectiva [label="Efectiva\\nruta activa y\\nambas ciudades activas"];
 RInactiva [label="No efectiva\\nruta inactiva", fillcolor="#E1E1E1"];
 CInactiva [label="No efectiva\\nuna ciudad inactiva", fillcolor="#FCE4D6"];
 i -> Efectiva [label="crear ruta con\\nciudades activas"];
 Efectiva -> RInactiva [label="desactivar ruta"];
 RInactiva -> Efectiva [label="reactivar ruta\\n[ciudades activas]"];
 Efectiva -> CInactiva [label="desactivar origen o destino"];
 CInactiva -> Efectiva [label="reactivar ciudad\\n[ruta activa y otra ciudad activa]"];
 RInactiva -> CInactiva [label="desactivar ciudad"];
 Efectiva -> f [label="eliminar ruta,\\nciudad o peaje que la usa\\n(ciudad: se elimina la ruta)"];
 RInactiva -> f [label="eliminar"];
 CInactiva -> f [label="eliminar"];
''', rank="TB")


def states_app(path: Path) -> None:
    state_diagram(path, INITIAL.format(name="i") + FINAL.format(name="f") + '''
 Inicio [label="Inicio\\n(diálogo: cargar o vacío)"];
 Sin [label="Sin datos\\n0 ciudades, dirty = falso"];
 Cargado [label="Cargado\\ndirty = falso"];
 Modificado [label="Modificado\\ndirty = verdadero", fillcolor="#FCE4D6"];
 Guardado [label="Guardado\\ndirty = falso"];
 i -> Inicio;
 Inicio -> Sin [label="empezar sin datos"];
 Inicio -> Cargado [label="cargar archivo válido"];
 Inicio -> Inicio [label="archivo inválido:\\nerror, estado intacto"];
 Sin -> Modificado [label="crear"];
 Cargado -> Modificado [label="crear / eliminar / desactivar /\\nmodificar / parámetros / deshacer"];
 Guardado -> Modificado [label="operación que cambia datos"];
 Modificado -> Guardado [label="guardar"];
 Cargado -> Sin [label="nuevo"];
 Modificado -> Sin [label="nuevo"];
 Guardado -> Sin [label="nuevo"];
 Modificado -> f [label="salir"];
 Guardado -> f [label="salir"];
 Cargado -> f [label="salir"];
 Sin -> f [label="salir"];
''', rank="TB")


# ------------------------------------------------------------------- contenido

def build() -> None:
    doc = Document()
    doc.core_properties.title = "Especificación técnica del Programa Estadístico de Rutas de Automóviles (PERA)"
    doc.core_properties.subject = "Parcial 3, Estructura de Datos: grafos ponderados"
    doc.core_properties.author = ""
    doc.core_properties.last_modified_by = ""
    setup(doc)
    folder = tempfile.TemporaryDirectory(prefix="pera-doc-")
    tmp = Path(os.environ.get("PERA_SPEC_FIGS") or folder.name)  # PERA_SPEC_FIGS conserva los PNG para revisarlos
    tmp.mkdir(parents=True, exist_ok=True)
    img = {k: tmp / f"{k}.png" for k in (
        "arq", "ent", "grafos", "dash", "cu1", "cu2", "sec1", "sec2", "sec3", "est1", "est2", "est3")}
    architecture_figure(img["arq"])
    entity_figure(img["ent"])
    graphs_figure(img["grafos"])
    dashboard_figure(img["dash"])
    use_case_general(img["cu1"])
    use_case_detail(img["cu2"])
    sequence_query(img["sec1"])
    sequence_route(img["sec2"])
    sequence_persist(img["sec3"])
    states_entity(img["est1"])
    states_route(img["est2"])
    states_app(img["est3"])

    doc.add_paragraph("UNIVERSIDAD POPULAR DEL CESAR  ·  INGENIERÍA DE SISTEMAS  ·  ESTRUCTURA DE DATOS", style="Subtitle")
    doc.add_paragraph("Especificación técnica del Programa Estadístico de Rutas de Automóviles (PERA)", style="Title")
    add_table(doc, ["Campo", "Detalle"], [
        ["Asignatura", "Estructura de Datos, Parcial 3 (grafos ponderados)"],
        ["Universidad y programa", "Universidad Popular del Cesar, Ingeniería de Sistemas"],
        ["Periodo", "2026-2"],
        ["Estudiante", "Rafael (iniciales REMR). Trabajo individual."],
        ["Programas", "Parcial3_REMR.cpp (motor C++) y Parcial3_REMR.py (ventana Python)"],
        ["Fecha límite de entrega", "Martes 1 de diciembre de 2026, 11:59 a. m."],
    ], [4.3, 12.4])

    # 1 ---------------------------------------------------------------
    heading(doc, "1 Introducción y objetivo")
    paragraph(doc, "El Ministerio de Transporte de Colombia necesita un Programa Estadístico de Rutas de Automóviles (PERA) "
                   "para el funcionamiento de los viajes en el país. El programa modela las rutas terrestres entre las "
                   "capitales de los departamentos como grafos ponderados, con datos reales, y permite calcular entre dos "
                   "ciudades cualesquiera los costos en tiempo, distancia, combustible y peajes.")
    paragraph(doc, "Objetivo general: construir dos programas, uno en C++ y otro en Python, que gestionen la información de los "
                   "viajes terrestres (ciudades, rutas y peajes), calculen la mejor ruta entre dos ciudades según cinco "
                   "criterios y presenten estadísticas descriptivas: un resumen de datos en C++ y un dashboard con "
                   "histogramas y diagramas de barras en Python (con mapa Folium como bono).")
    paragraph(doc, "Objetivos específicos:")
    for text in ("Diseñar una estructura de datos basada en grafos: tres grafos ponderados sobre las mismas ciudades "
                 "(distancia, combustible y peajes), como recomienda el enunciado.",
                 "Permitir ingresar, eliminar, desactivar, modificar y editar cualquier dato de ciudades, rutas, peajes y "
                 "parámetros de combustible.",
                 "Calcular, con Dijkstra, el camino óptimo entre dos ciudades por distancia, tiempo, combustible y peajes, "
                 "y entregar los cuatro totales de cada camino.",
                 "Lograr resultados idénticos en el motor C++ y en el motor Python (aritmética entera exacta, desempate determinista).",
                 "Permitir que el usuario elija, al iniciar, cargar los datos del archivo o trabajar sin datos.",
                 "Documentar el diseño, la estrategia y los diagramas UML de casos de uso, secuencia y estados."):
        bullet(doc, text)
    heading(doc, "Alcance", 2)
    paragraph(doc, "El sistema es local y no necesita servidor; el mapa Folium se abre en el navegador cuando el usuario lo pide y sus mosaicos requieren internet. El archivo incluido contiene 1.070 nodos (todas las cabeceras municipales de Colombia con carretera en OSRM, capitales incluidas), 2.453 tramos de carretera y 148 peajes, documentados en data/README.md. Cada nodo se une a sus vecinos más cercanos por la carretera real; un tramo solo se descarta si otra cadena de tramos es como máximo 3 % más larga, de modo que la red es conexa por construcción. Treinta cabeceras sin carretera en OSRM (costa pacífica, Amazonía y archipiélago) quedan fuera del grafo y siguen disponibles en el catálogo de localidades. San Andrés, Leticia, Inírida y Mitú se excluyeron del grafo porque no tienen carretera continua hacia el resto del país ni peajes; la evidencia está en data/access_research.json y siguen disponibles en el catálogo de localidades. Las 34 cabeceras que no son nodos del grafo son: San Andrés, Leticia, Inírida y Mitú; en el Chocó y la costa de Cauca y Nariño, Acandí, Bahía Solano, Bajo Baudó, Bojayá, Carmen del Darién, El Charco, El Litoral del San Juan, Francisco Pizarro, Guapi, Juradó, La Tola, López de Micay, Medio Atrato, Mosquera (Nariño), Murindó, Nuquí, Olaya Herrera, Río Iró, Santa Bárbara (Nariño), Sipí, Timbiquí, Unguía y Vigía del Fuerte; en la Amazonía y el oriente, Barrancominas, Carurú, Miraflores (Guaviare), Puerto Leguízamo, Puerto Nariño y Taraira; y Providencia. Solo se llega a ellas por río, mar o aire. "
                   "La ausencia de una ruta en los datos no demuestra la imposibilidad física de viajar. "
                   "Quedan fuera el tráfico en tiempo real, las categorías de "
                   "vehículo distintas de automóvil y el transporte aéreo o fluvial. Las rutas y sus totales son estimaciones "
                   "del modelo vial registrado; no incluyen tarifas de ferry ni de puerto, que no se han cuantificado. "
                   "Existen posibilidades de transporte de vehículos como carga hacia algunas capitales, pero no se ha demostrado "
                   "un ferry de pasajeros con automóvil ni se han inventado aristas fluviales o marítimas para cubrirlas.")
    paragraph(doc, "La ventana permite además consultar localidades colombianas del catálogo DIVIPOLA mediante OSRM bajo demanda. "
                   "Las opciones obtenidas son candidatas del proveedor, no óptimos globales; se conserva el grafo académico "
                   "del archivo como modo separado (pestaña «Red de carreteras (grafos PERA)»). El mapa de la ventana dibuja los límites "
                   "departamentales (Natural Earth, dominio público), el trazado vial de cada ruta (OSRM simplificado) y un panel con "
                   "tiempo, distancia, combustible, peajes y tarifa de cada peaje. Cada criterio distinto de la menor distancia se "
                   "compara con ella (km, horas y costos de más o de menos) para que un ahorro en peajes no oculte un rodeo enorme. La consola C++ consulta únicamente el grafo del archivo. "
                   "Los campos de origen y destino identifican localidad, municipio y departamento, sin sustituirlos por capitales.")
    heading(doc, "Interpretación del enunciado", 2)
    paragraph(doc, "Los puntos 5 y 7 reutilizan términos del parcial anterior. Sus operaciones se aplican aquí a "
                   "ciudades, rutas, peajes y parámetros; las estadísticas describen esos datos, sin crear entidades ajenas.")

    # 2 ---------------------------------------------------------------
    heading(doc, "2 Requerimientos")
    heading(doc, "2.1 Requerimientos funcionales", 2)
    add_table(doc, ["Id", "Requerimiento", "Prioridad"], [
        ["RF-01", "Gestionar ciudades (capitales): crear, listar, modificar, desactivar o reactivar y eliminar. Eliminar una ciudad elimina sus rutas.", "Alta"],
        ["RF-02", "Gestionar peajes: crear, listar, modificar, desactivar o reactivar y eliminar. Eliminar un peaje lo quita de las rutas que lo usan.", "Alta"],
        ["RF-03", "Gestionar rutas entre dos ciudades distintas: km, horas y lista de peajes; crear, modificar, desactivar o reactivar y eliminar. No se admite una segunda ruta entre el mismo par, en ningún sentido.", "Alta"],
        ["RF-04", "Mantener tres grafos sincronizados (distancia, combustible, peajes); el tiempo viaja en la misma arista.", "Alta"],
        ["RF-05", "Editar los parámetros de combustible (consumo, precio) y la velocidad por defecto; los pesos se recalculan.", "Alta"],
        ["RF-06", "Consultar entre dos ciudades el camino óptimo por distancia, tiempo, combustible, peajes y costo total (combustible más peajes) y, de cada uno, los cuatro totales (km, horas, combustible y peajes), con la opción de pasar por una ciudad intermedia. Informar que no hay camino registrado si no existe en el grafo.", "Alta"],
        ["RF-07", "Resumen estadístico en texto en el programa C++ (conteos, mínimo, máximo, media, mediana, histogramas ASCII, peajes por departamento, grados, rutas más largas y caras, componentes conexas).", "Alta"],
        ["RF-08", "Dashboard en Python con tarjetas, histogramas (distancia, tiempo, combustible, peajes) y diagramas de barras (peajes por departamento, grado por ciudad, rutas más caras).", "Alta"],
        ["RF-09", "Mapa Folium con la ruta consultada resaltada (bono). Se abre solo cuando el usuario lo pide.", "Media"],
        ["RF-10", "Guardar y cargar los datos en un archivo de texto; al iniciar, el usuario elige cargar el archivo o empezar sin datos.", "Alta"],
        ["RF-11", "Deshacer las últimas operaciones que cambian datos (Ctrl+Z).", "Media"],
        ["RF-12", "Ofrecer una consola autónoma en C++ con menú y una ventana gráfica en Python, cada una operativa por sí sola.", "Alta"],
    ], [1.6, 12.9, 2.2], center_first=True)
    heading(doc, "2.2 Requerimientos no funcionales", 2)
    add_table(doc, ["Id", "Requerimiento", "Categoría"], [
        ["RNF-01", "Interfaz y mensajes en español.", "Usabilidad"],
        ["RNF-02", "Los motores C++ y Python devuelven los mismos caminos y los mismos totales para la misma consulta, y guardan archivos idénticos.", "Consistencia"],
        ["RNF-03", "Aritmética exacta en enteros (km x 10, horas x 100, pesos); sin comparar números decimales.", "Exactitud"],
        ["RNF-04", "Una consulta cuesta O((V + E) log V) por criterio, con V ciudades y E rutas.", "Rendimiento"],
        ["RNF-05", "Si el archivo es inválido o una operación falla, se informa el error y el estado queda intacto; ninguna operación lanza una excepción al usuario.", "Robustez"],
        ["RNF-06", "Comunicación entre procesos mediante JSON de una línea en UTF-8 por la entrada y salida estándar, sin puertos de red.", "Portabilidad"],
        ["RNF-07", "Compilación con CMake (C++17, sin avisos con -Wall -Wextra -Wpedantic); ventana en Python 3.10 o superior. Los motores usan solo la librería estándar.", "Portabilidad"],
        ["RNF-08", "El motor Python funciona sin el binario C++ (respaldo automático).", "Disponibilidad"],
        ["RNF-09", "Los datos son reales y su procedencia está documentada (data/README.md).", "Calidad de datos"],
    ], [1.6, 12.2, 2.9], center_first=True)
    heading(doc, "2.3 Variables de entrada y salida del modelo", 2)
    paragraph(doc, "Las variables del modelo se identifican a continuación. Las entradas las da el usuario por la ventana, la consola "
                   "o el archivo de datos; las salidas las produce el motor y las muestra la interfaz.")
    add_table(doc, ["Tipo", "Variable", "Dominio", "Descripción"], [
        ["Entrada", "ciudad: id, nombre, departamento, lat, lon", "id = código DANE de 5 dígitos; coordenadas decimales", "Vértice del grafo (capital departamental)."],
        ["Entrada", "peaje: id, nombre, lat, lon, tarifa", "id P###; tarifa en pesos enteros (COP, categoría I, automóvil)", "Punto de cobro que se asigna a rutas."],
        ["Entrada", "ruta: id, origen, destino, km, horas, peajes", "id R###; km con un decimal; horas con dos; lista de ids P### (puede ser vacía)", "Arista no dirigida entre dos capitales conectadas por carretera sin pasar por otra capital."],
        ["Entrada", "activo", "verdadero o falso", "Baja lógica de ciudad, ruta o peaje."],
        ["Entrada", "consumo_km_gal, precio_gal, velocidad_kmh", "decimal con un decimal; pesos enteros; km/h entero", "Parámetros de combustible y velocidad por defecto (informativa)."],
        ["Entrada", "origen y destino de la consulta", "dos ids de ciudades activas", "Par de ciudades a consultar."],
        ["Entrada", "ruta de archivo", "texto", "Archivo de persistencia (por defecto data/pera_colombia.csv)."],
        ["Salida", "peso de la ruta: combustible", "pesos enteros", "redondeo(km / consumo x precio) por ruta."],
        ["Salida", "peso de la ruta: peajes", "pesos enteros", "Suma de tarifas de los peajes activos de la ruta."],
        ["Salida", "camino por criterio", "lista de ciudades y lista de rutas", "Camino óptimo por distancia, tiempo, combustible y peajes."],
        ["Salida", "totales de un camino", "km, horas, combustible (COP), peajes (COP)", "Los cuatro costos de cada camino óptimo."],
        ["Salida", "alcanzable", "verdadero o falso", "Falso cuando no hay camino en el grafo registrado."],
        ["Salida", "estadísticas", "conteos, mín/máx/media/mediana, histogramas, rankings", "Resumen descriptivo sobre las rutas efectivas."],
        ["Salida", "estado", "dirty, ciudades, peajes, rutas", "Si hay cambios sin guardar y los tamaños de los datos."],
        ["Salida", "mensaje de error", "texto en español", "Ciudad ausente, ruta repetida, archivo inválido, etc."],
    ], [1.5, 4.0, 5.0, 6.2])

    # 3 ---------------------------------------------------------------
    heading(doc, "3 Diseño de la estructura de datos")
    heading(doc, "3.1 Entidades y relaciones", 2)
    paragraph(doc, "El modelo tiene tres entidades. La ciudad es el vértice; la ruta es una arista no dirigida entre dos ciudades; "
                   "el peaje es un punto de cobro que se asigna a una o más rutas. Una ruta tiene exactamente dos ciudades y "
                   "cero o más peajes; un peaje puede estar en varias rutas; una ciudad puede tener cero o más rutas (cero "
                   "la deja aislada).")
    figure(doc, img["ent"], "Figura 1. Entidades del modelo, sus campos y sus relaciones.")
    add_table(doc, ["Entidad", "Campos", "Notas"], [
        ["Ciudad", "id (DANE, 5 dígitos), nombre, departamento, lat, lon, activo", "El id es una cadena y se ordena como cadena. El grado se calcula sobre las rutas efectivas."],
        ["Peaje", "id (P###), nombre, lat, lon, tarifa, activo", "Tarifa vigente de categoría I (automóvil), en pesos enteros."],
        ["Ruta", "id (R###), origen, destino, km, horas, peajes, activo", "Es no dirigida: el par (A, B) y el par (B, A) son la misma ruta, y solo puede existir una."],
        ["Parámetros", "consumo_km_gal, precio_gal, velocidad_kmh", "Se guardan en el archivo (líneas K). Cambiarlos reescribe el peso de combustible de todas las rutas."],
    ], [2.4, 6.4, 7.9])
    heading(doc, "3.2 Cómo se asocian los peajes a las rutas", 2)
    paragraph(doc, "Cada ruta lleva la lista de ids de los peajes que están sobre ella, en el orden del recorrido. El peaje no "
                   "pertenece a una ruta concreta: es una entidad propia, de modo que modificar su tarifa o desactivarlo "
                   "actualiza todas las rutas que lo usan. Reglas:")
    for text in ("El peso de peajes de una ruta es la suma de las tarifas de sus peajes activos. Un peaje inactivo se conserva en la lista pero no suma.",
                 "Eliminar un peaje lo quita de la lista de todas las rutas; desactivarlo no borra nada.",
                 "Al crear o modificar una ruta, cada peaje de la lista debe existir (error \"El peaje X no existe\")."):
        bullet(doc, text)
    heading(doc, "3.3 Ruta efectiva", 2)
    paragraph(doc, "Una ruta es efectiva cuando está activa y sus dos ciudades están activas. Solo las rutas efectivas aparecen en "
                   "los tres grafos, en la consulta y en las estadísticas. Desactivar una ciudad deja sin efecto sus rutas "
                   "sin borrarlas, y reactivarla las devuelve. Eliminar una ciudad sí elimina sus rutas; eliminar un peaje "
                   "lo quita de las rutas.")
    heading(doc, "3.4 Los tres grafos como listas de adyacencia", 2)
    paragraph(doc, "Los tres grafos tienen los mismos vértices (las ciudades) y las mismas aristas (las rutas efectivas); solo "
                   "cambia el peso: G_distancia guarda kilómetros, G_combustible guarda pesos de combustible y G_peajes guarda "
                   "pesos de peajes. El tiempo (horas) viaja en la misma arista y se optimiza igual, para completar, con el costo total (combustible más peajes, quinto grafo), los cinco "
                   "criterios de la consulta. En los grafos de peajes y de costo total el peso lleva un desempate por distancia, de modo que a igual costo gana el camino más corto. Cada grafo es una lista de adyacencia: para cada ciudad, la lista de vecinos con el "
                   "id de la ruta y el peso, ordenada por id de ruta. La figura 2 muestra los tres grafos del archivo de prueba "
                   "(tests/fixtures/mini.csv: cinco ciudades, seis rutas, cinco peajes), con R006 inactiva y Leticia aislada.")
    figure(doc, img["grafos"], "Figura 2. Los tres grafos del archivo de prueba y sus listas de adyacencia.")
    paragraph(doc, "El repositorio de datos mantiene los tres grafos sincronizados: cualquier cambio en una ruta, un peaje, una ciudad "
                   "o los parámetros reescribe los pesos afectados. La consulta nunca lee un grafo desactualizado.")
    heading(doc, "3.5 Aritmética exacta", 2)
    paragraph(doc, "Para que los dos motores empaten exactamente, los números se guardan como enteros: los kilómetros como "
                   "km_x10 (valor x 10), las horas como horas_x100 (valor x 100), el consumo como consumo_x10 y todo el dinero "
                   "en pesos enteros. Con consumo en km por galón y precio por galón, el combustible de una ruta es:")
    code_block(doc, "combustible = (2 * km_x10 * precio_gal + consumo_x10) / (2 * consumo_x10)   (división entera)")
    paragraph(doc, "Equivale a km / consumo x precio redondeado al peso, con las mitades hacia arriba. Ejemplo con R003 (86,0 km; "
                   "consumo 40,0 km/gal; precio 16.000 COP/gal): km_x10 = 860 y consumo_x10 = 400, luego combustible = "
                   "(2 x 860 x 16000 + 400) / 800 = 27.520.400 / 800 = 34.400 COP (valor exacto 860 x 16000 / 400 = 34.400). "
                   "Las sumas de un camino (km, horas, pesos) son sumas de enteros, sin errores de redondeo acumulados, y la "
                   "comparación de costos en Dijkstra es una comparación de enteros.")
    heading(doc, "3.6 Dijkstra con desempate determinista", 2)
    paragraph(doc, "Para cada criterio se ejecuta Dijkstra desde el origen sobre las aristas efectivas, con los pesos enteros del "
                   "criterio (km_x10, horas_x100, pesos de combustible o pesos de peajes). Para que ambos motores devuelvan "
                   "el mismo camino aun con empates de costo:")
    for text in ("La cola de prioridad se ordena por el par (costo, id de ciudad), con el id comparado como cadena.",
                 "Un vecino se relaja solo si el nuevo costo es estrictamente menor que el actual; un empate no cambia el predecesor.",
                 "Los vecinos de cada ciudad se recorren por id de ruta ascendente.",
                 "Origen igual a destino devuelve el camino de una sola ciudad con totales 0; una ciudad inexistente o inactiva "
                 "devuelve el error \"La ciudad X no existe\" o \"Ciudad inactiva: X\"."):
        bullet(doc, text)
    code_block(doc, '''
dijkstra(origen, criterio):
    costo[v] = infinito para todo v;  costo[origen] = 0;  cola = {(0, origen)}
    mientras cola no vacía:
        (c, u) = extraer el menor par (costo, id)
        si c > costo[u]: continuar                    # entrada vieja
        para cada ruta r de u en orden de id, con destino v:
            nuevo = c + peso(r, criterio)
            si nuevo < costo[v]:                      # estrictamente menor
                costo[v] = nuevo;  previo[v] = (u, r);  insertar (nuevo, v)''')
    paragraph(doc, "Complejidad: con una cola binaria cada criterio cuesta O((V + E) log V); la consulta ejecuta cinco, así que "
                   "sigue siendo O((V + E) log V). Para los 1.070 nodos y los 2.453 tramos incluidos el tiempo es despreciable. "
                   "El espacio es O(V + E) por grafo.")
    heading(doc, "3.7 Consulta A a B con los cinco criterios", 2)
    paragraph(doc, "La consulta ejecuta Dijkstra una vez por criterio. Para el camino óptimo de cada criterio se recorren sus "
                   "rutas y se calculan los cuatro totales (km, horas, combustible, peajes), de modo que el usuario ve, por "
                   "ejemplo, cuánto cuesta en peajes el camino más corto y cuánta distancia agrega el camino más barato en peajes.")
    paragraph(doc, "Ejemplo calculado a mano con tests/fixtures/mini.csv (consumo 40,0 km/gal, precio 16.000 COP/gal), de Bogotá a "
                   "Villavicencio. Las rutas efectivas son R001 a R005; R006 está inactiva y no participa. R002 incluye el "
                   "peaje P005, inactivo, que no suma. Pesos por ruta:")
    add_table(doc, ["Ruta", "Extremos", "km", "Horas", "Combustible (COP)", "Peajes (COP)"], [
        ["R001", "Bogotá - Tunja", "147,0", "2,75", "58.800", "12.900 (P001)"],
        ["R002", "Bogotá - Ibagué", "195,0", "3,60", "78.000", "25.200 (P002 + P003; P005 inactivo no suma)"],
        ["R003", "Bogotá - Villavicencio", "86,0", "2,20", "34.400", "20.000 (P004)"],
        ["R004", "Tunja - Villavicencio", "230,0", "5,50", "92.000", "0"],
        ["R005", "Ibagué - Villavicencio", "350,0", "7,00", "140.000", "0"],
        ["R006", "Tunja - Ibagué", "300,0", "6,00", "no participa (inactiva)", "-"],
    ], [1.4, 4.1, 1.5, 1.5, 3.4, 4.8], center_first=True)
    paragraph(doc, "Los caminos candidatos de Bogotá a Villavicencio son el directo por R003, el que pasa por Tunja (R001 + R004) "
                   "y el que pasa por Ibagué (R002 + R005):")
    add_table(doc, ["Camino", "km", "Horas", "Combustible (COP)", "Peajes (COP)"], [
        ["Directo: R003", "86,0", "2,20", "34.400", "20.000"],
        ["Por Tunja: R001 + R004", "147,0 + 230,0 = 377,0", "2,75 + 5,50 = 8,25", "58.800 + 92.000 = 150.800", "12.900 + 0 = 12.900"],
        ["Por Ibagué: R002 + R005", "195,0 + 350,0 = 545,0", "3,60 + 7,00 = 10,60", "78.000 + 140.000 = 218.000", "25.200 + 0 = 25.200"],
    ], [4.1, 3.4, 3.1, 3.5, 2.6])
    paragraph(doc, "Resultado de la consulta (el óptimo de cada criterio y sus cuatro totales):")
    add_table(doc, ["Criterio", "Camino óptimo", "km", "Horas", "Combustible (COP)", "Peajes (COP)"], [
        ["Distancia", "Bogotá - Villavicencio (R003)", "86,0", "2,20", "34.400", "20.000"],
        ["Tiempo", "Bogotá - Villavicencio (R003)", "86,0", "2,20", "34.400", "20.000"],
        ["Combustible", "Bogotá - Villavicencio (R003)", "86,0", "2,20", "34.400", "20.000"],
        ["Peajes", "Bogotá - Tunja - Villavicencio (R001, R004)", "377,0", "8,25", "150.800", "12.900"],
    ], [2.3, 5.2, 1.5, 1.5, 3.2, 3.0])
    paragraph(doc, "Distancia, tiempo y combustible coinciden en el camino directo; los peajes prefieren el camino por Tunja, que es "
                   "más largo pero evita el peaje de 20.000 COP. Traza de Dijkstra para el criterio de peajes desde Bogotá "
                   "(costo en pesos, previo entre paréntesis):")
    add_table(doc, ["Paso", "Se extrae", "Bogotá", "Tunja", "Ibagué", "Villavicencio"], [
        ["inicio", "-", "0", "inf", "inf", "inf"],
        ["1", "Bogotá (0)", "0", "12.900 (R001)", "25.200 (R002)", "20.000 (R003)"],
        ["2", "Tunja (12.900)", "0", "12.900", "25.200", "12.900 (R004, estrictamente menor)"],
        ["3", "Villavicencio (12.900)", "0", "12.900", "12.900 (R005, estrictamente menor)", "12.900"],
        ["4", "Ibagué (12.900)", "0", "12.900", "12.900", "12.900"],
    ], [1.4, 3.8, 1.7, 2.6, 3.7, 3.5], center_first=True)
    paragraph(doc, "El camino se reconstruye desde el destino con los predecesores: Villavicencio, Tunja, Bogotá. Leticia no tiene "
                   "rutas en el fixture: la consulta devuelve alcanzable = falso porque no hay camino registrado en esos datos.")
    heading(doc, "3.8 Grafo desconectado", 2)
    paragraph(doc, "Un vértice puede quedar aislado si no tiene aristas en el archivo cargado, como Leticia en el fixture. Dijkstra "
                   "no alcanza un vértice aislado desde otra ciudad y deja su costo en infinito, de modo que la consulta responde alcanzable = falso, sin "
                   "criterios. Lo mismo ocurre cuando desactivar una ciudad, una ruta o eliminar una ruta parte el grafo en "
                   "componentes. Las estadísticas informan el número de componentes conexas entre ciudades activas (las "
                   "aisladas cuentan como una componente cada una), lo que permite ver rápido si el grafo está partido.")
    heading(doc, "3.9 Complejidad de las operaciones", 2)
    add_table(doc, ["Operación", "Tiempo", "Observación"], [
        ["crear / modificar / desactivar ciudad, peaje o ruta", "O(grado) a O(E)", "Buscar por id en un diccionario; reescribir los pesos de las rutas afectadas."],
        ["eliminar ciudad", "O(E)", "Elimina sus rutas y reescribe las listas de adyacencia."],
        ["cambiar parámetros de combustible", "O(E)", "Reescribe el combustible de todas las rutas."],
        ["consulta A a B", "O((V + E) log V)", "Cinco ejecuciones de Dijkstra."],
        ["estadísticas", "O(E log E + V)", "Una pasada por las rutas efectivas, ordenamientos para medianas y rankings."],
        ["guardar y cargar", "O(V + E)", "Cargar construye grafos temporales y reemplaza el estado solo si todo es válido."],
    ], [5.6, 3.2, 7.9])

    # 4 ---------------------------------------------------------------
    heading(doc, "4 Estrategia de solución")
    paragraph(doc, "La solución separa el cálculo de la presentación. Un motor tiene los datos, los grafos y los algoritmos, y "
                   "responde cada acción con una respuesta estructurada; la interfaz solo muestra lo que recibe. El mismo "
                   "contrato lo cumplen dos motores, uno en C++ y otro en Python.")
    for text in (
        "Estructura: tres grafos ponderados como listas de adyacencia sobre las mismas ciudades, derivados del repositorio de "
        "ciudades, peajes y rutas (sección 3).",
        "Algoritmo: Dijkstra con cola de prioridad, aritmética entera y desempate por (costo, id de ciudad) y por id de ruta; "
        "una ejecución por criterio.",
        "Motor C++ (Parcial3_REMR.cpp): contiene el repositorio, los grafos, Dijkstra, las estadísticas y la persistencia; "
        "tiene consola con menú y resumen estadístico, y modo --api para la ventana.",
        "Ventana Python (Parcial3_REMR.py, CustomTkinter): tablas con crear, editar, eliminar y desactivar; consulta con cinco "
        "tarjetas; dashboard con matplotlib; mapa Folium. Incluye un motor Python autónomo con el mismo contrato.",
        "Consistencia: una prueba de interoperabilidad ejecuta la misma secuencia de acciones en ambos motores y compara las "
        "respuestas y los archivos guardados.",
        "Persistencia: un archivo de texto con líneas K, C, P y R, guardado de forma determinista; cargar es atómico.",
        "Deshacer: antes de cada operación que cambia datos se guarda una copia del estado (hasta 200).",
    ):
        bullet(doc, text)
    heading(doc, "Decisiones y alternativas", 2)
    add_table(doc, ["Decisión", "Alternativa descartada", "Motivo"], [
        ["Listas de adyacencia", "Matriz de adyacencia", "El grafo es ralo (cada capital tiene pocas rutas, E es mucho menor que V al cuadrado); la lista cuesta O(V + E) de espacio y el recorrido de vecinos es O(grado)."],
        ["Tres grafos sobre las mismas ciudades", "Un solo grafo con varios pesos por arista", "Es lo que recomienda el enunciado; cada grafo se puede consultar o mostrar por separado. Costo: sincronizarlos, que hace el repositorio. El tiempo viaja en la arista porque comparte las mismas aristas."],
        ["Pesos enteros (km x 10, horas x 100, pesos)", "Números decimales (double)", "Los motores C++ y Python empatan exactamente y no hay errores de redondeo ni empates falsos."],
        ["Dijkstra", "Bellman-Ford o Floyd-Warshall", "Los pesos no son negativos; Dijkstra es más eficiente para un par de ciudades. Floyd-Warshall calcula todos los pares, que no se piden."],
        ["Desempate por (costo, id) y por id de ruta", "Orden dependiente de la estructura interna", "Un camino único e idéntico en ambos motores."],
        ["Peaje como entidad propia, referenciada desde las rutas", "Peajes embebidos en cada ruta", "Una tarifa se cambia en un solo lugar; el peaje se puede desactivar o eliminar para todas las rutas."],
        ["Desactivar sin borrar", "Eliminar", "Es reversible; la ruta efectiva deja de contar sin perder los datos."],
        ["Motor C++ + ventana Python con JSON por stdin/stdout", "Interfaz web con servidor", "No requiere servidor ni red; ambos programas pedidos por el enunciado son reales y completos."],
        ["Vértices aislados sin aristas", "Rechazar grafos desconectados", "El modelo admite datos incompletos o rutas desactivadas; informa que no hay camino registrado."],
    ], [4.2, 4.3, 8.2])

    # 5 ---------------------------------------------------------------
    heading(doc, "5 Arquitectura: motor C++ y ventana Python")
    paragraph(doc, "La ventana Python lanza el motor C++ como proceso hijo con el argumento --api y se comunica por la entrada "
                   "y salida estándar. Si el binario no existe, intenta compilarlo con CMake; si no lo consigue, usa el motor "
                   "Python y lo indica en la barra de estado. El lanzador Iniciar PERA.pyw abre la ventana sin consola en Windows.")
    figure(doc, img["arq"], "Figura 3. Procesos y flujo de datos.")
    add_table(doc, ["Opción", "Efecto"], [
        ["--api", "Motor C++ en modo protocolo: solo escribe respuestas JSON por stdout."],
        ["--data RUTA", "Archivo de persistencia a usar."],
        ["--python-backend", "Fuerza el motor Python autónomo."],
        ["--cpp-binary RUTA", "Usa un binario C++ concreto."],
        ["--self-test", "Autoprueba del motor C++."],
    ], [4.2, 12.5], mono_cols=(0,))
    heading(doc, "5.1 Protocolo JSON", 2)
    paragraph(doc, "Cada solicitud es un objeto JSON plano en una sola línea UTF-8; cada una recibe una línea de respuesta. "
                   "Al conectarse, la ventana envía ping y exige protocol = \"1\". Una respuesta correcta es "
                   "{\"ok\":true, \"result\":{...}, \"state\":{\"dirty\", \"ciudades\", \"peajes\", \"rutas\"}}; un error, "
                   "{\"ok\":false, \"error\":\"texto\", \"state\":{...}}. El campo kind toma los valores city, toll o route.")
    add_table(doc, ["Acción", "Parámetros", "Efecto"], [
        ["ping", "-", "Devuelve backend (cpp o python) y protocol."],
        ["state", "-", "Devuelve el estado (dirty y conteos)."],
        ["reset", "-", "Vacía los datos (nuevo)."],
        ["load / save", "path", "Carga o guarda el archivo de persistencia."],
        ["undo", "-", "Deshace la última operación que cambió datos (hasta 200)."],
        ["params / set_params", "consumo_km_gal, precio_gal, velocidad_kmh", "Lee o cambia los parámetros de combustible."],
        ["list", "kind", "Lista las entidades de ese tipo, ordenadas por id."],
        ["get", "kind, id", "Devuelve una entidad."],
        ["create", "kind, campos", "Crea ciudad, peaje o ruta; sin id asigna P### o R### (máximo + 1)."],
        ["update", "kind, id, campos", "Cambia solo los campos enviados."],
        ["delete", "kind, id", "Elimina; en una ciudad devuelve también rutas_eliminadas."],
        ["toggle", "kind, id", "Alterna activo / inactivo."],
        ["query", "from, to", "Devuelve alcanzable y, por criterio, ciudades, rutas y totales."],
        ["stats", "-", "Devuelve las estadísticas (conteos, histogramas, rankings)."],
        ["shutdown", "-", "Termina el proceso."],
    ], [3.6, 4.6, 8.5], mono_cols=(0, 1))
    paragraph(doc, "Ejemplo de intercambio (consulta Bogotá a Villavicencio con el archivo de prueba, abreviado):")
    code_block(doc, '''
-> {"action":"query","from":"11001","to":"50001"}
<- {"ok":true,"result":{"from":"11001","to":"50001","alcanzable":true,
     "criterios":{"distancia":{"ciudades":["11001","50001"],"rutas":["R003"],
                  "totales":{"km":86.0,"horas":2.2,"combustible":34400,"peajes":20000}},
                  "tiempo":{...}, "combustible":{...},
                  "peajes":{"ciudades":["11001","15001","50001"],"rutas":["R001","R004"],
                  "totales":{"km":377.0,"horas":8.25,"combustible":150800,"peajes":12900}}}},
    "state":{"dirty":false,"ciudades":5,"peajes":5,"rutas":6}}
-> {"action":"query","from":"11001","to":"91001"}
<- {"ok":true,"result":{"from":"11001","to":"91001","alcanzable":false},"state":{...}}
-> {"action":"delete","kind":"city","id":"99999"}
<- {"ok":false,"error":"La ciudad 99999 no existe","state":{...}}''')
    paragraph(doc, "Los textos de error son idénticos en ambos motores: \"La ciudad X ya existe\", \"La ciudad X no existe\", "
                   "\"El peaje X no existe\", \"La ruta X no existe\", \"La ruta entre X y Y ya existe\", \"Una ruta necesita dos "
                   "ciudades distintas\", \"No hay nada que deshacer\", \"Ciudad inactiva: X\", \"Archivo inválido: ...\", "
                   "\"Acción desconocida: X\" y \"Campo inválido: X\". En modo --api la salida estándar contiene solo el "
                   "protocolo; los diagnósticos van a la salida de errores.")
    heading(doc, "5.2 Motor Python autónomo", 2)
    paragraph(doc, "La clase del motor Python expone handle(solicitud) → respuesta con las mismas acciones y el mismo contrato. La "
                   "ventana la usa cuando el motor C++ no arranca o cuando se pide --python-backend, y también puede ejecutarse "
                   "sin interfaz para las pruebas. Como ambos motores cumplen el mismo contrato, la ventana no distingue "
                   "cuál tiene detrás.")

    # 6 ---------------------------------------------------------------
    heading(doc, "6 Persistencia")
    paragraph(doc, "El archivo de datos (data/pera_colombia.csv) es de texto UTF-8; el separador es ';', las líneas que empiezan por "
                   "'#' son comentarios y las vacías se ignoran. Cada línea empieza con una letra que indica el tipo de registro:")
    code_block(doc, '''
# PERA v1
K;consumo_km_gal;40.0
K;precio_gal;16000
K;velocidad_kmh;55
C;id;nombre;departamento;lat;lon;activo
P;id;nombre;lat;lon;tarifa;activo
R;id;origen;destino;km;horas;peajes(ids con |, puede ir vacío);activo''')
    paragraph(doc, "Ejemplo con registros del archivo de prueba (tests/fixtures/mini.csv):")
    code_block(doc, '''
C;11001;Bogotá D.C.;Bogotá D.C.;4.71100;-74.07210;1
P;P001;Peaje Tunja;5.12000;-73.80000;12900;1
R;R002;11001;73001;195.0;3.60;P002|P003|P005;1
R;R004;15001;50001;230.0;5.50;;1''')
    for text in (
        "Guardar: escribe el encabezado, las líneas K (en ese orden), las C por id, las P por id y las R por id (orden de cadena "
        "ascendente). Formatos fijos: lat y lon con 5 decimales, km con 1, horas con 2, consumo con 1, precios, velocidad y tarifas "
        "enteros, activo 1 o 0. Un ';' dentro de un nombre se sustituye por un espacio. Así, guardar dos veces produce el mismo archivo.",
        "Cargar: es atómico. Se valida cada línea y se construyen los grafos en un estado temporal; solo si todo es válido reemplaza "
        "al actual. Errores: línea mal formada, id repetido, ruta con ciudad o peaje inexistente, origen igual a destino, ruta "
        "repetida entre el mismo par y número fuera de rango. Un archivo sin ciudades ni rutas es válido (vacío).",
        "Inicio: un diálogo, o la pregunta de la consola, ofrece cargar el archivo o empezar sin datos (enunciado, punto 10).",
        "Estado: dirty pasa a verdadero con cualquier operación que cambie datos y a falso al guardar o cargar.",
    ):
        bullet(doc, text)

    # 7 estadísticas --------------------------------------------------
    heading(doc, "7 Estadísticas")
    paragraph(doc, "Las estadísticas siguen un esquema descriptivo, como pide el punto 7 del enunciado, y se calculan sobre las rutas "
                   "efectivas. El motor produce los mismos números para ambas presentaciones (acción stats).")
    add_table(doc, ["Contenido", "Detalle"], [
        ["Conteos", "Ciudades (activas), peajes (activos), rutas (activas, efectivas) y componentes conexas."],
        ["Por grafo", "Para distancia, tiempo, combustible y peajes: cantidad, mínimo, máximo, media, mediana y total; histograma de 10 intervalos iguales entre mínimo y máximo."],
        ["Peajes por departamento", "Peajes activos que están en rutas efectivas, asignados al departamento de las ciudades de la ruta; ordenados por cantidad descendente."],
        ["Grados", "Número de rutas efectivas de cada ciudad."],
        ["Rutas destacadas", "Las cinco rutas de mayor valor en cada criterio (más largas, lentas, caras en combustible y en peajes)."],
    ], [4.0, 12.7])
    paragraph(doc, "En C++ la información se presenta como resumen de datos (punto 7a): tablas de texto, valores mínimo, máximo, media y "
                   "mediana, e histogramas ASCII, desde la opción de resumen estadístico de la consola. En Python se muestra el "
                   "dashboard (punto 7b) en la sección Resumen de la ventana, con la distribución de la figura siguiente, y, como bono, "
                   "el mapa Folium.")
    shots = ROOT / "docs" / "screenshots"
    figure(doc, shots / "dashboard.png", "Pantalla Resumen de la ventana (captura real): tarjetas e histogramas; el selector Barras muestra los diagramas de barras.", 16.0)
    for text in ("Tarjetas: ciudades, peajes, rutas efectivas y componentes.",
                 "Histogramas: distancia, tiempo, combustible y peajes por ruta.",
                 "Diagramas de barras: peajes por departamento, grado por ciudad y rutas más caras.",
                 "Mapa Folium (bono): las rutas muestran distancia, tiempo y costos; los peajes muestran nombre y tarifa. "
                 "Las capas de los caminos consultados muestran los totales de cada criterio. Se abre en el navegador cuando se solicita.",
                 "La tabla de rutas permite ver la lista completa de peajes con nombres, códigos, tarifas y estado; los inactivos no suman al costo."):
        bullet(doc, text)

    paragraph(doc, "La consulta entre ciudades de la red de carreteras (pestaña «Red de carreteras (grafos PERA)») calcula cinco caminos "
                   "óptimos: menor distancia, menor tiempo, menor combustible, menor costo en peajes y menor costo total "
                   "(combustible más peajes). El campo opcional «Pasar por» obliga a la ruta a pasar por una ciudad intermedia, de modo que el "
                   "usuario elige la carretera; cada camino distinto de la menor distancia se compara con ella (km, horas y costos de más o de menos). "
                   "Los combustibles muestran los galones y el precio por galón usados. El consumo puede rellenarse con un tipo de vehículo de referencia.")
    figure(doc, shots / "consulta.png", "Consulta de Cali a Medellín en la red de carreteras: cinco criterios, con camino, tramos, galones y totales.", 16.0)
    figure(doc, shots / "mapa.png", "Mapa de la ventana (sin internet): límites departamentales, trazado vial, peajes con tarifa y panel con tiempo y costos; admite zoom, desplazamiento y selección con clic.", 16.0)
    figure(doc, shots / "rutas.png", "Tabla de rutas con distancia, tiempo, combustible, costo de peajes y resumen de los peajes de cada tramo.", 16.0)
    paragraph(doc, "La consulta entre localidades usa centroides del catálogo DIVIPOLA y muestra la geometría devuelta por OSRM. "
                   "Las distancias, tiempos y combustible son estimaciones de las alternativas recibidas, no mínimos de toda la red. "
                   "Se descuentan del combustible los tramos ferry identificados; sin desglose se advierte que se usa toda la distancia. "
                   "Los peajes cercanos se estiman por proximidad: el catálogo de INVIAS contiene 179 registros: tres inactivos por estar fuera de operación, una tarifa completada con la tabla ANI y cinco aún sin tarifa, "
                   "y no cubre necesariamente todos los peajes. Un importe sin evidencia es desconocido, no gratuito; "
                   "la cercanía no confirma el sentido, la vía ni el cobro. No incluye cargos de puertos o ferry. "
                   "El servicio requiere conexión y puede no devolver ruta; ello no prueba imposibilidad física. "
                   "En una comprobación del 17 de noviembre de 2026, OSRM devolvió dos opciones Valledupar–Sabanalarga "
                   "de 348,9 y 376,0 km, y dos Valledupar–Pamplona de 657,2 y 629,5 km; son ejemplos variables, no promesas de disponibilidad. "
                   "Las alternativas se ofrecen como opciones seleccionables y el campo «Pasar por» fuerza una localidad intermedia. Cada respuesta buena "
                   "se guarda; sin conexión se reutiliza la última respuesta idéntica y la pantalla advierte que no es una consulta actual.")
    figure(doc, shots / "localidad.png", "Consulta Valledupar a Sabanalarga entre localidades: opciones del proveedor, galones y peajes próximos.", 16.0)
    figure(doc, shots / "mapa_localidad.png", "Mapa de la ruta vial entre localidades sobre los límites departamentales, con tarifas de los peajes próximos.", 16.0)

    # 8 UML -----------------------------------------------------------
    heading(doc, "8 Diagramas UML")
    heading(doc, "8.1 Diagramas de casos de uso", 2)
    paragraph(doc, "El actor principal es el usuario (estudiante o docente). Los actores secundarios son el motor de grafos y el "
                   "archivo de datos, que participan en las operaciones y en la persistencia.")
    figure(doc, img["cu1"], "Figura 5. Diagrama de casos de uso general.", 15.0)
    figure(doc, img["cu2"], "Figura 6. Detalle: consulta, creación de ruta y eliminación de ciudad.")
    add_table(doc, ["Caso de uso", "Flujo principal", "Alternativas"], [
        ["Consultar costos entre dos ciudades", "El usuario elige origen y destino; el motor ejecuta Dijkstra por los cinco criterios y devuelve camino y totales; la ventana muestra cinco tarjetas.", "Sin camino: informa que no hay ruta registrada. Ciudad inactiva o inexistente: error."],
        ["Gestionar ciudades, peajes y rutas", "El usuario crea, edita, desactiva o elimina desde la tabla; el motor valida, actualiza los grafos y responde con la entidad.", "Validación falla: error y datos intactos."],
        ["Editar parámetros de combustible", "El usuario cambia consumo, precio o velocidad; el motor reescribe los pesos de combustible.", "Valor fuera de rango: error."],
        ["Ver resumen estadístico / dashboard / mapa", "El motor calcula las estadísticas; C++ las imprime en texto y Python las dibuja.", "Sin datos: conteos en cero."],
        ["Cargar / guardar", "El motor lee o escribe el archivo de persistencia.", "Archivo inválido: error y estado intacto."],
        ["Deshacer", "El motor restaura la copia anterior.", "\"No hay nada que deshacer\"."],
    ], [4.2, 8.0, 4.5])
    heading(doc, "8.2 Diagramas de secuencia", 2)
    paragraph(doc, "Se muestran tres secuencias: la consulta de A a B, la creación de una ruta con validación de peajes y el "
                   "ciclo de cargar, guardar y deshacer. En todas, la ventana pide la operación al motor por el protocolo JSON.")
    figure(doc, img["sec1"], "Figura 7. Secuencia de la consulta de A a B, con el caso sin camino.")
    figure(doc, img["sec2"], "Figura 8. Secuencia de creación de una ruta con validación de ciudades y peajes.")
    figure(doc, img["sec3"], "Figura 9. Secuencia de carga atómica, guardado y deshacer.")
    heading(doc, "8.3 Diagramas de estados", 2)
    paragraph(doc, "Se modelan tres máquinas de estados: el ciclo de vida de una ciudad, una ruta o un peaje (activo, inactivo, "
                   "eliminado), el estado de efectividad de una ruta y los estados de la aplicación (sin datos, cargado, modificado, "
                   "guardado).")
    figure(doc, img["est1"], "Figura 10. Ciclo de vida de una ciudad, ruta o peaje: activo, inactivo y eliminado.", 7.5)
    figure(doc, img["est2"], "Figura 11. Estado de efectividad de una ruta.", 14.0)
    figure(doc, img["est3"], "Figura 12. Estados de la aplicación respecto de los datos y el archivo.", 13.5)

    # 9 ---------------------------------------------------------------
    heading(doc, "9 Estructura del proyecto y entregables")
    add_table(doc, ["Elemento del enunciado", "Archivo o carpeta"], [
        ["Programa en C++ (nombre con iniciales)", "src/cpp/Parcial3_REMR.cpp"],
        ["Programa en Python (nombre con iniciales)", "src/python/Parcial3_REMR.py (más pera_engine.py, pera_backend.py y ui/)"],
        ["Lanzador", "Iniciar PERA.pyw"],
        ["Compilación", "CMakeLists.txt; ejecutable de Windows en bin/windows/ con su huella SHA-256"],
        ["Archivo de persistencia (punto 9)", "data/pera_colombia.csv (procedencia en data/README.md)"],
        ["Especificación técnica (este documento)", "docs/especificacion_tecnica.docx, generado por scripts/build_technical_spec.py"],
        ["Pruebas", "tests/ (autoprueba C++, API, motor Python, interoperabilidad, ventana)"],
        ["Video explicativo (punto 3)", "MP4 de unos 5 minutos, sin rostro, en el repositorio (docs/video_parcial3.mp4); el enlace de YouTube se indica en el correo de entrega."],
        ["Entrega (puntos 5 a 7)", "Correo al docente, asunto \"Estructura de datos Parcial 3 Grupo # 2026-2\", martes 1 de diciembre, 11:59 a. m."],
    ], [6.4, 10.3])

    # 10 --------------------------------------------------------------
    doc.add_page_break()
    heading(doc, "10 Evidencia de pruebas")
    paragraph(doc, "Resultados de ejecutar cada prueba sobre la versión entregada, con los datos reales y con el fixture de 5 ciudades.").paragraph_format.keep_with_next = True
    add_table(doc, ["Prueba", "Qué verifica", "Cómo se ejecuta", "Resultado"], [
        ["Autoprueba C++", "Aritmética entera, Dijkstra y desempates, validación y persistencia del motor C++.", "pera_cpp --self-test", "Aprobada"],
        ["API C++", "Respuestas del protocolo JSON del motor C++ (ping, create, query, stats, errores).", "tests/integration/check_api.py", "Aprobada"],
        ["Motor Python", "Los mismos casos que la autoprueba C++, en el motor Python.", "tests/python/test_engine.py", "Aprobada"],
        ["Consulta del fixture", "Bogotá a Villavicencio: 86,0 km, 2,20 h, 34.400 COP y 20.000 COP de peajes por distancia, tiempo y combustible; 377,0 km, 8,25 h, 150.800 COP y 12.900 COP por peajes. Leticia sin ruta.", "Pruebas de ambos motores sobre tests/fixtures/mini.csv", "Aprobada"],
        ["Interoperabilidad", "Misma secuencia en ambos motores: iguales respuestas y archivos guardados (fixture y archivo real).", "tests/integration/check_interop.py", "Aprobada"],
        ["Persistencia", "Cargar y guardar reproduce el archivo; un archivo inválido deja el estado intacto.", "Pruebas de ambos motores", "Aprobada"],
        ["Ventana", "Humo de la ventana (tablas, consulta, dashboard, mapa) en pantalla virtual.", "tests/python/test_window_smoke.py", "Pendiente en esta revisión"],
        ["Datos reales", "Validación del archivo de datos (ids, referencias, rangos, conectividad).", "scripts/validate_data.py", "Aprobada"],
    ], [2.8, 7.0, 4.4, 2.5])

    # 11 --------------------------------------------------------------
    heading(doc, "11 Créditos y fuentes de datos")
    for text in (
        "Autor: Rafael (REMR), trabajo individual. Universidad Popular del Cesar, Ingeniería de Sistemas, Estructura de Datos, Parcial 3, 2026-2.",
        "Datos: el catálogo de localidades, capitales, coordenadas, distancias, tiempos, peajes y tarifas, el precio del combustible y el consumo, con su "
        "procedencia, fecha, límites y lo que es estimado, se describen en data/README.md. Este documento no repite esas cifras: "
        "los ejemplos usan solo el archivo de prueba tests/fixtures/mini.csv.",
        "Algoritmo: E. W. Dijkstra (1959), \"A note on two problems in connexion with graphs\".",
        "Herramientas: C++17 y CMake para el motor; Python 3, CustomTkinter, matplotlib y Folium para la ventana; python-docx, "
        "Pillow y Graphviz para generar este documento.",
        "Esta especificación se genera con scripts/build_technical_spec.py; los diagramas UML se dibujan por código dentro del mismo script.",
    ):
        bullet(doc, text)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    folder.cleanup()
    print(f"Documento generado: {OUTPUT}")


if __name__ == "__main__":
    build()
