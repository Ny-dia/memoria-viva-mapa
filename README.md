# Memoria Viva de Feminicidios — Mapa

Mapa de las muertes violentas de mujeres en México que compara lo que registra el Estado con lo que muestra la evidencia.

Proyecto de investigación independiente de Nydia Mejía Zavala.

## Capas del mapa

| Capa | Fuente | Qué cuenta | Unidad | Periodicidad | Nivel |
|---|---|---|---|---|---|
| Feminicidio oficial | SESNSP, víctimas del fuero común (metodología 2015–2025) | Víctimas que las fiscalías clasificaron como feminicidio | Personas | Mensual | Estatal |
| Muertes violentas de mujeres | INEGI, Estadísticas de Defunciones Registradas (EDR) | Mujeres muertas por presunto homicidio según el certificado de defunción | Personas | Anual | Estatal (municipal en CSV) |
| Brecha | INEGI y SESNSP | % de mujeres asesinadas registradas como feminicidio | Porcentaje | Anual | Estatal |
| Lo que el Estado no sabe | INEGI | % de mujeres asesinadas sin registro del parentesco con el agresor | Porcentaje | Anual | Estatal |
| Casos documentados (próximamente) | Memoria Viva de Feminicidios | Casos individuales clasificados con una rúbrica explícita | Personas | Continua | Punto / municipio |

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

En *Actions → Generar y publicar el mapa → Run workflow*, deja los enlaces que vienen por defecto y ejecútalo. El flujo:

1. Descarga la EDR del INEGI, las víctimas por estado del SESNSP (2015–2025, desde SharePoint) y la población del CONAPO.
2. Calcula las tres capas por estado y año (`scripts/generar_mapa.py`).
3. Publica `web/` en GitHub Pages. La página lee `web/datos/estados.json`.

Controles que imprime el registro: el total de presuntos homicidios de cada archivo del INEGI (debe coincidir con la cifra oficial; para 2025 son 29,488) y la población de mujeres del CONAPO.

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
