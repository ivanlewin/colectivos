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
| **GTFS** Buenos Aires Data | 2019 | **55 m** ✅ | **43.594** | sí (`stop_times`) | AMBA |
| **CNRT** KML | 2023 | 86 m ✅ | no | no | sólo jurisdicción nacional, RMBA |

### GTFS — la fuente principal recomendada

`https://data.buenosaires.gob.ar/dataset/colectivos-gtfs` → ZIP de 209 MB.

```
agency.txt          21 KB
calendar_dates.txt   1 KB
routes.txt          74 KB     1.052 rutas
shapes.txt          29 MB     2.066 trazas, 366 puntos cada una
stops.txt          3,2 MB     43.594 paradas (11.661 dentro de CABA)
stop_times.txt     1,4 GB     ← acá están las frecuencias
trips.txt           31 MB
```

Es la única fuente que trae las tres cosas que necesitamos: geometría que
sigue las calles, paradas, y con qué frecuencia pasa cada línea.

**Advertencia importante:** aunque el portal dice "actualizado el 1 de julio de
2026", los archivos adentro del ZIP están fechados el **30 de septiembre de
2019**. Son datos de hace siete años; varios recorridos cambiaron. También hay
un aviso en el portal de que los datasets GTFS "están suspendidos, en revisión y
corrección" — igual descargan bien.

Mitigación: cruzar contra el padrón EPOK actual (por `l_r_s`) y contra el KML
del CNRT de 2023 para detectar recorridos que ya no existen o que cambiaron.

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
| `trips_per_day` | `stop_times.txt`, para pesar por frecuencia real |

La cuadra ideal es `lines_on_block == 0` ordenada por `lines_walkable`
descendente. Pero el peso relativo de ruido y acceso es una preferencia
personal, así que **conviene exponer los pesos como sliders en la visualización**
en vez de fijar una fórmula. El valor del proyecto está en poder explorarlo.

Para procesar `stop_times.txt` (1,4 GB) usar **DuckDB** o Polars en streaming.
Pandas ingenuo no entra en memoria.

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

1. **El GTFS es de 2019.** Es el riesgo principal. Hay que medir cuánto se
   desvió cruzándolo con EPOK y el CNRT antes de confiar en los resultados.
2. **¿Un GTFS más nuevo?** Existe `colectivos-gtfs-frequency` en Buenos Aires
   Data, sin revisar todavía. Vale la pena mirarlo antes de arrancar.
3. **`stop_times.txt` de 1,4 GB** condiciona las herramientas: DuckDB, no pandas.
4. **Los umbrales (12 m, 25°, 400 m) son propuestas, no verdades.** Hay que
   calibrarlos contra la línea 65 y ajustarlos.
5. **Falta decidir si contar ramales o líneas.** Para el ruido probablemente
   importe la cantidad de colectivos por hora, no cuántas líneas distintas son.
