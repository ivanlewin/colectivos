"""Paso 1 — ¿Qué forma tiene el archivo?

Primera pasada a ciegas sobre data/routes.json: tipo del objeto raíz, cuántas
features hay, qué geometrías usan y qué claves trae cada feature en
`properties`. No asume nada sobre el contenido.

Uso: python3 scripts/01_structure.py
"""

import collections
import json

import common


def main():
    doc = common.load()

    common.heading("Objeto raíz")
    print("Tipo               :", type(doc).__name__)
    print("Claves             :", list(doc.keys()))
    print("type               :", doc.get("type"))
    print("¿declara crs?      :", "sí" if "crs" in doc else "NO (dato importante)")

    feats = doc["features"]
    common.heading("Features")
    print("Cantidad           :", len(feats))

    geom_types = collections.Counter(
        f["geometry"]["type"] if f.get("geometry") else None for f in feats
    )
    print("Tipos de geometría :", dict(geom_types))

    common.heading("Claves de properties (clave: cuántas features la traen)")
    keys = collections.Counter()
    for f in feats:
        keys.update(f.get("properties", {}).keys())
    for key, n in keys.most_common():
        note = "" if n == len(feats) else "   <-- no está en todas"
        print(f"  {key:12s}: {n}{note}")

    common.heading("Ejemplo: primera feature")
    f = feats[0]
    print(json.dumps(f["properties"], ensure_ascii=False, indent=2))

    geom = f["geometry"]
    coords = geom["coordinates"]

    def depth(c):
        n = 0
        while isinstance(c, list):
            n += 1
            c = c[0]
        return n

    print("\ngeometry.type       :", geom["type"])
    print("profundidad coords  :", depth(coords), "(2 = lista plana de pares x,y)")
    print("cantidad de vértices:", len(coords))
    print("primeros 3 vértices :", coords[:3])
    print("\nOjo: esos valores no son lat/lon. Ver scripts/03_crs.py")


if __name__ == "__main__":
    main()
