"""
Diagnóstico de completitud: ¿qué tanto registra el Estado sobre cada mujer asesinada?

  python scripts/diagnostico_calidad.py --edr datos_edr --sesnsp archivo.zip --salida diagnostico

Para las mujeres con presunto homicidio (INEGI, EDR) mide, por variable, qué porcentaje
de los registros trae un valor útil, cuál es "no especificado / se ignora" y cuál "no aplica".
Las etiquetas salen de los catálogos que vienen dentro de cada .zip del INEGI.
Para el SESNSP describe las víctimas de feminicidio por modalidad y rango de edad.

Escribe diagnostico/reporte.md y CSVs de apoyo.
"""
import argparse
import glob
import io
import os
import re
import sys
import unicodedata
import zipfile

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import fuentes_complementarias as fc  # noqa: E402

VARIABLES = {
    "par_agre": "Parentesco con el agresor",
    "vio_fami": "Violencia familiar",
    "embarazo": "Condición de embarazo",
    "rel_emba": "Relación de la muerte con el embarazo",
    "conindig": "Se considera indígena",
    "lengua": "Habla lengua indígena",
    "afromex": "Se considera afromexicana",
    "nacionalid": "Nacionalidad",
    "lugar_ocur": "Lugar donde ocurrió la lesión",
    "area_ur": "Área urbana o rural",
    "escolarida": "Escolaridad",
    "edo_civil": "Estado civil",
    "cond_act": "Condición de actividad",
    "ocupacion": "Ocupación",
    "derechohab": "Derechohabiencia",
    "asist_medi": "Asistencia médica",
    "necropsia": "Necropsia",
    "horas": "Hora de ocurrencia",
    "edad": "Edad",
    "mun_ocurr": "Municipio de ocurrencia",
}
CODIGOS_NE = {"8", "9", "88", "98", "99", "888", "998", "999", "9998", "9999", "4998"}


def norm(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def clasificar(etiqueta, codigo):
    e = norm(etiqueta)
    if "no aplica" in e:
        return "no_aplica"
    if any(k in e for k in ("no especificad", "se ignora", "ignorad", "no se sabe", "no identificad")):
        return "no_especificado"
    if not etiqueta and str(codigo) in CODIGOS_NE:
        return "no_especificado"
    return "util"


def leer_catalogos(z):
    """Diccionario {variable: {codigo: etiqueta}} a partir de los CSV de catálogos del zip."""
    cats = {}
    for n in z.namelist():
        base = os.path.basename(n).lower()
        if not base.endswith(".csv") or "conjunto_de_datos" in base or "defunciones_registradas" in base:
            continue
        if z.getinfo(n).file_size > 5_000_000:
            continue
        nombre = re.sub(r"\.csv$", "", base)
        try:
            df = pd.read_csv(io.BytesIO(z.read(n)), dtype=str, encoding="latin-1")
        except Exception:
            continue
        if df.shape[1] < 2:
            continue
        cod, desc = df.columns[0], df.columns[1]
        cats[nombre] = dict(zip(df[cod].astype(str).str.strip().str.lstrip("0").replace("", "0"),
                                df[desc].astype(str).str.strip()))
    return cats


def catalogo_para(var, cats):
    claves = {var, var.replace("_", ""), {"escolarida": "escolaridad", "ocupacion": "ocupaciones",
                                         "lugar_ocur": "lugar_ocurrencia", "par_agre": "parentesco",
                                         "nacionalid": "nacionalidad", "derechohab": "derechohabiencia"}.get(var, var)}
    for nombre, cat in cats.items():
        n = nombre.replace("cat_", "").replace("catalogo_", "")
        if n in claves or any(n.startswith(c) for c in claves):
            return nombre, cat
    return None, {}


def leer_edr(ruta):
    with zipfile.ZipFile(ruta) as z:
        csvs = sorted((n for n in z.namelist() if n.lower().endswith(".csv")),
                      key=lambda n: z.getinfo(n).file_size, reverse=True)
        datos = None
        for n in csvs:
            with z.open(n) as f:
                enc = f.readline().decode("latin-1").lower()
            if "sexo" in enc and ("presunto" in enc or "tipo_defun" in enc):
                datos = n
                break
        cats = leer_catalogos(z)
        df = pd.read_csv(io.BytesIO(z.read(datos)), dtype=str, encoding="latin-1", low_memory=False)
    df.columns = [c.strip().lower() for c in df.columns]
    if "presunto" not in df.columns:
        df = df.rename(columns={"tipo_defun": "presunto"})
    df = df[(pd.to_numeric(df["sexo"], errors="coerce") == 2) & (pd.to_numeric(df["presunto"], errors="coerce") == 2)]
    return df, cats


def perfil_variable(serie, var, cats):
    nombre_cat, cat = catalogo_para(var, cats)
    s = serie.fillna("").astype(str).str.strip()
    clave = s.str.lstrip("0").replace("", "0")
    if var == "edad":
        e = pd.to_numeric(s, errors="coerce")
        clases = pd.Series("util", index=s.index).where(~e.isin([4998, 998, 9998]), "no_especificado")
        etiquetas = clave
    elif var == "horas":
        h = pd.to_numeric(s, errors="coerce")
        clases = pd.Series("util", index=s.index).where(h.between(0, 23), "no_especificado")
        etiquetas = clave
    elif var == "mun_ocurr":
        m = pd.to_numeric(s, errors="coerce")
        clases = pd.Series("util", index=s.index).where(m.between(1, 998), "no_especificado")
        etiquetas = clave
    else:
        etiquetas = clave.map(lambda c: cat.get(c, ""))
        clases = pd.Series([clasificar(et, c) for et, c in zip(etiquetas, clave)], index=s.index)
        etiquetas = etiquetas.where(etiquetas != "", "código " + clave)
    return clases, etiquetas, nombre_cat


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--edr", required=True)
    p.add_argument("--sesnsp")
    p.add_argument("--salida", default="diagnostico")
    a = p.parse_args()
    os.makedirs(a.salida, exist_ok=True)

    partes, cats = [], {}
    for r in sorted(glob.glob(os.path.join(a.edr, "*.zip"))):
        df, c = leer_edr(r)
        print(f"{os.path.basename(r)}: {len(df):,} mujeres por presunto homicidio; {len(c)} catálogos")
        partes.append(df)
        cats.update(c)
    print("Catálogos encontrados:", sorted(cats)[:80])
    d = pd.concat(partes, ignore_index=True)
    d["anio"] = pd.to_numeric(d["anio_ocur"], errors="coerce")
    d = d[d["anio"].between(2015, 2100)]
    d["cve_ent"] = pd.to_numeric(d["ent_ocurr"], errors="coerce")

    filas, detalle, por_estado = [], [], {}
    for var, titulo in VARIABLES.items():
        if var not in d.columns:
            filas.append({"variable": var, "descripcion": titulo, "nota": "no existe en la base"})
            continue
        clases, etiquetas, nombre_cat = perfil_variable(d[var], var, cats)
        pct = clases.value_counts(normalize=True).mul(100)
        filas.append({"variable": var, "descripcion": titulo,
                      "util_%": round(pct.get("util", 0), 1),
                      "no_especificado_%": round(pct.get("no_especificado", 0), 1),
                      "no_aplica_%": round(pct.get("no_aplica", 0), 1),
                      "catalogo": nombre_cat or ""})
        if var not in ("edad", "horas", "mun_ocurr", "ocupacion"):
            top = etiquetas.value_counts(normalize=True).mul(100).round(1).head(8)
            for et, v in top.items():
                detalle.append({"variable": var, "valor": et, "%": v})
        util = (clases == "util")
        por_estado[var] = util.groupby(d["cve_ent"]).mean().mul(100).round(1)

    resumen = pd.DataFrame(filas)
    resumen.to_csv(os.path.join(a.salida, "completitud_variables.csv"), index=False)
    det = pd.DataFrame(detalle)
    det.to_csv(os.path.join(a.salida, "distribucion_valores.csv"), index=False)
    est = pd.DataFrame(por_estado)
    est.index.name = "cve_ent"
    est.to_csv(os.path.join(a.salida, "completitud_por_estado.csv"))

    anual = {}
    for var in ("par_agre", "vio_fami", "embarazo", "conindig", "afromex", "necropsia"):
        if var in d.columns:
            clases, _, _ = perfil_variable(d[var], var, cats)
            anual[var] = (clases == "util").groupby(d["anio"]).mean().mul(100).round(1)
    anual = pd.DataFrame(anual)

    md = ["# Diagnóstico de completitud — mujeres por presunto homicidio (INEGI, EDR)", "",
          f"Registros analizados: {len(d):,} (años de ocurrencia {int(d['anio'].min())}–{int(d['anio'].max())}).", "",
          "## Completitud por variable", "", resumen.to_markdown(index=False), "",
          "## Variables clave por año de ocurrencia (% con dato útil)", "", anual.to_markdown(), "",
          "## Distribución de valores", ""]
    for var in det["variable"].unique():
        md += [f"### {VARIABLES[var]} (`{var}`)", "",
               det[det["variable"] == var][["valor", "%"]].to_markdown(index=False), ""]
    md += ["## Completitud por estado (% con dato útil)", "",
           est[[c for c in ("par_agre", "vio_fami", "embarazo", "conindig", "necropsia") if c in est]]
           .describe().loc[["min", "50%", "max"]].round(1).to_markdown(), ""]

    if a.sesnsp:
        df = fc._abrir_tabla(a.sesnsp)
        meses = [c for c in df.columns if fc._norm(c) in fc.MESES]
        df["total"] = df[meses].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
        c_tipo = fc._col(df, "tipo de delito")
        f = df[df[c_tipo].map(fc._norm) == "feminicidio"]
        md += ["# SESNSP — víctimas de feminicidio, 2015–2025", ""]
        for col in ("Modalidad", "Rango de edad", "Sexo"):
            if col in f.columns:
                t = f.groupby(col)["total"].sum()
                md += [f"## {col}", "", (t / t.sum() * 100).round(1).rename("%").to_frame()
                       .assign(victimas=t.astype(int)).to_markdown(), ""]
        c_sexo = fc._col(df, "sexo", obligatoria=False)
        if c_sexo:
            muj = df[df[c_sexo].astype(str).map(fc._norm).str.startswith("muj")]
            comp = muj[muj[c_tipo].map(fc._norm).isin(["feminicidio", "homicidio"])]
            c_sub = fc._col(df, "subtipo de delito")
            t = comp.groupby([fc._col(df, "ano", "anio"), c_sub])["total"].sum().unstack(fill_value=0).astype(int)
            md += ["## Mujeres víctimas: feminicidio frente a homicidio, por año", "", t.to_markdown(), ""]

    texto = "\n".join(md)
    with open(os.path.join(a.salida, "reporte.md"), "w", encoding="utf-8") as fh:
        fh.write(texto)
    print(texto)


if __name__ == "__main__":
    main()
