# Inicio rápido — PyPSA-col

Este repositorio **sí construye y optimiza redes PyPSA**, utilizando como base
el repositorio del profesor Sergio Rivera y su adaptación colombiana de Grid2Poster.
El ejemplo funciona sin XM ni Copernicus una vez instaladas las dependencias.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[workflow,climate,dev]'
python scripts/bootstrap_sources.py
pypsa-col run --config config/demo.yaml
```

Abra `results/demo/report.html`. Allí encontrará despacho, energía embalsada,
precios marginales **del modelo** y el mapa de Grid2Poster. También se generan
redes `.nc`, tablas horarias CSV y pósteres PNG/PDF/SVG.

## Datos reales de XM

```bash
pypsa-col download-xm --config config/xm-example.yaml
pypsa-col run --config config/xm-example.yaml
```

La entrega incluye respuestas reales de 17 combinaciones de métrica/entidad para
el 31 de diciembre de 2023 al 2 de enero de 2024, más los listados actuales de la
API. Cada respuesta conserva URL, solicitud, fecha de descarga y huella SHA-256.
El día anterior se descarga para inicializar el almacenamiento hidráulico.

**Ojo:** el ejemplo híbrido mantiene una flota parcial y pesos regionales ilustrativos.
Su demanda nacional observada no convierte la red en una reproducción validada del
SIN. La energía no atendida del ejemplo no es una medición de apagones en Colombia.

## El Niño y expansión hacia 2030

```bash
pypsa-col run --config config/el-nino.yaml
pypsa-col run --config config/investment2030.yaml
```

Son experimentos ilustrativos. El primero reduce aportes e impone presupuestos de
energía hidráulica; el segundo incorpora inversiones por año de construcción,
vida útil y descuento. La inversión usa un bloque horario corto repetido: no es
adecuado para conclusiones de almacenamiento estacional o confiabilidad nacional.

## No inventar los 147 nodos o las 18 subáreas

El snapshot tiene 771 objetos de subestaciones OSM; 127 llevan etiquetas de
220/230/500 kV. No contiene un modelo eléctrico oficial validado de 147 barras.
El constructor conservador conserva capas de tensión e islas y exige
transformadores y parámetros revisados. La agrupación en 18 regiones requiere
un mapa completo de pertenencia con fuentes; no se inventan nombres o fronteras
oficiales para hacer coincidir el número deseado.

Use las plantillas de `data/user/` y lea `docs/NETWORK.md` y `docs/DATA.md`.

## Clima

ERA5 exige una cuenta CDS, aceptación de términos y credenciales personales fuera
del repositorio. No se descargó ERA5 en esta entrega. La conversión Atlite está
probada con un fixture meteorológico sintético claramente identificado. Un error
de descarga no se reemplaza de forma oculta por series sintéticas.

## Reproducibilidad

```bash
pytest -q
snakemake -s workflow/Snakefile --config study=config/demo.yaml --cores 2
# Prueba externa opcional de XM:
PYPSA_COL_RUN_LIVE=1 pytest tests/test_live.py -q
```

Antes de publicar una base abierta, el propietario debe aclarar la licencia del
repositorio fuente y revisar los términos de los datos XM/OSM/CDS. El código
nuevo es MIT; esa licencia no sustituye las licencias de datos ni las de terceros.
La entrega está en el espacio de trabajo; no se publicó en una cuenta remota.
