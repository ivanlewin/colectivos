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

**Hay visualización andando.** Están hechos el cruce de líneas con cuadras
(Paso A) y el mapa web. Falta el acceso caminando (Paso B) y el índice de cuadra
ideal (Paso C).

De las 31.961 cuadras de la Ciudad, **19.070 (59,7 %) no tienen ningún
colectivo**. El máximo son 29 líneas, en Constitución.

Dos hallazgos sobre los datos ordenan todo lo demás:

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
| [docs/02-data-sources.md](docs/02-data-sources.md) | Comparación de las fuentes disponibles y el plan de análisis |
| [docs/03-attribution.md](docs/03-attribution.md) | Cómo se atribuyen líneas a cuadras, y cuánto creerle |

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
web/        La visualización: un HTML y sus datos
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

```bash
# 4. abrir la visualización
bash scripts/serve.sh          # http://localhost:8000
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
| [07_attribute_lines.py](scripts/07_attribute_lines.py) | **Paso A**: qué líneas pasan por cada una de las 31.961 cuadras. |
| [08_build_web_data.py](scripts/08_build_web_data.py) | Prepara los GeoJSON que consume la página. |
| [serve.sh](scripts/serve.sh) | Levanta la visualización en localhost. |
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

### 2026-08-02 — Paso A: líneas por cuadra, y la primera visualización

Se cruzaron las trazas del GTFS con las 31.961 cuadras del callejero. El método
no es un buffer a secas: muestrea cada cuadra cada 10 m, ignora 15 m en cada
esquina y exige que la traza sea **paralela** a la cuadra. Sin ese filtro de
rumbo, cada esquina le regalaría líneas a la calle transversal.

Resultado: **19.070 cuadras (59,7 %) sin ningún colectivo**, 12.891 con al menos
uno, máximo 29 líneas. Validado por dos vías independientes: la jerarquía de vía
del callejero ordena como debe (distribuidoras principales 4,58 líneas de
promedio, vías locales 0,56, pasajes 1 %), y el recorrido reconstruido de la
línea 65 coincide con el mapa oficial del GCBA.
→ [docs/03-attribution.md](docs/03-attribution.md)

Se armó además la visualización en [web/](web/): mapa MapLibre con las cuadras
coloreadas por cantidad de líneas y un desplegable para ver el recorrido de
cualquiera de las 129 líneas. Al elegir una, dibuja las cuadras atribuidas como
banda ancha y encima la traza del GTFS, así el control de calidad se puede hacer
a ojo sobre el mapa.

### 2026-08-03 — Paso B: a cuántas líneas se llega caminando

Se armó un grafo peatonal con el callejero —31.961 cuadras, 18.148 esquinas— y
se corrió un Dijkstra multi-origen por línea desde sus paradas, cortando a
400 m. La distancia va **sobre la red de calles**, no en línea recta: medida en
recta, un radio de 400 m cruza las vías del Sarmiento, el Riachuelo o la General
Paz y cuenta paradas a las que no se llega.

Resultado: **mediana de 6 líneas a pie** por cuadra, máximo 37, y 1.402 cuadras
(4,4 %) sin ninguna. Por barrio va de San Nicolás (20,6) a Villa Soldati (2,1),
que es el orden que se conoce de la Ciudad. El grafo se validó por su
distribución de grados: 9.990 esquinas de grado 4 y 6.404 de grado 3, la firma
de un damero. → [docs/04-walking-access.md](docs/04-walking-access.md)

Cruzando las dos métricas ya asoma el objetivo del proyecto: de las 17.016
cuadras sin colectivo encima, **429 tienen 20 o más líneas a pie** — Ciudadela y
Tacuarí en Constitución, Marcelo T. de Alvear en Retiro, Finochietto en
Barracas.

### 2026-08-03 — Medir en colectivos por hora, no sólo en líneas

Contar líneas engaña: una que pasa cada 4 minutos y otra cada 40 suman lo mismo.
Se agregó la frecuencia real desde `frequencies.txt`, tomando como referencia un
día hábil a las 08:00 (7.799 colectivos/hora en toda la red).

El cambio de fondo fue **atribuir por ramal y no por línea**: la 96 tiene 70
trazas, y sumarle a una cuadra la frecuencia de toda la línea porque ve pasar un
solo ramal inflaría el número varias veces. Las líneas se cuentan una vez; los
colectivos por hora se suman. → [docs/05-service-frequency.md](docs/05-service-frequency.md)

Las dos unidades ordenan distinto, que es justamente el punto: por líneas
ganan los centros de trasbordo (Bernardo de Irigoyen, Retiro), por frecuencia
gana **Av. Santa Fe en Palermo** con 892 colectivos/hora. Entre las cuadras
tranquilas pasa lo mismo: por líneas domina Constitución, por frecuencia entra
Palermo.

La página ahora tiene dos selectores —qué mirar (lo que pasa por la cuadra / lo
que se toma a pie) y en qué unidad— con su propia escala de cortes cada
combinación. El acceso a pie quedó así incorporado al mapa.

Próximos pasos, en orden:

- [ ] Paso C: índice de cuadra ideal, combinando ruido y acceso con pesos
      ajustables en la página.
- [ ] Corregir el sesgo de borde: las paradas del conurbano se descartan, así
      que las cuadras pegadas a la General Paz y al Riachuelo quedan
      subestimadas.
- [ ] Permitir cambiar la hora de referencia: hoy son las 08:00 de un día hábil,
      fijas en una constante.
- [ ] Excluir autopistas del índice: van elevadas sobre calles de superficie y
      el análisis en dos dimensiones no puede separarlas.
- [ ] Pesar el ruido por colectivos/hora usando `frequencies.txt`, no por
      cantidad de líneas.
