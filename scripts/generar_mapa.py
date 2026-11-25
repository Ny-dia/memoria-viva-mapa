"""
Prepara los datos del mapa de tres capas (por estado).

  python scripts/generar_mapa.py --edr datos_edr [--sesnsp datos_sesnsp/x.zip] [--conapo datos_conapo/x.zip] --salida web

Escribe en web/datos/:
  estados.json                           datos que lee la página (web/index.html)
  estados.geojson                        límites estatales
  tres_capas_estado_anio.csv             tabla descargable con las tres capas
  homicidios_mujeres_municipio_anio.csv  capa INEGI a nivel municipal
"""
import argparse
import json
import os
import sys
import urllib.request

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import edr_homicidios_mujeres as edr  # noqa: E402
import fuentes_complementarias as fc  # noqa: E402

URL_ESTADOS = "https://raw.githubusercontent.com/strotgen/mexico-leaflet/master/states.geojson"
NOMBRES = {9: "Ciudad de México", 5: "Coahuila", 16: "Michoacán", 30: "Veracruz"}
MIN_CASOS_ANIO_COMPLETO = 500


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--edr", required=True, help="Carpeta con los .zip de la EDR (INEGI)")
    p.add_argument("--sesnsp", help=".zip de víctimas del fuero común estatal 2015-2025 (SESNSP)")
    p.add_argument("--conapo", help=".zip de la Conciliación demográfica y proyecciones (CONAPO)")
    p.add_argument("--salida", default="web")
    a = p.parse_args()
    out = os.path.join(a.salida, "datos")
    os.makedirs(out, exist_ok=True)

    print("== INEGI (EDR)")
    datos, sin_anio = edr.procesar(a.edr, lugar="ocurr")
    nacional = datos.groupby("anio").size()
    print(nacional.to_string())
    anios = sorted(int(x) for x in nacional.index if nacional[x] >= MIN_CASOS_ANIO_COMPLETO)
    edr.agregar(datos, "municipio").to_csv(os.path.join(out, "homicidios_mujeres_municipio_anio.csv"), index=False)
    tabla = edr.agregar(datos, "estado")
    tabla = tabla[(tabla["cve_ent"] != "NO_ESPECIFICADO") & tabla["anio"].isin(anios)].copy()
    tabla["anio"] = tabla["anio"].astype(int)

    fuentes = {"inegi": True, "sesnsp": False, "conapo": False}
    if a.sesnsp:
        print("== SESNSP")
        fem = fc.sesnsp_feminicidio(a.sesnsp)
        tabla = tabla.merge(fem, on=["cve_ent", "anio"], how="left")
        hom = fc.sesnsp_homicidio_doloso_mujeres(a.sesnsp)
        tabla = tabla.merge(hom, on=["cve_ent", "anio"], how="left")
        fuentes["sesnsp"] = bool(tabla["feminicidios_sesnsp"].notna().any())
    if a.conapo:
        print("== CONAPO")
        pob = fc.conapo_mujeres(a.conapo)
        tabla = tabla.merge(pob, on=["cve_ent", "anio"], how="left")
        fuentes["conapo"] = bool(tabla["mujeres_conapo"].notna().any())

    tabla.to_csv(os.path.join(out, "tres_capas_estado_anio.csv"), index=False)

    geo = json.load(urllib.request.urlopen(URL_ESTADOS))
    for ft in geo["features"]:
        pr = ft["properties"]
        ft["properties"] = {"cve": str(pr["state_code"]).zfill(2),
                            "nombre": NOMBRES.get(pr["state_code"], pr["state_name"])}
    with open(os.path.join(out, "estados.geojson"), "w", encoding="utf-8") as f:
        json.dump(geo, f, ensure_ascii=False)

    def entero(r, col):
        return int(r[col]) if col in r and pd.notna(r[col]) else None

    estados = {}
    for _, r in tabla.iterrows():
        estados.setdefault(r["cve_ent"], {})[str(int(r["anio"]))] = {
            "inegi": int(r["homicidios_mujeres"]),
            "arma_fuego": int(r["arma_fuego"]),
            "menores_18": int(r["menores_18"]),
            "sesnsp": entero(r, "feminicidios_sesnsp"),
            "hom_doloso": entero(r, "homicidio_doloso_mujeres_sesnsp"),
            "mujeres": entero(r, "mujeres_conapo"),
            **{k: int(r[k]) for k in edr.INDICADORES},
        }

    # años del SESNSP sin datos del INEGI (serie 2015-2025): solo SESNSP y población
    anios_sesnsp = []
    if fuentes["sesnsp"]:
        serie = fem.merge(hom, on=["cve_ent", "anio"], how="outer")
        if fuentes["conapo"]:
            serie = serie.merge(pob, on=["cve_ent", "anio"], how="left")
        serie = serie[serie["cve_ent"].isin([str(i).zfill(2) for i in range(1, 33)])]
        anios_sesnsp = sorted(int(x) for x in serie["anio"].unique())
        for _, r in serie.iterrows():
            a_ = str(int(r["anio"]))
            e = estados.setdefault(r["cve_ent"], {})
            if a_ in e:
                continue
            e[a_] = {"inegi": None, "sesnsp": entero(r, "feminicidios_sesnsp"),
                     "hom_doloso": entero(r, "homicidio_doloso_mujeres_sesnsp"),
                     "mujeres": entero(r, "mujeres_conapo")}
    salida = {"anios": sorted(set(anios) | set(anios_sesnsp)), "anios_inegi": anios,
              "anios_sesnsp": anios_sesnsp, "anio_preliminar": max(anios),
              "fuentes": fuentes, "estados": estados}
    with open(os.path.join(out, "estados.json"), "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False)

    cols = [c for c in ["homicidios_mujeres", "feminicidios_sesnsp", "mujeres_conapo"] if c in tabla]
    print("\nResumen nacional:")
    print(tabla.groupby("anio")[cols].sum().to_string())
    ref = max([x for x in anios if x != max(anios)] or anios)
    t = tabla[tabla["anio"] == ref]
    total = t["homicidios_mujeres"].sum()
    print(f"\nControl de categorías, {ref} (% nacional de mujeres asesinadas):")
    for k in edr.INDICADORES:
        print(f"  {k:22s} {t[k].sum() / total * 100:5.1f} %")
    if "homicidio_doloso_mujeres_sesnsp" in t:
        f_, h_ = t["feminicidios_sesnsp"].sum(), t["homicidio_doloso_mujeres_sesnsp"].sum()
        print(f"  feminicidio / (feminicidio + homicidio doloso), SESNSP: {f_ / (f_ + h_) * 100:.1f} %")
    nombres = {ft["properties"]["cve"]: ft["properties"]["nombre"] for ft in geo["features"]}
    print(f"\nAgresor registrado por estado, {ref} (% de mujeres asesinadas con parentesco del agresor):")
    for _, r in t.assign(p=(1 - t["agresor_sin_dato"] / t["homicidios_mujeres"]) * 100).sort_values("p", ascending=False).iterrows():
        print(f"  {nombres.get(r['cve_ent'], r['cve_ent']):22s} {r['p']:5.1f} %  ({int(r['homicidios_mujeres'] - r['agresor_sin_dato'])} de {int(r['homicidios_mujeres'])})")
    print(f"\nListo: {out}/estados.json  (fuentes: {fuentes})")


if __name__ == "__main__":
    main()
