"""Colombia GUI core, modelled on PyPSA-CL ``src/GUI.py``.

Chile PELP packages (E1–N3) become Colombia packages (C1–C3 conservador/BAU/
transición and U1–U3 UPME). Hydrology is ENSO / XM aportes rather than Chilean
GCM traces. The six component selectors, epoch queue and run_config dict match
the Chile ``run_gui`` return value so ``main.py`` can stay close to PyPSA-CL.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

ORDINAL_ENGLISH = [
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
]

# Visual language copied from PyPSA-CL (PELP navy / cyan / orange).
BASE_COLORS = {
    "fondo_azul_oscuro": "#081889",
    "cyan": "#18ADE5",
    "gray": "#8093AD",
    "orange": "#F7A823",
    "green": "#7DB928",
    "mint": "#99D0C1",
    "dark_green": "#397831",
    "white": "#FFFFFF",
    "black": "#000000",
    "section_bg": "#0a20a8",
    "section_border": "#2a40c8",
    "gold": "#FCD116",
    "flag_red": "#CE1126",
}

SCENARIO_NAMES = {
    "demand": [
        "Baja - C1",
        "Media - C2",
        "Alta - C3",
        "Baja - U1",
        "Media - U2",
        "Alta - U3",
    ],
    "climate": ["Niño", "Neutral", "Niña"],
    "hydrology": [
        "Seca (Niño XM)",
        "Media (histórica XM)",
        "Húmeda (Niña XM)",
    ],
    "fuel_price": ["Alto", "Medio", "Bajo"],
    "generation_investment_cost": ["Alto", "Medio", "Bajo"],
    "storage_investment_cost": ["Alto", "Medio", "Bajo"],
}

SCENARIO_MAP = {
    "C1 - Conservador (Niño / desfavorable)": {
        "demand": "Baja - C1",
        "climate": "Niño",
        "hydrology": "Seca (Niño XM)",
        "fuel_price": "Alto",
        "generation_investment_cost": "Alto",
        "storage_investment_cost": "Alto",
    },
    "C2 - BAU": {
        "demand": "Media - C2",
        "climate": "Neutral",
        "hydrology": "Media (histórica XM)",
        "fuel_price": "Medio",
        "generation_investment_cost": "Medio",
        "storage_investment_cost": "Medio",
    },
    "C3 - Transición energética (favorable)": {
        "demand": "Alta - C3",
        "climate": "Niña",
        "hydrology": "Húmeda (Niña XM)",
        "fuel_price": "Bajo",
        "generation_investment_cost": "Bajo",
        "storage_investment_cost": "Bajo",
    },
    "U1 - UPME desfavorable": {
        "demand": "Baja - U1",
        "climate": "Niño",
        "hydrology": "Seca (Niño XM)",
        "fuel_price": "Alto",
        "generation_investment_cost": "Alto",
        "storage_investment_cost": "Alto",
    },
    "U2 - UPME medio": {
        "demand": "Media - U2",
        "climate": "Neutral",
        "hydrology": "Media (histórica XM)",
        "fuel_price": "Medio",
        "generation_investment_cost": "Medio",
        "storage_investment_cost": "Medio",
    },
    "U3 - UPME favorable": {
        "demand": "Alta - U3",
        "climate": "Niña",
        "hydrology": "Húmeda (Niña XM)",
        "fuel_price": "Bajo",
        "generation_investment_cost": "Bajo",
        "storage_investment_cost": "Bajo",
    },
    "Otro": {},
}

PRESET_NAMES = [k for k in SCENARIO_MAP if k != "Otro"]
ALL_GLOBAL_NAMES = PRESET_NAMES + ["Otro"]

NETWORKS = {
    "osm-mesh": {
        "label": "OSM mesh · 251 barras (KVL)",
        "nc": "results/osm-interactive/network.nc",
        "nc_fallback": "data/streamlit/networks/osm-mesh.nc",
        "map": "results/osm-interactive/colombia_map.png",
        "map_fallback": "data/gui/sin_network.png",
    },
    "dashboard-sin": {
        "label": "Dashboard-SIN · 7 nodos (KCL)",
        "nc": "results/dashboard-sin/network.nc",
        "nc_fallback": "data/streamlit/networks/dashboard-sin.nc",
        "map": "results/dashboard-sin/red.png",
        "map_fallback": "data/gui/sin_network.png",
    },
}


def resolve_network_nc(root: Path, key: str) -> Path:
    spec = NETWORKS[key]
    for rel in (spec.get("nc"), spec.get("nc_fallback")):
        if not rel:
            continue
        path = Path(root) / rel
        if path.exists():
            return path
    raise FileNotFoundError(
        f"No hay network.nc para {key}. Coloque el archivo en {spec.get('nc')} "
        f"o {spec.get('nc_fallback')}."
    )

DEMAND_SCALE = {
    "Baja - C1": 0.92,
    "Media - C2": 1.00,
    "Alta - C3": 1.12,
    "Baja - U1": 0.90,
    "Media - U2": 1.00,
    "Alta - U3": 1.15,
}
HYDRO_SCALE = {
    "Seca (Niño XM)": 0.62,
    "Media (histórica XM)": 1.00,
    "Húmeda (Niña XM)": 1.18,
}
FUEL_SCALE = {"Alto": 1.25, "Medio": 1.00, "Bajo": 0.82}
HYDRO_CARRIERS = {"Storage Hydro", "Run of River", "Hydro", "RoR"}
THERMAL_CARRIERS = {"Hard Coal", "Gas", "Oil", "Coal", "Fuel Oil"}


def epoch_name_for(index: int) -> str:
    if 0 <= index < len(ORDINAL_ENGLISH):
        return f"{ORDINAL_ENGLISH[index]} epoch"
    return f"{index + 1}th epoch"


def suggested_end_date(start: str, rep_years: int) -> str:
    y = int(str(start)[:4]) + int(rep_years) - 1
    return f"{y}-12-31"


def flatten_user_data(scenarios: list, run_config: dict) -> dict:
    flat = []
    for s_idx, sc in enumerate(scenarios):
        for e_idx, ep in enumerate(sc["epochs"]):
            d = dict(ep)
            d["_scenario_index"] = s_idx
            d["_epoch_in_scenario"] = e_idx
            d["_global_epoch"] = len(flat)
            d.setdefault("global_scenario", sc["global_scenario"])
            flat.append(d)
    return {
        "scenarios": scenarios,
        "epochs": flat,
        "n_scenarios": len(scenarios),
        "run_config": run_config,
    }


def run_folder_name(user_data: dict) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    epochs = user_data["epochs"]
    n_sc = user_data.get("n_scenarios") or len(user_data.get("scenarios") or [])
    max_end = max(int(ep["end_date"][:4]) for ep in epochs)
    min_start = min(int(ep["start_date"][:4]) for ep in epochs)
    horizon = max_end - min_start + 1
    rep_y = max(int(ep.get("representative_years", 1)) for ep in epochs)
    rep_m = max(int(ep.get("representative_months", 1)) for ep in epochs)
    return f"{ts}_{n_sc}E_{horizon}H_{rep_y}Y_{rep_m}M"


def _write_progress(folder: Path, **kwargs) -> None:
    """Write progress.json. First arg is the directory; never pass outdir= as a kwarg."""
    kwargs.pop("outdir", None)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "progress.json"
    payload = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
    payload.update(kwargs)
    payload["updated"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_levers(n, settings: dict) -> dict:
    """Scale demand / hydro / thermal cost on an existing PyPSA network."""
    demand_key = settings.get("demand_scenario", "Media - C2")
    hydro_key = settings.get("hydrology_scenario", "Media (histórica XM)")
    fuel_key = settings.get("fuel_price_scenario", "Medio")
    d_s = DEMAND_SCALE.get(demand_key, 1.0)
    h_s = HYDRO_SCALE.get(hydro_key, 1.0)
    f_s = FUEL_SCALE.get(fuel_key, 1.0)
    climate = settings.get("climate_scenario", "Neutral")
    if climate == "Niño" and h_s >= 1.0:
        h_s *= 0.85
    elif climate == "Niña" and h_s <= 1.0:
        h_s *= 1.08

    if settings.get("coal_phase_out"):
        coal_idx = n.generators.index[n.generators.carrier.isin({"Hard Coal", "Brown Coal", "Coal"})]
        if len(coal_idx):
            n.generators.loc[coal_idx, "p_nom"] = 0.0
            if "p_nom_max" in n.generators.columns:
                n.generators.loc[coal_idx, "p_nom_max"] = 0.0

    if hasattr(n, "loads_t") and not n.loads_t.p_set.empty:
        n.loads_t.p_set = n.loads_t.p_set * d_s

    hydro_idx = n.generators.index[n.generators.carrier.isin(HYDRO_CARRIERS)]
    if len(hydro_idx):
        if "p_max_pu" in n.generators_t and not n.generators_t.p_max_pu.empty:
            cols = n.generators_t.p_max_pu.columns.intersection(hydro_idx)
            if len(cols):
                n.generators_t.p_max_pu[cols] = n.generators_t.p_max_pu[cols] * h_s
        else:
            n.generators.loc[hydro_idx, "p_nom"] = n.generators.loc[hydro_idx, "p_nom"] * h_s

    thermal_idx = n.generators.index[n.generators.carrier.isin(THERMAL_CARRIERS)]
    if len(thermal_idx) and "marginal_cost" in n.generators.columns:
        n.generators.loc[thermal_idx, "marginal_cost"] = (
            n.generators.loc[thermal_idx, "marginal_cost"] * f_s
        )
    return {"demand_scale": d_s, "hydro_scale": h_s, "fuel_scale": f_s}


def _export_epoch(n, outdir: Path, ep: dict, scales: dict, status: dict) -> None:
    gens = n.generators
    if hasattr(n, "generators_t") and not n.generators_t.p.empty:
        p = n.generators_t.p.copy()
        long = p.stack().rename("p_MW").reset_index()
        long.columns = ["snapshot", "generator", "p_MW"]
        long["carrier"] = long["generator"].map(gens.carrier)
        long["bus"] = long["generator"].map(gens.bus)
        long["global_scenario"] = ep.get("global_scenario")
        long["epoch"] = ep.get("name")
        long.to_csv(outdir / "generation_results.csv", index=False)
        mix = p.T.groupby(gens.carrier).sum().T
        mix.to_csv(outdir / "generation_by_carrier.csv")
    if hasattr(n, "lines_t") and not n.lines_t.p0.empty:
        f = n.lines_t.p0.stack().rename("p0_MW").reset_index()
        f.columns = ["snapshot", "line", "p0_MW"]
        f["global_scenario"] = ep.get("global_scenario")
        f["epoch"] = ep.get("name")
        f.to_csv(outdir / "transmission_results.csv", index=False)
    cap = gens.groupby("carrier")["p_nom"].sum().rename("p_nom_MW").to_frame()
    cap["global_scenario"] = ep.get("global_scenario")
    cap["epoch"] = ep.get("name")
    cap.to_csv(outdir / "installed_capacity.csv")
    if hasattr(n, "buses_t") and not n.buses_t.marginal_price.empty:
        n.buses_t.marginal_price.mean().rename("lmp_mean").to_csv(
            outdir / "nodal_marginal_prices.csv"
        )
    obj = float(status.get("objective") or 0.0)
    demand_gwh = float(n.loads_t.p_set.sum().sum()) / 1e3 if not n.loads_t.p_set.empty else 0.0
    gen_gwh = float(n.generators_t.p.clip(lower=0).sum().sum()) / 1e3 if not n.generators_t.p.empty else 0.0
    costs = pd.DataFrame(
        [
            {
                "global_scenario": ep.get("global_scenario"),
                "epoch": ep.get("name"),
                "objective_usd": obj,
                "demand_gwh": demand_gwh,
                "generation_gwh": gen_gwh,
                **scales,
            }
        ]
    )
    costs.to_csv(outdir / "system_costs.csv", index=False)
    meta = {
        **{k: ep.get(k) for k in ep},
        **scales,
        "solver_status": status.get("status"),
        "objective_usd": obj,
        "buses": int(len(n.buses)),
        "generators": int(len(n.generators)),
        "snapshots": int(len(n.snapshots)),
    }
    pd.DataFrame([meta]).to_csv(outdir / "run_metadata_log.csv", index=False)


def execute_run(root: Path, user_data: dict, outdir: Path | None = None) -> Path:
    """Solve each queued epoch on the chosen Colombia network (HiGHS default)."""
    import pypsa

    root = Path(root)
    if outdir is None:
        outdir = root / "outputs" / run_folder_name(user_data)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "scenario.json").write_text(
        json.dumps(user_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    epochs = user_data["epochs"]
    _write_progress(
        outdir,
        status="running",
        epoch_index=0,
        n_epochs=len(epochs),
        message="Arrancando PyPSA-col GUI…",
    )
    all_costs = []
    for i, ep in enumerate(epochs):
        net_key = ep.get("network", "osm-mesh")
        spec = NETWORKS.get(net_key, NETWORKS["osm-mesh"])
        try:
            nc = resolve_network_nc(root, net_key if net_key in NETWORKS else "osm-mesh")
        except FileNotFoundError:
            nc = root / spec["nc"]
        _write_progress(
            outdir,
            status="running",
            epoch_index=i,
            n_epochs=len(epochs),
            global_scenario=ep.get("global_scenario"),
            epoch=ep.get("name"),
            message=f"Época {i + 1}/{len(epochs)} · {ep.get('global_scenario')} · {spec['label']}",
        )
        if not nc.exists():
            _write_progress(
                outdir,
                status="error",
                message=f"No está {nc}. Corra primero el DAG OSM o dashboard-sin.",
            )
            raise FileNotFoundError(nc)
        n = pypsa.Network()
        n.import_from_netcdf(nc)
        scales = apply_levers(n, ep)
        solver = ep.get("solver_name") or "highs"
        threads = int(ep.get("solver_threads") or os.cpu_count() or 2)
        kwargs = {"solver_name": solver, "solver_options": {"threads": threads}}
        status = {"status": "skipped", "objective": None}
        try:
            res = n.optimize(**kwargs)
            # pypsa 1.2 returns (status, condition) or a linopy result
            if isinstance(res, tuple) and len(res) >= 1:
                status["status"] = str(res[0])
            else:
                status["status"] = str(getattr(res, "status", res))
            status["objective"] = float(getattr(n, "objective", 0) or 0)
        except Exception as exc:
            status["status"] = f"error: {exc}"
        ep_dir = outdir / f"s{ep.get('_scenario_index', 0):02d}_{_slug(ep.get('global_scenario', 'sc'))}_e{i:02d}"
        ep_dir.mkdir(parents=True, exist_ok=True)
        _export_epoch(n, ep_dir, ep, scales, status)
        try:
            from .io import load_config
            from .osm_mesh import emit_run_figures

            cfg = load_config(root / "config" / "osm-interactive.yaml")
            _write_progress(
                outdir,
                status="running",
                epoch_index=i,
                n_epochs=len(epochs),
                message=f"Figuras osm-interactive · {ep.get('global_scenario')} · {ep.get('name')}",
            )
            emit_run_figures(
                n,
                root,
                cfg,
                ep_dir,
                heading=f"{ep.get('global_scenario')} · {ep.get('name')}",
            )
        except Exception as exc:
            (ep_dir / "figures_error.txt").write_text(str(exc), encoding="utf-8")
        all_costs.append(
            {
                "global_scenario": ep.get("global_scenario"),
                "epoch": ep.get("name"),
                "objective_usd": status.get("objective"),
                "solver_status": status.get("status"),
                **scales,
            }
        )
        try:
            del n
        except Exception:
            pass
    pd.DataFrame(all_costs).to_csv(outdir / "system_costs.csv", index=False)
    _write_progress(
        outdir,
        status="done",
        epoch_index=len(epochs),
        n_epochs=len(epochs),
        message="Corrida terminada.",
        run_folder=str(outdir.relative_to(root) if outdir.is_relative_to(root) else outdir),
    )
    return outdir


def _slug(text: str) -> str:
    keep = []
    for ch in str(text).lower():
        if ch.isalnum():
            keep.append(ch)
        elif ch in " -_/":
            keep.append("-")
    s = "".join(keep).strip("-")
    while "--" in s:
        s = s.replace("--", "-")
    return s[:40] or "scenario"


def presets_payload() -> dict:
    return {
        "scenario_map": SCENARIO_MAP,
        "scenario_names": SCENARIO_NAMES,
        "preset_names": PRESET_NAMES,
        "all_global_names": ALL_GLOBAL_NAMES,
        "networks": {k: v["label"] for k, v in NETWORKS.items()},
        "colors": BASE_COLORS,
        "title": "PyPSA-col — a tool for Long-term Power Systems Planning in Colombia",
        "subtitle": "Sistema Interconectado Nacional (SIN) · XM DemaReal / CEN · malla OSM",
    }
