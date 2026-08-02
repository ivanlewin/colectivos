"""Paso A — ¿Qué líneas de colectivo pasan por cada cuadra?

Cruza las trazas del GTFS con el callejero de CABA para responder, cuadra por
cuadra, qué líneas circulan por ella.

El método no es un buffer a secas. Si uno se limita a preguntar "¿hay una traza
a menos de 12 m?", cada esquina contamina la calle transversal: la traza que
dobla pasa cerca de la punta de la cuadra de al lado. Por eso se hacen tres
cosas:

  1. Se muestrea la cuadra cada 10 m en vez de mirarla como un todo.
  2. Se descartan los extremos (INTERSECTION_SKIP_M), que es donde ocurre la
     contaminación de las esquinas.
  3. Se exige que la traza sea **paralela** a la cuadra (BEARING_TOLERANCE_DEG),
     lo que elimina las transversales que sí cruzan.

Una línea se atribuye a la cuadra si cumple todo eso en al menos
MIN_SAMPLE_RATIO de las muestras, es decir si la acompaña a lo largo y no la
roza en un punto.

Sólo se consideran las líneas del padrón vigente de EPOK, así que quedan afuera
las líneas suburbanas del GTFS que ya no entran a la Ciudad.

Escribe output/blocks_lines.csv con una fila por cuadra.

Requiere: bash scripts/00_download.sh all
Uso: python3 scripts/07_attribute_lines.py
"""

import collections
import csv
import json
import math
import re

import numpy as np
from shapely import STRtree
from shapely.geometry import LineString

import common

GTFS = common.ROOT / "data" / "gtfs_frequency"
STREETS = common.ROOT / "data" / "streets.geojson"
OUTPUT_CSV = common.ROOT / "output" / "blocks_lines.csv"

# Distancia máxima entre la muestra de la cuadra y la traza del colectivo.
# Tiene que tolerar el ancho de una avenida (la traza va por el centro de la
# calzada, el eje del callejero por el centro geométrico) sin llegar a la
# calle paralela, que está a ~110 m.
MATCH_DISTANCE_M = 15

# Diferencia máxima de rumbo entre la cuadra y la traza, módulo 180 grados.
# Es el filtro que descarta las calles transversales en las esquinas.
BEARING_TOLERANCE_DEG = 30

# Cada cuántos metros se muestrea la cuadra.
SAMPLE_STEP_M = 10

# Cuánto se ignora en cada punta de la cuadra: es la zona de la esquina, donde
# las trazas que doblan pasan cerca sin circular por esta cuadra.
INTERSECTION_SKIP_M = 15

# Fracción mínima de muestras que tienen que dar positivo para atribuir la
# línea. Con 0.6 se tolera que un tramo de la traza esté mal digitalizado, pero
# no que apenas roce la cuadra.
MIN_SAMPLE_RATIO = 0.6


def line_number(short_name):
    """'065A' -> 65. Devuelve None si no empieza con dígitos."""
    match = re.match(r"(\d+)", short_name or "")
    return int(match.group(1)) if match else None


def epok_line_roster():
    """Números de línea del padrón vigente de EPOK."""
    return {int(p["linea"]) for p in common.properties()}


def load_shape_segments(project, roster):
    """Segmentos de las trazas GTFS, proyectados a metros.

    Devuelve (lista de LineString, array de rumbos, array de número de línea).
    """
    route_line = {}
    with (GTFS / "routes.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            n = line_number(row["route_short_name"])
            if n in roster:
                route_line[row["route_id"]] = n

    shape_line = {}
    with (GTFS / "trips.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            n = route_line.get(row["route_id"])
            if n is not None and row.get("shape_id"):
                shape_line[row["shape_id"]] = n

    points = collections.defaultdict(list)
    with (GTFS / "shapes.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["shape_id"] in shape_line:
                points[row["shape_id"]].append((
                    int(row["shape_pt_sequence"]),
                    float(row["shape_pt_lon"]),
                    float(row["shape_pt_lat"]),
                ))

    geoms, bearings, lines = [], [], []
    for shape_id, pts in points.items():
        pts.sort()
        xs, ys = project([p[1] for p in pts], [p[2] for p in pts])
        n = shape_line[shape_id]
        for i in range(len(xs) - 1):
            dx, dy = xs[i + 1] - xs[i], ys[i + 1] - ys[i]
            if dx == 0 and dy == 0:
                continue
            geoms.append(LineString([(xs[i], ys[i]), (xs[i + 1], ys[i + 1])]))
            bearings.append(math.degrees(math.atan2(dx, dy)) % 180)
            lines.append(n)
    return geoms, np.array(bearings), np.array(lines)


def sample_block(coords):
    """Muestrea una cuadra ya proyectada: devuelve [(x, y, rumbo), ...].

    Ignora INTERSECTION_SKIP_M en cada punta. Si la cuadra es tan corta que no
    queda nada, usa el punto medio, para no perderla.
    """
    spans = []
    total = 0.0
    for i in range(len(coords) - 1):
        (x1, y1), (x2, y2) = coords[i], coords[i + 1]
        length = math.hypot(x2 - x1, y2 - y1)
        if length:
            bearing = math.degrees(math.atan2(x2 - x1, y2 - y1)) % 180
            spans.append((total, length, x1, y1, x2, y2, bearing))
            total += length

    if total == 0:
        return []

    start, end = INTERSECTION_SKIP_M, total - INTERSECTION_SKIP_M
    if end <= start:  # cuadra muy corta: usar sólo el centro
        start = end = total / 2

    samples = []
    distance = start
    while distance <= end:
        for offset, length, x1, y1, x2, y2, bearing in spans:
            if offset <= distance <= offset + length:
                t = (distance - offset) / length
                samples.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, bearing))
                break
        distance += SAMPLE_STEP_M
    return samples


def main():
    for path in (GTFS, STREETS):
        if not path.exists():
            raise SystemExit(f"Falta {path}. Corré: bash scripts/00_download.sh all")

    from pyproj import Transformer

    to_metric = Transformer.from_crs("EPSG:4326", common.CABA_CRS, always_xy=True)
    project = lambda lons, lats: to_metric.transform(lons, lats)

    roster = epok_line_roster()
    common.heading("Atribución de líneas a cuadras")
    print(f"Padrón EPOK vigente        : {len(roster)} líneas")

    geoms, bearings, seg_lines = load_shape_segments(project, roster)
    print(f"Segmentos de traza GTFS    : {len(geoms)}")
    print(f"Líneas con traza            : {len(set(seg_lines.tolist()))}")

    tree = STRtree(geoms)

    blocks = json.loads(STREETS.read_text(encoding="utf-8"))["features"]
    print(f"Cuadras del callejero      : {len(blocks)}")
    print(f"\nParámetros: {MATCH_DISTANCE_M} m de distancia, "
          f"{BEARING_TOLERANCE_DEG}° de rumbo, muestreo cada {SAMPLE_STEP_M} m,")
    print(f"ignorando {INTERSECTION_SKIP_M} m en cada esquina, "
          f"mínimo {MIN_SAMPLE_RATIO:.0%} de muestras.\n")

    rows = []
    for index, feature in enumerate(blocks):
        if index and index % 5000 == 0:
            print(f"   {index}/{len(blocks)} cuadras procesadas")

        props = feature["properties"]
        lonlat = feature["geometry"]["coordinates"]
        xs, ys = project([p[0] for p in lonlat], [p[1] for p in lonlat])
        samples = sample_block(list(zip(xs, ys)))

        hits = collections.Counter()
        if samples:
            pts_x = np.array([s[0] for s in samples])
            pts_y = np.array([s[1] for s in samples])
            sample_bearings = np.array([s[2] for s in samples])

            from shapely import points as make_points

            probes = make_points(pts_x, pts_y)
            pairs = tree.query(probes, predicate="dwithin", distance=MATCH_DISTANCE_M)

            # pairs[0] = índice de la muestra, pairs[1] = índice del segmento
            if pairs.size:
                delta = np.abs(sample_bearings[pairs[0]] - bearings[pairs[1]])
                aligned = np.minimum(delta, 180 - delta) <= BEARING_TOLERANCE_DEG
                per_line = collections.defaultdict(set)
                for sample_idx, line in zip(pairs[0][aligned], seg_lines[pairs[1][aligned]]):
                    per_line[int(line)].add(int(sample_idx))
                for line, matched in per_line.items():
                    if len(matched) / len(samples) >= MIN_SAMPLE_RATIO:
                        hits[line] = len(matched)

        found = sorted(hits)
        rows.append({
            "block_id": props["id"],
            "street": props["nomoficial"],
            "barrio": props["barrio"],
            "tipo_c": props["tipo_c"],
            "red_jerarq": props["red_jerarq"],
            "length_m": round(props["long"], 1),
            "n_lines": len(found),
            "lines": " ".join(f"{n:03d}" for n in found),
        })

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    common.heading("Resultado")
    counts = collections.Counter(r["n_lines"] for r in rows)
    sin_colectivo = counts[0]
    print(f"Cuadras sin ninguna línea  : {sin_colectivo} ({100*sin_colectivo/len(rows):.1f}%)")
    print(f"Cuadras con al menos una   : {len(rows)-sin_colectivo} "
          f"({100*(len(rows)-sin_colectivo)/len(rows):.1f}%)")
    print(f"Máximo de líneas en una cuadra: {max(counts)}")

    print("\nDistribución:")
    for n in sorted(counts)[:12]:
        print(f"   {n:2d} líneas: {counts[n]:6d} cuadras")

    print("\nControl de calidad — promedio de líneas por jerarquía de vía:")
    by_type = collections.defaultdict(list)
    for r in rows:
        by_type[r["red_jerarq"]].append(r["n_lines"])
    for key in sorted(by_type, key=lambda k: -np.mean(by_type[k])):
        values = by_type[key]
        print(f"   {str(key):36s} {np.mean(values):5.2f}  ({len(values)} cuadras)")
    print("Las troncales tienen que estar arriba y las vías locales abajo.")

    print("\nLas 10 cuadras con más líneas:")
    for r in sorted(rows, key=lambda r: -r["n_lines"])[:10]:
        print(f"   {r['n_lines']:2d}  {r['street']:28s} {r['barrio']}")

    print(f"\nEscrito {OUTPUT_CSV.relative_to(common.ROOT)}")


if __name__ == "__main__":
    main()
