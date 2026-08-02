# El dataset EPOK de recorridos

Caracterización completa de `data/routes.json`, descargado del portal EPOK del
Gobierno de la Ciudad de Buenos Aires el 2026-08-02.

Reproducible con `bash scripts/run_all.sh`; las salidas quedan en
[output/](../output/).

## Origen

```
https://epok.buenosaires.gob.ar/getGeoLayer/?categoria=colectivos&formato=geojson
```

GeoJSON `FeatureCollection` de ~3,5 MB.

Se llegó a este endpoint entrando a la página de una línea puntual
(`buenosaires.gob.ar/gcaba_historico/linea-65`), mirando la pestaña Network de
las devtools, y sacándole el parámetro `linea` a la consulta que hace el mapa.
Sin ese parámetro, el endpoint devuelve todas las líneas.

Dos detalles del endpoint que conviene tener a mano:

- Acepta **`srid=4326`** y devuelve lat/lon directamente, evitando toda la
  reproyección descrita más abajo.
- Rechaza pedidos sin `User-Agent` de navegador: responde vacío y curl falla
  con `Empty reply from server`.

Hay un segundo endpoint que usa la misma página:

```
https://epok.buenosaires.gob.ar/colectivos/obtener-recorridos-por-linea/?linea=065&jurisdiccion=D.F.
→ {"recorridos_list": ["065A", "065B"]}
```

Sólo lista los ramales de una línea, para poblar el desplegable del mapa. No
trae calles ni geometría.

## Qué contiene

**1027 features**, todas `LineString` (78.327 vértices en total). Cada feature
es **un ramal de una línea en un sentido** — no una línea.

| Nivel | Campo | Cantidad |
|---|---|---|
| Línea | `linea` | 132 |
| Ramal | `l_r` (línea + ramal) | 518 |
| Recorrido | `l_r_s` (línea + ramal + sentido) | **1027** |

`l_r_s` no tiene repetidos: es la clave natural del dataset. De los 518 ramales,
509 tienen ambos sentidos; 9 traen uno solo (`061A`–`061D`, `062A`–`062C` y
`117C` sólo IDA, `180G` sólo VUELTA).

## Atributos

| Campo | Ejemplo | Notas |
|---|---|---|
| `Id` | `colectivos\|3033` | Único por feature |
| `linea` | `015` | Número de línea, con ceros a la izquierda |
| `Recorrido` | `G` | Letra de ramal. 37 valores: `A`..`Z`, más `NN`, `AA`, etc. |
| `l_r` | `015G` | Línea + ramal |
| `l_r_s` | `015GIDA` | Línea + ramal + sentido — la clave |
| `sentido` | `IDA` | `IDA` (517) / `VUELTA` (510) |
| `razon_soci` | `TRANSPORTES SUR-NOR C.I.S.A.` | 86 empresas distintas |
| `jurisdicci` | `NACIONAL` | `NACIONAL` (896) / `D.F.` (131) |
| `modalidad` | `EXPRESO` | 8 valores: `COMUN`, `EXPRESO`, `COMUN (MDA)`, `EXPRESO AUTOPISTA`, … |
| `desde` / `hasta` | `VALENTIN ALSINA (PARTIDO DE LANUS…)` | Cabeceras en texto libre, sin normalizar |
| `camara` | `CEAP` | Cámara empresarial. 7 valores; **38 features lo traen en `null`** |

Los recorridos van de 5,0 km (`151DIDA`) a 131,7 km (`057BIDA`), con mediana de
29,2 km.

## Qué NO contiene

Sin paradas, frecuencias, horarios, tarifas ni identificadores tipo GTFS
(`route_id`, `shape_id`, `trip_id`). Tampoco un largo precalculado. Es
**geometría de traza + metadatos administrativos**, nada más.

---

## Advertencia 1 — Las coordenadas no son lat/lon

El archivo **no declara un bloque `crs`** y los valores van de ~10.600 a
~149.500. Están en el **sistema plano local de CABA** (metros, Transversa
Mercator con el origen desplazado a 100000/100000):

```
+proj=tmerc +lat_0=-34.6297166 +lon_0=-58.4627 +k=0.999998
+x_0=100000 +y_0=100000 +ellps=intl +units=m +no_defs
```

Si se carga sin reproyectar, los recorridos caen en el Golfo de Guinea.

Verificado en [scripts/03_crs.py](../scripts/03_crs.py) contrastando el primer
vértice de cada recorrido con el barrio que declara su campo `desde`:

| Recorrido | `desde` declarado | Primer vértice reproyectado |
|---|---|---|
| `015GIDA` | Valentín Alsina, Lanús | -34,6625 / -58,4157 ✓ |
| `029AIDA` | La Boca, CABA | -34,6405 / -58,3634 ✓ |
| `060AIDA` | Barracas, CABA | -34,6569 / -58,3794 ✓ |

`EPSG:9498` da un resultado plausible a primera vista pero desplazado ~80 km, y
`EPSG:22185` (Gauss-Krüger faja 5) cae en medio del Pacífico.

La forma práctica de evitar todo esto es pedir el archivo con `srid=4326`.

## Advertencia 2 — "De la Ciudad" es engañoso en las dos direcciones

- **Los recorridos vienen completos, no recortados al ejido de CABA.** El 43 %
  de los vértices cae fuera de la Ciudad, y sólo 228 de los 1027 recorridos
  quedan enteramente adentro. El bounding box real es lat -35,19..-34,04 /
  lon -59,44..-57,93, o sea el AMBA entero.
- **Pero sólo están las líneas que tocan CABA.** Los 1027 recorridos pasan por
  la Ciudad en algún tramo; ninguno la esquiva. Faltan 67 números del rango
  1–199 (3, 5, 6, 11, 13, 14, 16, 18, 27, 30, …), que son las líneas que no
  entran. Tampoco hay líneas municipales del conurbano ni numeración 200+.

## Advertencia 3 — La geometría no sirve para atribuir calles

La separación mediana entre vértices consecutivos es de **261 m**, cuando una
cuadra porteña mide ~110 m. El 29 % de los segmentos supera los 500 m y el más
largo mide 11,7 km en línea recta.

Es decir: **la traza no sigue las calles**, corta manzanas por el medio. Sirve
para dibujar el recorrido en un mapa a escala de ciudad, no para saber por qué
calle pasa un colectivo. El detalle y las alternativas están en
[02-data-sources.md](02-data-sources.md).
