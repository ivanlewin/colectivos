# colectivos

Buscar **la cuadra ideal de Buenos Aires**: una donde no pase ningún colectivo
por la puerta, pero con muchas líneas a pocos minutos caminando. No una
avenida — una calle a una o dos manzanas de una avenida, o de un cruce de
avenidas.

Para llegar ahí hace falta responder, cuadra por cuadra:

- ¿Por qué calles pasan más líneas de colectivo? ¿Por cuáles menos?
- ¿Por cuáles directamente no pasa ninguna?
- ¿Qué barrios están mejor y peor conectados?

El resultado final es un mapa web con esas capas. Cada cosa que averiguamos
queda como un script reproducible en [scripts/](scripts/), su salida en
[output/](output/) y lo aprendido en [docs/](docs/) — así el conocimiento no
vive sólo en la cabeza de alguien.

## Estado

Terminada la exploración de fuentes de datos, con las tres fuentes elegidas y
validadas. Todavía no empezó el análisis.

Dos hallazgos ordenan todo lo demás:

1. **El dataset de recorridos de EPOK, que fue el punto de partida, no sirve
   como fuente geométrica.** Sus vértices están separados 261 m (una cuadra son
   110 m): la traza corta manzanas por el medio y no permite saber por qué calle
   pasa un colectivo. Queda como padrón de líneas vigentes.
2. **El GTFS de Buenos Aires Data sí sirve** — 55 m entre puntos, más paradas y
   frecuencias — pero es de 2019 y no hay nada más nuevo publicado. Medimos que
   describe correctamente el 87 % de la red vigente, lo cual alcanza siempre que
   arrastremos ese dato hasta el mapa.

El detalle y el plan están en [docs/02-data-sources.md](docs/02-data-sources.md).

## Documentación

| Documento | Contenido |
|---|---|
| [docs/01-epok-dataset.md](docs/01-epok-dataset.md) | Qué contiene el dataset EPOK, sus atributos y sus tres advertencias |
| [docs/02-data-sources.md](docs/02-data-sources.md) | Comparación de las fuentes disponibles y el plan de análisis propuesto |

## Fuentes de datos

| Fuente | Archivo | Para qué |
|---|---|---|
| EPOK, recorridos | `data/routes.json` | Padrón vigente de líneas que pasan por CABA |
| Callejero de CABA | `data/streets.geojson` | **Unidad de análisis**: 31.961 features, una por cuadra |
| GTFS frequency | `data/gtfs_frequency/` | **Geometría que sigue las calles**, 42.463 paradas, headways |
| KML del CNRT (2023) | `data/cnrt_routes.kml` | Control de vigencia contra el GTFS de 2019 |

Sólo `data/routes.json` está versionado; el resto se baja con el script (~50 MB).

## Estructura del repo

```
data/       Datasets descargados (fuente de verdad, no se editan)
docs/       Lo que fuimos aprendiendo de los datos
scripts/    Un script por pregunta que nos hicimos
output/     La salida de cada script, versionada
```

## Cómo reproducir

```bash
# 1. datos — sin argumento baja sólo el dataset EPOK
bash scripts/00_download.sh          # ~3,5 MB
bash scripts/00_download.sh all      # todas las fuentes que usamos, ~50 MB

# 2. dependencias — los pasos 01 y 02 no las necesitan
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. correr el análisis y guardar las salidas en output/
bash scripts/run_all.sh
```

`run_all.sh` usa `.venv/bin/python` si existe, y si no el `python3` del sistema;
en ese caso saltea los pasos que necesitan pyproj en vez de fallar. Cada script
también corre solo:

```bash
.venv/bin/python scripts/03_crs.py
```

## Los scripts

| Script | Pregunta que responde |
|---|---|
| [00_download.sh](scripts/00_download.sh) | Bajar las fuentes. Respalda con fecha lo que ya estaba. |
| [01_structure.py](scripts/01_structure.py) | ¿Qué forma tiene el archivo de EPOK? |
| [02_attributes.py](scripts/02_attributes.py) | ¿Qué representa cada feature? Líneas vs ramales vs sentidos. |
| [03_crs.py](scripts/03_crs.py) | ¿En qué sistema de coordenadas está? Prueba candidatos y valida. |
| [04_coverage.py](scripts/04_coverage.py) | ¿Es de verdad "los colectivos de la Ciudad"? |
| [05_geometry_quality.py](scripts/05_geometry_quality.py) | ¿Sirve la geometría para atribuir colectivos a calles? Compara las tres fuentes. |
| [06_gtfs_freshness.py](scripts/06_gtfs_freshness.py) | ¿Cuánto sirve todavía el GTFS de 2019? Mide la cobertura de cada recorrido vigente. |
| [common.py](scripts/common.py) | Rutas, carga del dataset y definición del CRS. |

---

## Bitácora

### 2026-08-02 — Exploración del dataset EPOK

Se descargó y caracterizó de punta a punta. Confirma tener los recorridos de las
líneas que circulan por CABA, con dos matices: las trazas vienen completas hasta
el conurbano, y sólo están las líneas que entran a la Ciudad. Se identificó el
CRS, que el archivo no declara. → [docs/01-epok-dataset.md](docs/01-epok-dataset.md)

### 2026-08-02 — Búsqueda de la fuente geométrica

Se descubrió que la geometría de EPOK está demasiado simplificada para atribuir
colectivos a calles, y se compararon tres fuentes alternativas. El GTFS de
Buenos Aires Data gana por geometría densa + paradas + frecuencias, con la
salvedad de que sus archivos son de 2019. Se encontró además el callejero de
CABA, que da la unidad de análisis lista: una feature por cuadra.
→ [docs/02-data-sources.md](docs/02-data-sources.md)

### 2026-08-02 — Vigencia del GTFS: el proyecto es viable

Se confirmó que **no existe un GTFS más nuevo** de la Ciudad: los dos ZIP
publicados son del mismo feed de NSSA, válido hasta el 31/12/2019, y la API de
Transporte Público está dada de baja. Se midió entonces cuánto sirve todavía:
129 de las 132 líneas vigentes están en el GTFS, y la cobertura mediana por
recorrido es del **97 %** — el 86,7 % de los recorridos actuales tiene una traza
2019 que le calza en más del 80 %. Alcanza para el proyecto, arrastrando el
`coverage` por recorrido hasta el mapa para ser honestos sobre qué está
validado.

Se cambió la fuente principal al **GTFS frequency** (13 MB en vez de 209 MB, con
`frequencies.txt` en lugar de `stop_times.txt` de 1,4 GB).

Se descubrió además que la distancia mediana entre un vértice de EPOK y la traza
GTFS de su línea es de 0,1 m: **EPOK es una versión decimada de la misma
geometría base**.

Próximos pasos, en orden:

- [ ] Paso A: atribuir líneas a cuadras (buffer + filtro por rumbo), validando
      contra la línea 65.
- [ ] Paso B: grafo peatonal sobre el callejero y acceso a paradas a 400 m.
- [ ] Paso C: índice de cuadra ideal, con pesos ajustables.
- [ ] Paso D: mapa web con MapLibre.
