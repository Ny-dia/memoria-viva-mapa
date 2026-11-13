"""
Homicidios de mujeres por municipio y año — INEGI, Estadísticas de Defunciones Registradas (EDR).

Capa "universo total de mujeres asesinadas" para el mapa de Memoria Viva de Feminicidios.

USO
  1. Descarga los datos abiertos de la EDR (un .zip por año de registro) desde
     https://www.inegi.org.mx/programas/edr/#datos_abiertos
     y ponlos todos en una carpeta, p. ej. ./datos_edr/
  2. Corre:
       python edr_homicidios_mujeres.py ./datos_edr --salida ./salida
     Opcional, para obtener un GeoJSON listo para el mapa:
       python edr_homicidios_mujeres.py ./datos_edr --salida ./salida --geojson municipios.geojson
     (el GeoJSON de municipios debe tener la propiedad CVEGEO de 5 dígitos, como el Marco Geoestadístico del INEGI)

DECISIONES METODOLÓGICAS (documentadas para que sean auditables)
  - Mujer:            sexo == 2
  - Presunto homicidio: presunto == 2  (criterio que usa el INEGI en sus reportes de homicidio).
                      En las bases recientes la variable se llama tipo_defun; el script acepta ambos nombres.
                      Se reporta además cuántos de esos casos tienen causa CIE-10 X85–Y09 (agresiones)
                      como control de consistencia.
  - Año:              año de OCURRENCIA (anio_ocur), no de registro. Cada archivo anual del INEGI
                      contiene las defunciones REGISTRADAS ese año, incluidas algunas ocurridas antes;
                      por eso se juntan todos los archivos y se reagrupa por año de ocurrencia.
                      El año más reciente siempre estará incompleto (registros tardíos).
  - Lugar:            por defecto, municipio de ocurrencia (ent_ocurr + mun_ocurr). Se puede cambiar
                      con --lugar ocules (lugar de la lesión) o --lugar resid (residencia).
  - Unidad:           PERSONAS (cada registro es una defunción), no delitos ni carpetas.
  - Esto NO es un conteo de feminicidios: es el universo de mujeres muertas por presunto homicidio,
                      según el certificado de defunción, antes de cualquier investigación penal.
"""

import argparse
import glob
import io
import json
import os
import zipfile

import pandas as pd

COLUMNAS = [
    "sexo", "presunto", "tipo_defun", "causa_def", "anio_ocur", "anio_regis", "edad",
    "ent_ocurr", "mun_ocurr", "ent_ocules", "mun_ocules", "ent_resid", "mun_resid",
]


# ---------------------------------------------------------------- lectura
def _leer_csv(fuente):
    """Lee solo las columnas necesarias; tolera mayúsculas y codificación latin-1."""
    for enc in ("utf-8", "latin-1"):
        try:
            if hasattr(fuente, "seek"):
                fuente.seek(0)
            return pd.read_csv(
                fuente,
                usecols=lambda c: c.strip().lower() in COLUMNAS,
                dtype=str,
                encoding=enc,
                low_memory=False,
            )
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo leer el archivo con utf-8 ni latin-1")


def leer_archivo(ruta):
    """Acepta .csv o .zip de datos abiertos del INEGI (busca dentro el CSV de defunciones)."""
    if ruta.lower().endswith(".zip"):
        if not zipfile.is_zipfile(ruta):
            raise ValueError(f"{os.path.basename(ruta)} no es un .zip válido "
                             f"({os.path.getsize(ruta):,} bytes): revisa el enlace de descarga")
        with zipfile.ZipFile(ruta) as z:
            csvs = sorted((n for n in z.namelist() if n.lower().endswith(".csv")),
                          key=lambda n: z.getinfo(n).file_size, reverse=True)
            nombre = None
            for n in csvs:  # el CSV de datos es el que trae las columnas sexo y presunto
                with z.open(n) as f:
                    encabezado = f.readline().decode("latin-1").lower()
                if "sexo" in encabezado and ("presunto" in encabezado or "tipo_defun" in encabezado):
                    nombre = n
                    break
            if nombre is None:
                print(f"  Contenido de {os.path.basename(ruta)}:")
                for i, n in enumerate(csvs[:15]):
                    with z.open(n) as f:
                        enc = f.readline().decode("latin-1").strip()
                        fila = f.readline().decode("latin-1").strip()
                    if i == 0:
                        print(f"    {n} ({z.getinfo(n).file_size:,} bytes)\n      encabezado: {enc!r}\n      primera fila: {fila!r}")
                    else:
                        print(f"    {n} ({z.getinfo(n).file_size:,} bytes) -> {enc[:80]}")
                raise ValueError(f"No encontré el CSV con las columnas sexo/presunto dentro de {ruta}")
            print(f"  {os.path.basename(ruta)}: usando {nombre}")
            df = _leer_csv(io.BytesIO(z.read(nombre)))
    else:
        df = _leer_csv(ruta)
    df.columns = [c.strip().lower() for c in df.columns]
    # en las bases recientes del INEGI la variable "presunto" se llama "tipo_defun"
    if "presunto" not in df.columns and "tipo_defun" in df.columns:
        df = df.rename(columns={"tipo_defun": "presunto"})
    df["archivo"] = os.path.basename(ruta)
    return df


# ---------------------------------------------------------------- limpieza
def a_num(s):
    return pd.to_numeric(s, errors="coerce")


def es_agresion_cie10(causa):
    """True si la causa CIE-10 está entre X85 y Y09 (agresiones)."""
    c = causa.fillna("").str.upper().str.strip().str[:3]
    letra, num = c.str[0], pd.to_numeric(c.str[1:3], errors="coerce")
    return ((letra == "X") & (num >= 85)) | ((letra == "Y") & (num <= 9))


def es_arma_fuego(causa):
    """X93, X94, X95: agresión con disparo de arma de fuego."""
    return causa.fillna("").str.upper().str[:3].isin(["X93", "X94", "X95"])


def edad_en_anios(edad):
    """En la EDR, la edad en años se codifica 4001–4120 (4000 + años). Otros códigos = menores de 1 año o no especificado."""
    e = a_num(edad)
    anios = pd.Series(pd.NA, index=e.index, dtype="Int64")
    anios[(e >= 4000) & (e <= 4120)] = (e - 4000)[(e >= 4000) & (e <= 4120)].astype("Int64")
    anios[(e > 0) & (e < 4000)] = 0  # horas, días o meses -> menor de un año
    return anios


def cvegeo(ent, mun):
    """Clave geoestadística de 5 dígitos. Entidad >32 o municipio 999 se marcan como no especificado."""
    e, m = a_num(ent), a_num(mun)
    valido = e.between(1, 32) & m.between(1, 998)
    clave = e.astype("Int64").astype(str).str.zfill(2) + m.astype("Int64").astype(str).str.zfill(3)
    clave[~valido] = "NO_ESPECIFICADO"
    return clave, e.astype("Int64").astype(str).str.zfill(2).where(e.between(1, 32), "NO_ESPECIFICADO")


# ---------------------------------------------------------------- proceso
def procesar(carpeta, lugar="ocurr"):
    rutas = sorted(glob.glob(os.path.join(carpeta, "*.zip")) + glob.glob(os.path.join(carpeta, "*.csv")))
    if not rutas:
        raise SystemExit(f"No hay archivos .zip o .csv en {carpeta}")

    partes = []
    for r in rutas:
        try:
            df = leer_archivo(r)
        except ValueError as e:
            print(f"  ! {e}; se omite")
            continue
        faltan = {"sexo", "presunto", "anio_ocur", f"ent_{lugar}", f"mun_{lugar}"} - set(df.columns)
        if faltan:
            print(f"  ! {os.path.basename(r)}: faltan columnas {sorted(faltan)}; "
                  f"columnas encontradas: {sorted(df.columns)}; se omite")
            continue
        n_total = len(df)
        n_hom = (a_num(df["presunto"]) == 2).sum()
        df = df[(a_num(df["sexo"]) == 2) & (a_num(df["presunto"]) == 2)].copy()
        print(f"  {os.path.basename(r)}: {n_total:,} defunciones registradas; {n_hom:,} presuntos homicidios "
              f"(ambos sexos, control vs. INEGI); {len(df):,} mujeres por presunto homicidio")
        partes.append(df)

    if not partes:
        raise SystemExit("Ningún archivo se pudo procesar. Revisa los mensajes de arriba.")
    datos = pd.concat(partes, ignore_index=True)
    datos["anio"] = a_num(datos["anio_ocur"]).astype("Int64")
    datos["cvegeo"], datos["cve_ent"] = cvegeo(datos[f"ent_{lugar}"], datos[f"mun_{lugar}"])
    datos["agresion_cie10"] = es_agresion_cie10(datos.get("causa_def", pd.Series(index=datos.index, dtype=str)))
    datos["arma_fuego"] = es_arma_fuego(datos.get("causa_def", pd.Series(index=datos.index, dtype=str)))
    edad = edad_en_anios(datos.get("edad", pd.Series(index=datos.index, dtype=str)))
    datos["menor_18"] = (edad < 18).fillna(False)
    datos["edad_no_esp"] = edad.isna()
    # año de ocurrencia desconocido (9999) se excluye de la serie, pero se reporta
    sin_anio = (~datos["anio"].between(1990, 2100)).sum()
    datos = datos[datos["anio"].between(1990, 2100)]
    return datos, sin_anio


def agregar(datos, nivel):
    llave = "cvegeo" if nivel == "municipio" else "cve_ent"
    return (datos.groupby([llave, "anio"])
            .agg(homicidios_mujeres=("sexo", "size"),
                 con_causa_x85_y09=("agresion_cie10", "sum"),
                 arma_fuego=("arma_fuego", "sum"),
                 menores_18=("menor_18", "sum"),
                 edad_no_especificada=("edad_no_esp", "sum"))
            .reset_index()
            .sort_values([llave, "anio"]))


def a_geojson(mun, ruta_geo, ruta_salida):
    """Une la tabla municipal (formato ancho, una columna por año) al GeoJSON de municipios por CVEGEO."""
    ancho = mun.pivot(index="cvegeo", columns="anio", values="homicidios_mujeres").fillna(0).astype(int)
    ancho.columns = [f"h_{a}" for a in ancho.columns]
    tabla = ancho.to_dict(orient="index")
    with open(ruta_geo, encoding="utf-8") as f:
        geo = json.load(f)
    sin_match = 0
    for feat in geo["features"]:
        props = feat.setdefault("properties", {})
        clave = str(props.get("CVEGEO") or props.get("cvegeo") or "").zfill(5)
        valores = tabla.get(clave)
        if valores is None:
            sin_match += 1
            valores = {c: 0 for c in ancho.columns}
        props.update(valores)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(geo, f, ensure_ascii=False)
    claves_geo = {str(ft["properties"].get("CVEGEO") or ft["properties"].get("cvegeo") or "").zfill(5)
                  for ft in geo["features"]}
    huerfanas = set(tabla) - claves_geo
    print(f"  GeoJSON: {len(geo['features'])} municipios, {sin_match} sin casos; "
          f"{len(huerfanas)} claves de la tabla no encontradas en el GeoJSON")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("carpeta", help="Carpeta con los .zip o .csv de datos abiertos de la EDR")
    p.add_argument("--salida", default="salida")
    p.add_argument("--lugar", choices=["ocurr", "ocules", "resid"], default="ocurr",
                   help="ocurr = donde ocurrió la defunción (default); ocules = donde ocurrió la lesión; resid = residencia")
    p.add_argument("--geojson", help="GeoJSON de municipios con propiedad CVEGEO (opcional)")
    a = p.parse_args()

    os.makedirs(a.salida, exist_ok=True)
    print("Leyendo archivos…")
    datos, sin_anio = procesar(a.carpeta, a.lugar)

    mun = agregar(datos, "municipio")
    est = agregar(datos, "estado")
    mun.to_csv(os.path.join(a.salida, "homicidios_mujeres_municipio_anio.csv"), index=False)
    est.to_csv(os.path.join(a.salida, "homicidios_mujeres_estado_anio.csv"), index=False)

    nacional = datos.groupby("anio").size()
    print("\nMujeres por presunto homicidio, por año de ocurrencia (nacional):")
    print(nacional.to_string())
    no_esp = (datos["cvegeo"] == "NO_ESPECIFICADO").sum()
    inconsist = (~datos["agresion_cie10"]).sum()
    print(f"\nControles de calidad:")
    print(f"  municipio no especificado: {no_esp:,} ({no_esp / len(datos):.1%})")
    print(f"  año de ocurrencia no especificado (excluidos): {sin_anio:,}")
    print(f"  presunto homicidio con causa fuera de X85–Y09: {inconsist:,}")
    print(f"  año más reciente ({nacional.index.max()}) está incompleto por registros tardíos")

    if a.geojson:
        a_geojson(mun[mun["cvegeo"] != "NO_ESPECIFICADO"], a.geojson,
                  os.path.join(a.salida, "homicidios_mujeres_municipios.geojson"))
    print(f"\nListo. Archivos en {a.salida}/")


if __name__ == "__main__":
    main()
