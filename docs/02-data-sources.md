# Fuentes de datos y plan de análisis

Investigación hecha el 2026-08-02 para decidir cómo construir la visualización
de "por qué calles pasan los colectivos" y el índice de **cuadra ideal**.

## El objetivo

Encontrar, para cada cuadra de la Ciudad, dos números:

- **Ruido**: cuántas líneas de colectivo pasan *por esa cuadra*.
- **Acceso**: cuántas líneas se pueden tomar caminando pocos minutos.

La cuadra ideal es la que tiene **ruido cero y acceso alto**: no es una avenida,
pero está a una o dos manzanas de una. Ese es el eje de toda la visualización.

---

## El problema con el dataset EPOK

El GeoJSON de EPOK ([docs/01-epok-dataset.md](01-epok-dataset.md)) tiene el
padrón correcto de líneas, pero **su geometría está simplificada y no sigue las
calles**. Medido en [scripts/05_geometry_quality.py](../scripts/05_geometry_quality.py):

| | EPOK |
|---|---|
| Separación mediana entre vértices | **261 m** |
| Segmentos > 200 m | 58 % |
| Segmentos > 500 m | 29 % |
| Segmento más largo | **11,7 km en línea recta** |
| Giros cercanos a 90° | sólo 25 % |

Una cuadra porteña mide ~110 m. Con vértices cada 261 m, la polilínea corta
manzanas por el medio: en el mapa de la web del GCBA *parece* seguir calles
porque el zoom lo disimula, pero un solo segmento se come 2,5 km en recta.

**Consecuencia:** cualquier atribución de líneas a calles hecha sobre EPOK
—aunque sea con buffer o con map matching— va a inventar colectivos en calles
por las que no pasan y a perder calles por las que sí. EPOK no sirve como
fuente geométrica para este proyecto.

### Lo que sí aporta EPOK

- El **padrón vigente** de líneas y ramales que circulan por CABA (1027
  recorridos, actualizado), útil para filtrar y validar fuentes más viejas.
- Un hallazgo práctico: el endpoint acepta **`srid=4326`** y devuelve lat/lon
  directamente, sin necesidad de reproyectar.
  ```
  https://epok.buenosaires.gob.ar/getGeoLayer/?categoria=colectivos&formato=geojson&srid=4326
  ```
- El endpoint `colectivos/obtener-recorridos-por-linea/?linea=065&jurisdiccion=D.F.`
  sólo devuelve `{"recorridos_list": ["065A", "065B"]}`. Es para poblar el
  desplegable de la web; no trae calles ni geometría. No nos sirve.

> El portal EPOK rechaza pedidos sin `User-Agent` de navegador: responde vacío y
> curl falla con `Empty reply from server`.

---

## Comparación de fuentes

| Fuente | Vigencia | Separación mediana | Paradas | Frecuencias | Cobertura |
|---|---|---|---|---|---|
| **EPOK** `getGeoLayer` | actual | 261 m ❌ | no | no | líneas que tocan CABA (nacional + D.F.) |
| **GTFS frequency** BA Data | 2019 | **55 m** ✅ | **42.463** | sí (`frequencies`) | AMBA |
| GTFS completo BA Data | 2019 | 55 m ✅ | 43.594 | sí (`stop_times`, 1,4 GB) | AMBA |
| **CNRT** KML | 2023 | 86 m ✅ | no | no | sólo jurisdicción nacional, RMBA |

### GTFS frequency — la fuente principal

`https://data.buenosaires.gob.ar/dataset/colectivos-gtfs-frequency` → ZIP de 13 MB.

```
routes.txt          65 KB     1.027 rutas
shapes.txt          26 MB     2.022 trazas, 366 puntos cada una
stops.txt          4,1 MB     42.463 paradas (11.661 dentro de CABA)
frequencies.txt    827 KB     ← headway_secs por franja horaria
calendar.txt       228 B      HI hábil / SI sábado / DI domingo / FI feriado
trips.txt          359 KB
```

Es la única fuente que trae las tres cosas que necesitamos: geometría que sigue
las calles, paradas, y con qué frecuencia pasa cada línea.

Hay también un **GTFS completo** de 209 MB, pero lo único que agrega es
`stop_times.txt` (1,4 GB) con el horario exacto de cada parada. Para pesar por
frecuencia alcanza y sobra `frequencies.txt`, que ya viene con el `headway_secs`
calculado. **Usar la versión frequency**, salvo que en algún momento haga falta
el horario exacto.

### Vigencia: el GTFS es de 2019, y sí importa

Los dos ZIP declaran `feed_end_date=20191231` en `feed_info.txt`, publicados por
NSSA (SUBE). No hay un GTFS más nuevo: el portal marca los datasets GTFS y de
API como "suspendidos, en revisión y corrección", y la API de Transporte Público
está dada de baja. **Es lo más nuevo que hay con geometría usable.**

Medido en [scripts/06_gtfs_freshness.py](../scripts/06_gtfs_freshness.py),
comparando cada recorrido vigente de EPOK contra la mejor traza GTFS de su
misma línea, con tolerancia de 50 m:

| | |
|---|---|
| Líneas de EPOK presentes en el GTFS | **129 de 132** |
| Mediana de cobertura por recorrido | **97,0 %** |
| Recorridos con ≥ 95 % de cobertura | 599 (58,3 %) |
| Recorridos con ≥ 80 % de cobertura | **890 (86,7 %)** |
| Recorridos con ≥ 60 % de cobertura | 978 (95,2 %) |
| Recorridos sin ninguna traza de su línea | 16 (líneas 119, 145 y 164) |

Los que más cambiaron son los ramales de las líneas 8, 51, 50, 106 y 9
(cobertura 15–30 %).

Un dato revelador: la distancia mediana entre un vértice de EPOK y la traza GTFS
de su línea es de **0,1 m**. No es casualidad — **EPOK es una versión decimada
de la misma geometría base**. Eso explica por qué el padrón coincide tan bien y
refuerza la decisión: el GTFS es el original sin decimar.

**Conclusión: el proyecto es viable.** El GTFS de 2019 describe correctamente
~87 % de la red vigente. La cobertura por recorrido queda en
[output/route_coverage.csv](../output/route_coverage.csv), así que se puede
filtrar por nivel de confianza y decir honestamente en la visualización qué
porción del mapa está validada contra los recorridos actuales.

### Callejero de CABA — la unidad de análisis

`https://data.buenosaires.gob.ar/dataset/calles` → GeoJSON de 24 MB.

**31.961 features, y cada una es exactamente una cuadra** (largo mediano 104 m).
Es la unidad de análisis perfecta para este proyecto, sin necesidad de
construirla nosotros.

Campos útiles:

| Campo | Para qué sirve |
|---|---|
| `nomoficial`, `nom_mapa` | Nombre de la calle (2.741 calles distintas) |
| `barrio`, `comuna` | Agregar y comparar por barrio (49 barrios) |
| `tipo_c` | `CALLE` 22.554 / `AVENIDA` 6.994 / `PASAJE` 1.387 / `SENDERO` 485 … |
| `red_jerarq` | `VÍA LOCAL` 23.044 / `DISTRIBUIDORA` 7.921 / `TRONCAL` 995 |
| `sentido` | `CRECIENTE` / `DECRECIENTE` / `DOBLE` / `PEATONAL` (1.156) |
| `alt_izqini`, `alt_derfin` | Numeración: permite nombrar la cuadra ("Thames 1500–1600"). 28.493 de 31.961 tramos la tienen |
| `long` | Largo en metros, ya calculado |

`red_jerarq` y `tipo_c` sirven además como **control de calidad**: si el
análisis dice que por un `PASAJE` o una `VÍA LOCAL` pasan 15 líneas, casi
seguro hay un error de atribución.

---

## Plan propuesto

### Paso A — Atribuir líneas a cuadras

No alcanza con hacer un buffer alrededor de la traza e intersecar: en cada
esquina el buffer toca la calle transversal, y en avenidas anchas toca las
calles paralelas. Se contaminaría todo.

**Propuesto: buffer + filtro por rumbo.** Funciona justamente porque las trazas
del GTFS tienen puntos cada 55 m:

1. Proyectar todo a un CRS métrico (EPSG:5347, o el sistema local de CABA que
   ya tenemos definido en [`common.py`](../scripts/common.py)).
2. Partir cada traza GTFS en sus segmentos.
3. Para cada cuadra, buscar segmentos de traza que estén **a menos de ~12 m** y
   cuyo **rumbo difiera menos de ~25°** (módulo 180°).
4. Contar líneas distintas (`route_short_name`) por cuadra.

El filtro de rumbo es lo que descarta las transversales en las esquinas.

Si resulta ruidoso, el plan B es **map matching de verdad** con Valhalla Meili o
GraphHopper (HMM sobre el grafo de calles). Da mejores garantías pero requiere
levantar un servicio en Docker. Vale la pena empezar por lo simple y medir.

**Validación:** tomar la línea 65, cuyo recorrido conocemos y podemos ver en la
web del GCBA, y verificar a mano que las cuadras atribuidas coinciden.

### Paso B — Acceso caminando

1. Asignar cada parada del GTFS a su cuadra más cercana.
2. Armar un **grafo peatonal** con el callejero: cada cuadra es una arista, cada
   esquina un nodo. Ya viene listo para eso.
3. Dijkstra multi-origen desde las paradas, con corte en 400 m (~5 minutos).

Vale la pena hacer la distancia **de red** y no en línea recta desde el
principio: en línea recta se cuentan paradas del otro lado de una vía del tren o
de la General Paz, que en la práctica no se pueden alcanzar. Con el callejero ya
cargado, el costo extra es bajo.

### Paso C — El índice de cuadra ideal

Por cada cuadra:

| Métrica | Cómo sale |
|---|---|
| `lines_on_block` | Paso A |
| `lines_walkable` | Paso B, líneas distintas con parada a ≤ 400 m |
| `stops_walkable` | Paso B |
| `buses_per_hour` | `frequencies.txt`, para pesar por frecuencia real |
| `coverage` | Paso 6, para saber cuánto confiar en cada resultado |

La cuadra ideal es `lines_on_block == 0` ordenada por `lines_walkable`
descendente. Pero el peso relativo de ruido y acceso es una preferencia
personal, así que **conviene exponer los pesos como sliders en la visualización**
en vez de fijar una fórmula. El valor del proyecto está en poder explorarlo.

Para el ruido probablemente importe más `buses_per_hour` que la cantidad de
líneas distintas: convivir con una línea que pasa cada 3 minutos es peor que con
cuatro que pasan cada media hora. `frequencies.txt` da el `headway_secs` por
franja horaria y `calendar.txt` distingue hábil / sábado / domingo / feriado,
así que se puede calcular la franja que a uno le importe (dormir de noche, por
ejemplo).

### Paso D — La visualización

- **Mapa base:** MapLibre GL JS con teselas de CARTO Positron u OSM. Es abierto,
  no necesita token y el estilo gris claro deja que los datos sean el color.
  El basemap del GCBA también sirve, pero complica sin aportar mucho.
- **Datos:** 31.961 cuadras. Como GeoJSON recortado a lo necesario son ~6–8 MB,
  cargable directo. Si se pone lento, convertir a **PMTiles** con tippecanoe.
- **Capas conmutables:** líneas que pasan · acceso a pie · índice combinado.
- **Antes de programar nada:** mirar los resultados en **QGIS** o kepler.gl. Es
  la forma más rápida de detectar que la atribución quedó mal.

Agregados por barrio (49 polígonos) para responder "qué barrios están peor
conectados" — es una vista mucho más comunicable que 31.961 cuadras.

---

## Riesgos y decisiones abiertas

1. **El GTFS es de 2019 y no hay nada más nuevo con geometría usable.**
   Medido: describe bien ~87 % de la red vigente. Mitigación adoptada: arrastrar
   el `coverage` por recorrido hasta la visualización y ser explícitos sobre qué
   parte del mapa está validada. Los 137 recorridos con cobertura < 80 % hay que
   decidir si se excluyen o se marcan.
2. **Los umbrales (12 m, 25°, 400 m) son propuestas, no verdades.** Hay que
   calibrarlos contra la línea 65 y ajustarlos.
3. **Las líneas 119, 145 y 164 no están en el GTFS.** Son 16 recorridos sin
   geometría densa. Habría que ver si el KML del CNRT las cubre.
4. **El CNRT sólo tiene jurisdicción nacional**, así que no reemplaza al GTFS:
   se pierden las 131 features de jurisdicción D.F. y todas las paradas.

## Fuentes descartadas

- **API Transporte Público del GCBA** — daba tiempo real de colectivos, tren y
  subte. Está dada de baja.
- **Endpoint `obtener-recorridos-por-linea` de EPOK** — sólo devuelve la lista
  de ramales de una línea, para el desplegable del mapa.
- **GTFS completo (209 MB)** — sólo agrega `stop_times.txt` de 1,4 GB, que no
  necesitamos teniendo `frequencies.txt`.
