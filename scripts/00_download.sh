#!/usr/bin/env bash
# Descarga las fuentes de datos del proyecto en data/.
#
# Uso:
#   bash scripts/00_download.sh            # sólo el dataset EPOK (chico)
#   bash scripts/00_download.sh all        # todas las fuentes (~250 MB)
#   bash scripts/00_download.sh gtfs       # una fuente puntual
#
# Fuentes: epok | epok4326 | streets | gtfs | cnrt
# La comparación entre ellas está en docs/02-data-sources.md

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="$ROOT/data"
mkdir -p "$DATA"

UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"

# El portal EPOK rechaza pedidos sin User-Agent de navegador (devuelve una
# respuesta vacía y curl falla con "Empty reply from server").
fetch() {
  local url="$1" dest="$2" label="$3"
  if [[ -f "$dest" ]]; then
    local backup="${dest%.*}.$(date +%Y-%m-%d).${dest##*.}"
    echo "  ya existe, respaldando en $(basename "$backup")"
    cp "$dest" "$backup"
  fi
  echo "  descargando $label"
  curl -fsSL -A "$UA" "$url" -o "$dest"
  echo "  -> $(basename "$dest") ($(du -h "$dest" | cut -f1))"
}

want() { [[ "${1:-epok}" == "all" || "${1:-epok}" == "$2" ]]; }
TARGET="${1:-epok}"

# --- EPOK, recorridos de colectivos que pasan por CABA -----------------------
# Sin el parámetro srid las coordenadas vienen en el sistema plano local de
# CABA. Ver docs/01-epok-dataset.md y scripts/03_crs.py.
if want "$TARGET" epok; then
  echo "[epok] recorridos EPOK (coordenadas planas CABA)"
  fetch "https://epok.buenosaires.gob.ar/getGeoLayer/?categoria=colectivos&formato=geojson" \
        "$DATA/routes.json" "GeoJSON, CRS local"
fi

# Con srid=4326 el mismo endpoint devuelve lat/lon directamente.
if want "$TARGET" epok4326; then
  echo "[epok4326] recorridos EPOK en WGS84"
  fetch "https://epok.buenosaires.gob.ar/getGeoLayer/?categoria=colectivos&formato=geojson&srid=4326" \
        "$DATA/routes_wgs84.json" "GeoJSON, lat/lon"
fi

# --- Callejero de CABA, un feature por cuadra --------------------------------
if want "$TARGET" streets; then
  echo "[streets] callejero de CABA (Buenos Aires Data)"
  fetch "https://data.buenosaires.gob.ar/dataset/calles/resource/2941f731-0a2e-4391-b8c9-a2912a80c081/download" \
        "$DATA/streets.geojson" "GeoJSON, ~24 MB"
fi

# --- GTFS del AMBA: geometría densa + paradas + frecuencias ------------------
if want "$TARGET" gtfs; then
  echo "[gtfs] GTFS de colectivos (Buenos Aires Data) — ~209 MB, tarda"
  fetch "https://data.buenosaires.gob.ar/dataset/colectivos-gtfs/resource/juqdkmgo-571-resource/download" \
        "$DATA/gtfs.zip" "ZIP, ~209 MB"
  echo "  descomprimiendo en data/gtfs/"
  rm -rf "$DATA/gtfs" && mkdir -p "$DATA/gtfs"
  unzip -oq "$DATA/gtfs.zip" -d "$DATA/gtfs"
fi

# --- KML del CNRT: recorridos 2023 de jurisdicción nacional ------------------
if want "$TARGET" cnrt; then
  echo "[cnrt] recorridos AMBA jurisdicción nacional (CNRT, 2023)"
  fetch "https://datos.transporte.gob.ar/dataset/d67bd5a0-bd6e-4b02-a7ba-a9dd329b0d5e/resource/434c8107-b3ae-46cc-919e-a98b603c1ced/download/lineas_jn_rmba_cnrt.kml" \
        "$DATA/cnrt_routes.kml" "KML, ~10 MB"
fi

echo "Listo."
