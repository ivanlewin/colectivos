# Dos unidades de medida: líneas y colectivos por hora

Contar líneas es cómodo pero engaña: una línea que pasa cada 4 minutos y otra
que pasa cada 40 suman lo mismo. Por eso cada cuadra se mide en las dos
unidades, y la página deja elegir cuál mirar.

## De dónde sale la frecuencia

El GTFS *frequency* no lista cada viaje: modela el servicio con franjas horarias
y una frecuencia para cada una.

```
frequencies.txt
trip_id,start_time,end_time,headway_secs,exact_times
579HI0,16:02:00,19:04:00,420,0      -> un colectivo cada 7 min
579HI0,19:04:00,21:09:00,750,0      -> cada 12,5 min
```

Para tener un número comparable hay que pararse en un instante concreto. El
proyecto usa **un día hábil a las 08:00**, definido en
[`scripts/common.py`](../scripts/common.py):

- `service_id = HI` (el calendario tiene `HI` hábil, `SI` sábado, `DI` domingo,
  `FI` feriado).
- A las 08:00 está activo el 96 % de los trips de día hábil, el máximo del día.
  A las 22:00 baja al 71 %.

Con eso, `colectivos por hora = 3600 / headway_secs` de la franja que cubre las
08:00. En total, **7.799 colectivos por hora** circulando en la red.

## Por qué se atribuye por ramal y no por línea

Éste es el punto que hace que el número sea correcto o basura.

Los ramales de una línea no pasan por las mismas cuadras. La línea 96 tiene 70
trazas; la 152 tiene 6. Si a una cuadra que ve pasar un solo ramal se le sumara
la frecuencia de toda la línea, el número quedaría inflado varias veces.

Entonces:

- **La atribución geométrica se hace por traza** (`shape_id`), no por línea. El
  método del [Paso A](03-attribution.md) no cambia; cambia la unidad a la que se
  aplica.
- **Las líneas se cuentan una sola vez** aunque pasen varios de sus ramales.
- **Los colectivos por hora se suman**, porque cada ramal son servicios
  distintos: son colectivos que realmente pasan.

Lo mismo en el [Paso B](04-walking-access.md): el Dijkstra se corre por ramal
—unos 500 en vez de 129— y una cuadra suma la frecuencia de cada ramal que
alcanza a pie.

Las dos direcciones se suman también. Para el ruido es lo correcto: un colectivo
que pasa por la ventana molesta vaya para donde vaya.

## Los números

| | Líneas | Colectivos/hora |
|---|---|---|
| Mediana, cuadras con servicio encima | 2 | 30 |
| p90 | 7 | 123 |
| Máximo | 29 | **892** |
| Mediana, alcanzable a pie | 6 | 181 |
| Máximo a pie | 37 | 1.323 |

### Y ordenan distinto, que es el punto

Por cantidad de líneas, arriba están los centros de trasbordo:

| Líneas | Col/hora | Cuadra |
|---|---|---|
| 29 | 534 | Bernardo de Irigoyen, Constitución |
| 26 | 432 | San Martín, Retiro |
| 26 | 403 | Av. Antártida Argentina, Retiro |

Por colectivos por hora, gana **Av. Santa Fe en Palermo**, que tiene menos
líneas pero muchísima más frecuencia:

| Líneas | Col/hora | Cuadra |
|---|---|---|
| 22 | **892** | Av. Santa Fe, Palermo |
| 20 | 855 | Av. Santa Fe, Palermo |
| 21 | 651 | Av. Leandro N. Alem, Retiro |

El mismo efecto aparece en las cuadras tranquilas y bien conectadas. Ordenadas
por líneas a pie domina Constitución; ordenadas por colectivos por hora entra
**Palermo** —Borges, Güemes, Gurruchaga— que tiene menos líneas cerca pero el
corredor de Santa Fe a una cuadra.

## Verificación de los 892 col/hora

Un colectivo cada 4 segundos suena a error, así que se revisó:

- Esa cuadra tiene **176 trazas** atribuidas de 22 líneas distintas: son todos
  los ramales de esas líneas, en las dos direcciones.
- Ninguna traza tiene trips duplicados: cada `shape_id` corresponde a un ramal y
  una dirección, con su propia frecuencia. No hay doble conteo.
- La sospecha era que Santa Fe es mano única y que se estuvieran contando las
  dos direcciones sobre la misma calle. El callejero dice que **esa cuadra es
  `DOBLE`**: Santa Fe es mano única sólo en el tramo de Barrio Norte, y en
  Palermo es doble mano. Las dos direcciones pasan de verdad.

Es la respuesta honesta del modelo para el corredor de colectivos más cargado de
la Ciudad.

## Límites

**Es un instante, no un promedio.** Las 08:00 de un día hábil. Un servicio que
sólo corre de noche o los fines de semana no aparece. Cambiar la hora de
referencia es cambiar una constante en `common.py`.

**Los trips sin franja activa a esa hora quedan en cero**, no excluidos: si una
línea no circula a las 08:00, su aporte a esa cuadra es 0 pero la línea se sigue
contando en la métrica de cantidad. Las dos unidades no cuentan exactamente el
mismo universo, y eso es a propósito.

**Hereda la vigencia del GTFS 2019**, igual que todo lo demás. Las frecuencias
son las que se declaraban entonces, y son el dato que más envejece.
