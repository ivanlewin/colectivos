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

2. **Qué líneas paran en cada parada.** Encadenando `stop_times.txt` →
   `trips.txt` → `routes.txt`, filtrado al padrón vigente de EPOK. En el feed
   *frequency* que usa el proyecto son 17 MB y entran en memoria; en el GTFS
   completo el mismo archivo pesa 1,4 GB y habría que procesarlo en streaming.

3. **Cada parada se engancha a su cuadra más cercana**, y se calcula la
   distancia hasta cada una de sus dos puntas. Eso importa: una parada a mitad
   de cuadra no está en la esquina, y arrancar el cálculo desde la esquina más
   próxima sumaría hasta 50 m de error por parada.

4. **Un Dijkstra multi-origen por línea**, cortado a 400 m — unos 5 minutos
   caminando, el umbral habitual en planificación de transporte. Una cuadra
   tiene acceso a esa línea si alguna de sus dos puntas cae dentro del corte.

## Resultado

| | |
|---|---|
| Líneas del padrón con paradas | 129 |
| Paradas enganchadas al callejero | 8.399 |
| Mediana de líneas a pie por cuadra | **6** |
| Máximo | 37 |
| Cuadras sin ninguna línea a pie | 1.402 (4,4 %) |

Por barrio, los extremos:

| Mejor conectados | | Peor conectados | |
|---|---|---|---|
| San Nicolás | 20,6 | Villa Soldati | 2,1 |
| Constitución | 19,5 | Villa Pueyrredón | 4,7 |
| Monserrat | 18,0 | Villa Lugano | 4,8 |
| Balvanera | 16,7 | Mataderos | 4,9 |
| San Telmo | 15,8 | Villa Riachuelo | 4,9 |

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

**Paradas del conurbano.** De las 42.464 paradas del GTFS, sólo 8.399 caen a
menos de 60 m de una calle de CABA. El resto es del Gran Buenos Aires y se
descarta, porque el grafo peatonal es el callejero porteño y no tiene con qué
conectarlas. Consecuencia: **las cuadras pegadas a la General Paz o al Riachuelo
tienen el acceso subestimado**, porque una parada del otro lado del límite no se
cuenta aunque esté a 200 m caminando. Es el sesgo más importante de este paso, y
afecta justo a los barrios que ya aparecen peor conectados.

**El radio es una decisión, no un dato.** 400 m es una convención. Con 300 m el
ranking se concentra todavía más en el microcentro; con 800 m se aplana. Conviene
que sea ajustable en la visualización en vez de quedar fijo.

**Cuenta líneas, no servicio.** Una línea que pasa cada 4 minutos y otra que pasa
cada 40 suman lo mismo. Pesar por frecuencia real usando `frequencies.txt` es el
siguiente refinamiento.

**Hereda la vigencia del GTFS 2019**, igual que el Paso A. Y arrastra el sesgo de
que las paradas son las de 2019, que cambian más seguido que los recorridos.

## Adelanto del Paso C

Cruzando las dos métricas ya aparece lo que buscaba el proyecto. De las 17.016
cuadras sin ningún colectivo encima, **429 tienen 20 o más líneas a pie**. Las
primeras:

| Líneas a pie | Cuadra | Barrio |
|---|---|---|
| 36 | Ciudadela | Constitución |
| 32 | Tacuarí | Constitución |
| 32 | O'Brien | Constitución |
| 31 | Brasil | Constitución |
| 30 | Marcelo T. de Alvear | Retiro |
| 30 | Enrique Finochietto | Barracas |
| 29 | Reconquista | San Nicolás |
| 29 | Castelli | Balvanera |

Son exactamente lo que se buscaba: calles laterales a una o dos cuadras de los
centros de trasbordo, sin colectivos por la puerta. Falta convertir esto en un
índice con pesos ajustables y llevarlo al mapa.
