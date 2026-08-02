"""Paso D (datos) — Preparar los archivos que consume la página web.

Genera tres archivos en web/data/:

  blocks.geojson  las 31.961 cuadras con cuántas y cuáles líneas pasan
  routes.geojson  una MultiLineString por línea, con su recorrido
  lines.json      el listado de líneas para el desplegable

Todo se recorta en precisión y se simplifica, porque la página los carga
enteros desde el navegador y el tamaño importa.

Requiere haber corrido antes scripts/07_attribute_lines.py.
Uso: python3 scripts/08_build_web_data.py
"""

import collections
import csv
import json
import re

from shapely.geometry import LineString, mapping
from shapely.ops import linemerge

import common

GTFS = common.ROOT / "data" / "gtfs_frequency"
STREETS = common.ROOT / "data" / "streets.geojson"
BLOCKS_CSV = common.ROOT / "output" / "blocks_lines.csv"
WEB_DATA = common.ROOT / "web" / "data"

# Decimales de latitud/longitud que se conservan. 5 decimales son ~1 m, de
# sobra para un mapa, y recortan el archivo a la mitad.
PRECISION = 5

# Tolerancia de simplificación de los recorridos, en grados (~10 m). Las trazas
# del GTFS traen un punto cada 55 m; en una ciudad en damero, casi todos los
# puntos de una recta son redundantes.
SIMPLIFY_DEG = 0.0001


def round_coords(geometry):
    """Recorta la precisión de las coordenadas de un dict GeoJSON."""
    def walk(node):
        if isinstance(node, (int, float)):
            return round(node, PRECISION)
        return [walk(x) for x in node]

    return {"type": geometry["type"], "coordinates": walk(geometry["coordinates"])}


def line_number(short_name):
    match = re.match(r"(\d+)", short_name or "")
    return int(match.group(1)) if match else None


def build_blocks():
    """Cuadras del callejero con el resultado de la atribución."""
    attribution = {}
    with BLOCKS_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            attribution[int(row["block_id"])] = row

    features = []
    for feature in json.loads(STREETS.read_text(encoding="utf-8"))["features"]:
        props = feature["properties"]
        row = attribution.get(props["id"])
        if row is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": round_coords(feature["geometry"]),
            "properties": {
                "n": int(row["n_lines"]),
                "s": props["nom_mapa"] or props["nomoficial"],
                "b": props["barrio"] or "",
                "t": props["tipo_c"],
                "l": row["lines"],
            },
        })
    return {"type": "FeatureCollection", "features": features}


def build_routes():
    """Un feature por línea, con todos sus recorridos unidos y simplificados."""
    roster = {int(p["linea"]) for p in common.properties()}

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

    by_line = collections.defaultdict(list)
    for shape_id, pts in points.items():
        pts.sort()
        coords = [(lon, lat) for _, lon, lat in pts]
        if len(coords) > 1:
            by_line[shape_line[shape_id]].append(
                LineString(coords).simplify(SIMPLIFY_DEG)
            )

    features = []
    for number in sorted(by_line):
        merged = linemerge(by_line[number])
        features.append({
            "type": "Feature",
            "geometry": round_coords(mapping(merged)),
            "properties": {"linea": f"{number:03d}", "n": number},
        })
    return {"type": "FeatureCollection", "features": features}


def main():
    if not BLOCKS_CSV.exists():
        raise SystemExit(
            f"Falta {BLOCKS_CSV}. Corré antes: python3 scripts/07_attribute_lines.py"
        )
    WEB_DATA.mkdir(parents=True, exist_ok=True)

    common.heading("Generando los datos de la página")

    blocks = build_blocks()
    path = WEB_DATA / "blocks.geojson"
    path.write_text(json.dumps(blocks, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    print(f"blocks.geojson  {len(blocks['features']):6d} cuadras   "
          f"{path.stat().st_size / 1e6:6.1f} MB")

    routes = build_routes()
    path = WEB_DATA / "routes.geojson"
    path.write_text(json.dumps(routes, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    print(f"routes.geojson  {len(routes['features']):6d} líneas    "
          f"{path.stat().st_size / 1e6:6.1f} MB")

    # Cuántas cuadras recorre cada línea dentro de la Ciudad: sirve para
    # ordenar el desplegable y para mostrar algo de contexto al elegirla.
    blocks_per_line = collections.Counter()
    for feature in blocks["features"]:
        for code in feature["properties"]["l"].split():
            blocks_per_line[code] += 1

    lines = [
        {"linea": f["properties"]["linea"],
         "cuadras": blocks_per_line.get(f["properties"]["linea"], 0)}
        for f in routes["features"]
    ]
    path = WEB_DATA / "lines.json"
    path.write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
    print(f"lines.json      {len(lines):6d} líneas    "
          f"{path.stat().st_size / 1e3:6.1f} KB")

    total = sum(f["properties"]["n"] > 0 for f in blocks["features"])
    print(f"\nCuadras con al menos una línea: {total} de {len(blocks['features'])}")


if __name__ == "__main__":
    main()
