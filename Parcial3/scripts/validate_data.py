#!/usr/bin/env python3
"""Valida data/pera_colombia.csv (formato PERA v1): integridad, rangos y cobertura. Solo biblioteca estandar."""
import math, os, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pera_colombia.csv")


def hav(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


K, C, P, R, err, warnings = {}, {}, {}, {}, [], []
for n, line in enumerate(open(PATH, encoding="utf-8"), 1):
    line = line.rstrip("\n")
    if not line or line.startswith("#"):
        continue
    f = line.split(";")
    try:
        if f[0] == "K": K[f[1]] = float(f[2])
        elif f[0] == "C": C[f[1]] = (f[2], f[3], float(f[4]), float(f[5]), f[6])
        elif f[0] == "P": P[f[1]] = (f[2], float(f[3]), float(f[4]), int(f[5]), f[6])
        elif f[0] == "R": R[f[1]] = (f[2], f[3], float(f[4]), float(f[5]), [x for x in f[6].split("|") if x], f[7])
        else: err.append("linea %d: tipo desconocido" % n)
    except (IndexError, ValueError):
        err.append("linea %d: mal formada" % n)

if set(K) != {"consumo_km_gal", "precio_gal", "velocidad_kmh"}: err.append("parametros K incompletos")
for i, (nom, dep, lat, lon, _) in C.items():
    if not (-5 <= lat <= 13 and -82 <= lon <= -66): err.append("ciudad %s fuera de Colombia" % i)
for i, (nom, lat, lon, tar, _) in P.items():
    if not (-5 <= lat <= 13 and -82 <= lon <= -66): err.append("peaje %s fuera de Colombia" % i)
    if not (500 <= tar <= 40000): err.append("peaje %s tarifa rara: %d" % (i, tar))
pares, usados = set(), set()
for i, (a, b, km, h, ps, act) in R.items():
    if a not in C or b not in C: err.append("ruta %s: ciudad inexistente" % i); continue
    if a == b: err.append("ruta %s: origen = destino" % i)
    if (min(a, b), max(a, b)) in pares: err.append("ruta %s repetida" % i)
    pares.add((min(a, b), max(a, b)))
    for p in ps:
        usados.add(p)
        if p not in P: err.append("ruta %s: peaje %s inexistente" % (i, p))
    ca, cb = C[a], C[b]
    straight = hav(ca[2], ca[3], cb[2], cb[3])
    if km < straight * 0.98: err.append("ruta %s: %.1f km < linea recta %.1f" % (i, km, straight))
    # Rodeos grandes son reales (rios sin puente, cordilleras): se avisan, no son error de datos.
    if km > straight * (4.5 if straight < 80 else 2.7): warnings.append("ruta %s: %.1f km con recta %.1f (rodeo; revisar si hace falta)" % (i, km, straight))
    if km <= 0 or h <= 0:
        err.append("ruta %s: distancia y tiempo deben ser positivos" % i)
    else:
        avg = km / h
        if not (25 <= avg <= 95): warnings.append("ruta %s: velocidad media %.1f km/h; revisar" % (i, avg))
for p in P:
    if p not in usados: err.append("peaje %s no esta en ninguna ruta" % p)
touch = {x for a, b, *_ in R.values() for x in (a, b)}
isolated = sorted(C[c][0] for c in C if c not in touch)

print("ciudades %d, peajes %d, rutas %d" % (len(C), len(P), len(R)))
print("ciudades sin rutas registradas:", ", ".join(isolated) or "ninguna")
tot = sum(len(r[4]) for r in R.values())
print("peajes por ruta: %d asignaciones, max %d" % (tot, max(len(r[4]) for r in R.values())))
for w in warnings: print("AVISO:", w)
for e in err: print("ERROR:", e)
print("OK" if not err else "%d errores" % len(err))
sys.exit(1 if err else 0)
