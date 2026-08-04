# Las paradas vigentes: medir el error y taparlo

Todo el análisis geométrico se apoya en el GTFS de 2019. Hasta acá el proyecto
sabía que eso era un riesgo, pero no cuánto.

Las **paradas de colectivo** publicadas por la Secretaría de Transporte y Obras
Públicas —revisión de **junio de 2026**— permiten medirlo, y de paso corregir
buena parte.

## El caso que lo destapó

Probando el mapa apareció que por Lerma no pasa ningún colectivo, cuando había
memoria de líneas que vienen por Scalabrini Ortiz y doblan por ahí o por Jufré.

El diagnóstico llevó tres pasos:

1. **¿Está la traza en el GTFS y no la matcheamos?** No. Cuando un colectivo
   circula de verdad por una calle, la traza alineada está a **0,5–2 m** del
   eje (Araoz, Thames). En Lerma 302–400 la más cercana está a **142 m**: es la
   calle paralela. El filtro de rumbo estaba haciendo lo correcto.
2. **¿Lo tiene el CNRT 2023?** Tampoco.
3. **¿Lo tienen las paradas vigentes?** Sí, en parte: **Lerma no tiene ninguna
   parada, y Jufré tiene una de la línea 145** en el 210.

Y la 145 es justamente una de las líneas que **no existe en el GTFS 2019**.

## El dataset

`https://data.buenosaires.gob.ar/dataset/colectivos-paradas` → CSV de 0,8 MB.

| | |
|---|---|
| Publicado por | Secretaría de Transporte y Obras Públicas |
| Última revisión | 18 de junio de 2026 |
| Paradas | 6.959 |
| Líneas distintas | **137** |

Cada parada trae `CALLE`, `ALT PLANO`, coordenadas, barrio y hasta **seis
líneas** en `L1..L6`, cada una con su sentido en `l1_sen..l6_sen`.

Es la única fuente del proyecto que dice **directamente** qué líneas paran
dónde, sin geometría de por medio.

Detalles sucios: las coordenadas usan coma decimal, y una fila trae `V` donde
debería ir el número de línea.

## Es más completa que el padrón de EPOK, y eso escondía un error

Cinco líneas aparecen en las paradas y **no** en el padrón vigente de EPOK que
veníamos usando como referencia: **5, 6, 99, 112 y 175**.

No era sólo una curiosidad. El Paso A filtraba las trazas del GTFS contra ese
padrón, así que esas cinco líneas quedaban descartadas **aunque el GTFS sí las
tiene**: 5 con 4 trazas, 6 con 8, 99 con 2, 112 con 2, 175 con 2. Cinco líneas
con geometría propia afuera del mapa por un padrón incompleto.

Ahora el padrón es la unión de los dos, y las líneas realmente ausentes del
GTFS quedaron en tres: **119, 145 y 164**. El acierto contra las paradas subió
de 89,8 % a **91,4 %** sólo por esto.

## Cuánto le errábamos: 10,2 %

La prueba es directa: si hay una parada de la 145 en Jufré 210, la 145 pasa por
esa cuadra. Si nuestra atribución no la tiene, le erramos.

Medido en [`scripts/11_validate_stops.py`](../scripts/11_validate_stops.py):

| | |
|---|---|
| Pares parada-línea evaluados | 11.293 |
| La cuadra ya tenía esa línea | 10.321 (**91,4 %**) |
| No la tenía | 972 (**8,6 %**) |

Y el error tiene un patrón nítido:

| Línea | Faltan | De | Causa |
|---|---|---|---|
| 145 | 167 | 167 | no existe en el GTFS 2019 |
| 8 | 115 | 216 | el recorrido cambió desde 2019 |
| 6 | 91 | 91 | no está en el padrón EPOK |
| 99 | 88 | 88 | no está en el padrón EPOK |
| 119 | 56 | 56 | no existe en el GTFS 2019 |
| 90 | 37 | 153 | el recorrido cambió |
| 164 | 36 | 36 | no existe en el GTFS 2019 |
| 166 | 28 | 79 | el recorrido cambió |

Es una **cota inferior** del error: una línea pasa por muchas más cuadras que
las que tienen parada, así que esto detecta los faltantes pero no los sobrantes.

## Enganchar una parada a su cuadra no es trivial

La cuadra más cercana no siempre es la correcta. La parada de **Jufré 210 está
a 23 m del eje de Julián Álvarez y a 29 m del de Jufré**: tomar la más cercana
la asigna a la transversal.

Por eso se usa el nombre de calle que trae la parada. Entre las cuadras a menos
de 45 m se elige la más cercana **que además se llame igual**, y sólo si
ninguna coincide se cae a la más cercana a secas.

Comparar nombres tampoco es literal: las paradas dicen `RAUL SCALABRINI ORTIZ
AV.` y el callejero `SCALABRINI ORTIZ, RAUL AV.`. Se comparan **conjuntos de
palabras** sin acentos ni puntuación (Jaccard ≥ 0,6), así el orden no importa.

## Cómo se incorpora

En [`scripts/07_attribute_lines.py`](../scripts/07_attribute_lines.py): si hay
una parada vigente de una línea sobre una cuadra, esa línea se agrega, diga lo
que diga el GTFS.

El resultado pasa de 129 a **137 líneas** en el mapa, y de 12.861 a **13.038
cuadras** con al menos una línea. Las cinco que estaban completamente ausentes:

| Línea | Cuadras que gana |
|---|---|
| 145 | 152 |
| 99 | 87 |
| 6 | 86 |
| 119 | 53 |
| 164 | 35 |

La salida guarda **dos columnas**: `lines_gtfs` con lo que encontró el método
geométrico solo, y `lines` con el resultado final parcheado. La validación mide
contra la primera — si midiera contra la segunda daría 100 % por construcción,
porque esa columna ya incorpora estas mismas paradas.

## Límites

**El parche sólo alcanza a las cuadras con parada.** Entre parada y parada el
recorrido sigue sin conocerse. Para una línea ausente del GTFS como la 145, el
mapa muestra sus 152 cuadras con parada, no su recorrido continuo: se ve
punteado, no como una traza.

**No corrige los sobrantes.** Si el GTFS 2019 dice que una línea pasa por una
calle de la que ya se fue, las paradas no lo desmienten: sólo agregan.

**El Paso B sigue usando las paradas del GTFS 2019**, no éstas. Cambiarlo es
una mejora clara pero necesita resolver de dónde salen las frecuencias, que
este dataset no trae. Queda pendiente.
