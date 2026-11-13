"""
Genera el mapa por estado (HTML) a partir de los .zip de la EDR del INEGI.

  python scripts/generar_mapa.py datos_edr --salida web

Produce:
  web/index.html                              mapa interactivo (selector de año)
  web/datos/homicidios_mujeres_estado_anio.csv
  web/datos/homicidios_mujeres_municipio_anio.csv
"""
import argparse
import json
import os
import sys
import urllib.request

import branca.colormap as cm
import folium
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import edr_homicidios_mujeres as edr  # noqa: E402

URL_ESTADOS = "https://raw.githubusercontent.com/strotgen/mexico-leaflet/master/states.geojson"
NOMBRES = {9: "Ciudad de México", 5: "Coahuila", 16: "Michoacán", 30: "Veracruz"}
MIN_CASOS_ANIO_COMPLETO = 500  # años con menos casos a nivel nacional = solo registros tardíos


def construir_mapa(est, anios):
    geo = json.load(urllib.request.urlopen(URL_ESTADOS))
    for ft in geo["features"]:
        p = ft["properties"]
        p["nombre"] = NOMBRES.get(p["state_code"], p["state_name"])
        p["cve"] = str(p["state_code"]).zfill(2)

    vmax = est[est["anio"].isin(anios)]["homicidios_mujeres"].max()
    escala = cm.LinearColormap(["#fbe9e7", "#e57373", "#b71c1c", "#4a0000"], vmin=0, vmax=vmax,
                               caption="Mujeres muertas por presunto homicidio (INEGI, EDR)")

    m = folium.Map(location=[23.6, -102.5], zoom_start=5, tiles=None, control_scale=True)
    folium.TileLayer("OpenStreetMap", control=False, opacity=0.5).add_to(m)

    for i, anio in enumerate(anios):
        t = est[est["anio"] == anio].set_index("cve_ent")
        capa = json.loads(json.dumps(geo))
        for ft in capa["features"]:
            p = ft["properties"]
            fila = t.loc[p["cve"]] if p["cve"] in t.index else None
            for col, nombre in [("homicidios_mujeres", "homicidios"), ("arma_fuego", "arma_fuego"),
                                ("menores_18", "menores_18")]:
                p[nombre] = int(fila[col]) if fila is not None else 0
        folium.GeoJson(
            capa, name=str(anio), overlay=False, show=(i == len(anios) - 1),
            style_function=lambda f: {"fillColor": escala(f["properties"]["homicidios"]),
                                      "color": "#555", "weight": 0.6, "fillOpacity": 0.85},
            highlight_function=lambda f: {"weight": 2, "color": "#000"},
            tooltip=folium.GeoJsonTooltip(
                fields=["nombre", "homicidios", "arma_fuego", "menores_18"],
                aliases=["Estado", "Mujeres asesinadas (INEGI)", "Con arma de fuego", "Menores de 18"],
                localize=True),
        ).add_to(m)

    escala.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    titulo = """<div style="position:fixed;top:12px;left:60px;z-index:9999;background:white;padding:8px 14px;
    border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);font-family:sans-serif;max-width:420px">
    <b>Memoria Viva de Feminicidios</b><br>
    <span style="font-size:12px">Mujeres muertas por presunto homicidio, por estado de ocurrencia.
    Fuente: INEGI, Estadísticas de Defunciones Registradas. No es un conteo de feminicidios.
    Elige el año en el control de la derecha.
    <a href="datos/homicidios_mujeres_estado_anio.csv">Descargar datos</a></span></div>"""
    m.get_root().html.add_child(folium.Element(titulo))
    return m


def main():
    p = argparse.ArgumentParser()
    p.add_argument("carpeta", help="Carpeta con los .zip de la EDR")
    p.add_argument("--salida", default="web")
    a = p.parse_args()

    datos, sin_anio = edr.procesar(a.carpeta, lugar="ocurr")
    nacional = datos.groupby("anio").size()
    print("\nMujeres por presunto homicidio, por año de ocurrencia (nacional):")
    print(nacional.to_string())
    print(f"Año de ocurrencia no especificado (excluidos): {sin_anio}")

    mun = edr.agregar(datos, "municipio")
    est = edr.agregar(datos, "estado")
    est = est[est["cve_ent"] != "NO_ESPECIFICADO"]

    anios = sorted(int(x) for x in nacional.index if nacional[x] >= MIN_CASOS_ANIO_COMPLETO)
    print("Años en el mapa:", anios)

    os.makedirs(os.path.join(a.salida, "datos"), exist_ok=True)
    est.to_csv(os.path.join(a.salida, "datos", "homicidios_mujeres_estado_anio.csv"), index=False)
    mun.to_csv(os.path.join(a.salida, "datos", "homicidios_mujeres_municipio_anio.csv"), index=False)
    construir_mapa(est, anios).save(os.path.join(a.salida, "index.html"))
    print(f"Mapa guardado en {a.salida}/index.html")


if __name__ == "__main__":
    main()
