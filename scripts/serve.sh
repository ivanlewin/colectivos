#!/usr/bin/env bash
# Levanta la página de visualización en http://localhost:8000
#
# Uso: bash scripts/serve.sh [puerto]
#
# Hace falta un servidor: abrir web/index.html con file:// no funciona, porque
# el navegador bloquea el fetch de los GeoJSON.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8000}"

if [[ ! -f "$ROOT/web/data/blocks.geojson" ]]; then
  echo "Faltan los datos de la página. Corré primero:"
  echo "  python3 scripts/07_attribute_lines.py"
  echo "  python3 scripts/08_build_web_data.py"
  exit 1
fi

echo "Abriendo http://localhost:$PORT"
cd "$ROOT/web"
exec python3 -m http.server "$PORT"
