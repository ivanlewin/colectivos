"""Paso 5 — ¿Sirve esta geometría para saber por qué calles pasan los colectivos?

Ésta es la pregunta que decide el proyecto. Para atribuir líneas a cuadras hace
falta que la traza siga el eje de la calle. Si los vértices están separados
cientos de metros, la polilínea corta manzanas por el medio y cualquier
atribución a calles va a ser basura.

Mide la separación entre vértices consecutivos en las tres fuentes disponibles
y las compara. Requiere haber corrido antes:

    bash scripts/00_download.sh all

Uso: python3 scripts/05_geometry_quality.py
"""

import collections
import csv
import json
import math
import re
import statistics

import common

EARTH_RADIUS_M = 6_371_000


def haversine(a, b):
    """Distancia en metros entre dos puntos (lon, lat)."""
    (lon1, lat1), (lon2, lat2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def report(name, lines):
    """`lines` es un iterable de listas de puntos (lon, lat)."""
    segments = []
    total_points = 0
    count = 0
    for pts in lines:
        count += 1
        total_points += len(pts)
        segments.extend(haversine(pts[i], pts[i + 1]) for i in range(len(pts) - 1))

    if not segments:
        print(f"{name}: sin datos")
        return

    segments.sort()
    n = len(segments)
    over = lambda m: 100 * sum(1 for s in segments if s > m) / n
    print(f"\n{name}")
    print(f"  recorridos              : {count}")
    print(f"  puntos por recorrido    : {total_points / count:.0f} en promedio")
    print(f"  separación entre puntos : mediana {statistics.median(segments):6.1f} m")
    print(f"                            p90     {segments[int(n * 0.9)]:6.1f} m")
    print(f"                            máx     {segments[-1]:6.1f} m")
    print(f"  segmentos > 200 m       : {over(200):5.1f} %")
    print(f"  segmentos > 500 m       : {over(500):5.1f} %")


def load_epok():
    """Recorridos EPOK, reproyectados a lat/lon si hace falta."""
    path = common.DATASET
    if not path.exists():
        return None
    feats = json.loads(path.read_text(encoding="utf-8"))["features"]
    sample = feats[0]["geometry"]["coordinates"][0]
    if abs(sample[0]) > 180:  # está en coordenadas planas
        tf = common.transformer()
        return [
            [tf.transform(x, y) for x, y in f["geometry"]["coordinates"]] for f in feats
        ]
    return [f["geometry"]["coordinates"] for f in feats]


def load_gtfs_shapes():
    path = common.ROOT / "data" / "gtfs" / "shapes.txt"
    if not path.exists():
        return None
    shapes = collections.defaultdict(list)
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            shapes[row["shape_id"]].append(
                (int(row["shape_pt_sequence"]),
                 float(row["shape_pt_lon"]),
                 float(row["shape_pt_lat"]))
            )
    return [[p[1:] for p in sorted(pts)] for pts in shapes.values()]


def load_cnrt_kml():
    path = common.ROOT / "data" / "cnrt_routes.kml"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = []
    for block in re.findall(r"<coordinates>(.*?)</coordinates>", text, re.S):
        pts = []
        for token in block.split():
            parts = token.split(",")
            if len(parts) >= 2:
                try:
                    pts.append((float(parts[0]), float(parts[1])))
                except ValueError:
                    pass
        if len(pts) > 1:
            lines.append(pts)
    return lines


def main():
    common.heading("Separación entre vértices, por fuente")
    print("Referencia: una cuadra porteña mide ~110 m. Si la mediana está muy")
    print("por encima de eso, la traza no sigue las calles.")

    sources = [
        ("EPOK  (getGeoLayer, actual)", load_epok),
        ("GTFS  (Buenos Aires Data, 2019)", load_gtfs_shapes),
        ("CNRT  (KML jurisdicción nacional, 2023)", load_cnrt_kml),
    ]
    for name, loader in sources:
        data = loader()
        if data is None:
            print(f"\n{name}\n  no descargado — corré: bash scripts/00_download.sh all")
        else:
            report(name, data)

    common.heading("Conclusión")
    print("EPOK sirve como padrón de líneas vigentes, pero su geometría está")
    print("demasiado simplificada para atribuir colectivos a calles.")
    print("Para eso hay que usar el GTFS (o el KML del CNRT como control).")


if __name__ == "__main__":
    main()
