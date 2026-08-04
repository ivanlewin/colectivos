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

Sólo se consideran las líneas que sirven a la Ciudad —ver caba_line_roster()—,
así que quedan afuera las 130 y pico de líneas suburbanas que el GTFS trae y
que nunca entran a CABA.

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

# Distancia máxima de una parada vigente a la cuadra a la que se la asigna.
# Una parada está sobre la vereda, así que media calzada de margen alcanza.
STOP_SNAP_M = 30

# Debajo de esta cobertura de sus propias paradas, se considera que el GTFS
# 2019 ya no describe bien a esa línea y se le incorpora el recorrido
# reconstruido. Por encima, el GTFS es mejor fuente y se lo deja solo.
GTFS_COVERAGE_THRESHOLD = 0.7

STOP_ROUTES_CSV = common.ROOT / "output" / "stop_routes.csv"


def caba_line_roster():
    """Números de línea que sirven a la Ciudad.

    Se toma la unión de dos padrones porque ninguno es completo por sí solo.

    Durante un tiempo se usó sólo el de EPOK, y eso escondía un error: EPOK no
    lista las líneas 5, 6, 99, 112 y 175, así que el filtro las descartaba del
    GTFS **aunque el GTFS sí las tiene**. Cinco líneas con traza propia
    quedaban afuera del mapa por un padrón incompleto.

    Las paradas vigentes traen 137 líneas y son la fuente más actual, pero se
    unen con las de EPOK igual: es gratis y protege del caso simétrico.
    """
    from_epok = {int(p["linea"]) for p in common.properties()}
    from_stops = {line for *_rest, services in common.current_stops()
                  for line, _direction in services}
    return from_epok | from_stops


def shape_service(roster):
    """Servicio por traza: {shape_id: (número de línea, colectivos por hora)}.

    La atribución se hace por traza y no por línea porque los ramales de una
    misma línea no pasan por las mismas cuadras: sumar la frecuencia de toda la
    línea a cualquier cuadra que toque uno de sus ramales inflaría el número.

    Varios trips pueden compartir traza (típicamente ida y vuelta tienen la
    suya, pero no siempre), así que la frecuencia se acumula.
    """
    route_line = {
        row["route_id"]: common.line_number(row["route_short_name"])
        for row in common.gtfs_rows("routes.txt")
        if common.line_number(row["route_short_name"]) in roster
    }

    per_trip = {m: common.buses_per_hour_by_trip(m) for m in common.MOMENTS}

    service = {}
    for row in common.gtfs_rows("trips.txt"):
        number = route_line.get(row["route_id"])
        shape_id = row.get("shape_id")
        if number is None or not shape_id:
            continue
        line, buses = service.get(shape_id, (number, collections.Counter()))
        for moment, table in per_trip.items():
            buses[moment] += table.get(row["trip_id"], 0.0)
        service[shape_id] = (line, buses)
    return service


def load_shape_segments(project, service):
    """Segmentos de las trazas GTFS, proyectados a metros.

    Devuelve (lista de LineString, array de rumbos, array de índice de traza) y
    la lista de shape_id en ese mismo orden.
    """
    points = collections.defaultdict(list)
    for row in common.gtfs_rows("shapes.txt"):
        if row["shape_id"] in service:
            points[row["shape_id"]].append((
                int(row["shape_pt_sequence"]),
                float(row["shape_pt_lon"]),
                float(row["shape_pt_lat"]),
            ))

    shape_ids = sorted(points)
    index_of = {shape_id: i for i, shape_id in enumerate(shape_ids)}

    geoms, bearings, lines = [], [], []
    for shape_id in shape_ids:
        pts = points[shape_id]
        pts.sort()
        xs, ys = project([p[1] for p in pts], [p[2] for p in pts])
        n = index_of[shape_id]
        for i in range(len(xs) - 1):
            dx, dy = xs[i + 1] - xs[i], ys[i + 1] - ys[i]
            if dx == 0 and dy == 0:
                continue
            geoms.append(LineString([(xs[i], ys[i]), (xs[i + 1], ys[i + 1])]))
            bearings.append(math.degrees(math.atan2(dx, dy)) % 180)
            lines.append(n)
    return geoms, np.array(bearings), np.array(lines), shape_ids


def stops_to_blocks(block_geometries, block_ids, block_names, to_metric):
    """{id de cuadra: {líneas con parada ahí}} según las paradas vigentes.

    Corrige el punto ciego del método geométrico: éste sólo puede encontrar
    líneas que existan en el GTFS de 2019. Las que se crearon o cambiaron
    después son invisibles por más fino que se afine el matcheo.

    Una parada es evidencia directa e independiente: si hay una parada de la
    145 en Jufré 210, la 145 pasa por esa cuadra. Sólo alcanza a las cuadras
    *con* parada —entre parada y parada el recorrido sigue sin conocerse— así
    que es un piso, no una solución completa.
    """
    from shapely import STRtree
    from shapely.geometry import Point

    tree = STRtree(block_geometries)
    by_block = collections.defaultdict(set)
    for lon, lat, street, _number, services in common.current_stops():
        x, y = to_metric.transform(lon, lat)
        index = common.snap_stop(Point(x, y), tree, block_geometries,
                                 block_names, street, STOP_SNAP_M)
        if index is None:
            continue
        by_block[block_ids[index]].update(line for line, _sentido in services)
    return by_block


def merge_current_data(rows, stops_by_block):
    """Corrige el resultado geométrico con las fuentes vigentes de 2026.

    Dos correcciones, con distinto nivel de confianza:

    1. **Las paradas.** Si hay una parada de la línea X sobre la cuadra, X pasa
       por la cuadra. Es evidencia directa y se aplica siempre.

    2. **El recorrido reconstruido** entre paradas (12_reconstruct_routes.py).
       Es una inferencia, no un dato, y medida contra las líneas que el GTFS sí
       cubre bien da ~84 % de precisión. Por eso se aplica **sólo a las líneas
       que el GTFS 2019 no describe bien**: donde el GTFS anda, es mejor
       fuente, y agregarle la reconstrucción sólo puede meter ruido.

    El criterio de "no describe bien" es la cobertura de sus propias paradas:
    qué fracción de las cuadras donde la línea para ya la tenía el método
    geométrico.
    """
    by_block = {row["block_id"]: row for row in rows}

    # --- cobertura del GTFS por línea, medida en sus paradas ---
    covered = collections.Counter()
    total = collections.Counter()
    for block_id, lines in stops_by_block.items():
        row = by_block.get(block_id)
        if row is None:
            continue
        for line in lines:
            total[line] += 1
            if line in row["_gtfs"]:
                covered[line] += 1

    stale = {line for line in total
             if covered[line] / total[line] < GTFS_COVERAGE_THRESHOLD}

    # --- aplicar ---
    reconstructed = collections.defaultdict(set)
    if STOP_ROUTES_CSV.exists():
        with STOP_ROUTES_CSV.open(encoding="utf-8") as fh:
            for entry in csv.DictReader(fh):
                block_id = int(entry["block_id"])
                for code in entry["lines"].split():
                    line = int(code)
                    if line in stale:
                        reconstructed[block_id].add(line)

    for row in rows:
        block_id = row["block_id"]
        final = (set(row["_gtfs"])
                 | stops_by_block.get(block_id, set())
                 | reconstructed.get(block_id, set()))
        row["lines_gtfs"] = " ".join(f"{n:03d}" for n in sorted(row.pop("_gtfs")))
        row["lines"] = " ".join(f"{n:03d}" for n in sorted(final))
        row["n_lines"] = len(final)

    return stale, total, covered


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

    roster = caba_line_roster()
    common.heading("Atribución de líneas a cuadras")
    print(f"Padrón de líneas de CABA   : {len(roster)} líneas")

    service = shape_service(roster)
    geoms, bearings, seg_shapes, shape_ids = load_shape_segments(project, service)
    print(f"Trazas (ramales)           : {len(shape_ids)}")
    print(f"Segmentos de traza GTFS    : {len(geoms)}")
    print(f"Líneas con traza           : {len({v[0] for v in service.values()})}")
    for moment, spec in common.MOMENTS.items():
        total = sum(v[1][moment] for v in service.values())
        print(f"Colectivos/hora en la red  : {total:7.0f}   {spec['label']}")

    tree = STRtree(geoms)

    blocks = json.loads(STREETS.read_text(encoding="utf-8"))["features"]
    print(f"Cuadras del callejero      : {len(blocks)}")

    # Geometrías de las cuadras, para enganchar las paradas vigentes.
    block_geometries, block_ids, block_names = [], [], []
    for feature in blocks:
        coords = feature["geometry"]["coordinates"]
        xs, ys = project([c[0] for c in coords], [c[1] for c in coords])
        block_geometries.append(LineString(list(zip(xs, ys))))
        block_ids.append(feature["properties"]["id"])
        block_names.append(feature["properties"]["nomoficial"])

    stops_by_block = stops_to_blocks(block_geometries, block_ids,
                                     block_names, to_metric)
    stop_lines = {line for lines in stops_by_block.values() for line in lines}
    print(f"Cuadras con parada vigente : {len(stops_by_block)} "
          f"({len(stop_lines)} líneas distintas)")

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

        matched_shapes = []
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
                per_shape = collections.defaultdict(set)
                for sample_idx, shape in zip(pairs[0][aligned], seg_shapes[pairs[1][aligned]]):
                    per_shape[int(shape)].add(int(sample_idx))
                matched_shapes = [
                    shape_ids[shape] for shape, hit in per_shape.items()
                    if len(hit) / len(samples) >= MIN_SAMPLE_RATIO
                ]

        # Las líneas se cuentan una vez aunque pasen varios ramales; los
        # colectivos por hora se suman, porque cada ramal son buses distintos.
        lines_here = {service[s][0] for s in matched_shapes}
        buses_here = collections.Counter()
        for shape_id in matched_shapes:
            buses_here.update(service[shape_id][1])

        rows.append({
            "block_id": props["id"],
            "street": props["nomoficial"],
            "barrio": props["barrio"],
            "tipo_c": props["tipo_c"],
            "red_jerarq": props["red_jerarq"],
            "length_m": round(props["long"], 1),
            "n_shapes": len(matched_shapes),
            **{f"buses_hour{spec['suffix']}": round(buses_here[moment], 1)
               for moment, spec in common.MOMENTS.items()},
            # Sólo lo que encontró el método geométrico sobre el GTFS 2019.
            # Las correcciones con datos vigentes se aplican después, en
            # merge_current_data(), para poder medir una contra la otra.
            "_gtfs": lines_here,
        })

    common.heading("Corrección con las fuentes vigentes de 2026")
    stale, stop_total, stop_covered = merge_current_data(rows, stops_by_block)
    print(f"Líneas con menos del {GTFS_COVERAGE_THRESHOLD:.0%} de sus paradas "
          f"cubiertas por el GTFS 2019: {len(stale)} de {len(stop_total)}")
    print("A ésas se les incorpora el recorrido reconstruido; al resto no.\n")
    for line in sorted(stale, key=lambda n: stop_covered[n] / stop_total[n]):
        share = stop_covered[line] / stop_total[line]
        print(f"   línea {line:3d}: el GTFS cubre {share:4.0%} de sus "
              f"{stop_total[line]:3d} paradas")
    if not STOP_ROUTES_CSV.exists():
        print("\n   (falta output/stop_routes.csv — corré 12_reconstruct_routes.py)")

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

    buses = [r["buses_hour"] for r in rows if r["buses_hour"] > 0]  # momento por defecto
    buses.sort()
    print(f"\nColectivos por hora ({common.MOMENTS[common.DEFAULT_MOMENT]['label']}), en las cuadras que tienen:")
    print(f"   mediana : {buses[len(buses) // 2]:.1f}")
    print(f"   p90     : {buses[int(len(buses) * 0.9)]:.1f}")
    print(f"   máximo  : {buses[-1]:.1f}")

    print("\nControl de calidad — promedio por jerarquía de vía:")
    print(f"   {'':36s} {'líneas':>7s} {'col/hora':>9s}")
    by_type = collections.defaultdict(list)
    for r in rows:
        by_type[r["red_jerarq"]].append((r["n_lines"], r["buses_hour"]))
    for key in sorted(by_type, key=lambda k: -np.mean([v[0] for v in by_type[k]])):
        values = by_type[key]
        print(f"   {str(key):36s} {np.mean([v[0] for v in values]):7.2f} "
              f"{np.mean([v[1] for v in values]):9.2f}  ({len(values)} cuadras)")
    print("Las troncales tienen que estar arriba y las vías locales abajo.")

    print("\nLas 10 cuadras con más líneas:")
    for r in sorted(rows, key=lambda r: -r["n_lines"])[:10]:
        print(f"   {r['n_lines']:2d} líneas · {r['buses_hour']:5.1f} col/h  "
              f"{r['street']:28s} {r['barrio']}")

    print("\nLas 10 cuadras con más colectivos por hora:")
    for r in sorted(rows, key=lambda r: -r["buses_hour"])[:10]:
        print(f"   {r['n_lines']:2d} líneas · {r['buses_hour']:5.1f} col/h  "
              f"{r['street']:28s} {r['barrio']}")

    print(f"\nEscrito {OUTPUT_CSV.relative_to(common.ROOT)}")


if __name__ == "__main__":
    main()
