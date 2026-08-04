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

from shapely.geometry import LineString, mapping, shape
from shapely.ops import linemerge

import common

GTFS = common.ROOT / "data" / "gtfs_frequency"
STREETS = common.ROOT / "data" / "streets.geojson"
BARRIOS = common.ROOT / "data" / "barrios.geojson"
BLOCKS_CSV = common.ROOT / "output" / "blocks_lines.csv"
ACCESS_CSV = common.ROOT / "output" / "blocks_access.csv"
WEB_DATA = common.ROOT / "web" / "data"

# Decimales de latitud/longitud que se conservan. 5 decimales son ~1 m, de
# sobra para un mapa, y recortan el archivo a la mitad.
PRECISION = 5

# Tolerancia de simplificación de los recorridos, en grados (~10 m). Las trazas
# del GTFS traen un punto cada 55 m; en una ciudad en damero, casi todos los
# puntos de una recta son redundantes.
SIMPLIFY_DEG = 0.0001

# Sufijos de los momentos de referencia. El de por defecto va sin sufijo.
MOMENT_SUFFIXES = [spec["suffix"] for spec in common.MOMENTS.values()]

# El ruido de tránsito y qué cuadras tienen domicilios salen de la misma tabla
# que usa el índice. Se importan de allá para que no haya dos verdades.
from importlib import import_module

_ideal = import_module("10_ideal_blocks")
traffic_noise = _ideal.traffic_noise
NO_ADDRESSES = _ideal.NO_ADDRESSES

# El padrón de líneas se comparte con el Paso A, para que la página no muestre
# un conjunto de líneas distinto del que se analizó.
_attribute = import_module("07_attribute_lines")


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


def house_range(props):
    """Rango de altura catastral de la cuadra, p. ej. '1200–1299'.

    El callejero trae cuatro números: principio y fin de cada vereda (la de
    altura par y la de impar). El rango de la cuadra es el mínimo y el máximo
    de los cuatro. 3.468 de las 31.961 cuadras no tienen numeración: para ésas
    devuelve cadena vacía.
    """
    values = [
        props[key] for key in
        ("alt_izqini", "alt_izqfin", "alt_derini", "alt_derfin")
        if props.get(key)
    ]
    if not values:
        return ""
    low, high = int(min(values)), int(max(values))
    return str(low) if low == high else f"{low}–{high}"


def build_blocks():
    """Cuadras del callejero con el resultado de los pasos A y B.

    Cada cuadra lleva cuatro métricas, dos por dos: lo que pasa *por encima*
    (el ruido) contra lo que se alcanza *a pie* (el acceso), y cada una medida
    en cantidad de líneas o en colectivos por hora. Las dos unidades no ordenan
    igual —una línea cada 4 minutos no es lo mismo que una cada 40— así que la
    página deja elegir.
    """
    attribution = {}
    with BLOCKS_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            attribution[int(row["block_id"])] = row

    access = {}
    if ACCESS_CSV.exists():
        with ACCESS_CSV.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                access[int(row["block_id"])] = row

    features = []
    for feature in json.loads(STREETS.read_text(encoding="utf-8"))["features"]:
        props = feature["properties"]
        row = attribution.get(props["id"])
        if row is None:
            continue
        walk = access.get(props["id"], {})
        features.append({
            "type": "Feature",
            "geometry": round_coords(feature["geometry"]),
            "properties": {
                # Pasan por la cuadra. La cantidad de líneas no depende de la
                # hora; los colectivos por hora sí, así que van los tres
                # momentos, con sufijo salvo el de referencia.
                "n": int(row["n_lines"]),
                **{f"bh{s}": round(float(row[f"buses_hour{s}"]))
                   for s in MOMENT_SUFFIXES},
                # Se toman a pie, a 400 m por la red de calles.
                "nw": int(walk.get("n_lines_walk", 0)),
                **{f"bw{s}": round(float(walk.get(f"buses_hour_walk{s}", 0) or 0))
                   for s in MOMENT_SUFFIXES},
                # Identificación.
                "s": props["nom_mapa"] or props["nomoficial"],
                "a": house_range(props),
                "b": props["barrio"] or "",
                "t": props["tipo_c"],
                "l": row["lines"],
                # Para el índice de cuadra ideal: si la cuadra tiene
                # domicilios, y cuánto ruido de tránsito tiene por su tipo de
                # vía (proxy: velocidad máxima legal).
                "r": props["tipo_c"] not in NO_ADDRESSES,
                "tf": round(traffic_noise(props["tipo_c"], props["nomoficial"]), 3),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def build_routes():
    """Un feature por línea, con todos sus recorridos unidos y simplificados."""
    roster = _attribute.caba_line_roster()

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

    # Las líneas que el GTFS 2019 no tiene no pueden salir de sus trazas. Para
    # ésas se dibuja el recorrido que reconstruyó 12_reconstruct_routes.py,
    # uniendo las cuadras que se les atribuyeron. Es menos suave que una traza
    # GTFS —son segmentos de callejero pegados— pero es el recorrido real.
    from_blocks = collections.defaultdict(list)
    if BLOCKS_CSV.exists():
        attributed = collections.defaultdict(set)
        with BLOCKS_CSV.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                for code in row["lines"].split():
                    attributed[int(code)].add(int(row["block_id"]))

        missing = {n for n in attributed if n not in by_line}
        if missing:
            geometry_by_block = {
                f["properties"]["id"]: f["geometry"]["coordinates"]
                for f in json.loads(STREETS.read_text(encoding="utf-8"))["features"]
            }
            for number in missing:
                for block_id in attributed[number]:
                    coords = geometry_by_block.get(block_id)
                    if coords and len(coords) > 1:
                        from_blocks[number].append(LineString(coords))

    features = []
    for number in sorted(set(by_line) | set(from_blocks)):
        pieces = by_line.get(number) or from_blocks[number]
        merged = linemerge(pieces)
        features.append({
            "type": "Feature",
            "geometry": round_coords(mapping(merged)),
            "properties": {
                "linea": f"{number:03d}",
                "n": number,
                # De dónde salió la geometría, para poder avisarlo en la página.
                "src": "gtfs" if number in by_line else "paradas",
            },
        })
    return {"type": "FeatureCollection", "features": features}


BARRIO_KEYS = (["n", "nw", "tf"]
               + [f"bh{s}" for s in MOMENT_SUFFIXES]
               + [f"bw{s}" for s in MOMENT_SUFFIXES])


def build_barrios(blocks):
    """Los 48 barrios con el promedio de sus cuadras.

    Es la vista que comunica: 48 polígonos se leen de un vistazo y 31.961
    cuadras no. Sirve para la pregunta "¿qué barrios están mejor y peor
    conectados?", que a nivel cuadra se pierde en el detalle.

    El promedio se toma sólo sobre las cuadras con domicilios: incluir
    autopistas y senderos de parque correría la media de los barrios que tienen
    mucho de eso, sin que eso diga nada sobre vivir ahí.
    """
    if not BARRIOS.exists():
        return None

    totals = collections.defaultdict(lambda: collections.Counter())
    counts = collections.Counter()
    for feature in blocks["features"]:
        props = feature["properties"]
        if not props["b"] or not props["r"]:
            continue
        counts[props["b"]] += 1
        for key in BARRIO_KEYS:
            totals[props["b"]][key] += props[key]

    features = []
    for feature in json.loads(BARRIOS.read_text(encoding="utf-8"))["features"]:
        name = feature["properties"]["nombre"]
        blocks_here = counts.get(name, 0)
        if not blocks_here:
            continue
        mean = {k: totals[name][k] / blocks_here for k in BARRIO_KEYS}
        centre = shape(feature["geometry"]).representative_point()
        features.append({
            "type": "Feature",
            "geometry": round_coords(feature["geometry"]),
            "properties": {
                "s": name,
                "b": name,
                "cuadras": blocks_here,
                # Punto adentro del polígono, para que la lista pueda volar
                # hasta el barrio. No es el centroide: en barrios con forma de
                # ele el centroide puede caer afuera.
                "c": [round(centre.x, 5), round(centre.y, 5)],
                "r": True,
                "n": round(mean["n"], 2),
                "nw": round(mean["nw"], 2),
                "tf": round(mean["tf"], 3),
                **{f"bh{s}": round(mean[f"bh{s}"], 1) for s in MOMENT_SUFFIXES},
                **{f"bw{s}": round(mean[f"bw{s}"], 1) for s in MOMENT_SUFFIXES},
            },
        })
    return {"type": "FeatureCollection", "features": features}


def quantile_breaks(values, classes=4):
    """Cortes que parten `values` en `classes` grupos de tamaño parecido.

    Los promedios por barrio viven en un rango mucho más chico que los valores
    por cuadra —2,4 líneas contra 29—, así que la escala de cuadras dejaría a
    los 48 barrios apretados en la clase más baja. Cada capa necesita la suya.
    """
    ordered = sorted(values)
    return [round(ordered[int(len(ordered) * i / classes)], 2)
            for i in range(1, classes)]


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
         "cuadras": blocks_per_line.get(f["properties"]["linea"], 0),
         "src": f["properties"]["src"]}
        for f in routes["features"]
    ]
    barrios = build_barrios(blocks)
    if barrios is not None:
        path = WEB_DATA / "barrios.geojson"
        path.write_text(json.dumps(barrios, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
        print(f"barrios.geojson {len(barrios['features']):6d} barrios   "
              f"{path.stat().st_size / 1e6:6.1f} MB")

    # Las constantes del índice viajan con los datos: la página las lee de acá
    # en vez de tenerlas escritas a mano, así no pueden desincronizarse.
    norm_source = common.ROOT / "output" / "index_norm.json"
    if norm_source.exists():
        norm = json.loads(norm_source.read_text(encoding="utf-8"))
        if barrios is not None:
            # Cortes propios para la capa de barrios, en cuartiles.
            norm["barrio_breaks"] = {
                key: quantile_breaks([f["properties"][key] for f in barrios["features"]])
                for key in ["n", "nw"] + [f"bh{s}" for s in MOMENT_SUFFIXES]
                                       + [f"bw{s}" for s in MOMENT_SUFFIXES]
            }
        (WEB_DATA / "norm.json").write_text(json.dumps(norm, indent=2), encoding="utf-8")
        print("norm.json         constantes del índice y cortes por barrio")

    path = WEB_DATA / "lines.json"
    path.write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
    print(f"lines.json      {len(lines):6d} líneas    "
          f"{path.stat().st_size / 1e3:6.1f} KB")

    total = sum(f["properties"]["n"] > 0 for f in blocks["features"])
    print(f"\nCuadras con al menos una línea: {total} de {len(blocks['features'])}")


if __name__ == "__main__":
    main()
