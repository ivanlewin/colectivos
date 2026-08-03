# El índice de cuadra ideal

La pregunta que originó el proyecto: **¿dónde conviene vivir si uno quiere no
tener colectivos por la puerta pero sí muchos a la vuelta?**

Combina las dos métricas anteriores —el ruido del [Paso A](03-attribution.md) y
el acceso del [Paso B](04-walking-access.md)— en un solo número.

Implementado en dos lugares a propósito:
[`scripts/10_ideal_blocks.py`](../scripts/10_ideal_blocks.py) para el registro y
las constantes, y [`web/index.html`](../web/index.html) para el mapa.

## La fórmula

```
acceso  = min(acceso_de_la_cuadra / P99_acceso, 1)     -> 0..1
ruido   = min(ruido_de_la_cuadra  / P95_ruido,  1)     -> 0..1
puntaje = max(0, acceso - peso * ruido) * 100          -> 0..100
```

### Por qué el peso es un control y no un número

Cuánto molesta un colectivo pasando por la ventana no es un dato: es una
preferencia. Fijarlo sería inventar una respuesta. El control de la página lo
mueve entre 0 y 2, y el mapa se repinta en vivo:

| Peso | Qué significa | Cuadras sobre 60 | Barrios que encabezan |
|---|---|---|---|
| 0,0 | El ruido no importa: acceso puro | 3.050 | Retiro, Palermo |
| 0,5 | El ruido pesa la mitad que el acceso | 1.597 | Retiro, San Nicolás, Balvanera |
| 1,0 | Punto neutro: se compensan exactamente | 1.345 | Retiro, San Nicolás, Balvanera |
| 2,0 | Sólo sobreviven las cuadras casi sin colectivos | 1.188 | Retiro, San Nicolás, Balvanera |

### Por qué dos percentiles distintos

Normalizar contra el máximo aplastaría toda la escala: el máximo de ruido es
Av. Santa Fe con 892 colectivos por hora, un caso extremo contra el que
cualquier calle normal da casi cero.

Pero los dos lados necesitan cosas distintas:

- **El acceso usa el p99** (26 líneas / 861 colectivos por hora) porque es lo
  que tiene que **ordenar el ranking**. Con el p95 saturaban 1.753 cuadras en
  el puntaje máximo y arriba quedaba un empate inútil. Con el p99 saturan 369.
- **El ruido usa el p95** (6 líneas / 111 colectivos por hora) porque ahí no
  hace falta discriminar, sólo penalizar. Seis líneas por la puerta ya son
  muchas; que a partir de ahí penalice igual no cambia nada.

### El recorte en cero

Una cuadra donde el ruido supera al acceso no es "peor que nada": simplemente
no califica. Sin el recorte la escala se estiraría hacia negativos que no
significan nada, y el mapa gastaría medio rango de color en distinguir grados
de "no".

### Qué queda afuera

Las cuadras donde no vive nadie: autopistas y sus subidas, bajadas y enlaces,
puentes, túneles y senderos de parque. Son 857 de 31.961. Aparecen en gris como
"no califica".

## El resultado

Con peso 1,0 y medido en líneas, las mejores cuadras — una por calle, porque
doce veces la misma no ayuda a elegir:

| Cuadra | Barrio |
|---|---|
| Ciudadela 1181–1200 | Constitución |
| Pablo Giorello | Constitución |
| Tacuarí 1501–1600 | Constitución |
| O'Brien 1101–1200 | Constitución |
| Brasil 1401–1500 | Constitución |
| Marcelo T. de Alvear 401–500 | Retiro |
| Dr. Enrique Finochietto | Barracas |
| Reconquista 701–800 | San Nicolás |
| Castelli 201–300 | Balvanera |

Medido en colectivos por hora aparece **Palermo** —Borges, Güemes, Gurruchaga,
Darregueyra—: menos líneas cerca, pero el corredor de Santa Fe a una cuadra.

Son exactamente el perfil que se buscaba: calles laterales a una o dos cuadras
de un centro de trasbordo o de un corredor pesado, sin colectivos por la
puerta.

## Cómo se validó

**Las dos implementaciones se cruzan.** El ranking que calcula el navegador
coincide exactamente con el de `10_ideal_blocks.py`, que corre sobre el CSV por
un camino independiente. Son dos implementaciones de la misma fórmula, en dos
lenguajes, sobre dos representaciones de los datos.

## Límites

**El puntaje mide accesibilidad, no habitabilidad.** El ranking lo encabezan
cuadras de Retiro y Constitución que están pegadas a las terminales: mucho
acceso y poco tránsito de colectivos por esa cuadra puntual. Si son buenos
lugares para vivir depende de todo lo que este índice no mira — seguridad,
ruido de otras fuentes, servicios, precio. Padre Carlos Mugica, por ejemplo,
puntúa altísimo y es la Villa 31.

**Saturación arriba.** 369 cuadras llegan a 100 y el índice ya no las
distingue entre sí. En el mapa no molesta; en la lista se desempata por acceso
crudo.

**Hereda todo lo anterior**: la vigencia del GTFS 2019, el sesgo de borde de
las paradas del conurbano, el instante de referencia de las 08:00 y los
umbrales del Paso A. Ver cada documento.

**Las constantes están duplicadas.** `NORM` en `web/index.html` tiene que
coincidir con lo que imprime `10_ideal_blocks.py`. Si cambian los datos hay que
actualizar las dos.
