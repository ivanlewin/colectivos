"""Paso C — El índice de cuadra ideal.

Combina las métricas anteriores en un solo número: **acceso alto, ruido bajo**.
Una cuadra sin tránsito pesado por la puerta pero con muchos colectivos a la
vuelta.

El índice se calcula en el navegador, no acá, porque cuánto pesa el ruido
frente al acceso es una preferencia personal y conviene poder moverla con un
control. Este script existe para dos cosas:

  1. Calcular las constantes de normalización que usa la página, y dejarlas
     documentadas en vez de hardcodeadas a ojo.
  2. Dejar registrado el ranking con el peso por defecto, para poder
     compararlo si algo cambia.

## La fórmula

    acceso   = min(acceso_de_la_cuadra / P99_acceso, 1)      -> 0..1
    colectivos = min(ruido_de_la_cuadra / P95_ruido, 1)      -> 0..1
    tránsito = (velocidad_máxima - 20) / (100 - 20)          -> 0..1
    ruido    = max(colectivos, tránsito)                     -> 0..1
    puntaje  = max(0, acceso - peso * ruido) * 100           -> 0..100

### Las dos fuentes de ruido

Contar sólo colectivos deja pasar un error grosero: la 9 de Julio a la altura
de Corrientes puntuaba 85 sobre 100. El motivo es un artefacto de la
atribución —el callejero parte la avenida en calzadas paralelas y, con 140 m
de ancho, los colectivos caen a más de MATCH_DISTANCE_M de la calzada de
enfrente, así que 13 de sus 70 cuadras quedan con cero colectivos "encima"—
pero el problema de fondo es otro: **una avenida no es tranquila aunque no
pase ningún colectivo por ella.**

Por eso el ruido incorpora el tránsito general, usando como proxy la
**velocidad máxima legal** de cada tipo de vía. Es un dato externo a nuestro
análisis, sale del Código de Tránsito de la Ciudad (Ley 2148, art. 6.2.2), y
ordena exactamente lo que se quiere ordenar: un pasaje es más tranquilo que
una calle, y una calle más que una avenida.

Se toma el **máximo** de las dos fuentes y no la suma: una avenida sin
colectivos sigue siendo una avenida, y un pasaje por el que pasan diez líneas
sigue siendo ruidoso. Alcanza con que una de las dos cosas sea cierta.

### Las normalizaciones

Se normaliza contra un percentil y no contra el máximo porque el máximo es un
caso extremo —Av. Santa Fe con 892 colectivos por hora— que aplastaría toda la
escala contra el piso.

Los dos percentiles son distintos a propósito. El acceso usa el **p99** porque
es lo que tiene que ordenar el ranking: con el p95 saturaban 1.753 cuadras en
el puntaje máximo y arriba quedaba un empate inútil. El ruido de colectivos usa
el **p95** porque ahí no hace falta discriminar, sólo penalizar: seis líneas
por la puerta ya son muchas.

Se recorta en cero: una cuadra donde el ruido supera al acceso no es "peor que
nada", simplemente no califica.

Uso: python3 scripts/10_ideal_blocks.py
"""

import collections
import csv
import json

import common

ACCESS_CSV = common.ROOT / "output" / "blocks_access.csv"
OUTPUT_CSV = common.ROOT / "output" / "ideal_blocks.csv"
# Las constantes de normalización que consume la página. Se escriben acá y
# 08_build_web_data.py las copia a web/data/, para que no haya que
# mantenerlas a mano en el HTML.
NORM_JSON = common.ROOT / "output" / "index_norm.json"

# Peso por defecto del ruido.
DEFAULT_WEIGHT = 1.0

# Velocidad máxima legal por tipo de vía, en km/h. Código de Tránsito y
# Transporte de la Ciudad (Ley 2148, art. 6.2.2):
#
#   pasajes y calles de convivencia ... 20
#   calles y colectoras .............. 40
#   avenidas ......................... 60  (70 en cinco avenidas parque)
#   autopistas y vías rápidas ........ 80 a 100
#
# Se usa como proxy de tranquilidad: es un dato externo al análisis y ordena
# los tipos de vía exactamente como se los quiere ordenar.
SPEED_LIMIT_KMH = {
    "PASAJE": 20,
    "PASAJE PARTICULAR": 20,
    "PASAJE PEATONAL": 20,
    "PASAJE PÚBLICO": 20,
    "CALLE PASAJE PARTICULAR": 20,
    "CALLE PEATONAL": 20,
    "SENDERO": 20,
    "CALLE": 40,
    "BOULEVARD": 40,
    "AVENIDA": 60,
    "PUENTE": 60,
    "TÚNEL": 60,
    "AUTOPISTA": 100,
    "SUBIDA AUTOPISTA": 100,
    "BAJADA AUTOPISTA": 100,
    "ENLACE AUTOPISTA": 100,
}
DEFAULT_SPEED_KMH = 40

# El artículo 6.2.2 no se agota en la regla general: nombra vías concretas con
# límites propios, y varias de ellas el callejero las clasifica de un modo que
# subestima muchísimo su tránsito. La Av. Intendente Cantilo figura como CALLE
# —40 km/h por la regla general— y es una vía rápida de 100.
#
# Se compara por `nomoficial` exacto. Importa que sea exacto: "COLECTORA
# CANTILO, INT." es una colectora y le corresponden los 40 de la regla
# general, no los 100 de la Cantilo.
SPEED_BY_NAME_KMH = {
    # a.1) Vías rápidas, 100 km/h. Las autopistas nombradas en el código
    # (25 de Mayo, Perito Moreno, Cámpora, Illia) ya vienen tipificadas como
    # AUTOPISTA en el callejero, así que no hacen falta acá.
    "CANTILO, INT.": 100,
    "LUGONES, LEOPOLDO AV.": 100,
    "AUTOPISTA DELLEPIANE LUIS TTE. GRAL.": 100,

    # a.2 y a.3) La Gral. Paz tiene tres límites según el tramo y el tipo de
    # calzada: 100 entre Lugones y la AU Palazzo, 80 en el resto de las
    # centrales, 60 en las de tránsito pesado. El callejero la trae entera
    # bajo un solo nombre y sin distinguir calzadas, así que no se puede
    # separar por tramo. Se le asigna el valor del medio: es una
    # simplificación, pero cualquiera de los tres la aleja de los 60 km/h de
    # una avenida común, que es lo que importa acá.
    "PAZ, GRAL. AV.": 80,

    # b) Avenidas con máxima de 70 en vez de 60.
    "FIGUEROA ALCORTA, PRES. AV.": 70,
    "DARSENA FIGUEROA ALCORTA, PRES. AV.": 70,
    "DEL LIBERTADOR AV.": 70,
    "27 DE FEBRERO AV.": 70,
    "QUIROGA JUAN FACUNDO BRIG. GRAL.": 70,
    "OBLIGADO RAFAEL, AV.COSTANERA": 70,
}

CALMEST_KMH, BUSIEST_KMH = 20, 100

# Cuadras sin domicilios: no son candidatas por más tranquilas que sean. Los
# senderos de parque son el caso que importa — tienen velocidad de pasaje y
# sin esta lista encabezarían el ranking. Las autopistas ya quedan afuera
# solas, porque su ruido de tránsito es 1.
NO_ADDRESSES = {
    "SENDERO", "PUENTE", "TÚNEL",
    "AUTOPISTA", "SUBIDA AUTOPISTA", "BAJADA AUTOPISTA", "ENLACE AUTOPISTA",
}

# Las dos unidades: (nombre, columna de acceso, columna de ruido).
UNITS = [
    ("líneas", "n_lines_walk", "n_lines_on"),
    ("colectivos por hora", "buses_hour_walk", "buses_hour_on"),
]


def speed_limit(tipo_c, street=None):
    """Velocidad máxima legal de la cuadra, en km/h.

    Las vías nombradas en el artículo 6.2.2 ganan sobre la regla general por
    tipo de vía.
    """
    if street and street in SPEED_BY_NAME_KMH:
        return SPEED_BY_NAME_KMH[street]
    return SPEED_LIMIT_KMH.get(tipo_c, DEFAULT_SPEED_KMH)


def traffic_noise(tipo_c, street=None):
    """Ruido de tránsito 0..1, derivado de la velocidad máxima legal."""
    speed = speed_limit(tipo_c, street)
    return (speed - CALMEST_KMH) / (BUSIEST_KMH - CALMEST_KMH)


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(int(len(ordered) * fraction), len(ordered) - 1)]


def score(access, buses, traffic, norm_access, norm_buses, weight):
    a = min(access / norm_access, 1) if norm_access else 0
    b = min(buses / norm_buses, 1) if norm_buses else 0
    return max(0.0, a - weight * max(b, traffic)) * 100


def main():
    if not ACCESS_CSV.exists():
        raise SystemExit(
            f"Falta {ACCESS_CSV}. Corré antes: python3 scripts/09_walking_access.py"
        )

    rows = list(csv.DictReader(ACCESS_CSV.open(encoding="utf-8")))
    for row in rows:
        for key in ("n_lines_walk", "n_lines_on"):
            row[key] = int(row[key])
        for key in ("buses_hour_walk", "buses_hour_on"):
            row[key] = float(row[key] or 0)
        row["traffic"] = traffic_noise(row["tipo_c"], row["street"])
        row["candidate"] = row["tipo_c"] not in NO_ADDRESSES

    common.heading("Ruido de tránsito por tipo de vía")
    print("Proxy: velocidad máxima legal (Ley 2148, art. 6.2.2).\n")
    by_type = collections.Counter(r["tipo_c"] for r in rows)
    for tipo in sorted(by_type, key=lambda t: (traffic_noise(t), -by_type[t])):
        speed = SPEED_LIMIT_KMH.get(tipo, DEFAULT_SPEED_KMH)
        mark = "" if tipo not in NO_ADDRESSES else "   (sin domicilios)"
        print(f"   {str(tipo):20s} {speed:3d} km/h -> ruido {traffic_noise(tipo):.2f}"
              f"   {by_type[tipo]:6d} cuadras{mark}")

    common.heading("Vías con límite propio (art. 6.2.2)")
    print("Ganan sobre la regla general por tipo de vía.\n")
    named = collections.Counter(
        r["street"] for r in rows if r["street"] in SPEED_BY_NAME_KMH)
    for street, speed in sorted(SPEED_BY_NAME_KMH.items(), key=lambda kv: -kv[1]):
        rows_here = [r for r in rows if r["street"] == street]
        if not rows_here:
            print(f"   {street:38s} {speed:3d} km/h   SIN COINCIDENCIAS")
            continue
        general = traffic_noise(rows_here[0]["tipo_c"])
        actual = traffic_noise(rows_here[0]["tipo_c"], street)
        print(f"   {street:38s} {speed:3d} km/h   ruido {general:.2f} -> {actual:.2f}"
              f"   {named[street]:4d} cuadras")

    common.heading("Constantes de normalización")
    print("Se escriben en output/index_norm.json y la página las lee de ahí,")
    print("así no hay dos verdades que se puedan desincronizar.\n")
    print(f"{'':22s} {'acceso (p99)':>14s} {'colectivos (p95)':>18s}")

    constants = {}
    for label, access_key, noise_key in UNITS:
        norm_access = percentile([r[access_key] for r in rows], 0.99)
        norm_buses = percentile([r[noise_key] for r in rows], 0.95)
        constants[label] = (access_key, noise_key, norm_access, norm_buses)
        print(f"{label:22s} {norm_access:14.1f} {norm_buses:18.1f}")

    NORM_JSON.write_text(json.dumps({
        "lines": {"access": constants["líneas"][2],
                  "noise": constants["líneas"][3]},
        "buses": {"access": round(constants["colectivos por hora"][2], 1),
                  "noise": round(constants["colectivos por hora"][3], 1)},
    }, indent=2), encoding="utf-8")

    candidates = [r for r in rows if r["candidate"]]
    print(f"\nCuadras candidatas: {len(candidates)} de {len(rows)} "
          f"({len(rows) - len(candidates)} sin domicilios)")

    # --- ranking con el peso por defecto, en las dos unidades ---
    for label, (access_key, noise_key, norm_access, norm_buses) in constants.items():
        for row in candidates:
            row[f"score_{access_key}"] = round(
                score(row[access_key], row[noise_key], row["traffic"],
                      norm_access, norm_buses, DEFAULT_WEIGHT), 1)

        common.heading(f"Las 15 mejores cuadras, medido en {label}")
        print(f"(peso del ruido = {DEFAULT_WEIGHT})\n")
        best = sorted(candidates, key=lambda r: -r[f"score_{access_key}"])[:15]
        for r in best:
            print(f"   {r[f'score_{access_key}']:5.1f}  {r['tipo_c'][:7]:7s} "
                  f"{r['n_lines_on']:2d} encima · {r['n_lines_walk']:2d} a pie   "
                  f"{r['street'][:28]:28s} {r['barrio']}")

    # --- control: la 9 de Julio, que era el caso que fallaba ---
    common.heading("Control: Av. 9 de Julio")
    access_key, noise_key, norm_access, norm_buses = constants["líneas"]
    nine = [r for r in rows if "9 DE JULIO" in r["street"] and r["tipo_c"] == "AVENIDA"]
    quiet = [r for r in nine if r["n_lines_on"] == 0]
    print(f"{len(nine)} cuadras, {len(quiet)} de ellas sin colectivos atribuidos.")
    print("Ésas eran las que puntuaban como calle tranquila. Ahora:\n")
    for r in sorted(quiet, key=lambda r: -r[access_key])[:5]:
        without = score(r[access_key], r[noise_key], 0, norm_access, norm_buses, 1.0)
        with_traffic = score(r[access_key], r[noise_key], r["traffic"],
                             norm_access, norm_buses, 1.0)
        print(f"   {r['n_lines_walk']:2d} líneas a pie   "
              f"sólo colectivos: {without:5.1f}   con tránsito: {with_traffic:5.1f}")

    # --- sensibilidad al peso ---
    common.heading("Sensibilidad al peso del ruido")
    print("Cuántas cuadras superan 60 puntos, y qué barrios encabezan:\n")
    for weight in (0.0, 0.5, 1.0, 1.5, 2.0):
        scored = [
            (score(r[access_key], r[noise_key], r["traffic"],
                   norm_access, norm_buses, weight), r)
            for r in candidates
        ]
        good = [s for s, _ in scored if s >= 60]
        top = sorted(scored, key=lambda pair: -pair[0])[:40]
        barrios = collections.Counter(r["barrio"] for _, r in top if r["barrio"])
        leaders = ", ".join(b for b, _ in barrios.most_common(3))
        print(f"   peso {weight:.1f} -> {len(good):5d} cuadras sobre 60   "
              f"| top 40: {leaders}")

    # --- salida ---
    fields = ["block_id", "street", "barrio", "tipo_c", "traffic",
              "n_lines_on", "n_lines_walk", "buses_hour_on", "buses_hour_walk",
              "score_n_lines_walk", "score_buses_hour_walk"]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(candidates, key=lambda r: -r["score_n_lines_walk"]))

    print(f"\nEscrito {OUTPUT_CSV.relative_to(common.ROOT)}")


if __name__ == "__main__":
    main()
