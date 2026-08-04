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


def buses_per_hour_by_service(by_service):
    """{(línea, sentido): colectivos por hora}.

    Las frecuencias salen del GTFS 2019, la única fuente que las tiene, y allí
    vienen por ramal con un `direction_id` 0/1 que no se puede mapear con
    confianza al 'I'/'V' de las paradas: nada dice cuál es cuál, y equivocarse
    invertiría ida con vuelta.

    Así que se reparte el total de la línea en partes iguales entre los
    sentidos que tenga. Ida y vuelta suelen tener servicio simétrico, así que
    el error está acotado, y una cuadra que alcanza los dos sentidos recupera
    el total exacto de la línea.

    Las ocho líneas que el GTFS no tiene quedan en cero: cuentan para la
    métrica de cantidad de líneas pero no aportan a la de colectivos por hora.
    """
    route_line = {
        row["route_id"]: common.line_number(row["route_short_name"])
        for row in common.gtfs_rows("routes.txt")
    }
    per_trip = {m: common.buses_per_hour_by_trip(m) for m in common.MOMENTS}

    by_line = collections.defaultdict(collections.Counter)
    for row in common.gtfs_rows("trips.txt"):
        line = route_line.get(row["route_id"])
        if line is None:
            continue
        for moment, table in per_trip.items():
            by_line[line][moment] += table.get(row["trip_id"], 0.0)

    directions = collections.Counter(line for line, _ in by_service)
    return {
        (line, direction): {
            moment: by_line[line][moment] / directions[line]
            for moment in common.MOMENTS
        }
        for line, direction in by_service
    }


def stops_by_service():
    """{(línea, sentido): [(lon, lat), ...]} de las paradas vigentes.

    Fuente: Secretaría de Transporte y Obras Públicas, junio de 2026. Reemplaza
    a las del GTFS 2019, que era la única disponible cuando se escribió este
    paso.

    Se agrupa por línea **y sentido** porque es la granularidad que trae el
    dataset, y porque importa: llegar a la parada de la ida no da acceso a la
    vuelta, que suele ir por otra calle.

    Nota sobre el sesgo de borde: se probó sumar las paradas del GTFS que caen
    fuera de CABA, para que las cuadras pegadas a la General Paz o al Riachuelo
    dejaran de tener medio radio de caminata ciego. No sirve, y la medición es
    contundente: de 30.802 paradas foráneas, ninguna quedó a menos de 60 m de
    una calle de CABA, y **cero cuadras** ganaron una sola línea. El problema
    no son las paradas sino el grafo: el callejero termina en el límite de la
    Ciudad, así que aunque la parada exista no hay por dónde caminar hasta
    ella. Arreglarlo de verdad necesita una red de calles del conurbano, que el
    proyecto no tiene.
    """
    by_service = collections.defaultdict(list)
    for lon, lat, _street, _number, services in common.current_stops():
        for line, direction in services:
            by_service[(line, direction)].append((lon, lat))
    return by_service


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

    by_service = stops_by_service()
    buses = buses_per_hour_by_service(by_service)
    lines = {line for line, _ in by_service}
    print(f"Paradas vigentes (junio 2026) : "
          f"{len({c for v in by_service.values() for c in v})}")
    print(f"Líneas                        : {len(lines)}")
    print(f"Combinaciones línea + sentido : {len(by_service)}")
    print(f"Sin frecuencia en el GTFS 2019: "
          f"{len({line for line in lines if not any(buses[k] for k in by_service if k[0] == line)})}"
          f"   (suman 0 col/hora)")

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
    # Las coordenadas se deduplican: una misma parada sirve a varias líneas y
    # engancharla una sola vez ahorra la mayor parte del trabajo.
    tree = STRtree(graph.geometries)
    entry_points = {}          # (lon, lat) -> [(nodo, metros hasta ese nodo)]
    unmatched = 0
    for coord in {c for coords in by_service.values() for c in coords}:
        point = Point(*project(*coord))
        index = tree.nearest(point)
        geometry = graph.geometries[index]
        if point.distance(geometry) > 60:
            unmatched += 1
            continue
        # Distancia caminando hasta cada punta de esa cuadra.
        along = geometry.project(point)
        _, node_a, node_b = graph.blocks[index]
        entry_points[coord] = [(node_a, along), (node_b, geometry.length - along)]

    print(f"\nParadas enganchadas al callejero: {len(entry_points)}")
    print(f"   descartadas por estar lejos   : {unmatched}")
    print("   (las del conurbano que no llegan a tocar una calle de CABA: el")
    print("    grafo termina en el límite, así que a ésas no se puede caminar)")

    # --- una corrida de Dijkstra por línea y sentido ---
    # La línea se cuenta una sola vez aunque se alcancen sus dos sentidos; los
    # colectivos por hora se suman, porque ida y vuelta son servicios
    # distintos y alcanzar los dos vale más que alcanzar uno.
    lines_per_block = collections.defaultdict(set)
    buses_per_block = collections.defaultdict(collections.Counter)
    stops_near = collections.Counter()

    print(f"\nCalculando alcance a {WALK_RADIUS_M} m por línea y sentido...")
    for count, (service, coords) in enumerate(sorted(by_service.items()), 1):
        sources = {}
        for coord in coords:
            for node, distance in entry_points.get(coord, []):
                if distance < sources.get(node, math.inf):
                    sources[node] = distance
        if not sources:
            continue
        reached = graph.dijkstra(sources, WALK_RADIUS_M)
        line, _direction = service
        frequency = buses[service]
        for block_id, node_a, node_b in graph.blocks:
            if node_a in reached or node_b in reached:
                lines_per_block[block_id].add(line)
                buses_per_block[block_id].update(frequency)
        if count % 50 == 0:
            print(f"   {count}/{len(by_service)} combinaciones procesadas")

    # Paradas a pie, sin distinguir línea: una sola corrida desde todas.
    all_sources = {}
    for entries in entry_points.values():
        for node, distance in entries:
            if distance < all_sources.get(node, math.inf):
                all_sources[node] = distance
    reached_any = graph.dijkstra(all_sources, WALK_RADIUS_M)
    for entries in entry_points.values():
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
            "red_jerarq": source.get("red_jerarq", ""),
            "n_lines_on": int(source.get("n_lines", 0)),
            "lines_on": source.get("lines", ""),
            "n_lines_walk": len(walkable),
            "lines_walk": " ".join(f"{n:03d}" for n in walkable),
            **{f"buses_hour_walk{spec['suffix']}":
               round(buses_per_block[block_id][moment], 1)
               for moment, spec in common.MOMENTS.items()},
            **{f"buses_hour_on{spec['suffix']}":
               float(source.get(f"buses_hour{spec['suffix']}", 0) or 0)
               for moment, spec in common.MOMENTS.items()},
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

    walk_buses = sorted(r["buses_hour_walk"] for r in rows)
    print(f"\nColectivos por hora accesibles a pie:")
    print(f"   mediana : {walk_buses[len(walk_buses) // 2]:.0f}")
    print(f"   máximo  : {walk_buses[-1]:.0f}")

    print("\nPor barrio — los 8 mejores y los 8 peores (líneas · col/hora):")
    by_barrio = collections.defaultdict(list)
    for r in rows:
        if r["barrio"]:
            by_barrio[r["barrio"]].append((r["n_lines_walk"], r["buses_hour_walk"]))
    mean = lambda vs, i: sum(v[i] for v in vs) / len(vs)
    ranked = sorted(by_barrio.items(), key=lambda kv: -mean(kv[1], 0))
    for name, values in ranked[:8]:
        print(f"   {mean(values, 0):5.1f} · {mean(values, 1):6.0f}   {name}")
    print("   ...")
    for name, values in ranked[-8:]:
        print(f"   {mean(values, 0):5.1f} · {mean(values, 1):6.0f}   {name}")

    common.heading("Adelanto del Paso C: cuadras tranquilas y bien conectadas")
    quiet = [r for r in rows if r["n_lines_on"] == 0 and r["tipo_c"] in ("CALLE", "PASAJE")]

    # Las dos métricas ordenan distinto: por eso la página las deja elegir.
    for label, key in (("líneas a pie", "n_lines_walk"),
                       ("colectivos por hora a pie", "buses_hour_walk")):
        print(f"\nSin colectivo encima, ordenadas por {label}:\n")
        for r in sorted(quiet, key=lambda r: -r[key])[:10]:
            print(f"   {r['n_lines_walk']:3d} líneas · {r['buses_hour_walk']:6.0f} col/h   "
                  f"{r['street']:28s} {r['barrio']}")

    print(f"\nHay {len(quiet)} cuadras sin colectivo encima; "
          f"{sum(1 for r in quiet if r['n_lines_walk'] >= 20)} tienen 20 o más líneas a pie.")

    print(f"\nEscrito {OUTPUT_CSV.relative_to(common.ROOT)}")


if __name__ == "__main__":
    main()
