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

# El http.server pelado no manda Cache-Control, así que el navegador se queda
# con una copia vieja de los GeoJSON: regenerás los datos, recargás, y seguís
# viendo lo anterior. Con no-cache revalida siempre.
exec python3 -c '
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()


port = int(sys.argv[1])
ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
' "$PORT"
