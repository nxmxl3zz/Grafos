"""Genera la especificación técnica de PAA (Taller 3, árboles AVL) en formato DOCX.

Uso (necesita python-docx, Pillow y graphviz `dot`):
    python scripts/build_technical_spec.py
Salida: docs/especificacion_tecnica.docx
"""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import tempfile

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
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


# ---------------------------------------------------------------- árboles AVL

def tree_height(node) -> int:
    return 0 if node is None else 1 + max(tree_height(node[1]), tree_height(node[2]))


def balance(node) -> int:
    return tree_height(node[1]) - tree_height(node[2])


def layout(node, depth=0, out=None, counter=None, side="R"):
    """Posición en orden (x) y profundidad (y) de cada nodo: (nodo, x, y, hijoIzq, hijoDer)."""
    if out is None:
        out, counter = [], [0]
    if node is None:
        return None, out
    left, _ = layout(node[1], depth + 1, out, counter, "L")
    item = {"node": node, "x": counter[0], "y": depth, "side": side}
    counter[0] += 1
    right, _ = layout(node[2], depth + 1, out, counter, "R")
    item["l"], item["r"] = left, right
    if left:
        left["side"] = "L"
    out.append(item)
    return item, out


def draw_tree(draw, tree, box_xy, highlight=(), inactive=(), unit=70, radius=26) -> None:
    """Dibuja un árbol (clave, izq, der) con el factor de balance junto a cada nodo."""
    root, items = layout(tree)
    if root is None:
        return
    left, top, right, bottom = box_xy
    max_x = max(i["x"] for i in items)
    max_y = max(i["y"] for i in items)
    step_x = min(unit, (right - left - 2 * radius) / max(max_x, 1))
    step_y = min(unit + 20, (bottom - top - 2 * radius) / max(max_y, 1))
    ox = left + (right - left - max_x * step_x) / 2
    pos = {id(i): (ox + i["x"] * step_x, top + radius + i["y"] * step_y) for i in items}
    for it in items:
        for child in (it["l"], it["r"]):
            if child:
                draw.line((pos[id(it)], pos[id(child)]), fill=NAVY, width=4)
    for it in items:
        x, y = pos[id(it)]
        key = it["node"][0]
        fill = WARN if key in highlight else INACTIVE if key in inactive else "white"
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill, outline=NAVY, width=3)
        center_text(draw, int(x), int(y) - 15, str(key), font(26, True))
        bf = balance(it["node"])
        label = f"fb {bf:+d}" if bf else "fb 0"
        lf = font(21)
        lx = x - radius - 6 - text_width(draw, label, lf) if it["side"] == "L" and it is not root else x + radius + 6
        draw.text((lx, y - 12), label, font=lf, fill=(150, 30, 30) if abs(bf) > 1 else GRAY)


def panel_row(path: Path, rows: list[dict], title_size=26) -> None:
    """Filas de paneles de árboles. Cada fila: {'title', 'panels': [(caption, tree, highlight)]}."""
    row_h = 330
    canvas = Image.new("RGB", (WIDTH, 20 + len(rows) * row_h), "white")
    draw = ImageDraw.Draw(canvas)
    for r, row in enumerate(rows):
        top = 10 + r * row_h
        draw.text((20, top), row["title"], font=font(title_size, True), fill=NAVY)
        panels = row["panels"]
        count = len(panels)
        slot = (WIDTH - 40) // count
        for p, (caption, tree, hl, *rest) in enumerate(panels):
            inactive = rest[0] if rest else ()
            left = 20 + p * slot
            draw_tree(draw, tree, (left + 30, top + 75, left + slot - 90, top + row_h - 70),
                      highlight=hl, inactive=inactive)
            center_text(draw, left + slot // 2 - 20, top + row_h - 45, caption, font(23), GRAY)
            if p < count - 1:
                line_arrow(draw, (left + slot - 65, top + 175), (left + slot - 5, top + 175))
        if r < len(rows) - 1:
            draw.line((20, top + row_h - 8, WIDTH - 20, top + row_h - 8), fill=(200, 208, 216), width=2)
    canvas.save(path)


def n(key, left=None, right=None):
    return (key, left, right)


def rotation_figures(path_a: Path, path_b: Path) -> None:
    rr = n(10, None, n(20, None, n(30)))
    ll = n(30, n(20, n(10)), None)
    rl = n(10, None, n(30, n(20)))
    lr = n(30, n(10, None, n(20)), None)
    ok = n(20, n(10), n(30))
    panel_row(path_a, [
        {"title": "Caso RR (derecha-derecha): se insertan 10, 20, 30; rotación simple a la izquierda en 10",
         "panels": [("antes: 10 queda con fb -2", rr, (10,)), ("después de rotar", ok, ())]},
        {"title": "Caso LL (izquierda-izquierda): se insertan 30, 20, 10; rotación simple a la derecha en 30",
         "panels": [("antes: 30 queda con fb +2", ll, (30,)), ("después de rotar", ok, ())]},
    ])
    panel_row(path_b, [
        {"title": "Caso RL (derecha-izquierda): se insertan 10, 30, 20; derecha en 30 y luego izquierda en 10",
         "panels": [("antes: 10 con fb -2, hijo 30 con fb +1", rl, (10,)),
                    ("tras rotar a la derecha en 30", n(10, None, n(20, None, n(30))), (10,)),
                    ("tras rotar a la izquierda en 10", ok, ())]},
        {"title": "Caso LR (izquierda-derecha): se insertan 30, 10, 20; izquierda en 10 y luego derecha en 30",
         "panels": [("antes: 30 con fb +2, hijo 10 con fb -1", lr, (30,)),
                    ("tras rotar a la izquierda en 10", n(30, n(20, n(10)), None), (30,)),
                    ("tras rotar a la derecha en 30", ok, ())]},
    ])


def delete_figure(path: Path) -> None:
    before = n(20, n(10, n(5)), n(30, n(25), n(40)))
    after = n(25, n(10, n(5)), n(30, None, n(40)))
    before2 = n(20, n(10), n(30, None, n(40)))
    after2 = n(30, n(20), n(40))
    panel_row(path, [
        {"title": "Eliminar 20 (dos hijos): se copia el sucesor in-orden (25) y se quita su nodo original",
         "panels": [("antes", before, (20,)), ("después: 25 ocupa la raíz, sin rotación", after, (25,))]},
        {"title": "Eliminar 10 (hoja): 20 queda con fb -2 y su hijo derecho con fb -1, rotación RR en 20",
         "panels": [("antes", before2, (10,)), ("después: 30 es la nueva raíz", after2, (30,))]},
    ])


def inactive_figure(path: Path) -> None:
    tree = n(20, n(10, n(5), n(15)), n(30, n(25), n(40)))
    canvas = Image.new("RGB", (WIDTH, 380), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((20, 10), "Árbol con el nodo 10 desactivado (gris): sigue en su lugar y sigue contando para la altura",
              font=font(26, True), fill=NAVY)
    draw_tree(draw, tree, (150, 85, 700, 330), inactive=(10,))
    box(draw, (850, 110, 1360, 300), ["Nodo desactivado", "activo = falso", "se conserva en el árbol", "la búsqueda lo informa"], size=23)
    canvas.save(path)


def node_figure(path: Path) -> None:
    canvas = Image.new("RGB", (WIDTH, 470), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((20, 20, 560, 440), radius=14, fill=PALE, outline=NAVY, width=3)
    center_text(draw, 290, 32, "Nodo", font(30, True))
    draw.line((20, 78, 560, 78), fill=NAVY, width=3)
    fields = ["clave : entero (int32)", "etiqueta : texto", "activo : booleano", "altura : entero",
              "izq : puntero / referencia a Nodo", "der : puntero / referencia a Nodo"]
    for i, text in enumerate(fields):
        draw.text((45, 95 + i * 56), text, font=font(26), fill=NAVY)
    # Nodo con hijos
    draw.ellipse((860, 40, 960, 140), fill="white", outline=NAVY, width=3)
    center_text(draw, 910, 70, "20", font(32, True))
    draw.text((975, 105), "altura 2, fb 0", font=font(22), fill=GRAY)
    draw.ellipse((700, 250, 800, 350), fill="white", outline=NAVY, width=3)
    center_text(draw, 750, 280, "10", font(32, True))
    draw.ellipse((1020, 250, 1120, 350), fill="white", outline=NAVY, width=3)
    center_text(draw, 1070, 280, "30", font(32, True))
    draw.line((885, 128, 770, 255), fill=NAVY, width=3)
    draw.line((935, 128, 1050, 255), fill=NAVY, width=3)
    draw.text((640, 188), "izq", font=font(23), fill=GRAY)
    draw.text((1010, 188), "der", font=font(23), fill=GRAY)
    draw.text((640, 360), "altura 1, fb 0", font=font(22), fill=GRAY)
    draw.text((960, 360), "altura 1, fb 0", font=font(22), fill=GRAY)
    draw.text((610, 410), "fb(n) = altura(izq) - altura(der); altura(nulo) = 0; hoja = 1", font=font(23), fill=NAVY)
    canvas.save(path)


# ------------------------------------------------------------------ arquitectura

def architecture_figure(path: Path) -> None:
    canvas = Image.new("RGB", (WIDTH, 610), "white")
    draw = ImageDraw.Draw(canvas)
    box(draw, (20, 60, 270, 190), ["Usuario"], size=27)
    box(draw, (350, 30, 760, 220), ["Ventana Python", "CustomTkinter", "canvas, animación,", "recorridos"], size=24)
    box(draw, (880, 30, 1380, 220), ["Motor C++ (paa_cpp)", "modo --api", "AVL, operaciones,", "persistencia"], size=24)
    line_arrow(draw, (275, 125), (345, 125))
    line_arrow(draw, (765, 85), (875, 85))
    line_arrow(draw, (875, 165), (765, 165))
    draw.text((775, 38), "JSON", font=font(22), fill=GRAY)
    draw.text((765, 172), "stdin/stdout", font=font(20), fill=GRAY)
    box(draw, (350, 330, 760, 520), ["Motor Python", "autónomo", "(mismo contrato)"], WARN, size=24)
    line_arrow(draw, (555, 225), (555, 325), dashed=True)
    draw.text((570, 262), "si C++ no arranca", font=font(21), fill=GRAY)
    box(draw, (880, 330, 1380, 520), ["data/arbol_avl.txt", "clave;etiqueta;activo", "una línea por nodo"], size=24)
    line_arrow(draw, (1130, 225), (1130, 325))
    line_arrow(draw, (765, 425), (875, 425), dashed=True)
    draw.text((20, 330), "Dos programas que funcionan", font=font(23, True), fill=NAVY)
    draw.text((20, 362), "solos: el motor C++ tiene su", font=font(23, True), fill=NAVY)
    draw.text((20, 394), "propia consola (GotoXY/ANSI);", font=font(23, True), fill=NAVY)
    draw.text((20, 426), "Python incluye su motor.", font=font(23, True), fill=NAVY)
    canvas.save(path)


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


def use_case_general(path: Path) -> None:
    names = ["Crear árbol vacío", "Insertar clave", "Eliminar clave",
             "Buscar clave", "Desactivar / reactivar clave", "Modificar etiqueta",
             "Ver recorridos pre/in/post-orden", "Controlar la animación", "Cargar datos o iniciar sin datos", "Guardar árbol"]
    step = 92
    height = 150 + len(names) * step
    canvas = Image.new("RGB", (WIDTH, height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((300, 20, 1090, height - 15), radius=10, outline=NAVY, width=3)
    draw.text((318, 30), "Sistema PAA (ventana Python + motor AVL)", font=font(24, True), fill=GRAY)
    centers = {}
    for i, name in enumerate(names):
        cy = 120 + i * step
        centers[name] = (695, cy)
        usecase(draw, 695, cy, name, w=500, h=64)
    mid = height // 2
    actor(draw, 110, mid - 110, "Usuario\n(estudiante)")
    for name, (cx, cy) in centers.items():
        line_arrow(draw, (190, mid - 20), (cx - 250, cy), width=2)
    # actores secundarios
    actor(draw, 1260, 150, "Motor AVL\n(C++ / Python)")
    actor(draw, 1260, height - 330, "Archivo\narbol_avl.txt")
    for name in ["Insertar clave", "Eliminar clave", "Buscar clave", "Desactivar / reactivar clave",
                 "Modificar etiqueta", "Ver recorridos pre/in/post-orden"]:
        cx, cy = centers[name]
        line_arrow(draw, (1180, 210), (cx + 250, cy), width=2)
    for name in ["Cargar datos o iniciar sin datos", "Guardar árbol"]:
        cx, cy = centers[name]
        line_arrow(draw, (1180, height - 270), (cx + 250, cy), width=2)
    canvas.save(path)


def use_case_detail(path: Path) -> None:
    canvas = Image.new("RGB", (WIDTH, 620), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((250, 15, WIDTH - 20, 605), radius=10, outline=NAVY, width=3)
    draw.text((268, 25), "Detalle de insertar y eliminar", font=font(24, True), fill=GRAY)
    usecase(draw, 560, 110, "Insertar clave", 360, 70)
    usecase(draw, 560, 310, "Devolver pasos y recorridos", 440, 70)
    usecase(draw, 560, 510, "Eliminar clave", 360, 70)
    usecase(draw, 1090, 310, "Rebalancear con rotaciones\nLL, RR, LR, RL", 440, 90)
    actor(draw, 100, 200, "Usuario")
    line_arrow(draw, (150, 260), (380, 115), width=2)
    line_arrow(draw, (150, 280), (380, 505), width=2)
    line_arrow(draw, (560, 148), (560, 272), width=2, dashed=True)
    line_arrow(draw, (560, 472), (560, 348), width=2, dashed=True)
    draw.text((575, 195), "<<include>>", font=font(21), fill=NAVY)
    draw.text((575, 405), "<<include>>", font=font(21), fill=NAVY)
    # extend: la rotación extiende insertar y eliminar
    line_arrow(draw, (880, 280), (740, 130), width=2, dashed=True)
    line_arrow(draw, (880, 340), (740, 490), width=2, dashed=True)
    draw.text((830, 175), "<<extend>>", font=font(21), fill=NAVY)
    draw.text((830, 420), "<<extend>>", font=font(21), fill=NAVY)
    center_text(draw, 1090, 365, "[si |fb| > 1]", font(21), GRAY)
    canvas.save(path)


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


def sequence_insert(path: Path) -> None:
    sequence_figure(path, ["Usuario", "Ventana\nPython", "Motor\nC++ / Python", "Árbol AVL"], [
        (0, 1, "Escribe clave y etiqueta, Insertar"),
        (1, 2, "insert {key, label}"),
        (2, 3, "insert(clave, etiqueta)"),
        (3, 3, "descender: compare / descend"),
        (3, 3, "place: nodo nuevo como hoja"),
        (3, 3, "height: altura y fb hacia arriba"),
        (3, 3, "fb = -2: rotate RR"),
        (3, 2, "pasos y árbol final", "ret"),
        (2, 1, "ok, steps, tree, traversals", "ret"),
        (1, 1, "por cada paso: dibujar tree"),
        (1, 0, "árbol balanceado y recorridos", "ret"),
    ], frames=[(9, 9, "loop [cada paso]")])


def sequence_delete(path: Path) -> None:
    sequence_figure(path, ["Usuario", "Ventana\nPython", "Motor\nC++ / Python", "Árbol AVL"], [
        (0, 1, "Indica la clave, Eliminar"),
        (1, 2, "delete {key}"),
        (2, 3, "erase(clave)"),
        (3, 3, "localizar: compare / descend"),
        (3, 3, "dos hijos: replace con sucesor"),
        (3, 3, "remove: quitar el nodo"),
        (3, 3, "height / balance hacia la raíz"),
        (3, 3, "rotate si |fb| = 2"),
        (3, 2, "pasos y árbol final", "ret"),
        (2, 1, "ok, steps, tree, traversals", "ret"),
        (1, 0, "animación y recorridos", "ret"),
        (3, 2, "notfound: clave inexistente", "ret"),
        (2, 1, "ok:false, error", "ret"),
        (1, 0, "mensaje; árbol intacto", "ret"),
    ], frames=[(0, 10, "alt [la clave existe]"), (11, 13, "[la clave no existe]")])


def sequence_persist(path: Path) -> None:
    sequence_figure(path, ["Usuario", "Ventana\nPython", "Motor\nC++ / Python", "Archivo\narbol_avl.txt"], [
        (0, 1, "Archivo > Abrir"),
        (1, 2, "load {path}"),
        (2, 3, "leer líneas"),
        (3, 2, "clave;etiqueta;activo", "ret"),
        (2, 2, "validar e insertar en árbol temporal"),
        (2, 1, "ok:true, tree, dirty:false", "ret"),
        (1, 0, "árbol cargado y dibujado", "ret"),
        (2, 1, "si hay línea inválida: ok:false", "ret"),
        (0, 1, "Archivo > Guardar"),
        (1, 2, "save {path}"),
        (2, 2, "recorrer en pre-orden"),
        (2, 3, "escribir una línea por nodo"),
        (2, 1, "ok:true, dirty:false", "ret"),
        (1, 0, "confirmación en la barra", "ret"),
    ], frames=[(0, 7, "carga: se reemplaza el árbol solo si todo es válido"), (8, 13, "guardado")])


# --------------------------------------------------------------------- estados

DOT_HEAD = ('digraph G {{ rankdir={rank}; bgcolor="white"; nodesep=0.7; ranksep=0.9; pad=0.2;\n'
            ' node [fontname="DejaVu Sans", fontsize=19, shape=box, style="rounded,filled", fillcolor="#E8EFF6", color="#19344E", fontcolor="#19344E", penwidth=1.6];\n'
            ' edge [fontname="DejaVu Sans", fontsize=17, color="#19344E", fontcolor="#19344E", penwidth=1.5];\n')


def state_diagram(path: Path, body: str, rank="LR") -> None:
    source = DOT_HEAD.format(rank=rank) + body + "\n}\n"
    subprocess.run(["dot", "-Tpng", "-Gdpi=170", "-o", str(path)], input=source.encode(), check=True)


INITIAL = ' {name} [label="", shape=circle, width=0.25, style=filled, fillcolor="#19344E"];\n'
FINAL = ' {name} [label="", shape=doublecircle, width=0.3, style=filled, fillcolor="#19344E"];\n'


def states_node(path: Path) -> None:
    state_diagram(path, INITIAL.format(name="i") + FINAL.format(name="f") + '''
 Activo; Inactivo [fillcolor="#E1E1E1"];
 i -> Activo [label="insertar(clave, etiqueta)"];
 Activo -> Inactivo [label="desactivar"];
 Inactivo -> Activo [label="reactivar"];
 Activo -> Activo [label="modificar etiqueta,\\nbuscar"];
 Inactivo -> Inactivo [label="modificar etiqueta,\\nbuscar (se informa inactivo)"];
 Activo -> f [label="eliminar"];
 Inactivo -> f [label="eliminar"];
''', rank="TB")


def states_tree(path: Path) -> None:
    state_diagram(path, INITIAL.format(name="i") + '''
 Vacio [label="Vacío"];
 Balanceado [label="Balanceado\\n|fb| <= 1 en todo nodo"];
 Desbalanceado [label="Desbalanceado\\n(transitorio)\\n|fb| = 2 en algún nodo", fillcolor="#FCE4D6"];
 i -> Vacio [label="crear"];
 Vacio -> Balanceado [label="insertar"];
 Balanceado -> Desbalanceado [label="insertar o eliminar\\nsube la altura de un lado"];
 Desbalanceado -> Balanceado [label="rotar (LL, RR, LR, RL)"];
 Balanceado -> Balanceado [label="insertar o eliminar\\nsin romper el balance"];
 Balanceado -> Vacio [label="eliminar el último nodo"];
 Balanceado -> Vacio [label="nuevo / reset"];
''', rank="TB")


def states_app(path: Path) -> None:
    state_diagram(path, INITIAL.format(name="i") + FINAL.format(name="f") + '''
 Inicio [label="Inicio\\n(diálogo: cargar o vacío)"];
 Sin [label="Sin datos\\nsize = 0, dirty = falso"];
 Cargado [label="Cargado\\ndirty = falso"];
 Modificado [label="Modificado\\ndirty = verdadero", fillcolor="#FCE4D6"];
 Guardado [label="Guardado\\ndirty = falso"];
 i -> Inicio;
 Inicio -> Sin [label="empezar sin datos"];
 Inicio -> Cargado [label="cargar archivo válido"];
 Inicio -> Inicio [label="archivo inválido:\\nerror, árbol intacto"];
 Sin -> Modificado [label="insertar"];
 Cargado -> Modificado [label="insertar / eliminar /\\ndesactivar / modificar"];
 Guardado -> Modificado [label="operación que cambia el árbol"];
 Modificado -> Guardado [label="guardar"];
 Cargado -> Sin [label="nuevo"];
 Modificado -> Sin [label="nuevo"];
 Guardado -> Sin [label="nuevo"];
 Modificado -> f [label="salir"];
 Guardado -> f [label="salir"];
 Cargado -> f [label="salir"];
 Sin -> f [label="salir"];
''', rank="TB")


def states_player(path: Path) -> None:
    state_diagram(path, INITIAL.format(name="i") + '''
 Reposo [label="En reposo\\nsin pasos pendientes"];
 Rep [label="Reproduciendo\\nun paso por intervalo"];
 Pausa [label="En pausa"];
 Fin [label="Terminado\\núltimo árbol visible"];
 i -> Reposo;
 Reposo -> Rep [label="la operación devuelve steps"];
 Rep -> Rep [label="temporizador: dibujar el paso\\nsiguiente (la velocidad fija el intervalo)"];
 Rep -> Pausa [label="pausa"];
 Pausa -> Rep [label="reanudar"];
 Pausa -> Pausa [label="paso a paso:\\navanzar un paso"];
 Rep -> Fin [label="último paso"];
 Pausa -> Fin [label="último paso"];
 Fin -> Reposo [label="aceptar / nueva operación"];
''', rank="TB")


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


def figure(doc, path: Path, caption: str, width_cm: float = 16.4) -> None:
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


# ------------------------------------------------------------------- contenido

def build() -> None:
    doc = Document()
    doc.core_properties.title = "Especificación técnica del Programa de Aprendizaje de Árboles (PAA)"
    doc.core_properties.subject = "Taller 3, Estructura de Datos: árboles AVL"
    doc.core_properties.author = ""
    doc.core_properties.last_modified_by = ""
    setup(doc)
    folder = tempfile.TemporaryDirectory(prefix="paa-doc-")
    tmp = Path(os.environ.get("PAA_SPEC_FIGS") or folder.name)  # PAA_SPEC_FIGS conserva los PNG para revisarlos
    tmp.mkdir(parents=True, exist_ok=True)
    img = {k: tmp / f"{k}.png" for k in (
        "arq", "nodo", "rot1", "rot2", "borrado", "inactivo", "cu1", "cu2", "sec1", "sec2", "sec3",
        "est1", "est2", "est3", "est4")}
    architecture_figure(img["arq"])
    node_figure(img["nodo"])
    rotation_figures(img["rot1"], img["rot2"])
    delete_figure(img["borrado"])
    inactive_figure(img["inactivo"])
    use_case_general(img["cu1"])
    use_case_detail(img["cu2"])
    sequence_insert(img["sec1"])
    sequence_delete(img["sec2"])
    sequence_persist(img["sec3"])
    states_node(img["est1"])
    states_tree(img["est2"])
    states_app(img["est3"])
    states_player(img["est4"])

    doc.add_paragraph("UNIVERSIDAD POPULAR DEL CESAR  ·  INGENIERÍA DE SISTEMAS  ·  ESTRUCTURA DE DATOS", style="Subtitle")
    doc.add_paragraph("Especificación técnica del Programa de Aprendizaje de Árboles (PAA)", style="Title")
    add_table(doc, ["Campo", "Detalle"], [
        ["Asignatura", "Estructura de Datos, Taller 3 (árboles binarios AVL)"],
        ["Universidad y programa", "Universidad Popular del Cesar, Ingeniería de Sistemas"],
        ["Periodo", "2026-2"],
        ["Estudiante", "Rafael (iniciales REMR). Trabajo individual."],
        ["Identificación", "Los datos de identificación se entregan en el archivo de texto aparte, como pide el enunciado."],
        ["Programas", "Taller3_REMR.cpp (motor C++) y Taller3_REMR.py (ventana Python)"],
        ["Fecha límite de entrega", "Martes 1 de diciembre de 2026, 11:59 a. m."],
    ], [4.3, 12.4])

    # 1 ---------------------------------------------------------------
    heading(doc, "1 Introducción y objetivo")
    paragraph(doc, "El programa de Ingeniería de Sistemas de la Universidad Popular del Cesar necesita un Programa de "
                   "Aprendizaje de Árboles (PAA) para enseñar los árboles binarios AVL de forma visual. Un árbol AVL es "
                   "un árbol binario de búsqueda que se mantiene balanceado: en cada nodo, las alturas de sus dos "
                   "subárboles difieren como máximo en uno. Cuando una inserción o una eliminación rompe esa condición, "
                   "el árbol se repara con rotaciones.")
    paragraph(doc, "Objetivo general: construir dos programas, uno en C++ y otro en Python, que permitan gestionar un "
                   "árbol AVL y mostrar de forma visual, paso a paso, dónde se ubica un dato nuevo, cómo cambian los "
                   "factores de balance y qué rotación se aplica. Los recorridos pre-orden, in-orden y post-orden "
                   "permanecen siempre visibles.")
    paragraph(doc, "Objetivos específicos:")
    for text in ("Ofrecer, para el árbol, las funciones de creación, inclusión, eliminación, desactivación, consulta, "
                 "modificación y persistencia que pide el enunciado.",
                 "Animar cada operación con los pasos de comparación, ubicación, cálculo de altura y rotación (LL, RR, LR, RL).",
                 "Lograr el mismo comportamiento en el motor C++ y en el motor Python, y comprobarlo con una prueba de interoperabilidad.",
                 "Permitir que el usuario elija, al iniciar, cargar los datos del archivo o trabajar sin datos.",
                 "Documentar el diseño, la estrategia y los diagramas UML de casos de uso, secuencia y estados."):
        bullet(doc, text)
    heading(doc, "Alcance", 2)
    paragraph(doc, "El sistema es local: no usa navegador, servidor ni internet. El árbol guarda claves enteras con una "
                   "etiqueta de texto. Quedan fuera de alcance otras estructuras (árboles rojo-negro, B, heaps) y la "
                   "edición concurrente por varios usuarios.")

    # 2 ---------------------------------------------------------------
    heading(doc, "2 Requerimientos")
    heading(doc, "2.1 Requerimientos funcionales", 2)
    add_table(doc, ["Id", "Requerimiento", "Prioridad"], [
        ["RF-01", "Crear un árbol AVL vacío (nuevo árbol).", "Alta"],
        ["RF-02", "Insertar una clave entera con su etiqueta, ubicándola como en un árbol binario de búsqueda y rebalanceando con rotaciones si es necesario. Las claves duplicadas se rechazan con un mensaje.", "Alta"],
        ["RF-03", "Eliminar una clave. Un nodo con dos hijos se reemplaza por su sucesor in-orden; el árbol se rebalancea.", "Alta"],
        ["RF-04", "Desactivar un nodo (queda en el árbol, se marca inactivo y sigue balanceando) y reactivarlo.", "Alta"],
        ["RF-05", "Buscar una clave e informar si existe, si no existe o si existe pero está inactiva.", "Alta"],
        ["RF-06", "Modificar la etiqueta de una clave. Cambiar la clave equivale a eliminar e insertar.", "Media"],
        ["RF-07", "Mostrar siempre los recorridos pre-orden, in-orden y post-orden.", "Alta"],
        ["RF-08", "Animar cada inserción o eliminación paso a paso: comparaciones, ubicación, alturas, factores de balance y rotaciones LL, RR, LR, RL, con control de velocidad, pausa y avance paso a paso.", "Alta"],
        ["RF-09", "Guardar el árbol en un archivo de texto y cargarlo; al iniciar, el usuario elige cargar los datos o trabajar sin datos.", "Alta"],
        ["RF-10", "Mantener una bitácora de las rotaciones realizadas.", "Media"],
        ["RF-12", "Deshacer las últimas operaciones (Ctrl+Z), en ambos motores.", "Media"],
        ["RF-11", "Ofrecer una consola autónoma en C++ (con dibujo del árbol por posicionamiento de cursor) y una ventana gráfica en Python, cada una operativa por sí sola.", "Alta"],
    ], [1.6, 12.9, 2.2], center_first=True)
    heading(doc, "2.2 Requerimientos no funcionales", 2)
    add_table(doc, ["Id", "Requerimiento", "Categoría"], [
        ["RNF-01", "Interfaz y mensajes en español.", "Usabilidad"],
        ["RNF-02", "Los motores C++ y Python producen el mismo árbol, los mismos recorridos y la misma lista de pasos para la misma secuencia de operaciones.", "Consistencia"],
        ["RNF-03", "Una inserción, eliminación o búsqueda cuesta O(log n); la altura nunca supera 1,44·log2(n+2).", "Rendimiento"],
        ["RNF-04", "Si el archivo de datos es inválido, el programa informa el error y deja el árbol intacto; ninguna operación lanza una excepción al usuario.", "Robustez"],
        ["RNF-05", "Comunicación entre procesos mediante JSON de una línea en UTF-8 por la entrada y salida estándar, sin puertos de red.", "Portabilidad"],
        ["RNF-06", "Compilación con CMake (C++17); la ventana requiere Python 3.10 o superior y CustomTkinter 6.0.0. En Windows de 64 bits se incluye un ejecutable del motor.", "Portabilidad"],
        ["RNF-07", "El motor Python funciona sin el binario C++ (respaldo automático).", "Disponibilidad"],
        ["RNF-08", "Las animaciones no bloquean la ventana: cada paso se programa con un temporizador.", "Usabilidad"],
    ], [1.6, 12.2, 2.9], center_first=True)
    heading(doc, "2.3 Variables de entrada y salida del modelo", 2)
    paragraph(doc, "Como pide el enunciado (punto 2), las variables del modelo se identifican a continuación. Las "
                   "entradas las da el usuario por la ventana o la consola; las salidas las produce el motor y las muestra la interfaz.")
    add_table(doc, ["Tipo", "Variable", "Dominio", "Descripción"], [
        ["Entrada", "clave", "entero de 32 bits con signo", "Valor que ordena el árbol; única. Se acepta negativa, cero o muy grande dentro del rango int32."],
        ["Entrada", "etiqueta", "texto UTF-8", "Dato asociado a la clave; puede estar vacía. Al guardar, un ';' o salto de línea se sustituye por un espacio."],
        ["Entrada", "operación", "insertar, eliminar, buscar, desactivar/reactivar, modificar, guardar, cargar, nuevo", "Acción que pide el usuario."],
        ["Entrada", "ruta de archivo", "texto", "Archivo de persistencia (por defecto data/arbol_avl.txt)."],
        ["Entrada", "velocidad, pausa, paso", "control de la ventana", "Parámetros de la reproducción de la animación."],
        ["Salida", "árbol", "nodos con clave, etiqueta, activo, altura y fb", "Estructura final y la de cada paso, para dibujarla."],
        ["Salida", "factores de balance", "entero en [-1, 1] en reposo", "Valor de fb de cada nodo (puede llegar a ±2 de forma transitoria)."],
        ["Salida", "bitácora de rotaciones", "lista de tipos LL, RR, LR, RL y nodo pivote", "Rotaciones aplicadas por la operación."],
        ["Salida", "recorridos", "tres listas de claves", "Pre-orden, in-orden (claves ascendentes) y post-orden."],
        ["Salida", "resultado de búsqueda", "encontrada, inactiva, no encontrada", "Estado de la clave consultada."],
        ["Salida", "estado", "size (entero), dirty (booleano)", "Cantidad de nodos y si hay cambios sin guardar."],
        ["Salida", "mensaje de error", "texto en español", "Duplicado, clave ausente, archivo inválido, etc."],
    ], [1.7, 3.4, 4.6, 7.0])

    # 3 ---------------------------------------------------------------
    heading(doc, "3 Diseño de la estructura de datos")
    heading(doc, "3.1 Nodo del árbol AVL", 2)
    paragraph(doc, "El árbol se modela con nodos enlazados. Cada nodo guarda su clave, la etiqueta, la marca de actividad, "
                   "la altura de su subárbol y los enlaces a los hijos. Guardar la altura en el nodo evita recalcularla "
                   "recorriendo el subárbol y deja el factor de balance en tiempo constante.")
    figure(doc, img["nodo"], "Figura 1. Estructura del nodo y su significado en un árbol de tres nodos.")
    add_table(doc, ["Campo", "Tipo", "Uso"], [
        ["clave", "entero (int32)", "Criterio de orden: menores a la izquierda, mayores a la derecha."],
        ["etiqueta", "texto", "Información que el usuario asocia a la clave."],
        ["activo", "booleano", "Verdadero si el nodo está activo; falso si se desactivó (el nodo permanece en el árbol)."],
        ["altura", "entero", "Altura del subárbol con raíz en el nodo. Nulo = 0; hoja = 1."],
        ["izq, der", "enlace a Nodo", "Subárboles izquierdo y derecho; nulos si no existen."],
    ], [3.0, 3.6, 10.1], mono_cols=(0,))
    heading(doc, "3.2 Altura y factor de balance", 2)
    paragraph(doc, "altura(nodo) = 1 + max(altura(izq), altura(der)), con altura(nulo) = 0. El factor de balance es "
                   "fb(nodo) = altura(izq) - altura(der). Un árbol es AVL si fb ∈ {-1, 0, +1} en todos los nodos. "
                   "Si fb = +2 el nodo está cargado a la izquierda; si fb = -2, a la derecha. En los dibujos, cada nodo "
                   "muestra su fb junto al círculo.")
    heading(doc, "3.3 Rotaciones", 2)
    paragraph(doc, "Tras insertar o eliminar, el algoritmo sube desde el punto de cambio hacia la raíz recalculando altura y fb. "
                   "En el primer nodo con |fb| = 2 se aplica una de cuatro rotaciones, según dónde esté el exceso:")
    add_table(doc, ["Caso", "Condición", "Rotación", "Ejemplo (inserciones)"], [
        ["LL", "fb(nodo) = +2 y fb(hijo izq) ≥ 0", "simple a la derecha en el nodo", "30, 20, 10"],
        ["RR", "fb(nodo) = -2 y fb(hijo der) ≤ 0", "simple a la izquierda en el nodo", "10, 20, 30"],
        ["LR", "fb(nodo) = +2 y fb(hijo izq) < 0", "izquierda en el hijo izquierdo y luego derecha en el nodo", "30, 10, 20"],
        ["RL", "fb(nodo) = -2 y fb(hijo der) > 0", "derecha en el hijo derecho y luego izquierda en el nodo", "10, 30, 20"],
    ], [1.6, 5.0, 6.2, 3.9], center_first=True)
    paragraph(doc, "Las figuras 2 y 3 muestran un ejemplo mínimo de cada caso. El nodo con fb fuera de rango aparece "
                   "sombreado.")
    figure(doc, img["rot1"], "Figura 2. Rotaciones simples RR y LL con tres claves.")
    figure(doc, img["rot2"], "Figura 3. Rotaciones dobles RL y LR: dos rotaciones simples encadenadas.")
    paragraph(doc, "Una rotación simple solo reasigna tres enlaces y recalcula dos alturas, por lo que cuesta O(1). La "
                   "bitácora registra el tipo de caso (LL, RR, LR o RL) y el nodo pivote donde se detectó el desbalance.")
    heading(doc, "3.4 Inserción", 2)
    paragraph(doc, "Se desciende desde la raíz comparando la clave: a la izquierda si es menor, a la derecha si es mayor, "
                   "y se rechaza si es igual. El nodo nuevo entra como hoja con altura 1. Al regresar de la recursión se "
                   "recalcula altura y fb en cada ancestro y se rota si hace falta. Una inserción necesita a lo sumo una "
                   "rotación (simple o doble).")
    heading(doc, "3.5 Eliminación", 2)
    paragraph(doc, "Se localiza el nodo. Hoja: se quita. Un hijo: lo reemplaza ese hijo. Dos hijos: se copia al nodo la "
                   "clave, etiqueta y marca del sucesor in-orden (el menor del subárbol derecho) y se elimina el nodo "
                   "original del sucesor. Después se recalcula hacia la raíz, y a diferencia de la inserción puede hacer "
                   "falta una rotación en varios niveles (hasta O(log n)).")
    figure(doc, img["borrado"], "Figura 4. Eliminación de un nodo con dos hijos y eliminación que dispara una rotación.")
    heading(doc, "3.6 Desactivación", 2)
    paragraph(doc, "Desactivar no cambia la forma del árbol: solo pone activo = falso. El nodo sigue ordenando y balanceando, "
                   "la búsqueda lo reporta como inactivo, se muestra en gris y los recorridos lo incluyen. Reactivarlo "
                   "devuelve activo = verdadero. Así se separa la baja lógica (reversible) de la eliminación física.")
    figure(doc, img["inactivo"], "Figura 5. Nodo desactivado dentro del árbol.")
    heading(doc, "3.7 Recorridos y complejidad", 2)
    add_table(doc, ["Recorrido", "Orden de visita", "Uso didáctico"], [
        ["Pre-orden", "raíz, izquierda, derecha", "Reproduce la forma del árbol; es el orden del archivo de persistencia."],
        ["In-orden", "izquierda, raíz, derecha", "Entrega las claves en orden ascendente (comprueba la propiedad BST)."],
        ["Post-orden", "izquierda, derecha, raíz", "Visita los hijos antes que el padre."],
    ], [2.6, 4.6, 9.5])
    add_table(doc, ["Operación", "Tiempo", "Observación"], [
        ["insertar / eliminar / buscar", "O(log n)", "Altura ≤ 1,44·log2(n+2)."],
        ["desactivar / reactivar / modificar etiqueta", "O(log n)", "Es una búsqueda más un cambio de campo."],
        ["recorridos, guardar, cargar", "O(n)", "Cargar reinserta n claves: O(n log n)."],
        ["rotación", "O(1)", "Tres enlaces y dos alturas."],
    ], [6.0, 2.6, 8.1])

    # 4 ---------------------------------------------------------------
    heading(doc, "4 Estrategia de solución")
    paragraph(doc, "La solución separa el cálculo de la presentación. Un motor calcula cada operación y devuelve, además del "
                   "resultado, la lista ordenada de pasos con una foto del árbol en cada uno. La interfaz solo reproduce esa "
                   "lista. Así el mismo código de animación sirve para cualquier motor.")
    for text in (
        "Estructura: nodo con altura almacenada y factor de balance derivado (sección 3).",
        "Algoritmo: inserción y eliminación recursivas de árbol binario de búsqueda; al regresar de cada llamada se "
        "recalcula la altura, se emite un paso height con el fb y, si |fb| = 2, se aplica la rotación y se emite un paso rotate. "
        "Los pasos de balance salen de abajo hacia arriba.",
        "Motor C++ (Taller3_REMR.cpp): contiene el AVL, las operaciones y la persistencia; tiene consola autónoma con dibujo "
        "del árbol (GotoXY por secuencias ANSI) y modo --api para la ventana.",
        "Ventana Python (Taller3_REMR.py, CustomTkinter): dibuja el árbol en un canvas, reproduce los pasos con un "
        "temporizador y muestra la bitácora y los tres recorridos. Incluye un motor Python autónomo con el mismo contrato.",
        "Consistencia: una prueba de interoperabilidad ejecuta la misma secuencia de operaciones en ambos motores y compara "
        "árbol, recorridos y pasos tipo a tipo.",
        "Persistencia: un archivo de texto con una línea por nodo en pre-orden; al cargar se construye un árbol temporal "
        "que reemplaza al actual solo si todo el archivo es válido.",
    ):
        bullet(doc, text)
    heading(doc, "Decisiones y alternativas", 2)
    add_table(doc, ["Decisión", "Alternativa descartada", "Motivo"], [
        ["Altura guardada en el nodo", "Calcularla en cada consulta", "Evita O(n) por consulta y mantiene O(log n) total."],
        ["Desactivar sin quitar el nodo", "Eliminar físicamente", "Es reversible y deja ver que un nodo inactivo sigue balanceando."],
        ["Clave duplicada rechazada", "Permitir duplicados", "Mantiene la búsqueda determinista y el recorrido in-orden estrictamente creciente."],
        ["Sucesor in-orden", "Predecesor in-orden", "Convención más común; el resultado es válido con cualquiera."],
        ["Motor C++ + ventana Python", "Interfaz web con servidor; lógica en JavaScript", "No requiere servidor ni internet; ambos programas pedidos por el enunciado son reales."],
        ["Pasos con foto del árbol", "Que la interfaz recalcule las rotaciones", "La interfaz no duplica lógica AVL y no puede divergir del motor."],
    ], [4.2, 4.9, 7.6])

    # 5 ---------------------------------------------------------------
    heading(doc, "5 Arquitectura: motor C++ y ventana Python")
    paragraph(doc, "La ventana Python lanza el motor C++ como proceso hijo con el argumento --api y se comunica por la "
                   "entrada y salida estándar. Si el binario no existe, intenta compilarlo con CMake; si no lo consigue, "
                   "usa el motor Python y lo indica en la barra de estado. El lanzador Iniciar PAA.pyw abre la ventana "
                   "sin consola en Windows.")
    figure(doc, img["arq"], "Figura 6. Procesos y flujo de datos.")
    add_table(doc, ["Opción", "Efecto"], [
        ["--api", "Motor C++ en modo protocolo: solo escribe respuestas JSON por stdout."],
        ["--data RUTA", "Archivo de persistencia a usar."],
        ["--python-backend", "Fuerza el motor Python autónomo."],
        ["--cpp-binary RUTA", "Usa un binario C++ concreto."],
        ["--self-test", "Autoprueba del motor C++ (imprime OK)."],
    ], [4.2, 12.5], mono_cols=(0,))
    heading(doc, "5.1 Protocolo JSON", 2)
    paragraph(doc, "Cada solicitud es un objeto JSON en una sola línea UTF-8 terminada en salto de línea; cada solicitud "
                   "recibe una sola línea de respuesta. Al conectarse, la ventana envía ping y exige protocol = \"1\"; con otra "
                   "versión no usa el proceso.")
    add_table(doc, ["Acción", "Parámetros", "Efecto"], [
        ["ping", "-", "Devuelve backend (cpp o python) y protocol."],
        ["state", "-", "Devuelve árbol, recorridos y estado (dirty, size)."],
        ["reset", "-", "Vacía el árbol (nuevo)."],
        ["load / save", "path", "Carga o guarda el archivo de persistencia."],
        ["insert", "key, label", "Inserta; emite pasos."],
        ["delete", "key", "Elimina; emite pasos."],
        ["search", "key", "Busca; informa found, notfound o inactiva."],
        ["toggle", "key", "Alterna activo / inactivo."],
        ["update", "key, label", "Cambia la etiqueta."],
        ["undo", "-", "Deshace la última operación que cambió el árbol (hasta 200)."],
        ["traversals", "-", "Devuelve pre, in y post."],
        ["shutdown", "-", "Termina el proceso."],
    ], [3.0, 3.4, 10.3], mono_cols=(0, 1))
    paragraph(doc, "Ejemplo de intercambio (insertar 30 en un árbol que ya contiene 10 y 20):")
    code_block(doc, '''
-> {"action":"insert","key":30,"label":"treinta"}
<- {"ok":true,
    "result":{"key":30},
    "steps":[{"t":"compare","key":30,"with":10,"tree":{...}},
             {"t":"descend","dir":"R","tree":{...}}, ...,
             {"t":"rotate","type":"RR","pivot":10,"tree":{...}}],
    "tree":{"k":20,"l":"veinte","a":1,"h":2,"bf":0,"L":{...},"R":{...}},
    "traversals":{"pre":[20,10,30],"in":[10,20,30],"post":[10,30,20]},
    "state":{"dirty":true,"size":3}}
-> {"action":"insert","key":30,"label":"otra"}
<- {"ok":false,"error":"La clave 30 ya existe","state":{"dirty":true,"size":3}}''')
    heading(doc, "5.2 Contrato de pasos", 2)
    paragraph(doc, "Ambos motores emiten exactamente el mismo formato. Cada paso es {\"t\":TIPO, ..., \"tree\":SNAP}. SNAP es null "
                   "o {\"k\":clave,\"l\":etiqueta,\"a\":0|1,\"h\":altura,\"bf\":fb,\"L\":SNAP,\"R\":SNAP}: la foto del árbol justo "
                   "después del paso, de modo que la ventana solo dibuja.")
    add_table(doc, ["Tipo de paso", "Campos", "Significado"], [
        ["compare", "key, with", "Se compara la clave con el nodo 'with'."],
        ["descend", "dir (L o R)", "Se baja al hijo izquierdo o derecho."],
        ["place", "key", "El nodo nuevo queda como hoja."],
        ["found / notfound", "key", "Resultado de una búsqueda."],
        ["replace", "key, with", "Un nodo con dos hijos copia los datos de su sucesor."],
        ["remove", "key", "Se quita físicamente un nodo."],
        ["height", "key, h, bf", "Se recalcula la altura y el factor de balance de un nodo."],
        ["rotate", "type (LL, RR, LR, RL), pivot", "Se rota; pivot es el nodo desbalanceado."],
        ["toggle", "key, active", "Se desactivó o reactivó un nodo."],
        ["update", "key", "Se cambió la etiqueta."],
    ], [3.4, 4.6, 8.7], mono_cols=(0, 1))
    paragraph(doc, "Una respuesta correcta tiene la forma {\"ok\":true, \"result\", \"steps\", \"tree\", \"traversals\", \"state\"}; "
                   "un error, {\"ok\":false, \"error\", \"state\"}. Los pasos de balance se emiten de abajo hacia arriba. En modo "
                   "--api la salida estándar contiene solo el protocolo; los mensajes de diagnóstico van a la salida de errores.")
    heading(doc, "5.3 Motor Python autónomo", 2)
    paragraph(doc, "La clase Engine de Python expone handle(solicitud) → respuesta con las mismas acciones y el mismo "
                   "contrato. La ventana la usa cuando el motor C++ no arranca o cuando se pide --python-backend, y también "
                   "puede ejecutarse sin interfaz para las pruebas. Como ambos motores cumplen el mismo contrato, la "
                   "ventana no distingue cuál tiene detrás.")

    # 6 ---------------------------------------------------------------
    heading(doc, "6 Persistencia")
    paragraph(doc, "El archivo de datos (data/arbol_avl.txt) es de texto UTF-8 con una línea por nodo: "
                   "clave;etiqueta;activo, donde activo vale 1 o 0. Los nodos se escriben en pre-orden, de modo que al "
                   "reinsertarlos en ese orden se reconstruye exactamente el mismo árbol.")
    code_block(doc, '''
20;veinte;1
10;diez;1
5;cinco;0
30;treinta;1''')
    for text in (
        "Guardar: recorre el árbol en pre-orden y escribe una línea por nodo. Un ';' o un salto de línea dentro de la "
        "etiqueta se reemplaza por un espacio.",
        "Cargar: lee y valida cada línea (tres campos, clave entera, activo 0 o 1, sin claves repetidas) y reinserta en un "
        "árbol temporal. Solo si todo es válido el árbol temporal sustituye al actual; si no, se devuelve un error y el "
        "árbol queda intacto. Un archivo vacío se trata como error claro.",
        "Inicio: un diálogo pregunta si cargar el archivo o empezar sin datos (enunciado, punto 10).",
        "Estado: dirty pasa a verdadero con cualquier operación que cambie el árbol y a falso al guardar o cargar.",
    ):
        bullet(doc, text)

    # 7 ---------------------------------------------------------------
    heading(doc, "7 Diagramas UML")
    heading(doc, "7.1 Diagramas de casos de uso", 2)
    paragraph(doc, "El actor principal es el usuario (estudiante o docente). Los actores secundarios son el motor AVL y el "
                   "archivo de datos, que participan en las operaciones del árbol y en la persistencia.")
    figure(doc, img["cu1"], "Figura 7. Diagrama de casos de uso general.", 15.0)
    figure(doc, img["cu2"], "Figura 8. Detalle de insertar y eliminar: rotaciones, pasos y recorridos.")
    add_table(doc, ["Caso de uso", "Flujo principal", "Posparticipación / alternativas"], [
        ["Insertar clave", "El usuario escribe clave y etiqueta; el motor ubica el nodo, rebalancea y devuelve los pasos; la ventana los anima.", "Clave duplicada: error y árbol intacto."],
        ["Eliminar clave", "El usuario indica la clave; el motor quita el nodo (sucesor si tiene dos hijos), rebalancea y devuelve los pasos.", "Clave ausente: error."],
        ["Buscar clave", "El motor recorre el camino de comparaciones y responde.", "Encontrada, inactiva o no encontrada."],
        ["Desactivar / reactivar", "El motor cambia la marca activo del nodo; el nodo se pinta en gris.", "Clave ausente: error."],
        ["Modificar etiqueta", "El motor cambia la etiqueta del nodo.", "Para cambiar la clave: eliminar e insertar."],
        ["Cargar / guardar", "El motor lee o escribe el archivo de persistencia.", "Archivo inválido: error y árbol intacto."],
    ], [3.4, 8.6, 4.7])

    heading(doc, "7.2 Diagramas de secuencia", 2)
    paragraph(doc, "Se muestran tres secuencias: insertar con rotación, eliminar y cargar o guardar. En todas, la ventana "
                   "pide la operación al motor por el protocolo JSON y después reproduce los pasos recibidos.")
    figure(doc, img["sec1"], "Figura 9. Secuencia de inserción con rotación RR (insertar 30 sobre 10, 20).")
    figure(doc, img["sec2"], "Figura 10. Secuencia de eliminación, con el caso de clave inexistente.")
    figure(doc, img["sec3"], "Figura 11. Secuencia de carga y de guardado del archivo.")

    heading(doc, "7.3 Diagramas de estados", 2)
    paragraph(doc, "Se modelan cuatro máquinas de estados: el ciclo de vida de un nodo (activo, inactivo, eliminado), el del "
                   "árbol, los estados de la aplicación (sin datos, cargado, modificado, guardado) y el reproductor de animación.")
    figure(doc, img["est1"], "Figura 12. Ciclo de vida de un nodo: activo, inactivo y eliminado.", 9.5)
    figure(doc, img["est2"], "Figura 13. Ciclo de vida del árbol: el desbalance es transitorio y se corrige con rotaciones.", 10.0)
    figure(doc, img["est3"], "Figura 14. Estados de la aplicación respecto de los datos y el archivo.", 13.5)
    figure(doc, img["est4"], "Figura 15. Estados del reproductor de animación.", 13.5)

    # 8 ---------------------------------------------------------------
    doc.add_page_break()
    heading(doc, "8 Estructura del proyecto y entregables")
    add_table(doc, ["Elemento del enunciado", "Archivo o carpeta"], [
        ["Programa en C++ (nombre con iniciales)", "src/cpp/Taller3_REMR.cpp"],
        ["Programa en Python (nombre con iniciales)", "src/python/Taller3_REMR.py (más paa_engine.py y paa_backend.py)"],
        ["Lanzador", "Iniciar PAA.pyw"],
        ["Compilación", "CMakeLists.txt (destino paa_cpp); ejecutable de Windows en bin/windows/ con su huella SHA-256"],
        ["Archivo de persistencia", "data/arbol_avl.txt"],
        ["Especificación técnica (este documento)", "docs/especificacion_tecnica.docx, generado por scripts/build_technical_spec.py"],
        ["Pruebas", "tests/ (autoprueba C++, pruebas del motor Python, interoperabilidad)"],
        ["Archivo de identificación", "Archivo de texto aparte (lo entrega el estudiante)"],
        ["Video explicativo", "Se carga en YouTube; el enlace se entrega con los archivos"],
    ], [6.4, 10.3])

    # 9 ---------------------------------------------------------------
    heading(doc, "9 Evidencia de pruebas")
    paragraph(doc, "Resultados de las pruebas ejecutadas el 17 de noviembre de 2026 sobre la versión entregada.")
    add_table(doc, ["Prueba", "Qué verifica", "Cómo se ejecuta", "Resultado"], [
        ["Autoprueba C++", "Rotaciones LL, RR, LR, RL; borrado de hoja, un hijo y dos hijos; duplicados y claves ausentes; 1..1000 con altura ≤ 1,44·log2(n); persistencia.", "paa_cpp --self-test", "Aprobada"],
        ["API C++", "Respuestas de ping, insert, search, toggle, save, load, error de duplicado y shutdown.", "tests/integration/check_api.py", "Aprobada"],
        ["Motor Python", "Los mismos casos que la autoprueba C++.", "python3 -I tests/python/test_engine.py", "Aprobada (32 pruebas)"],
        ["Interoperabilidad", "Misma secuencia en ambos motores: igual árbol, recorridos y pasos (incluye claves negativas, 0 y 2147483647).", "tests/integration/check_interop.py", "Aprobada (más de 300 operaciones, sin diferencias)"],
        ["Ventana", "Capturas del árbol tras insertar 1..7 y tras una rotación, en pantalla virtual.", "tests/python/test_window_smoke.py (motor C++ y Python) y revisión visual", "Aprobada"],
        ["Persistencia", "Guardar y cargar reproduce el mismo pre-orden; archivo inválido deja el árbol intacto.", "Autoprueba y pruebas del motor Python", "Aprobada"],
    ], [2.8, 7.0, 4.4, 2.5])
    paragraph(doc, "Las pruebas de la ventana se ejecutan en una pantalla virtual; incluyen guardar, abrir, nuevo, deshacer y carga de un archivo inválido.")

    # 10 --------------------------------------------------------------
    heading(doc, "10 Créditos")
    for text in (
        "Autor: Rafael (REMR), trabajo individual. Universidad Popular del Cesar, Ingeniería de Sistemas, Estructura de Datos, Taller 3, 2026-2.",
        "Árboles AVL: G. M. Adelson-Velskii y E. M. Landis (1962), \"Un algoritmo para la organización de la información\".",
        "Herramientas: C++17 y CMake para el motor; Python 3 y CustomTkinter 6.0.0 para la ventana; python-docx, Pillow y Graphviz para generar este documento.",
        "Esta especificación se genera con scripts/build_technical_spec.py; los diagramas UML se dibujan por código dentro del mismo script.",
    ):
        bullet(doc, text)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    folder.cleanup()
    print(f"Documento generado: {OUTPUT}")


if __name__ == "__main__":
    build()
