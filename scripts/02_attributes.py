"""Paso 2 — ¿Qué representa cada feature?

Distribución de valores de cada atributo y estadísticas de las geometrías.
Acá se responde la pregunta central: una feature NO es una línea de colectivo,
es un ramal en un sentido (l_r_s = línea + ramal + sentido).

Uso: python3 scripts/02_attributes.py
"""

import collections
import math

import common


def show_distribution(props, key, top=None):
    counts = collections.Counter(p[key] for p in props)
    print(f"\n{key}: {len(counts)} valores distintos")
    for value, n in counts.most_common(top):
        print(f"   {value!r}: {n}")
    if top and len(counts) > top:
        print(f"   ... ({len(counts) - top} valores más)")


def route_length_km(feature):
    """Largo aproximado del recorrido, en km.

    Las unidades del CRS son metros sobre un plano, así que sumar la distancia
    euclídea entre vértices consecutivos es una buena aproximación.
    """
    coords = feature["geometry"]["coordinates"]
    meters = sum(math.dist(coords[i], coords[i + 1]) for i in range(len(coords) - 1))
    return meters / 1000


def main():
    feats = common.features()
    props = [f["properties"] for f in feats]

    common.heading("Distribución de los atributos categóricos")
    for key in ("jurisdicci", "sentido", "modalidad", "camara"):
        show_distribution(props, key)
    show_distribution(props, "Recorrido", top=15)

    common.heading("Niveles de identidad: línea vs ramal vs recorrido")
    lines = sorted({p["linea"] for p in props})
    print(f"linea  (línea)                   : {len(lines)} distintas")
    print(f"l_r    (línea + ramal)           : {len({p['l_r'] for p in props})} distintos")
    print(f"l_r_s  (línea + ramal + sentido) : {len({p['l_r_s'] for p in props})} distintos")
    print(f"Id     (identificador único)     : {len({p['Id'] for p in props})}")
    print(f"features                         : {len(feats)}")

    duplicated = [
        k for k, n in collections.Counter(p["l_r_s"] for p in props).items() if n > 1
    ]
    print(f"\nl_r_s repetidos: {duplicated if duplicated else 'ninguno'}")
    print("=> cada feature es un ramal en un sentido; la clave natural es l_r_s")

    print(f"\nLíneas presentes:\n{lines}")

    common.heading("Pares IDA / VUELTA")
    by_branch = collections.defaultdict(set)
    for p in props:
        by_branch[p["l_r"]].add(p["sentido"])
    complete = [k for k, v in by_branch.items() if v == {"IDA", "VUELTA"}]
    partial = {k: sorted(v) for k, v in by_branch.items() if len(v) == 1}
    print(f"Ramales con ambos sentidos  : {len(complete)} / {len(by_branch)}")
    print(f"Ramales con un solo sentido : {len(partial)}")
    for k, v in sorted(partial.items()):
        print(f"   {k}: sólo {v[0]}")

    common.heading("Empresas (razon_soci)")
    operators = collections.Counter(p["razon_soci"] for p in props)
    print(f"{len(operators)} razones sociales distintas. Top 10 por recorridos:")
    for name, n in operators.most_common(10):
        print(f"   {n:3d}  {name}")

    common.heading("Geometrías (en unidades del sistema plano de CABA)")
    xs, ys, total_vertices = [], [], 0
    for f in feats:
        for x, y in f["geometry"]["coordinates"]:
            xs.append(x)
            ys.append(y)
            total_vertices += 1
    print(f"Vértices totales : {total_vertices}")
    print(f"Rango X          : {min(xs):.1f} .. {max(xs):.1f}")
    print(f"Rango Y          : {min(ys):.1f} .. {max(ys):.1f}")

    sizes = sorted(len(f["geometry"]["coordinates"]) for f in feats)
    print(
        f"Vértices por recorrido: mín {sizes[0]}, "
        f"mediana {sizes[len(sizes) // 2]}, máx {sizes[-1]}"
    )

    lengths = sorted((route_length_km(f), f["properties"]["l_r_s"]) for f in feats)
    print(
        f"\nLargo del recorrido: mín {lengths[0][0]:.1f} km ({lengths[0][1]}), "
        f"mediana {lengths[len(lengths) // 2][0]:.1f} km, "
        f"máx {lengths[-1][0]:.1f} km ({lengths[-1][1]})"
    )
    print("Los 5 recorridos más largos:")
    for km, name in lengths[-5:][::-1]:
        print(f"   {km:7.1f} km  {name}")

    common.heading("Ejemplos por jurisdicción")
    for jurisdiction in sorted({p["jurisdicci"] for p in props}):
        print(f"\n{jurisdiction}:")
        for p in [q for q in props if q["jurisdicci"] == jurisdiction][:3]:
            print(f"   {p['l_r_s']:14s} {p['razon_soci']}")
            print(f"   {'':14s} {p['desde'][:45]} -> {p['hasta'][:45]}")


if __name__ == "__main__":
    main()
