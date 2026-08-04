#!/usr/bin/env bash
# Corre los cuatro pasos de análisis y guarda la salida de cada uno en output/,
# para que quede registrado el resultado y no sólo el código.
#
# Uso: bash scripts/run_all.sh
#
# Los pasos 03 y 04 necesitan pyproj. Si no está instalado se saltean con un
# aviso, en vez de hacer fallar toda la corrida.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/output"

# Usa el virtualenv del proyecto si existe; si no, el python3 del sistema.
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="python3"
fi
echo "Intérprete: $PY"

run_step() {
  local script="$1"
  local name="${script%.py}"
  echo "==> $script"
  if "$PY" "$ROOT/scripts/$script" > "$ROOT/output/$name.txt" 2>&1; then
    echo "    ok -> output/$name.txt"
  else
    echo "    FALLÓ (ver output/$name.txt)"
    tail -3 "$ROOT/output/$name.txt" | sed 's/^/    /'
  fi
}

run_step 01_structure.py
run_step 02_attributes.py

if "$PY" -c "import pyproj" 2>/dev/null; then
  run_step 03_crs.py
  run_step 04_coverage.py
  # Compara las fuentes de geometría; avisa solo si falta alguna descarga.
  run_step 05_geometry_quality.py
  run_step 06_gtfs_freshness.py
  # Los números son el orden en que se escribieron los scripts, no el de
  # ejecución. La cadena del análisis es ésta:
  #
  #   12  reconstruye recorridos desde las paradas     -> stop_routes.csv
  #   07  atribuye líneas a cuadras y las corrige      -> blocks_lines.csv
  #   09  acceso caminando                             -> blocks_access.csv
  #   10  índice de cuadra ideal                       -> ideal_blocks.csv
  #   11  mide el error contra las paradas vigentes
  #   08  arma los archivos de la página               -> web/data/
  run_step 12_reconstruct_routes.py
  # El paso 07 tarda un par de minutos: cruza 31.961 cuadras con las trazas.
  run_step 07_attribute_lines.py
  run_step 09_walking_access.py
  run_step 10_ideal_blocks.py
  run_step 11_validate_stops.py
  run_step 08_build_web_data.py
else
  echo "==> 03_crs.py y 04_coverage.py salteados: falta pyproj"
  echo "    instalalo con: pip install -r requirements.txt"
fi
