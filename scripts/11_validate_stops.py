"""Validación — ¿Cuánto le erramos, medido contra las paradas vigentes?

Hasta acá el proyecto no tenía forma de medir su propio error. Las paradas de
colectivo publicadas por la Secretaría de Transporte (junio de 2026) sí lo
permiten: cada parada dice en qué calle está y qué líneas paran ahí.

La prueba es directa: si hay una parada de la línea 145 en Jufré 210, entonces
la 145 pasa por esa cuadra. Si nuestra atribución no la tiene, le erramos.

Es una cota inferior del error, no una medición completa: una línea pasa por
muchas más cuadras que las que tienen parada, así que esto detecta los faltantes
pero no los sobrantes.

Requiere: bash scripts/00_download.sh stops
Uso: python3 scripts/11_validate_stops.py
"""

import collections
import csv
import json

from shapely import STRtree
from shapely.geometry import LineString, Point

import common

BLOCKS_CSV = common.ROOT / "output" / "blocks_lines.csv"
STREETS = common.ROOT / "data" / "streets.geojson"
OUTPUT_CSV = common.ROOT / "output" / "stop_validation.csv"

# Distancia máxima de una parada a la cuadra a la que se la asigna. Una parada
# está sobre la vereda, así que media calzada de margen alcanza.
SNAP_DISTANCE_M = 30


def main():
    from pyproj import Transformer

    to_metric = Transformer.from_crs("EPSG:4326", common.CABA_CRS, always_xy=True)

    common.heading("Validación contra las paradas vigentes")

    attribution = {}
    with BLOCKS_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            attribution[int(row["block_id"])] = row

    blocks = json.loads(STREETS.read_text(encoding="utf-8"))["features"]
    geometries, block_ids, names = [], [], []
    for feature in blocks:
        coords = feature["geometry"]["coordinates"]
        xs, ys = to_metric.transform([c[0] for c in coords], [c[1] for c in coords])
        geometries.append(LineString(list(zip(xs, ys))))
        block_ids.append(feature["properties"]["id"])
        names.append(feature["properties"]["nomoficial"])
    tree = STRtree(geometries)

    stops = common.current_stops()
    roster = {int(p["linea"]) for p in common.properties()}
    print(f"Paradas vigentes        : {len(stops)}")
    print(f"Líneas en las paradas   : "
          f"{len({n for *_, s in stops for n, _ in s})}")
    print(f"Líneas en el padrón EPOK: {len(roster)}")

    only_stops = {n for *_, s in stops for n, _ in s} - roster
    if only_stops:
        print(f"\nLíneas que están en las paradas y NO en el padrón EPOK: "
              f"{sorted(only_stops)}")
        print("El padrón de EPOK no es exhaustivo.")

    hits = misses = far = 0
    missing = collections.Counter()
    total = collections.Counter()
    rows = []

    for lon, lat, street, number, services in stops:
        x, y = to_metric.transform(lon, lat)
        index = common.snap_stop(Point(x, y), tree, geometries, names,
                                 street, SNAP_DISTANCE_M)
        if index is None:
            far += 1
            continue

        block_id = block_ids[index]
        # Se valida contra `lines_gtfs`, la atribución geométrica sola. Usar
        # `lines` daría 100 % por construcción: esa columna ya incorpora estas
        # mismas paradas.
        attributed = set(attribution.get(block_id, {}).get("lines_gtfs", "").split())

        for line, direction in services:
            code = f"{line:03d}"
            total[code] += 1
            if code in attributed:
                hits += 1
            else:
                misses += 1
                missing[code] += 1
                rows.append({
                    "line": code,
                    "direction": direction,
                    "street": street,
                    "number": number,
                    "block_id": block_id,
                    "in_epok_roster": line in roster,
                })

    evaluated = hits + misses
    common.heading("Resultado")
    print(f"Paradas descartadas por estar a más de {SNAP_DISTANCE_M} m "
          f"de cualquier cuadra: {far}")
    print(f"\nPares parada-línea evaluados: {evaluated}")
    print(f"   la cuadra ya tiene esa línea : {hits} ({100 * hits / evaluated:.1f} %)")
    print(f"   no la tiene                  : {misses} ({100 * misses / evaluated:.1f} %)")

    common.heading("Dónde está el error")
    print("Líneas ordenadas por paradas sin atribuir:\n")
    print(f"   {'línea':>6} {'faltan':>7} {'de':>6} {'':>6}  causa probable")
    for code, count in missing.most_common(15):
        number = int(code)
        share = 100 * count / total[code]
        if number not in roster:
            cause = "no está en el padrón EPOK"
        elif share > 95:
            cause = "la línea no existe en el GTFS 2019"
        else:
            cause = "el recorrido cambió desde 2019"
        print(f"   {code:>6} {count:7d} {total[code]:6d} {share:5.0f} %  {cause}")

    if not rows:
        print("\nNo falta ninguna: la atribución geométrica cubre todas las paradas.")
        return

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["line"], r["street"])))

    print(f"\nEl detalle de cada faltante queda en "
          f"{OUTPUT_CSV.relative_to(common.ROOT)}")
    print("Todas esas paradas sí están incorporadas al resultado final: el "
          "parche\nde 07_attribute_lines.py las agrega. Lo que se mide acá es "
          "cuánto\nquedaría afuera si dependiéramos sólo del GTFS de 2019.")


if __name__ == "__main__":
    main()
