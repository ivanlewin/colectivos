# El índice de cuadra ideal

La pregunta que originó el proyecto: **¿dónde conviene vivir si uno quiere no
tener tránsito pesado por la puerta pero sí muchos colectivos a la vuelta?**

Combina el ruido —el del [Paso A](03-attribution.md) más el del tránsito
general— con el acceso del [Paso B](04-walking-access.md).

Implementado en dos lugares a propósito:
[`scripts/10_ideal_blocks.py`](../scripts/10_ideal_blocks.py) para el registro y
las constantes, y [`web/index.html`](../web/index.html) para el mapa.

## La fórmula

```
acceso     = min(acceso_de_la_cuadra / P99_acceso, 1)     -> 0..1
colectivos = min(ruido_de_la_cuadra  / P95_ruido,  1)     -> 0..1
tránsito   = (velocidad_máxima - 20) / (100 - 20)         -> 0..1
ruido      = max(colectivos, tránsito)                    -> 0..1
puntaje    = max(0, acceso - peso * ruido) * 100          -> 0..100
```

## Las dos fuentes de ruido

La primera versión contaba sólo colectivos, y dejaba pasar un error grosero:
**la 9 de Julio a la altura de Corrientes puntuaba 85 sobre 100.**

Hay dos cosas detrás de eso, y sólo una es un bug.

**El artefacto.** El callejero parte la 9 de Julio en calzadas paralelas —70
cuadras para su recorrido— y con 140 m de ancho los colectivos que circulan por
un lado caen a más de los 15 m de tolerancia de la calzada de enfrente. Trece
de esas 70 cuadras quedan con cero colectivos atribuidos.

**El problema de fondo.** Aunque la atribución fuera perfecta, *una avenida no
es tranquila aunque no pase ningún colectivo por ella*. El índice medía ruido
de colectivos y lo llamaba tranquilidad.

La solución no fue excluir avenidas —un corte binario— sino graduar el ruido de
tránsito usando como proxy la **velocidad máxima legal** de cada tipo de vía.
Es un dato externo al análisis, sale del Código de Tránsito de la Ciudad
([Ley 2148, art. 6.2.2](https://juristeca.jusbaires.gob.ar/compilacion-normativa-juristeca/ley-2148/tit-6/)),
y ordena exactamente lo que se quiere ordenar:

| Tipo de vía | Velocidad máxima | Ruido de tránsito | Cuadras |
|---|---|---|---|
| Pasajes, peatonales, senderos | 20 km/h | 0,00 | 1.973 |
| Calles y colectoras, boulevards | 40 km/h | 0,25 | 22.622 |
| Avenidas (y puentes, túneles) | 60 km/h | 0,50 | 7.060 |
| Autopistas, subidas, bajadas, enlaces | 100 km/h | 1,00 | 306 |

Se toma el **máximo** de las dos fuentes y no la suma: una avenida sin
colectivos sigue siendo una avenida, y un pasaje por el que pasan diez líneas
sigue siendo ruidoso. Alcanza con que una de las dos cosas sea cierta.

### El efecto sobre la 9 de Julio

Las cinco cuadras sin colectivos atribuidos, con peso 1,0:

| Líneas a pie | Sólo colectivos | Con tránsito |
|---|---|---|
| 23 | 88,5 | **38,5** |
| 22 | 84,6 | **34,6** |
| 22 | 84,6 | **34,6** |
| 21 | 80,8 | **30,8** |
| 18 | 69,2 | **19,2** |

## El peso es un control, no un número

Cuánto molesta el ruido no es un dato: es una preferencia. El control de la
página lo mueve entre 0 y 2, y el mapa se repinta en vivo:

| Peso | Qué significa | Cuadras sobre 60 | Barrios que encabezan |
|---|---|---|---|
| 0,0 | El ruido no importa: acceso puro | 3.050 | Retiro, Palermo |
| 0,5 | El ruido pesa la mitad que el acceso | 940 | Retiro, San Nicolás, Constitución |
| 1,0 | Punto neutro | 326 | Retiro, San Nicolás, Liniers |
| 2,0 | Sólo lo más tranquilo sobrevive | 48 | Caballito, Nueva Pompeya, Constitución |

Con el ruido de tránsito incorporado, el peso discrimina mucho más: antes iba
de 3.050 a 1.188 cuadras sobre 60, ahora de 3.050 a 48.

## Por qué dos percentiles distintos

Normalizar contra el máximo aplastaría toda la escala: el máximo de ruido de
colectivos es Av. Santa Fe con 892 por hora, un caso extremo contra el que
cualquier calle normal da casi cero.

Pero los dos lados necesitan cosas distintas:

- **El acceso usa el p99** (26 líneas / 861 colectivos por hora) porque es lo
  que tiene que **ordenar el ranking**. Con el p95 saturaban 1.753 cuadras en
  el puntaje máximo y arriba quedaba un empate inútil. Con el p99 saturan 369.
- **El ruido de colectivos usa el p95** (6 líneas / 111 por hora) porque ahí no
  hace falta discriminar, sólo penalizar. Seis líneas por la puerta ya son
  muchas.

## El recorte en cero

Una cuadra donde el ruido supera al acceso no es "peor que nada": simplemente
no califica. Sin el recorte la escala se estiraría hacia negativos que no
significan nada, y el mapa gastaría medio rango de color en distinguir grados
de "no".

## Qué queda afuera del ranking

Las cuadras sin domicilios: senderos de parque, puentes, túneles, autopistas y
sus ramas. Son 857 de 31.961. Los senderos son el caso que importa: tienen
velocidad de pasaje y sin esta lista encabezarían el ranking. Las autopistas ya
quedan afuera solas, porque su ruido de tránsito es 1.

## El resultado

Con peso 1,0 y medido en líneas, una cuadra por calle:

| Puntaje | Tipo | Cuadra | Barrio |
|---|---|---|---|
| 100 | pasaje | Ciudadela | Constitución |
| 100 | pasaje | Pablo Giorello | Constitución |
| 96 | pasaje | Bueras | Liniers |
| 92 | pasaje | Casco | Liniers |
| 92 | pasaje | Moisés Lebensohn | Nueva Pompeya |
| 92 | pasaje | Corina Kavanagh | Retiro |
| 85 | pasaje | Carabelas | San Nicolás |
| 81 | pasaje | Timbó | Flores |
| 77 | pasaje | Bertres | Caballito |

El ranking pasó a estar dominado por **pasajes**, que es la respuesta correcta:
20 km/h, sin colectivos, y algunos con acceso excelente. Corina Kavanagh, a
media cuadra de Plaza San Martín, es el ejemplo de manual.

Bajando el peso a 0,5 vuelven a aparecer calles: Beruti y Godoy Cruz en
Palermo, Reconquista en San Nicolás.

## Cómo se validó

**Las dos implementaciones se cruzan.** El ranking que calcula el navegador
coincide exactamente con el de `10_ideal_blocks.py`, que corre sobre el CSV por
un camino independiente. Dos implementaciones de la misma fórmula, en dos
lenguajes, sobre dos representaciones de los datos.

**El caso que falló tiene su propio control.** El script imprime el puntaje de
las cuadras de la 9 de Julio con y sin el término de tránsito, así la
regresión se detecta sola si alguien cambia la fórmula.

## Límites

**El puntaje mide accesibilidad y tipo de vía, no habitabilidad.** No sabe nada
de seguridad, precio, servicios, ruido de bares o de obras. Padre Carlos Mugica
puntuaba altísimo en la versión anterior y es la Villa 31.

**La velocidad máxima es un proxy, no una medición.** Una calle de 40 km/h
puede ser un embudo de tránsito y un pasaje puede desembocar en una avenida.
Medir tránsito real requeriría otra fuente de datos.

**El ruido de colectivos y el de tránsito no son independientes**: las avenidas
concentran las dos cosas. Tomar el máximo evita contarlas dos veces.

**Saturación arriba.** 369 cuadras llegan a 100 en el término de acceso. En el
mapa no molesta; en la lista se desempata por acceso crudo.

**Hereda todo lo anterior**: la vigencia del GTFS 2019, el sesgo de borde de
las paradas del conurbano, el instante de referencia de las 08:00 y los
umbrales del Paso A.

**Las constantes están duplicadas.** `NORM` en `web/index.html` tiene que
coincidir con lo que imprime `10_ideal_blocks.py`. El ruido de tránsito, en
cambio, se precalcula en Python y viaja en los datos, así que ahí no hay dos
verdades.
