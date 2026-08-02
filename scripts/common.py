"""Utilidades compartidas por los scripts de análisis.

Centraliza tres cosas que todos los scripts necesitan:
  - dónde está el dataset,
  - cómo cargarlo,
  - la definición del sistema de coordenadas en el que vienen las geometrías.
"""

import json
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
