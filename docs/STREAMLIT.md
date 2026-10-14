# Streamlit Cloud — PyPSA-col con solver HiGHS

`app.py` en la raíz del repo es un dashboard Streamlit. **La primera pestaña es
la GUI PyPSA-CL** (épocas, C1–C3/U1–U3, cola, restricciones, solver) y
**sí ejecuta PyPSA + HiGHS**. Las demás pestañas cubren Generación / Demanda /
Explorador de planta / Red SIN / CSV de resultados, como el tablero XM.

## Local

```bash
cd pypsa-col
pip install -r requirements.txt
PYTHONPATH=src streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

## GitHub + Streamlit Community Cloud

1. Cree un repo en GitHub y suba **este** proyecto (incluya `app.py`,
   `requirements.txt`, `packages.txt`, `src/`, `config/`, `data/streamlit/`,
   `data/gui/`, `.streamlit/config.toml`).
2. No hace falta subir `results/`, `.venv/` ni `site/` (Netlify).
3. Entre a [https://share.streamlit.io](https://share.streamlit.io) con GitHub.
4. **Create app** y rellene:

| Campo Streamlit Cloud | Valor |
| --- | --- |
| Repository | `su-usuario/pypsa-col` |
| Branch | `main` |
| **Main file path** | **`app.py`** |
| App URL (opcional) | `pypsa-col` → `https://pypsa-col.streamlit.app` |

5. **Advanced settings** (opcional):
   - Python version: **3.12**
   - No secrets obligatorios (XM va empaquetado en `data/streamlit/xm/`)

6. Deploy. El primer build instala `pypsa`, `highspy`, `geopandas` (~3–5 min).

### Qué debe existir en GitHub

```
app.py
requirements.txt
packages.txt          → libgomp1 (HiGHS)
runtime.txt           → python-3.12
.streamlit/config.toml
src/pypsa_col/        → gui_core, osm_mesh, dashboard_sin, …
config/*.yaml
data/streamlit/networks/*.nc
data/streamlit/xm/*.csv
data/streamlit/figures/*.png
data/gui/logo + mapa
```

`data/processed/` y `results/` están en `.gitignore`; por eso
`data/streamlit/` replica la red y el bundle XM para la nube.

## Uso de la GUI (pestaña 1)

1. Global scenario (C1…U3 o Otro).
2. Add Epoch (fechas + años representativos + red OSM o 7 nodos).
3. Add scenario to queue (se puede encolar varios).
4. **Run all scenarios** → HiGHS + figuras 0–5 (mapa, LMP, explore, despacho).

Tope práctico en Community Cloud: ~1 GB RAM. Un despacho OSM 48 h cabe;
no lance un GEP de 8760 h.

## Git (ejemplo)

```bash
git add app.py requirements.txt packages.txt runtime.txt \
        .streamlit src config data/streamlit data/gui docs/STREAMLIT.md
git commit -m "Streamlit app with HiGHS GUI"
git push origin main
```
