"""
Descarga archivos validando que sean .zip reales.
Soporta enlaces públicos de SharePoint (los que usa el SESNSP): primero abre el enlace
para obtener la cookie de acceso y luego pide la descarga.

  python scripts/descargar.py CARPETA URL [URL ...]
"""
import os
import re
import sys
import zipfile
from urllib.parse import urlparse

import requests

UA = {"User-Agent": "Mozilla/5.0"}


def nombre_archivo(url, resp):
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
    if m:
        return requests.utils.unquote(m.group(1))
    return os.path.basename(urlparse(url).path) or "descarga.zip"


def descargar(url, carpeta):
    s = requests.Session()
    s.headers.update(UA)
    if "sharepoint.com" in url:
        s.get(url, timeout=120)  # obtiene la cookie del enlace público
        url_dl = url + ("&" if "?" in url else "?") + "download=1"
    else:
        url_dl = url
    r = s.get(url_dl, timeout=600, stream=True)
    r.raise_for_status()
    destino = os.path.join(carpeta, nombre_archivo(url, r))
    with open(destino, "wb") as f:
        for bloque in r.iter_content(1 << 20):
            f.write(bloque)
    tam = os.path.getsize(destino)
    if not zipfile.is_zipfile(destino):
        os.remove(destino)
        raise SystemExit(f"ERROR: {url} no devolvió un .zip válido ({tam:,} bytes, "
                         f"{r.headers.get('content-type')}). Revisa el enlace.")
    print(f"  OK {os.path.basename(destino)} ({tam / 1e6:.1f} MB)")
    return destino


if __name__ == "__main__":
    carpeta, urls = sys.argv[1], [u for a in sys.argv[2:] for u in re.split(r"[\s,;]+", a) if u]
    os.makedirs(carpeta, exist_ok=True)
    for u in urls:
        print(f"Descargando {u}")
        descargar(u, carpeta)
