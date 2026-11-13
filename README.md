# Memoria Viva de Feminicidios — Mapa

Mapa de las muertes violentas de mujeres en México que compara lo que registra el Estado con lo que muestra la evidencia.

Proyecto de investigación independiente de Nydia Mejía Zavala.

## Capas del mapa

| Capa | Fuente | Qué cuenta | Unidad | Periodicidad | Nivel |
|---|---|---|---|---|---|
| Feminicidio oficial | SESNSP, incidencia delictiva | Delitos clasificados como feminicidio por las fiscalías | Delitos (2015–2025); víctimas por municipio desde 2026, por confirmar | Mensual | Municipal |
| Muertes violentas de mujeres | INEGI, Estadísticas de Defunciones Registradas (EDR) | Mujeres muertas por presunto homicidio según el certificado de defunción | Personas | Anual | Municipal |
| Casos documentados | Memoria Viva de Feminicidios | Casos individuales clasificados con una rúbrica explícita | Personas | Continua | Punto / municipio |

La diferencia entre la capa del INEGI y la del SESNSP es el universo de mujeres asesinadas que el Estado no registró como víctimas de feminicidio. La capa de casos documentados trata de explicar esa diferencia caso por caso, con evidencia que se puede rastrear.

**Las fuentes no se suman.** Miden etapas distintas y se traslapan. Se comparan y cada una se etiqueta por lo que mide (INEGI, *La medición del feminicidio en México*, En números núm. 28, 2023).

## Estructura

```
scripts/   procesamiento de datos
datos/     resultados procesados (CSV, GeoJSON) que consume la página
web/       página del mapa
```

## Uso

### Publicar el mapa con GitHub Actions (sin instalar nada)

1. Ve a la página de datos abiertos de la EDR del INEGI (https://www.inegi.org.mx/programas/edr/#datos_abiertos), haz clic derecho en el `.zip` de cada año que quieras y elige *Copiar dirección del enlace*.
2. En este repositorio, abre *Actions → Generar y publicar el mapa → Run workflow*, pega los enlaces separados por espacios y ejecútalo.
3. Al terminar, el mapa queda publicado en GitHub Pages. Los datos procesados quedan disponibles en `datos/`, dentro del sitio.

### Capa INEGI (EDR), en tu computadora

1. Descarga los `.zip` de datos abiertos por año de registro desde https://www.inegi.org.mx/programas/edr/#datos_abiertos y ponlos en `datos_edr/`. Esta carpeta no se sube al repositorio.
2. Corre:

```bash
pip install pandas
python scripts/edr_homicidios_mujeres.py datos_edr --salida datos
# opcional, para generar el GeoJSON del mapa:
python scripts/edr_homicidios_mujeres.py datos_edr --salida datos --geojson municipios.geojson
```

Las decisiones de método (mujer = `sexo 2`, presunto homicidio = `presunto 2`, año de ocurrencia, municipio de ocurrencia) están documentadas al inicio del script.

## Claves y secretos

Las claves de API (por ejemplo, Firecrawl) **nunca** se ponen en el código. Se guardan en *Settings → Secrets and variables → Actions*, o en un archivo `.env` local que no se sube al repositorio.
