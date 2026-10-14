# PyPSA-col GUI (after PyPSA-CL)

The configuration interface follows
[PyPSA-CL `src/GUI.py`](https://github.com/paredes-vergara/PyPSA-CL/blob/main/src/GUI.py)
(Paredes-Vergara, PELP 2028-2032, Chilean SEN). Layout, colours, epoch queue,
six locked component selectors, sequential/parallel run config and the
`run_gui()` return contract are the same. Content is Colombia’s SIN.

## How to open it

```bash
# Browser GUI (same three-column PELP screen; works without a desktop display)
PYTHONPATH=src python -m pypsa_col gui --host 0.0.0.0 --port 7860
# or
python src/main.py --web

# Desktop Tkinter twin (needs DISPLAY, optional tkcalendar + Pillow)
python src/main.py --tk
```

Headless, Chile-style:

```bash
python src/main.py --scenario-json path/to/scenario.json
```

Outputs land in `outputs/<timestamp>_<n>E_<horizon>H_<Y>Y_<M>M/`, with the same
CSV names PyPSA-CL writes (`generation_results.csv`, `transmission_results.csv`,
`installed_capacity.csv`, `system_costs.csv`, `nodal_marginal_prices.csv`,
`run_metadata_log.csv`, `progress.json`).

## Chile → Colombia mapping

| PyPSA-CL (Chile SEN / PELP) | PyPSA-col (Colombia SIN / UPME–XM) |
| --- | --- |
| E1–E3 exploratorio, N1–N3 normativo | **C1–C3** conservador / BAU / transición, **U1–U3** UPME |
| Demand Baja/Media/Alta | Demanda UPME Baja/Media/Alta (scale on DemaReal) |
| Climate `current_projections` | **Niño / Neutral / Niña** |
| Hydrology MIROC / NorESM / H_19xx | **Seca / media / húmeda** (XM aportes, ENSO) |
| Fuel & capex Alto/Medio/Bajo | Same levers on thermal `marginal_cost` |
| 234-node SEN map `sen_network.png` | OSM 251-bus SIN map (or 7-node dashboard-SIN) |
| Gurobi default | **HiGHS** default |
| Full GEP + hydraulic network | Dispatch on the existing solved PyPSA network with those levers. Epoch dates label the planning horizon; the representative window is the snapshots already in `network.nc`. |

Extra Colombia controls: red OSM-mesh vs dashboard-SIN, meta FNCE, cierre de carbón.

## Files

| Path | Role |
| --- | --- |
| `src/GUI.py` | Tkinter port of Chile `GUI.py` |
| `src/main.py` | Chile-style driver (`run_gui` / `--scenario-json` / `--web`) |
| `src/pypsa_col/gui_core.py` | Presets, scales, exporters |
| `src/pypsa_col/web_gui.py` | Flask server for the browser GUI |
| `src/pypsa_col/gui_static/index.html` | Three-column PELP layout |
| `data/gui/logo_pypsa_col.png` | Header (Chile used `logo_PELP.png`) |
| `data/gui/sin_network.png` | Right-hand SIN map (Chile used `sen_network.png`) |
