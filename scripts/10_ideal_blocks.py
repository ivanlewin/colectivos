"""Paso C — El índice de cuadra ideal.

Combina las dos métricas anteriores en un solo número: **acceso alto, ruido
bajo**. Una cuadra sin colectivos por la puerta pero con muchos a la vuelta.

El índice se calcula en el navegador, no acá, porque cuánto pesa el ruido
frente al acceso es una preferencia personal y conviene poder moverla con un
control. Este script existe para dos cosas:

  1. Calcular las constantes de normalización que usa la página, y dejarlas
     documentadas en vez de hardcodeadas a ojo.
  2. Dejar registrado el ranking con el peso por defecto, para poder
     compararlo si algo cambia.

## La fórmula

    acceso  = min(acceso_de_la_cuadra  / P99_acceso, 1)      -> 0..1
    ruido   = min(ruido_de_la_cuadra   / P95_ruido,  1)      -> 0..1
    puntaje = max(0, acceso - peso * ruido) * 100            -> 0..100

Se normaliza contra un percentil y no contra el máximo porque el máximo es un
caso extremo —Av. Santa Fe con 892 colectivos por hora— que aplastaría toda la
escala contra el piso.

Los dos percentiles son distintos a propósito. El acceso usa el **p99** porque
es lo que tiene que ordenar el ranking: con el p95 saturaban 1.753 cuadras en
el puntaje máximo y arriba quedaba un empate inútil. El ruido usa el **p95**
porque ahí no hace falta discriminar, sólo penalizar: seis líneas por la puerta
ya son muchas, y que a partir de ahí penalice igual no cambia nada.

Se recorta en cero: una cuadra donde el ruido supera al acceso no es "peor que
nada", simplemente no califica. Sin el recorte, la escala se estiraría hacia
valores negativos que no significan nada útil.

Con peso 0 el índice es acceso puro. Con peso 1 una avenida con mucho servicio
se compensa exactamente con su propio ruido. Con peso 2 sólo sobreviven las
cuadras casi sin colectivos encima.

Uso: python3 scripts/10_ideal_blocks.py
"""

import collections
import csv

import common

ACCESS_CSV = common.ROOT / "output" / "blocks_access.csv"
OUTPUT_CSV = common.ROOT / "output" / "ideal_blocks.csv"

# Peso por defecto del ruido. 1.0 es el punto neutro: una cuadra con tanto
# servicio encima como acceso a pie da cero.
DEFAULT_WEIGHT = 1.0

# En estas cuadras no vive nadie, así que quedan fuera del ranking.
NOT_RESIDENTIAL = {
    "AUTOPISTA", "SUBIDA AUTOPISTA", "BAJADA AUTOPISTA", "ENLACE AUTOPISTA",
    "SENDERO", "PUENTE", "TÚNEL",
}

# Las dos unidades en las que se puede mirar todo: (nombre, columna de acceso,
# columna de ruido).
UNITS = [
    ("líneas", "n_lines_walk", "n_lines_on"),
    ("colectivos por hora", "buses_hour_walk", "buses_hour_on"),
]


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(int(len(ordered) * fraction), len(ordered) - 1)]


def score(access, noise, norm_access, norm_noise, weight):
    a = min(access / norm_access, 1) if norm_access else 0
    n = min(noise / norm_noise, 1) if norm_noise else 0
    return max(0.0, a - weight * n) * 100


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
        row["residential"] = row["tipo_c"] not in NOT_RESIDENTIAL

    common.heading("Constantes de normalización")
    print("Son las que usa la página. Si cambian los datos, hay que")
    print("actualizarlas también en web/index.html (constante NORM).\n")
    print(f"{'':22s} {'acceso (p99)':>14s} {'ruido (p95)':>13s}   saturan arriba")

    constants = {}
    for label, access_key, noise_key in UNITS:
        norm_access = percentile([r[access_key] for r in rows], 0.99)
        norm_noise = percentile([r[noise_key] for r in rows], 0.95)
        constants[label] = (access_key, noise_key, norm_access, norm_noise)
        saturated = sum(1 for r in rows if r[access_key] >= norm_access)
        print(f"{label:22s} {norm_access:14.1f} {norm_noise:13.1f}   {saturated}")

    residential = [r for r in rows if r["residential"]]
    print(f"\nCuadras en el ranking: {len(residential)} de {len(rows)} "
          f"({len(rows) - len(residential)} descartadas por no ser residenciales)")

    # --- ranking con el peso por defecto, en las dos unidades ---
    for label, access_key, noise_key, p95_access, p95_noise in (
        (k, *v) for k, v in constants.items()
    ):
        for row in residential:
            row[f"score_{access_key}"] = round(
                score(row[access_key], row[noise_key], p95_access, p95_noise,
                      DEFAULT_WEIGHT), 1)

        common.heading(f"Las 15 mejores cuadras, medido en {label}")
        print(f"(peso del ruido = {DEFAULT_WEIGHT})\n")
        best = sorted(residential, key=lambda r: -r[f"score_{access_key}"])[:15]
        for r in best:
            print(f"   {r[f'score_{access_key}']:5.1f}  "
                  f"{r['n_lines_on']:2d} encima · {r['n_lines_walk']:2d} a pie   "
                  f"{r['street'][:30]:30s} {r['barrio']}")

    # --- cómo se reparte el puntaje, y cómo lo mueve el peso ---
    access_key, noise_key, p95_access, p95_noise = constants["líneas"]
    common.heading("Sensibilidad al peso del ruido")
    print("Cuántas cuadras superan 60 puntos, y qué barrios encabezan:\n")
    for weight in (0.0, 0.5, 1.0, 1.5, 2.0):
        scored = [
            (score(r[access_key], r[noise_key], p95_access, p95_noise, weight), r)
            for r in residential
        ]
        good = [s for s, _ in scored if s >= 60]
        top = sorted(scored, key=lambda pair: -pair[0])[:40]
        barrios = collections.Counter(r["barrio"] for _, r in top if r["barrio"])
        leaders = ", ".join(f"{b}" for b, _ in barrios.most_common(3))
        print(f"   peso {weight:.1f} -> {len(good):5d} cuadras sobre 60   "
              f"| top 40: {leaders}")

    # --- salida ---
    fields = ["block_id", "street", "barrio", "tipo_c",
              "n_lines_on", "n_lines_walk", "buses_hour_on", "buses_hour_walk",
              "score_n_lines_walk", "score_buses_hour_walk"]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(residential, key=lambda r: -r["score_n_lines_walk"]))

    print(f"\nEscrito {OUTPUT_CSV.relative_to(common.ROOT)}")


if __name__ == "__main__":
    main()
