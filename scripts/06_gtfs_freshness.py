"""Paso 6 — ¿Cuánto sirve todavía el GTFS de 2019?

El GTFS es la única fuente con geometría que sigue las calles, pero su
`feed_info.txt` declara `feed_end_date=20191231`: son datos de 2019. EPOK, en
cambio, está actualizado pero su geometría no sirve (paso 5).

La salida de esto decide si el proyecto es viable: mide, recorrido por
recorrido, qué fracción de la traza vigente de EPOK cae sobre la mejor traza
del GTFS de la misma línea. Un recorrido con cobertura alta es un recorrido que
no cambió y cuya geometría densa de 2019 podemos usar con confianza.

Escribe output/route_coverage.csv con el resultado por recorrido, para poder
filtrar después por nivel de confianza.

Requiere:
    bash scripts/00_download.sh all

Uso: python3 scripts/06_gtfs_freshness.py
"""

import collections
import csv
import json
import math
import re
import statistics

import common

GTFS = common.ROOT / "data" / "gtfs_frequency"
EPOK_WGS84 = common.ROOT / "data" / "routes_wgs84.json"
OUTPUT_CSV = common.ROOT / "output" / "route_coverage.csv"

# Un vértice de EPOK se considera "sobre" la traza GTFS si hay un punto de la
# traza a menos de esta distancia. 50 m tolera el ancho de una avenida y los
# errores de digitalización, sin llegar a tolerar un cambio de calle.
TOLERANCE_M = 50

# Lado de la celda del índice espacial, en grados (~330 m). Se buscan siempre
# las 9 celdas vecinas, así que cubre de sobra la tolerancia.
CELL = 0.003

M_PER_DEG_LAT = 111_320
M_PER_DEG_LON = 92_000  # a la latitud de Buenos Aires


def line_number(short_name):
    """Número de línea a partir del route_short_name del GTFS ('065A' -> 65)."""
    match = re.match(r"(\d+)", short_name or "")
    return int(match.group(1)) if match else None


def load_gtfs_shapes_by_line():
    """{número de línea: {shape_id: índice espacial de sus puntos}}"""
    route_to_line = {}
    with (GTFS / "routes.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            n = line_number(row["route_short_name"])
            if n is not None and n < 200:
                route_to_line[row["route_id"]] = n

    line_to_shapes = collections.defaultdict(set)
    with (GTFS / "trips.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            n = route_to_line.get(row["route_id"])
            if n is not None and row.get("shape_id"):
                line_to_shapes[n].add(row["shape_id"])

    points = collections.defaultdict(list)
    with (GTFS / "shapes.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            points[row["shape_id"]].append(
                (float(row["shape_pt_lat"]), float(row["shape_pt_lon"]))
            )

    index = {}
    for shape_id, pts in points.items():
        grid = collections.defaultdict(list)
        for lat, lon in pts:
            grid[(int(lat / CELL), int(lon / CELL))].append((lat, lon))
        index[shape_id] = grid
    return line_to_shapes, index


def distance_to_shape(grid, lat, lon):
    """Distancia en metros al punto más cercano de la traza, o inf si está lejos."""
    gi, gj = int(lat / CELL), int(lon / CELL)
    best = math.inf
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            for a, b in grid.get((gi + di, gj + dj), ()):
                d = ((a - lat) * M_PER_DEG_LAT) ** 2 + ((b - lon) * M_PER_DEG_LON) ** 2
                best = min(best, d)
    return math.sqrt(best)


def main():
    if not GTFS.exists():
        raise SystemExit(
            f"Falta {GTFS}. Corré: bash scripts/00_download.sh gtfsfreq"
        )

    # EPOK en lat/lon: preferimos la descarga con srid=4326; si no está,
    # reproyectamos la que tenemos.
    if EPOK_WGS84.exists():
        feats = json.loads(EPOK_WGS84.read_text(encoding="utf-8"))["features"]
        routes = [
            (f["properties"], [(la, lo) for lo, la in f["geometry"]["coordinates"]])
            for f in feats
        ]
    else:
        tf = common.transformer()
        routes = []
        for f in common.features():
            pts = [tf.transform(x, y) for x, y in f["geometry"]["coordinates"]]
            routes.append((f["properties"], [(la, lo) for lo, la in pts]))

    line_to_shapes, index = load_gtfs_shapes_by_line()

    common.heading("Vigencia del GTFS 2019 frente al padrón EPOK actual")
    print(f"Tolerancia: un vértice cuenta como coincidente si hay un punto de la")
    print(f"traza GTFS a menos de {TOLERANCE_M} m.\n")

    results = []
    for props, vertices in routes:
        n = int(props["linea"])
        best_coverage, best_shape = None, None
        for shape_id in line_to_shapes.get(n, ()):
            grid = index.get(shape_id)
            if not grid:
                continue
            hits = sum(
                1 for lat, lon in vertices
                if distance_to_shape(grid, lat, lon) <= TOLERANCE_M
            )
            coverage = hits / len(vertices)
            if best_coverage is None or coverage > best_coverage:
                best_coverage, best_shape = coverage, shape_id
        results.append((props["l_r_s"], n, best_coverage, best_shape))

    missing = [r for r in results if r[2] is None]
    matched = sorted((r for r in results if r[2] is not None), key=lambda r: r[2])

    print(f"Recorridos vigentes en EPOK        : {len(results)}")
    print(f"Sin ninguna traza GTFS de su línea : {len(missing)}")
    if missing:
        print(f"   {', '.join(r[0] for r in missing[:12])}")

    print("\nCobertura del recorrido actual por la mejor traza GTFS:")
    for threshold in (0.95, 0.90, 0.80, 0.60):
        k = sum(1 for _, _, c, _ in matched if c >= threshold)
        print(f"   >= {threshold:.0%} de los vértices : {k:4d} recorridos "
              f"({100 * k / len(results):5.1f}%)")
    print(f"\n   mediana de cobertura: {statistics.median([c for _, _, c, _ in matched]):.1%}")

    print("\nRecorridos que más cambiaron desde 2019:")
    for key, _, coverage, _ in matched[:10]:
        print(f"   {key:14s} {coverage:6.1%}")

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["l_r_s", "linea", "coverage", "gtfs_shape_id"])
        for key, n, coverage, shape_id in results:
            writer.writerow([key, n, "" if coverage is None else f"{coverage:.4f}",
                             shape_id or ""])
    print(f"\nEscrito {OUTPUT_CSV.relative_to(common.ROOT)} "
          f"({len(results)} filas) para filtrar por confianza.")


if __name__ == "__main__":
    main()
