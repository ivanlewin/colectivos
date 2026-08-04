# Acceso caminando

Cómo se responde "¿a cuántas líneas llego a pie desde esta cuadra?" — el otro
lado del [Paso A](03-attribution.md), que cuenta las que pasan por encima.

Implementado en [scripts/09_walking_access.py](../scripts/09_walking_access.py)
→ `output/blocks_access.csv`.

## El problema

Medir el acceso en línea recta es cómodo y está mal. Un radio de 400 m alrededor
de una cuadra de Caballito atraviesa las vías del Sarmiento; uno en Barracas
cruza el Riachuelo; uno en Villa Devoto se mete en Provincia por encima de la
General Paz. En los tres casos cuenta paradas a las que no se llega caminando.

En una ciudad cortada por vías, autopistas y un río, la única medida honesta es
la **distancia sobre la red de calles**.

## El método

1. **Grafo peatonal a partir del callejero.** Cada cuadra es una arista con su
   largo real en metros; cada esquina, un nodo. Las puntas se unen con 2 m de
   tolerancia, porque el callejero no siempre cierra las esquinas con
   coordenadas idénticas.

   Las autopistas y sus subidas, bajadas y enlaces quedan afuera: por ahí no se
   camina, y dejarlas adentro abriría atajos que no existen.

2. **Qué líneas paran en cada parada.** Sale directo de las **paradas
   vigentes** de la Secretaría de Transporte (junio de 2026), que traen la
   lista de líneas y su sentido en cada parada. Reemplazan a las del GTFS 2019,
   que era la única fuente cuando se escribió este paso.

   Se agrupa por línea **y sentido**, que es la granularidad que trae el
   dataset y la que corresponde: llegar a la parada de la ida no da acceso a la
   vuelta, que suele ir por otra calle.

3. **Cada parada se engancha a su cuadra más cercana**, y se calcula la
   distancia hasta cada una de sus dos puntas. Eso importa: una parada a mitad
   de cuadra no está en la esquina, y arrancar el cálculo desde la esquina más
   próxima sumaría hasta 50 m de error por parada.

4. **Un Dijkstra multi-origen por línea y sentido**, cortado a 400 m — unos 5
   minutos caminando, el umbral habitual en planificación de transporte. Una
   cuadra alcanza ese servicio si alguna de sus dos puntas cae dentro del corte.

   La línea se cuenta una sola vez aunque se alcancen sus dos sentidos; los
   colectivos por hora se suman, porque ida y vuelta son servicios distintos.

## Resultado

| | |
|---|---|
| Líneas con paradas | **137** |
| Combinaciones línea + sentido | 293 |
| Paradas enganchadas al callejero | 6.836 de 6.852 |
| Mediana de líneas a pie por cuadra | **6** |
| Máximo | 39 |
| Cuadras sin ninguna línea a pie | 1.254 (3,9 %) |

Por barrio, los extremos:

| Mejor conectados | líneas · col/h | Peor conectados | líneas · col/h |
|---|---|---|---|
| San Nicolás | 22,9 · 637 | Villa Soldati | 2,2 · 56 |
| Constitución | 19,8 · 698 | Mataderos | 4,7 · 129 |
| Monserrat | 18,5 · 611 | Villa Riachuelo | 4,7 · 114 |
| Balvanera | 17,1 · 524 | Villa Pueyrredón | 5,0 · 140 |
| San Telmo | 15,9 · 441 | Paternal | 5,0 · 135 |

## Cómo se validó

**La forma del grafo.** Con 31.961 cuadras quedan 18.148 esquinas, y la
distribución de grados es la de una ciudad en damero: 9.990 esquinas de grado 4
(cruce de dos calles), 6.404 de grado 3 (una calle que termina contra otra), 720
de grado 2. Sólo 153 esquinas quedan sin conexión. Si el pegado de puntas
hubiera fallado, el grado 1 dominaría y la red estaría rota en pedazos.

**El ranking de barrios.** San Nicolás y Constitución arriba, Villa Soldati
último por lejos. Coincide con lo que se sabe de la conectividad de la Ciudad, y
ninguno de los dos extremos está metido en el método: salen de los datos.

## Limitaciones conocidas

**El sesgo de borde no se pudo arreglar, y se midió por qué.** Las cuadras
pegadas a la General Paz o al Riachuelo tienen medio radio de caminata fuera de
la Ciudad, donde no hay paradas en el dataset vigente. Se probó completarlo con
las paradas del GTFS que caen fuera de CABA, y el resultado fue contundente: de
**30.802 paradas foráneas, ninguna** quedó a menos de 60 m de una calle
porteña, y **cero cuadras** ganaron una sola línea.

El problema no son las paradas sino el grafo: el callejero termina en el límite
de la Ciudad, así que aunque la parada exista no hay por dónde caminar hasta
ella. Arreglarlo de verdad necesita una red de calles del conurbano, que el
proyecto no tiene. El sesgo sigue en pie y afecta justo a los barrios que ya
aparecen peor conectados.

**Las frecuencias siguen saliendo del GTFS 2019**, la única fuente que las
tiene, y allí vienen por ramal con un `direction_id` 0/1 que no se puede mapear
con confianza al `I`/`V` de las paradas. Así que el total de cada línea se
reparte en partes iguales entre sus sentidos: ida y vuelta suelen tener servicio
simétrico, el error queda acotado, y una cuadra que alcanza los dos sentidos
recupera el total exacto. Tres líneas —119, 145 y 164— no están en el GTFS y
suman 0 colectivos por hora, aunque sí cuentan como líneas.

**El radio es una decisión, no un dato.** 400 m es una convención. Con 300 m el
ranking se concentra todavía más en el microcentro; con 800 m se aplana. Conviene
que sea ajustable en la visualización en vez de quedar fijo.

**Contar líneas y contar servicio son dos cosas distintas**, y por eso ahora se
miden las dos. Ver [05-service-frequency.md](05-service-frequency.md).

## Adelanto del Paso C

Cruzando las dos métricas aparece lo que buscaba el proyecto: de las 16.671
cuadras sin ningún colectivo encima, **549 tienen 20 o más líneas a pie**.

Eso se convirtió en el índice del [Paso C](06-ideal-block-index.md), que agrega
la tercera pieza —el ruido de tránsito— y lo lleva al mapa con el peso
ajustable.
