"""Utilidades compartidas por los scripts de análisis.

Centraliza tres cosas que todos los scripts necesitan:
  - dónde está el dataset,
  - cómo cargarlo,
  - la definición del sistema de coordenadas en el que vienen las geometrías.
"""

import collections
import csv
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "routes.json"

# URL de origen (portal EPOK del Gobierno de la Ciudad de Buenos Aires).
SOURCE_URL = (
    "https://epok.buenosaires.gob.ar/getGeoLayer/"
    "?categoria=colectivos&formato=geojson"
)

# El archivo NO declara un bloque `crs`, y las coordenadas no son lat/lon:
# son metros en el sistema plano local de CABA (Transversa Mercator con el
# origen desplazado a 100000/100000). La verificación empírica de esta
# definición está en scripts/03_crs.py.
CABA_CRS = (
    "+proj=tmerc +lat_0=-34.6297166 +lon_0=-58.4627 +k=0.999998 "
    "+x_0=100000 +y_0=100000 +ellps=intl +units=m +no_defs"
)

# Bounding box aproximado del ejido de la Ciudad, en lat/lon. Se usa sólo para
# estimar qué porción de cada recorrido cae dentro de CABA; es una caja, no el
# polígono real, así que los porcentajes son aproximados.
CABA_BBOX = {"lat_min": -34.706, "lat_max": -34.526,
             "lon_min": -58.532, "lon_max": -58.335}


def load():
    """Devuelve el FeatureCollection completo."""
    if not DATASET.exists():
        raise SystemExit(
            f"No se encontró {DATASET}.\n"
            f"Descargalo con: bash scripts/00_download.sh"
        )
    with DATASET.open(encoding="utf-8") as fh:
        return json.load(fh)


def features():
    """Devuelve la lista de features del GeoJSON."""
    return load()["features"]


def properties():
    """Devuelve sólo los diccionarios de `properties` de cada feature."""
    return [f["properties"] for f in features()]


def transformer():
    """Transformer de coordenadas planas CABA -> lat/lon (EPSG:4326).

    Se construye con always_xy=True, así que `transform(x, y)` devuelve
    (lon, lat) en ese orden.
    """
    from pyproj import Transformer

    return Transformer.from_crs(CABA_CRS, "EPSG:4326", always_xy=True)


def heading(text):
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


# --------------------------------------------------------------------- GTFS

GTFS = ROOT / "data" / "gtfs_frequency"

# Momento de referencia para medir el servicio: un día hábil a las 08:00.
# El GTFS modela el servicio por franjas con una frecuencia cada una, así que
# hay que pararse en un instante concreto. A las 08:00 está activo el 96 % de
# los trips de día hábil, que es el máximo del día.
PEAK_SERVICE_ID = "HI"    # HI = hábil, SI = sábado, DI = domingo, FI = feriado
PEAK_SECONDS = 8 * 3600


def line_number(short_name):
    """'065A' -> 65. None si no arranca con dígitos."""
    match = re.match(r"(\d+)", short_name or "")
    return int(match.group(1)) if match else None


def _seconds(clock):
    hours, minutes, seconds = (int(p) for p in clock.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def buses_per_hour_by_trip():
    """{trip_id: colectivos por hora} en el momento de referencia.

    Sólo trips del servicio de día hábil. Un trip sin franja activa a esa hora
    queda afuera: ese servicio no está circulando.
    """
    windows = collections.defaultdict(list)
    with (GTFS / "frequencies.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            windows[row["trip_id"]].append((
                _seconds(row["start_time"]),
                _seconds(row["end_time"]),
                int(row["headway_secs"]),
            ))

    per_trip = {}
    with (GTFS / "trips.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["service_id"] != PEAK_SERVICE_ID:
                continue
            for start, end, headway in windows.get(row["trip_id"], ()):
                if start <= PEAK_SECONDS < end and headway:
                    per_trip[row["trip_id"]] = 3600 / headway
                    break
    return per_trip


def gtfs_rows(name):
    """Filas de un archivo del GTFS como diccionarios."""
    with (GTFS / name).open(encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


# ------------------------------------------------------- paradas vigentes

STOPS_CSV = ROOT / "data" / "stops.csv"


def current_stops():
    """Paradas de colectivo vigentes: [(lon, lat, calle, altura, {(línea, sentido)})].

    Publicado por la Secretaría de Transporte y Obras Públicas, revisión de
    junio de 2026. Es la fuente más actualizada del proyecto y la única que
    dice directamente qué líneas paran dónde.

    Trae hasta seis líneas por parada en columnas L1..L6, cada una con su
    sentido en l1_sen..l6_sen ('I' ida, 'V' vuelta). Las coordenadas vienen
    con coma decimal.
    """
    if not STOPS_CSV.exists():
        raise SystemExit(
            f"Falta {STOPS_CSV}. Descargalo con: bash scripts/00_download.sh stops"
        )

    stops = []
    with STOPS_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                lon = float(row["coord_X"].replace(",", "."))
                lat = float(row["coord_Y"].replace(",", "."))
            except (ValueError, AttributeError):
                continue

            services = set()
            for slot in range(1, 7):
                number = (row.get(f"L{slot}") or "").strip()
                # Una fila del CSV trae 'V' donde debería ir el número.
                if not number.isdigit():
                    continue
                direction = (row.get(f"l{slot}_sen") or "").strip() or "?"
                services.add((int(number), direction))

            if services:
                stops.append((lon, lat, row.get("CALLE", ""),
                              row.get("ALT PLANO", ""), services))
    return stops


def street_tokens(name):
    """Nombre de calle normalizado a conjunto de palabras, sin acentos.

    Las dos fuentes escriben el mismo nombre en distinto orden: las paradas
    dicen "RAUL SCALABRINI ORTIZ AV." y el callejero "SCALABRINI ORTIZ, RAUL
    AV.". Comparar conjuntos de palabras hace que el orden no importe.
    """
    if not name:
        return frozenset()
    plain = unicodedata.normalize("NFKD", name.upper())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return frozenset(t for t in re.split(r"[^A-Z0-9]+", plain) if t)


def snap_stop(point, tree, geometries, names, street, max_distance=45):
    """Índice de la cuadra a la que corresponde una parada, o None.

    La cuadra más cercana no siempre es la correcta: una parada cerca de la
    esquina puede quedar más cerca del eje de la transversal que del de su
    propia calle. La parada de Jufré 210, por ejemplo, está a 23 m de Julián
    Álvarez y a 29 m de Jufré.

    Por eso se prefiere, entre las cuadras del entorno, la más cercana que
    además *se llame igual* que la calle declarada por la parada. Si ninguna
    coincide por nombre, se cae a la más cercana a secas.
    """
    candidates = tree.query(point, predicate="dwithin", distance=max_distance)
    if not len(candidates):
        return None
    candidates = sorted(candidates, key=lambda i: point.distance(geometries[i]))
    for index in candidates:
        if same_street(street, names[index]):
            return index
    return candidates[0]


def same_street(a, b, threshold=0.6):
    """Si dos nombres de calle designan la misma calle.

    Jaccard sobre las palabras: tolera "AV.", comas y orden distinto, pero no
    confunde calles diferentes.
    """
    x, y = street_tokens(a), street_tokens(b)
    if not x or not y:
        return False
    return len(x & y) / len(x | y) >= threshold
