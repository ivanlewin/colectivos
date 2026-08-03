"""Paso B — ¿Cuántas líneas se pueden tomar caminando desde cada cuadra?

El Paso A responde qué colectivos pasan *por* la cuadra, que es el ruido. Éste
responde lo otro: a qué colectivos se llega a pie, que es el acceso.

La distancia se mide **sobre la red de calles**, no en línea recta. Importa: en
línea recta se cuentan paradas del otro lado de las vías del Sarmiento o de la
General Paz, a las que en la práctica no se llega. Para eso se arma un grafo
peatonal con el callejero —cada cuadra es una arista, cada esquina un nodo— y
se corre un Dijkstra multi-origen desde las paradas de cada línea, cortando a
WALK_RADIUS_M.

Las autopistas y sus ramas quedan afuera del grafo: por ahí no se camina.

Escribe output/blocks_access.csv con una fila por cuadra.

Requiere: scripts/07_attribute_lines.py y bash scripts/00_download.sh all
Uso: python3 scripts/09_walking_access.py
"""

import collections
import csv
import heapq
import json
import math
import re

from shapely import STRtree
from shapely.geometry import LineString, Point

import common

GTFS = common.ROOT / "data" / "gtfs_frequency"
STREETS = common.ROOT / "data" / "streets.geojson"
BLOCKS_CSV = common.ROOT / "output" / "blocks_lines.csv"
OUTPUT_CSV = common.ROOT / "output" / "blocks_access.csv"

# Cuánto se considera "a pie". 400 m son unos 5 minutos caminando, el umbral
# habitual en planificación de transporte para acceso a una parada.
WALK_RADIUS_M = 400

# Tolerancia para dar por unidas dos puntas de cuadra. El callejero no siempre
# cierra las esquinas con coordenadas idénticas.
NODE_SNAP_M = 2

# Por acá no se camina, así que no son aristas del grafo peatonal.
NON_WALKABLE = {
    "AUTOPISTA", "SUBIDA AUTOPISTA", "BAJADA AUTOPISTA", "ENLACE AUTOPISTA",
}


def line_number(short_name):
    match = re.match(r"(\d+)", short_name or "")
    return int(match.group(1)) if match else None


def stops_by_line(roster):
    """{número de línea: {stop_id, ...}} para las líneas del padrón vigente.

    Encadena stop_times -> trips -> routes. En el feed *frequency* que usa el
    proyecto, stop_times.txt son 17 MB y entra en memoria sin problema; en el
    GTFS completo son 1,4 GB y haría falta procesarlo en streaming.
    """
    route_line = {}
    with (GTFS / "routes.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            n = line_number(row["route_short_name"])
            if n in roster:
                route_line[row["route_id"]] = n

    trip_line = {}
    with (GTFS / "trips.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            n = route_line.get(row["route_id"])
            if n is not None:
                trip_line[row["trip_id"]] = n

    by_line = collections.defaultdict(set)
    with (GTFS / "stop_times.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            n = trip_line.get(row["trip_id"])
            if n is not None:
                by_line[n].add(str(row["stop_id"]))
    return by_line


def load_stop_coords(project):
    """{stop_id: (x, y)} en metros."""
    coords = {}
    with (GTFS / "stops.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                lon, lat = float(row["stop_lon"]), float(row["stop_lat"])
            except (TypeError, ValueError):
                continue
            coords[str(row["stop_id"])] = project(lon, lat)
    return coords


class WalkGraph:
    """Grafo peatonal: nodos en las esquinas, aristas en las cuadras."""

    def __init__(self):
        self.nodes = {}                                  # clave redondeada -> id
        self.adjacency = collections.defaultdict(list)   # id -> [(vecino, metros)]
        self.blocks = []                                 # (block_id, nodo_a, nodo_b)
        self.geometries = []                             # LineString por cuadra
        self.block_ids = []

    def node_id(self, x, y):
        key = (round(x / NODE_SNAP_M), round(y / NODE_SNAP_M))
        if key not in self.nodes:
            self.nodes[key] = len(self.nodes)
        return self.nodes[key]

    def add_block(self, block_id, coords, walkable):
        length = sum(math.dist(coords[i], coords[i + 1]) for i in range(len(coords) - 1))
        if length == 0:
            return
        a = self.node_id(*coords[0])
        b = self.node_id(*coords[-1])
        self.blocks.append((block_id, a, b))
        self.geometries.append(LineString(coords))
        self.block_ids.append(block_id)
        if walkable and a != b:
            self.adjacency[a].append((b, length))
            self.adjacency[b].append((a, length))

    def dijkstra(self, sources, cutoff):
        """sources: {nodo: distancia inicial}. Devuelve {nodo: distancia}."""
        best = dict(sources)
        heap = [(d, n) for n, d in sources.items()]
        heapq.heapify(heap)
        while heap:
            distance, node = heapq.heappop(heap)
            if distance > best.get(node, math.inf):
                continue
            for neighbour, weight in self.adjacency[node]:
                nd = distance + weight
                if nd <= cutoff and nd < best.get(neighbour, math.inf):
                    best[neighbour] = nd
                    heapq.heappush(heap, (nd, neighbour))
        return best


def main():
    for path in (GTFS, STREETS, BLOCKS_CSV):
        if not path.exists():
            raise SystemExit(f"Falta {path}. Ver el encabezado de este script.")

    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:4326", common.CABA_CRS, always_xy=True)
    project = lambda lon, lat: transformer.transform(lon, lat)

    common.heading("Acceso caminando")

    roster = {int(p["linea"]) for p in common.properties()}
    by_line = stops_by_line(roster)
    print(f"Líneas del padrón con paradas : {len(by_line)}")
    print(f"Paradas distintas             : {len({s for v in by_line.values() for s in v})}")

    stop_coords = load_stop_coords(project)

    # --- grafo peatonal ---
    graph = WalkGraph()
    features = json.loads(STREETS.read_text(encoding="utf-8"))["features"]
    for feature in features:
        props = feature["properties"]
        coords = [project(lon, lat) for lon, lat in feature["geometry"]["coordinates"]]
        graph.add_block(props["id"], coords, props["tipo_c"] not in NON_WALKABLE)

    print(f"\nGrafo peatonal: {len(graph.blocks)} cuadras, {len(graph.nodes)} esquinas")
    degrees = collections.Counter(len(v) for v in graph.adjacency.values())
    print(f"   esquinas sin conexión: {len(graph.nodes) - len(graph.adjacency)}")
    print(f"   grado más común      : {degrees.most_common(3)}")

    # --- cada parada, enganchada a la cuadra más cercana ---
    tree = STRtree(graph.geometries)
    entry_points = {}          # stop_id -> [(nodo, metros hasta ese nodo)]
    unmatched = 0
    for stop_id, (x, y) in stop_coords.items():
        point = Point(x, y)
        index = tree.nearest(point)
        geometry = graph.geometries[index]
        if point.distance(geometry) > 60:   # parada lejos de toda calle de CABA
            unmatched += 1
            continue
        # Distancia caminando hasta cada punta de esa cuadra.
        along = geometry.project(point)
        _, node_a, node_b = graph.blocks[index]
        entry_points[stop_id] = [(node_a, along), (node_b, geometry.length - along)]

    print(f"\nParadas enganchadas al callejero: {len(entry_points)}")
    print(f"   descartadas por estar lejos   : {unmatched} (paradas del conurbano)")

    # --- una corrida de Dijkstra por línea ---
    lines_per_block = collections.defaultdict(set)
    stops_near = collections.Counter()
    block_index = {bid: i for i, (bid, _, _) in enumerate(graph.blocks)}

    for count, (number, stop_ids) in enumerate(sorted(by_line.items()), 1):
        sources = {}
        for stop_id in stop_ids:
            for node, distance in entry_points.get(stop_id, []):
                if distance < sources.get(node, math.inf):
                    sources[node] = distance
        if not sources:
            continue
        reached = graph.dijkstra(sources, WALK_RADIUS_M)
        for block_id, node_a, node_b in graph.blocks:
            if node_a in reached or node_b in reached:
                lines_per_block[block_id].add(number)
        if count % 25 == 0:
            print(f"   {count}/{len(by_line)} líneas procesadas")

    # Paradas a pie, sin distinguir línea: una sola corrida desde todas.
    all_sources = {}
    for stop_id in entry_points:
        for node, distance in entry_points[stop_id]:
            if distance < all_sources.get(node, math.inf):
                all_sources[node] = distance
    reached_any = graph.dijkstra(all_sources, WALK_RADIUS_M)
    for stop_id, entries in entry_points.items():
        for node, _ in entries:
            if node in reached_any:
                stops_near[node] += 1

    # --- salida ---
    attribution = {}
    with BLOCKS_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            attribution[int(row["block_id"])] = row

    rows = []
    for block_id, node_a, node_b in graph.blocks:
        walkable = sorted(lines_per_block.get(block_id, ()))
        source = attribution.get(block_id, {})
        rows.append({
            "block_id": block_id,
            "street": source.get("street", ""),
            "barrio": source.get("barrio", ""),
            "tipo_c": source.get("tipo_c", ""),
            "n_lines_on": int(source.get("n_lines", 0)),
            "lines_on": source.get("lines", ""),
            "n_lines_walk": len(walkable),
            "lines_walk": " ".join(f"{n:03d}" for n in walkable),
            "n_stops_walk": stops_near.get(node_a, 0) + stops_near.get(node_b, 0),
        })

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    # --- resumen ---
    common.heading("Resultado")
    walk_counts = [r["n_lines_walk"] for r in rows]
    walk_counts.sort()
    median = walk_counts[len(walk_counts) // 2]
    print(f"Líneas a {WALK_RADIUS_M} m caminando, por cuadra:")
    print(f"   mediana : {median}")
    print(f"   máximo  : {walk_counts[-1]}")
    print(f"   cuadras sin ninguna línea a pie: {sum(1 for c in walk_counts if c == 0)} "
          f"({100 * sum(1 for c in walk_counts if c == 0) / len(rows):.1f}%)")

    print("\nPromedio de líneas a pie por barrio — los 8 mejores y los 8 peores:")
    by_barrio = collections.defaultdict(list)
    for r in rows:
        if r["barrio"]:
            by_barrio[r["barrio"]].append(r["n_lines_walk"])
    ranked = sorted(by_barrio.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))
    for name, values in ranked[:8]:
        print(f"   {sum(values) / len(values):5.1f}  {name}")
    print("   ...")
    for name, values in ranked[-8:]:
        print(f"   {sum(values) / len(values):5.1f}  {name}")

    common.heading("Adelanto del Paso C: cuadras tranquilas y bien conectadas")
    print("Cuadras sin ningún colectivo encima, ordenadas por líneas a pie:\n")
    quiet = [r for r in rows if r["n_lines_on"] == 0 and r["tipo_c"] in ("CALLE", "PASAJE")]
    quiet.sort(key=lambda r: -r["n_lines_walk"])
    for r in quiet[:15]:
        print(f"   {r['n_lines_walk']:3d} líneas a pie · {r['street']:30s} {r['barrio']}")
    print(f"\nHay {len(quiet)} cuadras sin colectivo encima; "
          f"{sum(1 for r in quiet if r['n_lines_walk'] >= 20)} tienen 20 o más líneas a pie.")

    print(f"\nEscrito {OUTPUT_CSV.relative_to(common.ROOT)}")


if __name__ == "__main__":
    main()
