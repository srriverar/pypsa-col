# Publicar PyPSA-col en Netlify

Netlify sirve **HTML/CSS/JS estático**. No puede instalar PyPSA, Linopy ni HiGHS,
ni correr `n.optimize()`. Lo que se publica es:

- la GUI (misma pantalla que PyPSA-CL, contenido Colombia)
- los mapas osm-interactive ya calculados (Colombia, LMP, `n.explore`, despacho)
- la cola de escenarios, que **descarga un JSON** para resolverlo en su PC

La carpeta que hay que subir se llama **`site/`** (ya está armada en el repo).

```
site/
├── index.html                          ← página principal (esto es la app)
├── presets.json                        ← escenarios C1–C3 / U1–U3
├── README.txt
├── assets/
│   ├── logo_pypsa_col.png
│   ├── sin_network.png                 ← mapa de la columna derecha
│   └── dashboard_red.png
└── results/osm-interactive/
    ├── colombia_map.png
    ├── lmp.png
    ├── dispatch.png
    ├── explore_load.html
    ├── explore_capacity.html
    ├── explore_flow.html
    └── report.html
```

No suba el repo entero (`src/`, `.venv/`, `network.nc`, Snakemake). Netlify no
los usa y el `.nc` es innecesario.

---

## Camino A — arrastrar la carpeta (el más rápido, sin Git)

1. Abra [https://app.netlify.com](https://app.netlify.com) e inicie sesión
   (GitHub / e-mail).
2. En el menú izquierdo: **Sites**.
3. En el pie de la página de Sites está **Want to deploy a new site without
   connecting to Git? Drag and drop your site output folder here**.
4. En su disco abra `pypsa-col/site` (la carpeta **dentro**, no `pypsa-col`).
5. Arrastre **esa carpeta `site`** al recuadro de Netlify.
6. Espere 10–30 s. Netlify le da una URL tipo
   `https://random-name-123456.netlify.app`.
7. (Opcional) **Site configuration → Domain management → Options → Change site
   name** → por ejemplo `pypsa-col` → queda `https://pypsa-col.netlify.app`.

Para actualizar mapas: vuelva a generar figuras, ejecute
`python scripts/build_netlify_site.py` si hace falta, y en Netlify
**Deploys → Drag and drop a new folder** otra vez con `site/`.

---

## Camino B — conectar GitHub (cada `git push` republica)

1. Suba el repositorio a GitHub (incluya la carpeta `site/`).
2. En Netlify: **Add new site → Import an existing project → GitHub**.
3. Autorice Netlify y elija el repo `pypsa-col`.
4. Rellene **exactamente** estos campos (el resto déjelo vacío):

| Campo en Netlify | Qué poner | Qué no poner |
| --- | --- | --- |
| **Project name** | `pypsa-col` (o el que quiera) | — |
| **Branch to deploy** | `main` | — |
| **Base directory** | *(vacío)* | no ponga `src` ni `site` aquí |
| **Build command** | *(vacío)* o `echo static` | no ponga `pip install` ni `python -m pypsa_col` |
| **Publish directory** | `site` | no ponga `.` ni `src` ni `results` |
| **Functions directory** | *(vacío)* | no hay serverless |
| **Environment variables** | ninguna obligatoria | no hace falta `PYTHONPATH` |

5. **Deploy pypsa-col**. El primer deploy tarda ~1 min (hay ~20 MB de HTML de
   pydeck).

El archivo `netlify.toml` en la raíz del repo ya dice `publish = "site"`. Si lo
deja, Netlify ignora un Build command vacío y publica `site/`.

---

## Qué verá en la web

- Cabecera amarilla: aviso de que el sitio es estático.
- GUI C1–C3 / U1–U3, épocas, cola (igual que Chile).
- **Run all scenarios** descarga `pypsa-col-scenario.json` (Netlify no resuelve).
- Abajo, las 5 figuras osm-interactive:
  0 mapa Colombia (naranja demanda / verde generación),
  1 LMP, 2 carga nodal, 3 tartas, 4 flujos, 5 despacho.

Para resolver de verdad el JSON:

```bash
cd pypsa-col
PYTHONPATH=src python src/main.py --scenario-json pypsa-col-scenario.json
```

---

## Lo que no hay que intentar en Netlify

| Idea | Por qué no |
| --- | --- |
| `pip install pypsa` en Build command | la imagen de build no es su solver; además el sitio publicado es solo estático |
| Netlify Functions en Python | tope ~50 MB y 10–26 s; PyPSA+HiGHS no cabe ni termina |
| Publicar `results/*.nc` | inútil en el navegador |
| Publish directory = raíz del repo | expondría `src/` y configs; la home no sería la GUI |

Si necesita **Run** en la nube (HiGHS en vivo), use un servicio con contenedor
(Render, Fly.io, Railway, Hugging Face Spaces) y, si quiere, ponga en el HTML:

```html
<script>window.PYPSA_COL_API = "https://su-backend.ejemplo.com";</script>
```

antes de cerrar `</body>`. Entonces la GUI en Netlify llamará a ese API.

---

## Regenerar `site/` en local

```bash
# después de un snakemake OSM o una corrida GUI
PYTHONPATH=src python scripts/build_netlify_site.py
```

Eso refresca logo, mapa y figuras. El `index.html` de `site/` ya está adaptado
a rutas relativas; no lo pise a ciegas.
