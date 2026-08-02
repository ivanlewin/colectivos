# Atribuir líneas a cuadras

Cómo se responde "¿qué colectivos pasan por esta cuadra?" y cuánto se le puede
creer al resultado.

Implementado en [scripts/07_attribute_lines.py](../scripts/07_attribute_lines.py).

## El problema

Hay que cruzar 31.961 cuadras del callejero con las trazas del GTFS. La forma
obvia —bufferear la traza e intersecar— no sirve: en cada esquina, la traza que
dobla pasa a pocos metros de la punta de las cuadras vecinas, y esas cuadras se
llevarían líneas que nunca las recorren. Con 20.000 esquinas, el error se
acumula hasta arruinar el mapa.

## El método

Tres decisiones, cada una atacando una fuente de error distinta:

1. **Muestrear la cuadra cada 10 m** en lugar de tratarla como un objeto único.
   Así se puede exigir que la traza la acompañe *a lo largo*, no que la toque en
   un punto.
2. **Ignorar 15 m en cada punta.** Es la zona de la esquina, donde se produce la
   contaminación de las transversales.
3. **Exigir que la traza sea paralela a la cuadra** (rumbo dentro de 30°, módulo
   180°). Éste es el filtro que realmente elimina las calles que cruzan.

Una línea se atribuye a la cuadra si hay un segmento de su traza a menos de 15 m
y alineado en al menos el **60 % de las muestras**.

| Parámetro | Valor | Por qué |
|---|---|---|
| `MATCH_DISTANCE_M` | 15 m | Tolera el ancho de una avenida sin llegar a la calle paralela (~110 m) |
| `BEARING_TOLERANCE_DEG` | 30° | Descarta transversales; tolera calles que no son perfectamente rectas |
| `SAMPLE_STEP_M` | 10 m | ~8 muestras en una cuadra típica de 104 m |
| `INTERSECTION_SKIP_M` | 15 m | La zona de esquina |
| `MIN_SAMPLE_RATIO` | 60 % | Tolera un tramo mal digitalizado, no un roce |

Sólo se consideran las líneas del **padrón vigente de EPOK**, así que quedan
afuera las suburbanas del GTFS que ya no entran a la Ciudad.

## El resultado

| | |
|---|---|
| Cuadras sin ninguna línea | **19.070 (59,7 %)** |
| Cuadras con al menos una | 12.891 (40,3 %) |
| Máximo en una cuadra | 29 líneas |

Las diez cuadras con más líneas están todas en **Retiro** (Ramos Mejía, San
Martín, Antártida Argentina) y **Constitución** (Bernardo de Irigoyen) — los dos
grandes centros de trasbordo de la Ciudad.

## Validación

**Control por jerarquía de vía.** No se usó `red_jerarq` en el cálculo, así que
sirve de control independiente. El orden sale como tiene que salir:

| Jerarquía | Promedio de líneas |
|---|---|
| Vía distribuidora principal | 4,58 |
| Vía troncal | 3,32 |
| Vía distribuidora complementaria | 1,54 |
| Vía local | 0,56 |

Y por tipo de calle: el 81 % de las avenidas tiene colectivos contra el **1 % de
los pasajes**. Si el filtro de rumbo no funcionara, los pasajes estarían llenos
de líneas fantasma.

**Control visual con la línea 65.** Se eligió porque su recorrido es conocido y
se puede contrastar con el mapa oficial del GCBA. Las 347 cuadras atribuidas
dibujan: Constitución → Barracas → Av. Caseros → Av. La Plata → Av. Corrientes →
Chacarita → Av. Álvarez Thomas → Cabildo → Juramento → Belgrano C. Coincide.

La página web ([web/index.html](../web/index.html)) deja hacer este control con
cualquier línea: al elegir una del desplegable dibuja las cuadras atribuidas
como una banda ancha y encima, fina, la traza del GTFS. Si la atribución está
bien, la traza cae justo sobre la banda.

## Limitaciones conocidas

1. **Autopistas.** El 83 % de los tramos de autopista tiene líneas atribuidas,
   con 5,2 de promedio. Parte es real —EPOK tiene una modalidad "EXPRESO
   AUTOPISTA"— pero parte es error: las autopistas porteñas van elevadas sobre
   calles de superficie, y en dos dimensiones no hay forma de separarlas. Para
   el índice de cuadra ideal conviene excluir `AUTOPISTA`, `SUBIDA`, `BAJADA` y
   `ENLACE AUTOPISTA`: nadie vive ahí.
2. **1.729 cuadras sin barrio** en el callejero (el campo viene vacío). Afecta
   los agregados por barrio, no la atribución.
3. **28 senderos con líneas atribuidas.** Son caminos de parque que corren
   paralelos y pegados a una avenida. Es ruido menor.
4. **Todo hereda la vigencia del GTFS 2019.** Ver
   [02-data-sources.md](02-data-sources.md): la geometría describe bien el 87 %
   de la red actual.

## Qué falta

El resultado de este paso es "cuántas líneas pasan". Para el índice de cuadra
ideal falta el otro lado: **cuántas se pueden tomar caminando**, que es el Paso
B (grafo peatonal sobre el callejero + paradas del GTFS a 400 m). Recién ahí se
puede buscar la cuadra con ruido cero y acceso alto.
