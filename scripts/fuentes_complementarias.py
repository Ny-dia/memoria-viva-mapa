"""
Lectura de las fuentes complementarias del mapa:

  - SESNSP: víctimas de feminicidio por estado y año (archivo "2015 - 2025 (Fuero Común - Víctimas).
    Incidencia delictiva estatal"). Cuenta PERSONAS.
  - CONAPO: población de mujeres a mitad de año por estado (Conciliación demográfica 1950-2019 y
    Proyecciones 2020-2070, archivo 0_Pob_Mitad_1950_2070.xlsx).
"""
import io
import zipfile

import pandas as pd

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()
    return s.replace("_", " ")


def _abrir_tabla(ruta_zip, preferir=None):
    """Devuelve un DataFrame con el CSV o Excel más grande dentro del zip."""
    with zipfile.ZipFile(ruta_zip) as z:
        candidatos = [i for i in z.infolist()
                      if i.filename.lower().endswith((".csv", ".xlsx", ".xls")) and not i.is_dir()]
        if preferir:
            pref = [i for i in candidatos if preferir.lower() in i.filename.lower()]
            candidatos = pref or candidatos
        if not candidatos:
            raise ValueError(f"{ruta_zip}: no hay CSV/Excel dentro. Contenido: {z.namelist()}")
        info = max(candidatos, key=lambda i: i.file_size)
        datos = z.read(info)
    print(f"  leyendo {info.filename} ({info.file_size / 1e6:.1f} MB)")
    if info.filename.lower().endswith(".csv"):
        for enc in ("utf-8", "latin-1"):
            try:
                return pd.read_csv(io.BytesIO(datos), encoding=enc, low_memory=False)
            except UnicodeDecodeError:
                continue
    return pd.read_excel(io.BytesIO(datos))


def _col(df, *claves, obligatoria=True):
    for c in df.columns:
        n = _norm(c)
        if any(n == k or n.startswith(k) for k in claves):
            return c
    if obligatoria:
        raise ValueError(f"No encontré la columna {claves}. Columnas: {list(df.columns)}")
    return None


def sesnsp_feminicidio(ruta_zip):
    """Víctimas de feminicidio por estado y año (todas las modalidades; excluye tentativas si vienen separadas)."""
    df = _abrir_tabla(ruta_zip)
    print(f"  columnas SESNSP: {list(df.columns)}")
    c_anio = _col(df, "ano", "anio")
    c_ent = _col(df, "clave ent", "cve ent", "clave entidad")
    c_tipo = _col(df, "tipo de delito")
    c_sub = _col(df, "subtipo de delito", obligatoria=False)
    meses = [c for c in df.columns if _norm(c) in MESES]
    if len(meses) != 12:
        raise ValueError(f"Esperaba 12 columnas de meses, encontré {meses}")

    tipos = df[c_tipo].astype(str)
    print("  valores con 'femin' en tipo de delito:", sorted(tipos[tipos.str.lower().str.contains("femin")].unique()))
    f = df[tipos.map(_norm) == "feminicidio"].copy()
    if c_sub:
        subs = f[c_sub].astype(str)
        print("  subtipos de feminicidio:", sorted(subs.unique()))
        f = f[~subs.map(_norm).str.contains("tentativa")]
    f["victimas"] = f[meses].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    out = (f.groupby([c_ent, c_anio])["victimas"].sum().reset_index()
             .rename(columns={c_ent: "cve_ent", c_anio: "anio", "victimas": "feminicidios_sesnsp"}))
    out["cve_ent"] = pd.to_numeric(out["cve_ent"], errors="coerce").astype("Int64").astype(str).str.zfill(2)
    out["anio"] = pd.to_numeric(out["anio"], errors="coerce").astype(int)
    out["feminicidios_sesnsp"] = out["feminicidios_sesnsp"].astype(int)
    print("  feminicidios SESNSP por año (nacional):")
    print(out.groupby("anio")["feminicidios_sesnsp"].sum().to_string())
    return out


def conapo_mujeres(ruta_zip, anio_min=2010, anio_max=2030):
    """Población de mujeres a mitad de año por estado (CVE_GEO 1-32)."""
    import openpyxl
    with zipfile.ZipFile(ruta_zip) as z:
        nombre = next(n for n in z.namelist() if "pob_mitad" in n.lower() and n.lower().endswith(".xlsx"))
        print(f"  leyendo {nombre}")
        wb = openpyxl.load_workbook(io.BytesIO(z.read(nombre)), read_only=True)
    filas = wb.worksheets[0].iter_rows(values_only=True)
    enc = [_norm(c) for c in next(filas)]
    i_anio, i_cve, i_sexo, i_pob = (enc.index("ano"), enc.index("cve geo"),
                                    enc.index("sexo"), enc.index("poblacion"))
    acum = {}
    for r in filas:
        anio, cve, sexo = r[i_anio], r[i_cve], r[i_sexo]
        if anio is None or not (anio_min <= int(anio) <= anio_max):
            continue
        if not cve or int(cve) == 0 or str(sexo).lower()[:3] != "muj":
            continue
        k = (str(int(cve)).zfill(2), int(anio))
        acum[k] = acum.get(k, 0) + int(r[i_pob])
    out = pd.DataFrame([(k[0], k[1], v) for k, v in acum.items()],
                       columns=["cve_ent", "anio", "mujeres_conapo"])
    print(f"  población de mujeres: {out['anio'].min()}–{out['anio'].max()}, "
          f"nacional {out['anio'].max()}: {out[out['anio'] == out['anio'].max()]['mujeres_conapo'].sum():,}")
    return out
