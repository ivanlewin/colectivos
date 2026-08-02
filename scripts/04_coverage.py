"""Paso 4 — ¿Es realmente "los colectivos de la Ciudad"?

Responde las dos preguntas que quedan sobre el alcance del dataset:

  1. ¿Los recorridos están recortados al ejido de CABA, o siguen hasta el
     conurbano? (Respuesta: siguen enteros.)
  2. ¿Están todas las líneas, o sólo las que tocan la Ciudad? (Respuesta:
     sólo las que tocan la Ciudad.)

También verifica qué campos NO existen, que es tan importante como saber
cuáles sí.

Requiere pyproj.
Uso: python3 scripts/04_coverage.py
"""

import collections

import common


def main():
    feats = common.features()
    props = [f["properties"] for f in feats]
    tf = common.transformer()
    bbox = common.CABA_BBOX

    common.heading("¿Cuánto de cada recorrido cae dentro de CABA?")
    print("Usando un bounding box aproximado de la Ciudad, no el polígono real,")
    print("así que los porcentajes son estimativos.\n")

    inside_total = outside_total = 0
    only_caba = never_caba = 0
    for f in feats:
        inside = outside = 0
        for x, y in f["geometry"]["coordinates"]:
            lon, lat = tf.transform(x, y)
            if (bbox["lat_min"] <= lat <= bbox["lat_max"]
                    and bbox["lon_min"] <= lon <= bbox["lon_max"]):
                inside += 1
            else:
                outside += 1
        inside_total += inside
        outside_total += outside
        if outside == 0:
            only_caba += 1
        if inside == 0:
            never_caba += 1

    total = inside_total + outside_total
    print(f"Vértices dentro de CABA      : {inside_total} ({100 * inside_total / total:.1f}%)")
    print(f"Vértices fuera (GBA/Provincia): {outside_total} ({100 * outside_total / total:.1f}%)")
    print(f"Recorridos 100% dentro de CABA: {only_caba} / {len(feats)}")
    print(f"Recorridos que NO tocan CABA  : {never_caba} / {len(feats)}")
    print("\n=> los recorridos vienen completos, no recortados al ejido,")
    print("   pero todos pasan por la Ciudad en algún tramo.")

    common.heading("¿Están todas las líneas?")
    numbers = sorted({int(p["linea"]) for p in props})
    missing = [n for n in range(1, 200) if n not in numbers]
    print(f"Presentes: {len(numbers)} líneas, de la {min(numbers)} a la {max(numbers)}")
    print(f"Ausentes en el rango 1..199: {len(missing)}")
    print(missing)
    print("\n=> son las líneas nacionales/provinciales que no entran a CABA.")
    print("   Tampoco hay líneas municipales del conurbano ni numeración 200+.")

    common.heading("Ramales por línea")
    per_line = collections.Counter(p["linea"] for p in props)
    print(f"Promedio de features por línea: {len(feats) / len(numbers):.1f}")
    print("Líneas con más ramales x sentidos:")
    for line, n in per_line.most_common(5):
        print(f"   línea {line}: {n} recorridos")

    common.heading("Campos que NO están en el dataset")
    present = set()
    for p in props:
        present |= set(p.keys())
    for field in ("paradas", "stops", "frecuencia", "horario", "tarifa",
                  "route_id", "shape_id", "trip_id", "longitud", "km"):
        print(f"   {field:12s}: {'SÍ' if field in present else 'no'}")
    print("\n=> es geometría de traza + metadatos administrativos.")
    print("   Para paradas, frecuencias y horarios hay que ir al GTFS")
    print("   del Ministerio de Transporte, que es otro dataset.")


if __name__ == "__main__":
    main()
