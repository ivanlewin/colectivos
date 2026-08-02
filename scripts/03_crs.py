"""Paso 3 — ¿En qué sistema de coordenadas están las geometrías?

El archivo no declara `crs` y sus coordenadas van de ~10.600 a ~149.500, así
que claramente no son lat/lon. Este script prueba tres candidatos y valida el
resultado contra un dato independiente: el campo `desde`, que dice en texto
dónde arranca cada recorrido. Si al reproyectar el primer vértice caemos en el
barrio que declara `desde`, el CRS es el correcto.

Requiere pyproj.
Uso: python3 scripts/03_crs.py
"""

import common

CANDIDATES = {
    # Sistema plano local de CABA, definido a mano.
    "CABA local (tmerc)": common.CABA_CRS,
    # Sistema oficial de la Ciudad publicado como código EPSG.
    "EPSG:9498": "EPSG:9498",
    # Gauss-Krüger POSGAR 94 faja 5, el otro sospechoso habitual en datos
    # geográficos argentinos.
    "EPSG:22185 (GK faja 5)": "EPSG:22185",
}

# Recorridos con cabecera conocida, para contrastar la reproyección contra la
# ubicación real del barrio declarado en `desde`.
CHECKS = {
    "015GIDA": ("Valentín Alsina, Lanús", -34.678, -58.420),
    "029AIDA": ("La Boca, CABA", -34.635, -58.363),
    "060AIDA": ("Barracas, CABA", -34.650, -58.380),
}


def main():
    from pyproj import Transformer

    feats = common.features()
    sample = feats[0]["geometry"]["coordinates"][0]

    common.heading("Prueba de candidatos sobre un mismo punto")
    print(f"Punto de prueba (proyectado): {sample}")
    print("Debería caer en el AMBA, es decir cerca de lat -34.6, lon -58.4\n")
    for name, definition in CANDIDATES.items():
        try:
            tf = Transformer.from_crs(definition, "EPSG:4326", always_xy=True)
            lon, lat = tf.transform(*sample)
            verdict = "PLAUSIBLE" if -35.5 < lat < -34.0 and -59.5 < lon < -57.5 else "descartado"
            print(f"  {name:24s} -> lat {lat:9.5f}, lon {lon:9.5f}   {verdict}")
        except Exception as exc:  # pragma: no cover - depende de la instalación
            print(f"  {name:24s} -> ERROR: {exc}")

    common.heading("Validación contra las cabeceras declaradas en `desde`")
    tf = common.transformer()
    by_key = {f["properties"]["l_r_s"]: f for f in feats}
    for key, (place, ref_lat, ref_lon) in CHECKS.items():
        f = by_key.get(key)
        if f is None:
            print(f"  {key}: no está en el dataset")
            continue
        lon, lat = tf.transform(*f["geometry"]["coordinates"][0])
        # Un grado son ~111 km; con 0.02° (~2 km) alcanza para confirmar barrio.
        ok = abs(lat - ref_lat) < 0.03 and abs(lon - ref_lon) < 0.03
        print(f"  {key:10s} desde = {f['properties']['desde'][:44]}")
        print(f"  {'':10s} primer vértice -> ({lat:.4f}, {lon:.4f})")
        print(f"  {'':10s} esperado {place} ~({ref_lat}, {ref_lon})  {'OK' if ok else 'NO COINCIDE'}\n")

    common.heading("Bounding box del dataset completo, en lat/lon")
    xs, ys = [], []
    for f in feats:
        for x, y in f["geometry"]["coordinates"]:
            xs.append(x)
            ys.append(y)
    lon_min, lat_min = tf.transform(min(xs), min(ys))
    lon_max, lat_max = tf.transform(max(xs), max(ys))
    print(f"lat {lat_min:.4f} .. {lat_max:.4f}")
    print(f"lon {lon_min:.4f} .. {lon_max:.4f}")
    print("\nEso cubre el AMBA entero, no sólo la Ciudad.")

    common.heading("Definición a usar para reproyectar")
    print(common.CABA_CRS)


if __name__ == "__main__":
    main()
