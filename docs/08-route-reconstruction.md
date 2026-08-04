# Reconstruir un recorrido desde sus paradas

El parche de paradas de [07-current-stops.md](07-current-stops.md) tapa el
agujero sólo donde hay parada. Una línea ausente del GTFS 2019, como la 145,
quedaba punteada: 152 cuadras sueltas en vez de un recorrido.

Entre dos paradas consecutivas el colectivo circula por algo. Este paso
reconstruye ese "algo".

## El método

No hace falta ordenar las paradas de una línea —dato que el CSV no trae, y que
es difícil de inferir cuando la línea tiene varios ramales—. Alcanza con unir
**cada par de paradas cercanas** de la misma línea y sentido por el camino más
corto sobre la red de calles circulables: las consecutivas están a 200–400 m y
se unen solas, las de ramales distintos quedan lejos y no se tocan.

Tres filtros evitan inventar recorridos:

| Filtro | Valor | Para qué |
|---|---|---|
| `PAIR_RADIUS_M` | 500 m | sólo une paradas cercanas en línea recta |
| `MAX_PATH_M` | 750 m | techo absoluto del camino |
| `MAX_DETOUR` | 1,8× | techo relativo a la línea recta |

El techo relativo es el que más trabaja. Doblar una esquina da una relación de
~1,4; rodear una manzana entera da más, y eso ya es señal de que esas dos
paradas no son consecutivas.

La red excluye lo que un colectivo no puede transitar: senderos de parque,
pasajes peatonales y todo lo que el callejero marca con `sentido = PEATONAL`.

**Se ignoran las manos únicas.** El callejero trae `sentido`, pero no de qué
punta a qué punta corre la geometría de cada cuadra, así que aplicarlo tiene
tanto riesgo de invertirlo como de acertarlo. El techo de rodeo acota el daño.

## Cuánto se le puede creer

La reconstrucción es una **inferencia**, no un dato. Se la puede medir contra
las líneas que el GTFS 2019 sí describe bien: si para ésas la reconstrucción
coincide con la atribución geométrica, el método sirve.

Sobre 117 líneas con más de 100 cuadras atribuidas:

| | |
|---|---|
| Precisión mediana | **84 %** |
| Recall mediano | 61 % |

- **Precisión 84 %**: de cada 100 cuadras que la reconstrucción propone, 84 las
  confirma el GTFS. Y es un piso, no un techo: parte del 16 % restante son
  cambios de recorrido reales posteriores a 2019. La línea 8 —la que más
  cambió— da 41 % de precisión, que en su caso es lo esperable, no un error.
- **Recall 61 %**: se pierde el resto porque las paradas son más ralas que el
  recorrido, y porque los tramos fuera de CABA no tienen paradas en este
  dataset.

## Se aplica sólo donde hace falta

Con 84 % de precisión, sumarle la reconstrucción a una línea que el GTFS ya
describe bien sólo puede meter ruido. Así que se aplica **únicamente a las
líneas que el GTFS 2019 no describe bien**.

El criterio es objetivo y se calcula solo: qué fracción de las cuadras donde la
línea tiene parada ya la tenía el método geométrico. Debajo del 70 %, entra la
reconstrucción.

Dan 11 de 137 líneas:

| Línea | El GTFS cubre | de sus paradas |
|---|---|---|
| 5, 6, 99, 112, 119, 145, 164, 175 | **0 %** | ausentes del GTFS |
| 8 | 48 % | 192 |
| 179 | 50 % | 2 |
| 166 | 67 % | 70 |

Las otras 126 conservan la atribución del GTFS sin tocar.

## El resultado

| | Antes | Después |
|---|---|---|
| Líneas en el mapa | 129 | **137** |
| Cuadras con al menos una línea | 12.861 | **13.324** |
| Cuadras de la línea 145 | 152 punteadas | **484 continuas** |

En la página, esas ocho líneas también aparecen en el desplegable: su geometría
se arma pegando las cuadras del callejero que se les atribuyeron. Se ve menos
suave que una traza GTFS, y el panel lo aclara —"recorrido reconstruido a
partir de sus paradas"— para no presentarlo como dato duro.

## Límites

**Es una inferencia.** Uno de cada seis tramos puede estar mal. Para las ocho
líneas ausentes del GTFS la alternativa era no tener nada, así que conviene;
para el resto no se aplica.

**No corrige sobrantes.** Si el GTFS dice que una línea pasa por una calle de
la que ya se fue, ni las paradas ni la reconstrucción lo desmienten: las dos
fuentes sólo agregan.

**El umbral del 70 % es una decisión, no un óptimo.** Sube o baja cuántas
líneas reciben la corrección; no se calibró contra nada porque no hay verdad
independiente contra la cual hacerlo.

**Hereda el enganche de paradas a cuadras** descrito en
[07-current-stops.md](07-current-stops.md), con su desambiguación por nombre de
calle.
