# PyPSA-col

**An auditable Colombian power-system research workflow built on your ColombiaCongestionV2 repository.**

PyPSA · Linopy · HiGHS · XM SINERGOX · Atlite/ERA5 · Grid2Poster

> **Status: working research scaffold, not a validated national planning model.**
> The offline seven-hub demo, XM hybrid, drought scenario and multi-investment
> example run. The physical/18-region research workflows deliberately require
> reviewed electrical data and crosswalks. Neither 147 official buses nor an
> official 18-subarea mapping is fabricated. This is an independent project, not
> an official XM, UPME or PyPSA release.

## 1. Quick start

Python **3.11–3.13**; development delivery tested on Python 3.13.16. Start in this
repository's root directory. HiGHS is installed as a Python wheel; no commercial
solver is needed.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e '.[workflow,climate,dev]'
python scripts/bootstrap_sources.py

# Fully offline after dependencies and source are available
pypsa-col run --config config/demo.yaml
# Open results/demo/report.html in your browser
pytest -q
```

### GUI (PyPSA-CL layout, Colombia content)

The scenario/epoch screen is modelled on
[`paredes-vergara/PyPSA-CL` `src/GUI.py`](https://github.com/paredes-vergara/PyPSA-CL/blob/main/src/GUI.py)
(PELP Chile). Presets **C1–C3 / U1–U3** lock demand, ENSO climate, XM hydrology,
fuel and capex; *Otro* unlocks free combination. See [`docs/GUI.md`](docs/GUI.md).

```bash
pip install -e '.[gui]'
PYTHONPATH=src python -m pypsa_col gui          # browser, 0.0.0.0:7860
python src/main.py --tk                         # desktop Tkinter (needs DISPLAY)
python src/main.py --scenario-json scenario.json
```

### Streamlit (sí corre HiGHS)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Primera pestaña = GUI PyPSA-CL; **Run all scenarios** llama a PyPSA + HiGHS.
Deploy en Community Cloud: Main file = `app.py`. Pasos:
[`docs/STREAMLIT.md`](docs/STREAMLIT.md).

### Netlify (sitio estático)

Netlify **no ejecuta** PyPSA/HiGHS. Suba solo la carpeta `site/` (GUI + mapas
osm-interactive ya calculados). Guía de campos y arrastre:
[`docs/NETLIFY.md`](docs/NETLIFY.md).

`bootstrap_sources.py` either verifies the source snapshot bundled in this
delivery, or clones the exact locked Git commit. It refuses to overwrite changes.
The network is a real **PyPSA Network**, solved through **Linopy and HiGHS**.
The original Streamlit application is not imported or executed.

A lean installation without climate or Snakemake is `pip install -e '.[dev]'`.
`requirements-lock.txt` records the complete tested Python 3.13 environment;
for other supported Python versions use the project extras so pip can select
compatible wheels. The PyPSA/Linopy/HiGHS solver stack is pinned in `pyproject.toml`; this PyPSA
release retains compatibility with the source repository's pandas<3 convention.

## 2. What was actually reused

Source: **[srriverar/colombiacongestionV2](https://github.com/srriverar/colombiacongestionV2)**,
commit `a6fcf7622249f555d81e293a11f05b8a6aee7c39`.
All source-file SHA-256 values are in `config/sources.lock.json`.

| Source asset | How PyPSA-col uses it |
|---|---|
| `app.py` | Safely parses default fleet, seven transport corridors and demand weights with AST; does **not** import Streamlit. |
| `data/geo/*.geojson` | Uses the actual OSM line, substation and plant snapshots, not invented geographic coordinates. |
| `tools/gis_data.py` | Loads the source geometries and inventories. |
| `tools/paratec_join.py` | Resolves the seven hub anchors, routes model corridors over OSM, emits quality reports, supplies **explicitly unverified** typical line parameters, and inspects PARATEC CSV/XLSX exports. |
| `tools/grid2poster_col.py` | Executes the Colombian offline renderer for PNG/PDF/SVG, using its 18 themes, voltage tiers, boundaries and ZNI insets. |
| `tools/themes/` + license | Preserves the upstream Grid2Poster styling and MIT attribution. |
| `data/reference/` | Preserves mainland and island boundaries; islands are never electrically attached to SIN. |

The source's current `app.py` actually implements a **SciPy/HiGHS seven-hub
transport LP**, despite older README claims of a PyPSA implementation. This
repository supplies the PyPSA implementation rather than repeating that claim.
The seven-hub topology remains explicitly a transport approximation (KCL, not KVL).

### Source audit, not assumed counts

At the locked revision, the files contain **2,333 line features, 771 substation
features and 297 plant features**. Of the substations, **127** have a maximum
voltage tag of 220, 230 or 500 kV. These are OSM features, not validated electrical
buses. Default conservative reconstruction yields **272 voltage-level/junction
buses, 337 retained line segments and 20 connected components**, without invented
transformers. Rejected self-loops, inferred station matches and islands are saved.
See `docs/NETWORK.md` before using these candidates for research.

## 3. Reproducible scenarios

```bash
# Separate inflow reduction + custom Linopy hydro energy budgets
pypsa-col run --config config/el-nino.yaml

# Vintage-based generation, battery and transport expansion, 2026/2028/2030
pypsa-col run --config config/investment2030.yaml

# Real XM national demand and hydrological ratios, illustrative spatial/fleet model
pypsa-col run --config config/xm-example.yaml

# Same workflow as an explicit, restartable Snakemake DAG
snakemake -s workflow/Snakefile --config study=config/demo.yaml --cores 2
snakemake -s workflow/Snakefile --config study=config/investment2030.yaml --cores 2
snakemake -s workflow/Snakefile --config study=config/xm-example.yaml --dry-run
```

Use **`--config study=...`** for this Snakefile, not `--configfile`: the repository
loader resolves each YAML's relative `extends` chain. All data paths in YAML are
relative to the repository root. Run IDs isolate `resources/<id>` and `results/<id>`.
Different historical download windows should also have distinct `xm.processed_dir`
and matching `inputs.xm_dir` when running concurrently.

The 2030 example annualizes a repeated 48-hour block and uses a hypothetical 20%
inflow reduction. **It is a software/economics demonstration, not a forecast.**
Do not use this short block for seasonal reservoir planning or firm-capacity claims.

## 4. XM: real downloads, not stubs

```bash
pypsa-col download-xm --config config/xm-example.yaml
# Force a new retrieval (for revised source data):
pypsa-col download-xm --config config/xm-example.yaml --refresh
```

The delivered example was actually downloaded from `servapibi.xm.com.co`:
**17 datasets / 44,906 normalized records**, covering **2023-12-31–2024-01-02**
for observations and the API's current **2026-10-12** lists. Raw responses, request
sidecars, processed CSVs and a manifest are included in the delivery archive.
They are generated/ignored in ordinary Git checkouts, but reproducible with the command.
The extra preceding day supplies an initial reservoir-state observation.

- Live `(MetricId, Entity)` catalog discovery; compatible parser for the official
  legacy **double-encoded JSON string** (fixes the earlier `.get` exception).
- At most **30 inclusive days per request**, retries/backoff, timeouts, exact filters,
  offline cache replay, SHA-256 verification and explicit failures on missing data.
- Hourly demand, `Gene`, `DispoReal`, daily historical net capacity, stored/useful
  reservoir energy, inflows, prices, resource/river/reservoir lists and `DemaOR`.
- **Hour01 → 00:00 local time**; kWh/hour → MW; reservoir kWh → MWh;
  daily inflow MWh/day → MW by dividing by 24; price remains COP until explicitly converted.
- Real missing values in resource generation/availability stay missing. Never
  treat absent dispatch as zero or observed dispatch as available capacity.
- A discovered API quirk: `PorcVoluUtilDiar` is labeled `%` but the sample contains
  fractional values. Model filling fractions are derived from stored/useful energy,
  not guessed from that unit label. See `docs/DATA.md`.
- Current resource lists are **not** silently treated as historical plant registries.

`xm-example` deliberately combines observed national inputs with the source
**illustrative partial fleet** and inherited spatial weights. Its large unserved
energy is a **model coverage mismatch**, not evidence of Colombian outages.
For actual studies use `xm_mapped`, with complete reviewed resource/bus and
reservoir/river crosswalks. `Gene` and national price are exported as validation
references; no false calibration or national-price/LMP equivalence is asserted.

## 5. ERA5 / Atlite

A Copernicus CDS account, accepted ERA5 terms and a personal credential are required.
Credentials must stay in the user's home/environment, never in the repository.

```bash
# See docs/CLIMATE.md for credentials, scope and processing assumptions
pypsa-col build-cutout --config config/era5.yaml
pypsa-col run --config config/era5.yaml
```

La Guajira wind and Cesar/Santander PV use area-weighted cutout cells, a configurable
turbine/panel, and explicit **UTC → America/Bogota** alignment. The provided site
polygons are illustrative resource boxes, **not official boundaries or legally
eligible land**. No real ERA5 cutout is bundled, and a failed request never falls
back silently to synthetic profiles. See `docs/CLIMATE.md`.

## 6. Physical network and 18-region research mode

```bash
pypsa-col audit-source --config config/demo.yaml
pypsa-col build-network --config config/physical-candidate.yaml
# Review resources/physical-candidate/{physical_buses,physical_lines,endpoint_matches,rejected_lines}.csv

# Inspect a downloaded PARATEC export with YOUR upstream name normalizer:
pypsa-col inspect-paratec --config config/research.yaml --file data/user/paratec.xlsx

# AFTER supplying the required reviewed data and ERA5 cutout:
pypsa-col run --config config/research.yaml
pypsa-col run --config config/clustered18.yaml
```

The last two commands intentionally stop until the user supplies:

1. Reviewed line ratings/Ohmic R/X/B and explicit transformer connections.
2. A complete historical XM resource-to-model-bus map with costs and availability/profile decisions.
3. Reservoir-to-turbine and river-to-reservoir allocations, avoiding cascade double counting.
4. A sourced demand allocation (weights must conserve national demand).
5. For 18-region mode, a complete cited busmap with exactly 18 reviewed region names.

Templates are in `data/user/*.example.csv`; they contain headers only, not fabricated
official data. Snapping never joins different voltages. The geographic routing
heuristic used for a poster is **not reused for electrical connectivity**.
Regional aggregation is a lossless cut-set-capacity transport reduction, not an
AC/PTDF equivalent or N-1 transfer capability.

## 7. Outputs

Each complete run writes:

- `network.nc`, `solver.json`, `summary.json` — solved PyPSA network, status, versions and QA.
- Hourly dispatch, load, SOC, charging, LMP, line/Link flows and physical residual CSVs.
- `energy_by_period.csv`, `active_capacities.csv`, `branches.csv` — period-aware results.
- `grid2poster.png`, `.pdf`, `.svg`, `.json` — actual source renderer plus modeled
  corridor overlays, route status, OSM IDs and attribution.
- `report.html` — **self-contained, offline** report with embedded charts and map.

Raw and normalized input hashes, resolved configurations and climate assumptions
are kept alongside intermediate networks in `resources/`. Non-optimal solutions
and residual failures raise errors; they are never accepted as successful studies.

## 8. Repository layout

```text
config/                 Inheritable studies and pinned source/hash manifest
src/pypsa_col/          Tested library: XM, source audit, climate, topology, model, results
scripts/                Thin script entry points + safe source bootstrap
workflow/Snakefile      Dependency-aware workflow (no network calls in demo mode)
external/              Pinned ColombiaCongestionV2 source snapshot
data/                   Raw XM, normalized tables, references and reviewed user inputs
cutouts/                Credential-gated ERA5 NetCDFs (ignored)
resources/              Prepared inputs, base/prepared networks and provenance (generated)
results/                Solved networks, CSVs, Grid2Poster and offline reports (generated)
tests/                  Unit, fixture and solver integration tests; live tests opt in
docs/                   Data contracts, equations, limitations and reproducibility notes
.github/workflows/      Offline CI and solver tests
```

## 9. Modeling corrections versus the original snippet

- Uses `p_nom_extendable`, **not** `p_extendable`.
- Reads `network.buses_t.marginal_price`, **not** `p_marginal_pricing`.
- Hydro is a non-pumping energy-limited `StorageUnit`, with inflow, spill, initial
  energy and terminal/cyclic conditions — not unlimited cheap generation.
- Separates hourly storage transitions from economic repetition weights.
- Annualized capital costs, period discount weights, explicit vintages/lifetimes
  and shared technical potentials replace a one-day/full-year cost mismatch.
- Never uses a lossy `Link` with negative dispatch: that would produce reverse-flow
  energy gains. The transport representation is lossless in both directions.
- Research electrical lines use **Ohms**, transformers use own-base **per-unit**,
  and thermal ratings/units require review.

## OSM mesh interactivo (Snakemake)

Red de **251 barras** OSM + plantas XM, mapas `n.explore()` (pydeck) y DAG completo:

```bash
snakemake -s workflow/Snakefile.osm.smk --cores 2
```

Informe: `results/osm-interactive/report.html`. Método: `docs/OSM_MESH.md`.

## Dashboard SIN nodal (plantas y demanda reales)

Un quinto ejemplo usa las pestañas **Generación**, **Demanda** y el **Explorador de planta**
de https://dashboard-sin-nodal.streamlit.app/ sobre el mismo bundle XM:

```bash
python scripts/run_dashboard_sin.py
```

Colores: paleta del workshop PyPSA Labs (`Carrier.color`). Informe:
`results/dashboard-sin/informe.html`. Detalle: `docs/DASHBOARD_SIN.md`.

## 10. Validation and packaging

See `docs/VALIDATION.md` for the actual 40-test live-enabled run, completed demo/XM
DAGs, numerical residuals and explicit untested/review-required items. Normal CI
runs the 39 offline tests; the external XM smoke test is opt-in.

A local delivery ZIP (no credentials, Git internals, virtual environment or private
user engineering files) can be rebuilt with:

```bash
python scripts/package_release.py --include-source --include-example-data
```

The ZIP includes a per-file SHA-256 `RELEASE_MANIFEST.json`; its separate
`.zip.sha256` file verifies the download. Inclusion is not permission for public
redistribution of upstream source/data; review the notices first.

## 11. Research, licensing and contribution

Read `docs/MODEL.md`, `docs/RESEARCH_READINESS.md` and `THIRD_PARTY_NOTICES.md` before
publishing numerical conclusions. New code is MIT. OSM-derived data retain ODbL
attribution/share-alike obligations; XM/CDS and boundary terms are separate.
The pinned user repository has **no root license grant**, only an educational
purpose statement: its owner should explicitly select a code license before
redistributing the combined repository publicly. This delivery does not relicense it.

`CITATION.cff` supplies software metadata without inventing a DOI. `CONTRIBUTING.md`
describes the review and testing expectations. This repository is delivered locally;
it has **not** been pushed to your remote account.
