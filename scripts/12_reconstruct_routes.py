"""Reconstruir el recorrido de una línea a partir de sus paradas.

El parche de paradas de [`07_attribute_lines.py`](07_attribute_lines.py) sólo
alcanza a las cuadras que *tienen* parada. Una línea ausente del GTFS 2019,
como la 145, aparece punteada: 152 cuadras sueltas en vez de un recorrido.

Entre dos paradas consecutivas el colectivo circula por algo. Este script
reconstruye ese "algo" buscando el camino más corto entre paradas cercanas de
la misma línea y sentido, sobre la red de calles circulables.

## El método

No hace falta ordenar las paradas de una línea —dato que el CSV no trae y que
es difícil de inferir cuando la línea tiene varios ramales—. Alcanza con unir
**cada par de paradas cercanas** de la misma línea y sentido: las consecutivas
quedan a 200–400 m y se unen solas; las de ramales distintos quedan lejos y no
se tocan.

Tres filtros evitan inventar recorridos:

  - **PAIR_RADIUS_M**: sólo se unen paradas cercanas en línea recta.
  - **MAX_PATH_M**: el camino no puede ser largo en términos absolutos.
  - **MAX_DETOUR**: ni mucho más largo que la línea recta entre las dos. Doblar
    una esquina da una relación de ~1,4; rodear una manzana entera da más, y
    eso ya es señal de que esas dos paradas no son consecutivas.

Escribe output/stop_routes.csv, que 07_attribute_lines.py incorpora.

Requiere: bash scripts/00_download.sh stops streets
Uso: python3 scripts/12_reconstruct_routes.py   (correr ANTES que el 07)
"""

import collections
import csv
import heapq
import json
import math

from shapely import STRtree
from shapely.geometry import LineString, Point

import common

STREETS = common.ROOT / "data" / "streets.geojson"
OUTPUT_CSV = common.ROOT / "output" / "stop_routes.csv"

# Dos puntas de cuadra a menos de esto son la misma esquina.
NODE_SNAP_M = 12

# Distancia máxima de una parada a su cuadra.
STOP_SNAP_M = 45

# Sólo se intenta unir paradas de la misma línea y sentido separadas por menos
# de esto en línea recta. Las paradas consecutivas rondan los 200-400 m.
PAIR_RADIUS_M = 500

# A cuántas vecinas se une cada parada. Es el parámetro que más importa.
#
# Unir todos los pares dentro del radio parece inofensivo pero no lo es: donde
# las paradas se amontonan —una línea que zigzaguea, o dos tramos suyos a pocas
# cuadras— genera del orden de n² tramos y el resultado es una retícula, no un
# recorrido. Se veía clarísimo en Villa Crespo con la línea 145.
#
# Un recorrido es una cadena: cada parada tiene una anterior y una siguiente.
# Con 2 vecinas eso se reproduce, y en las bifurcaciones la unión de las
# cadenas de cada rama cubre las dos.
NEIGHBOURS_PER_STOP = 2

# Techo absoluto del camino reconstruido.
MAX_PATH_M = 750

# Y techo relativo: cuántas veces la distancia en línea recta. Doblar una
# esquina da ~1,4; más que esto ya no parece un tramo entre paradas
# consecutivas sino un rodeo inventado.
MAX_DETOUR = 1.8

# Por acá no circula un colectivo, así que no pueden formar parte de un
# recorrido reconstruido.
NOT_DRIVABLE = {
    "SENDERO", "PASAJE PEATONAL", "CALLE PEATONAL", "PASAJE PARTICULAR",
    "CALLE PASAJE PARTICULAR",
}


class DriveGraph:
    """Red de calles circulables. Las aristas recuerdan de qué cuadra son."""

    def __init__(self):
        self.nodes = {}
        self.adjacency = collections.defaultdict(list)   # nodo -> [(vecino, m, cuadra)]
        self.ends = {}                                   # block_id -> (nodo_a, nodo_b)
        self.geometries = []
        self.block_ids = []
        self.names = []

    def node_id(self, x, y):
        key = (round(x / NODE_SNAP_M), round(y / NODE_SNAP_M))
        if key not in self.nodes:
            self.nodes[key] = len(self.nodes)
        return self.nodes[key]

    def add_block(self, block_id, coords, name, drivable):
        length = sum(math.dist(coords[i], coords[i + 1]) for i in range(len(coords) - 1))
        if length == 0:
            return
        self.geometries.append(LineString(coords))
        self.block_ids.append(block_id)
        self.names.append(name)
        a, b = self.node_id(*coords[0]), self.node_id(*coords[-1])
        self.ends[block_id] = (a, b)
        # Se ignoran las manos únicas: el callejero trae `sentido`, pero no de
        # qué punta a qué punta corre la geometría, así que no se puede aplicar
        # sin riesgo de invertirlo. El techo de rodeo acota el daño.
        if drivable and a != b:
            self.adjacency[a].append((b, length, block_id))
            self.adjacency[b].append((a, length, block_id))

    def shortest_path(self, sources, targets, cutoff):
        """Camino más corto entre dos conjuntos de nodos.

        Devuelve (metros, [block_id, ...]) o (None, []) si no llega dentro de
        `cutoff`. `sources` y `targets` son las dos puntas de la cuadra de cada
        parada: se toma la mejor combinación.
        """
        best = {node: 0.0 for node in sources}
        came_from = {}
        heap = [(0.0, node) for node in sources]
        heapq.heapify(heap)
        targets = set(targets)

        while heap:
            distance, node = heapq.heappop(heap)
            if distance > best.get(node, math.inf):
                continue
            if node in targets:
                path, cursor = [], node
                while cursor in came_from:
                    previous, block_id = came_from[cursor]
                    path.append(block_id)
                    cursor = previous
                return distance, path[::-1]
            for neighbour, weight, block_id in self.adjacency[node]:
                step = distance + weight
                if step <= cutoff and step < best.get(neighbour, math.inf):
                    best[neighbour] = step
                    came_from[neighbour] = (node, block_id)
                    heapq.heappush(heap, (step, neighbour))
        return None, []


def main():
    if not STREETS.exists():
        raise SystemExit(f"Falta {STREETS}. Corré: bash scripts/00_download.sh streets")

    from pyproj import Transformer

    to_metric = Transformer.from_crs("EPSG:4326", common.CABA_CRS, always_xy=True)

    common.heading("Reconstrucción de recorridos desde las paradas")

    graph = DriveGraph()
    for feature in json.loads(STREETS.read_text(encoding="utf-8"))["features"]:
        props = feature["properties"]
        coords = feature["geometry"]["coordinates"]
        xs, ys = to_metric.transform([c[0] for c in coords], [c[1] for c in coords])
        drivable = (props["tipo_c"] not in NOT_DRIVABLE
                    and props["sentido"] != "PEATONAL")
        graph.add_block(props["id"], list(zip(xs, ys)), props["nomoficial"], drivable)

    drivable_count = sum(len(v) for v in graph.adjacency.values()) // 2
    print(f"Red circulable: {len(graph.block_ids)} cuadras, "
          f"{drivable_count} transitables, {len(graph.nodes)} esquinas")

    tree = STRtree(graph.geometries)

    # --- cada parada, enganchada a su cuadra ---
    by_service = collections.defaultdict(list)   # (línea, sentido) -> [(x, y, block_id)]
    unmatched = 0
    for lon, lat, street, _number, services in common.current_stops():
        x, y = to_metric.transform(lon, lat)
        index = common.snap_stop(Point(x, y), tree, graph.geometries,
                                 graph.names, street, STOP_SNAP_M)
        if index is None:
            unmatched += 1
            continue
        block_id = graph.block_ids[index]
        for line, direction in services:
            by_service[(line, direction)].append((x, y, block_id))

    print(f"Paradas sin cuadra a menos de {STOP_SNAP_M} m: {unmatched}")
    print(f"Combinaciones línea+sentido: {len(by_service)}")
    print(f"\nUniendo paradas a menos de {PAIR_RADIUS_M} m, "
          f"con camino ≤ {MAX_PATH_M} m y ≤ {MAX_DETOUR}× la recta...\n")

    # --- unir pares cercanos ---
    lines_by_block = collections.defaultdict(set)
    attempted = joined = 0

    for count, ((line, direction), stops) in enumerate(sorted(by_service.items()), 1):
        # Las cuadras con parada se atribuyen siempre, haya camino o no.
        for _x, _y, block_id in stops:
            lines_by_block[block_id].add(line)

        # Cada parada propone sus NEIGHBOURS_PER_STOP vecinas más cercanas. El
        # conjunto de pares es la unión, así que una parada puede terminar con
        # más de dos si otras la eligen.
        pairs = set()
        for i, (x1, y1, block_a) in enumerate(stops):
            nearby = sorted(
                ((math.dist((x1, y1), (x2, y2)), j)
                 for j, (x2, y2, _b) in enumerate(stops) if j != i),
                key=lambda pair: pair[0],
            )[:NEIGHBOURS_PER_STOP]
            for straight, j in nearby:
                if 0 < straight <= PAIR_RADIUS_M and block_a != stops[j][2]:
                    pairs.add((min(i, j), max(i, j)))

        for i, j in pairs:
            x1, y1, block_a = stops[i]
            x2, y2, block_b = stops[j]
            straight = math.dist((x1, y1), (x2, y2))
            attempted += 1
            distance, path = graph.shortest_path(
                graph.ends[block_a], graph.ends[block_b],
                min(MAX_PATH_M, straight * MAX_DETOUR))
            if distance is None or not path:
                continue
            joined += 1
            for block_id in path:
                lines_by_block[block_id].add(line)

        if count % 50 == 0:
            print(f"   {count}/{len(by_service)} combinaciones procesadas")

    print(f"\nPares evaluados: {attempted}, unidos: {joined} "
          f"({100 * joined / attempted:.0f} %)")

    # --- salida ---
    rows = [
        {"block_id": block_id,
         "lines": " ".join(f"{n:03d}" for n in sorted(lines))}
        for block_id, lines in sorted(lines_by_block.items())
    ]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["block_id", "lines"])
        writer.writeheader()
        writer.writerows(rows)

    common.heading("Resultado")
    print(f"Cuadras con alguna línea reconstruida: {len(rows)}")

    per_line = collections.Counter()
    for lines in lines_by_block.values():
        for line in lines:
            per_line[line] += 1

    print("\nLas líneas que el GTFS 2019 no tiene, ahora reconstruidas:")
    for line in (145, 119, 164, 6, 99, 5, 112, 175):
        if line in per_line:
            print(f"   línea {line:3d}: {per_line[line]:4d} cuadras")

    print(f"\nEscrito {OUTPUT_CSV.relative_to(common.ROOT)}")
    print("Lo incorpora 07_attribute_lines.py, que hay que correr después.")


if __name__ == "__main__":
    main()
