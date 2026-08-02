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

Terminada la exploración de fuentes de datos. Todavía no empezó el análisis.

El hallazgo que ordena todo lo demás: **el dataset de recorridos del portal
EPOK, que fue el punto de partida, no sirve como fuente geométrica.** Su traza
tiene los vértices separados 261 m en promedio (una cuadra son 110 m), así que
corta manzanas por el medio y no permite saber por qué calle pasa un colectivo.
El GTFS de Buenos Aires Data tiene 55 m de separación y además trae paradas y
frecuencias: es la fuente principal para seguir.

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
| GTFS de colectivos | `data/gtfs/` | Geometría que sigue las calles, 43.594 paradas, frecuencias |
| KML del CNRT (2023) | `data/cnrt_routes.kml` | Control de vigencia contra el GTFS de 2019 |

Sólo `data/routes.json` está versionado; el resto se baja con el script (son
~250 MB en total).

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
bash scripts/00_download.sh all      # todas las fuentes, ~250 MB

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

Próximos pasos, en orden:

- [ ] Revisar el dataset `colectivos-gtfs-frequency` por si hay un GTFS más nuevo.
- [ ] Medir cuánto se desvió el GTFS de 2019 cruzándolo con el padrón EPOK actual.
- [ ] Paso A: atribuir líneas a cuadras (buffer + filtro por rumbo), validando
      contra la línea 65.
- [ ] Paso B: grafo peatonal sobre el callejero y acceso a paradas a 400 m.
- [ ] Paso C: índice de cuadra ideal, con pesos ajustables.
- [ ] Paso D: mapa web con MapLibre.
