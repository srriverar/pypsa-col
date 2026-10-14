"""Prepare explicit model tables from synthetic, hybrid, or reviewed XM inputs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pypsa

from .io import (
    check_reviewed,
    read_timeseries,
    record_inputs,
    require_columns,
    snapshots,
    write_json,
)
from .xm import load_metric, verify_processed


def series_for(
    frame: pd.DataFrame, code: str, index: pd.DatetimeIndex, daily: bool = False
) -> pd.Series:
    selected = frame[frame.entity_code.astype(str).eq(str(code))]
    if selected.empty or selected.timestamp.duplicated().any():
        raise ValueError(f"Missing/non-unique observations for {code}")
    values = selected.set_index("timestamp").value
    result = values.reindex(index.normalize() if daily else index)
    result.index = index
    if result.isna().any() or not np.isfinite(result.to_numpy()).all():
        raise ValueError(f"Incomplete time series for {code}; missing values are not interpolated.")
    return result.astype(float)


def system_series(folder: Path, metric: str, quantity: str, index, daily=False):
    frame = load_metric(folder, metric, "Sistema", quantity)
    codes = frame.entity_code.unique()
    if len(codes) != 1:
        raise ValueError(f"{metric}: expected exactly one national total, got {codes}")
    return series_for(frame, codes[0], index, daily)


def allocate_demand(total: pd.Series, weights: pd.DataFrame, buses) -> pd.DataFrame:
    require_columns(weights, ["bus", "weight"], "demand allocation")
    if weights.bus.duplicated().any() or not set(weights.bus).issubset(set(buses)):
        raise ValueError("Demand allocation has duplicate or unknown buses")
    if (weights.weight < 0).any() or not np.isclose(weights.weight.sum(), 1.0, atol=1e-10):
        raise ValueError("Non-negative demand weights must sum to 1 exactly within tolerance")
    if total.isna().any() or (total < 0).any():
        raise ValueError("Invalid total demand")
    w = weights.set_index("bus").weight.reindex(buses, fill_value=0)
    result = pd.DataFrame(np.outer(total, w), index=total.index, columns=w.index)
    if not np.allclose(result.sum(axis=1), total, rtol=1e-12):
        raise AssertionError("Demand conservation failure")
    return result


def _reviewed_csv(path: Path, columns) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Required reviewed input {path} missing. See data/user/README.md; "
            "unreviewed templates cannot be used as real system data."
        )
    frame = pd.read_csv(path, dtype={"resource_code": str}, keep_default_na=False)
    require_columns(frame, columns, str(path))
    check_reviewed(frame, str(path))
    return frame


def _demo_inputs(root: Path, config: dict, n: pypsa.Network, index):
    if config["network"]["mode"] != "seven_hub":
        raise ValueError(
            "Demo/hybrid source fleet only matches seven_hub. Use xm_mapped for other topologies."
        )
    source = root / "resources/source"
    fleet = pd.read_csv(source / "generators.csv", keep_default_na=False)
    weights = pd.read_csv(source / "load_weights.csv")
    shape = np.clip(0.7 + 0.3 * np.sin(np.pi * (index.hour.to_numpy() - 6) / 12), 0.5, 1.1)
    total = pd.Series(weights.peak_mw.sum() * shape, index=index)
    hydro = fleet[fleet.carrier.eq("hydro")].copy()
    generators = fleet[~fleet.carrier.eq("hydro")].copy()
    hydro["e_nom"] = hydro.p_nom * config["hydro"]["demo_max_hours"]
    hydro["soc_initial"] = hydro.e_nom * config["hydro"]["demo_initial_fraction"]
    inflow = pd.DataFrame(
        {
            r["name"]: np.full(
                len(index), r["p_nom"] * config["hydro"]["demo_inflow_capacity_factor"]
            )
            for r in hydro.to_dict("records")
        },
        index=index,
    )
    if config["inputs"]["mode"] == "xm_hybrid":
        folder = root / config["inputs"]["xm_dir"]
        total = system_series(folder, config["inputs"]["demand_metric"], "hourly_mw", index)
        prior = pd.DatetimeIndex([index[0].normalize() - pd.Timedelta(days=1)])
        volume = system_series(folder, "VoluUtilDiarEner", "energy_mwh", prior, True).iloc[0]
        capacity_prior = system_series(folder, "CapaUtilDiarEner", "energy_mwh", prior, True).iloc[
            0
        ]
        capacity = system_series(folder, "CapaUtilDiarEner", "energy_mwh", index, True)
        inflow_system = system_series(folder, "AporEner", "energy_mwh", index, True) / 24
        if capacity_prior <= 0 or not 0 <= volume / capacity_prior <= 1:
            raise ValueError("Invalid observed national reservoir filling fraction")
        hydro["soc_initial"] = hydro.e_nom * volume / capacity_prior
        # HYBRID proxy: preserve national inflow/storage ratio, not fake regional observations.
        for row in hydro.to_dict("records"):
            inflow[row["name"]] = inflow_system / capacity * row["e_nom"]
    demand = allocate_demand(total, weights, n.buses.index)
    availability = pd.DataFrame(1.0, index=index, columns=generators.name)
    hydro_availability = pd.DataFrame(1.0, index=index, columns=hydro.name)
    return generators, hydro, demand, inflow, availability, hydro_availability


def _mapped_inputs(root: Path, config: dict, n: pypsa.Network, index, profiles):
    folder = root / config["inputs"]["xm_dir"]
    user = root / config["inputs"]["user_dir"]
    if index[0].hour != 0 or index[-1].hour != 23:
        raise ValueError("Mapped daily hydrology requires complete Colombian days.")
    mapping = _reviewed_csv(
        user / "resource_busmap.csv",
        ["resource_code", "name", "bus", "carrier", "marginal_cost", "efficiency", "profile"],
    )
    if mapping.resource_code.duplicated().any() or mapping.name.duplicated().any():
        raise ValueError("Resources must map once; names must be unique")
    if not set(mapping.bus).issubset(n.buses.index):
        raise ValueError("Resource crosswalk refers to unknown buses")
    cap = load_metric(folder, "CapEfecNeta", "Recurso", "power_mw")
    window = cap[cap.timestamp.between(index[0].normalize(), index[-1].normalize())]
    active = set(window.loc[window.value > 0, "entity_code"])
    missing = active - set(mapping.resource_code)
    if missing:
        raise ValueError(
            f"{len(missing)} positive-capacity XM resources lack a reviewed busmap; "
            f"examples: {sorted(missing)[:8]}. No silent fleet dropping."
        )
    mapping = mapping[mapping.resource_code.isin(active)].copy()
    if mapping.empty:
        raise ValueError("No mapped active resources")
    availability = pd.DataFrame(index=index)
    capacities = {}
    for row in mapping.to_dict("records"):
        values = series_for(cap, row["resource_code"], index, daily=True)
        if (values < 0).any() or values.max() <= 0:
            raise ValueError("Invalid historical capacity")
        capacities[row["resource_code"]] = values
        availability[row["name"]] = values / values.max()
    mapping["p_nom"] = mapping.resource_code.map(lambda code: capacities[code].max())
    generators = mapping[~mapping.carrier.eq("hydro")].copy()
    for row in generators.to_dict("records"):
        if row["carrier"] in {"solar", "wind", "ror"} and not row["profile"]:
            raise ValueError("Wind/solar/run-of-river resources require an explicit profile.")
        if row["profile"]:
            if row["profile"] not in profiles:
                raise ValueError(f"Unknown renewable/run-of-river profile {row['profile']}")
            availability[row["name"]] *= profiles[row["profile"]]
    resources_hydro = mapping[mapping.carrier.eq("hydro")]
    reservoirs = _reviewed_csv(user / "reservoir_map.csv", ["reservoir", "resource_code"])
    rivers = _reviewed_csv(user / "river_map.csv", ["river", "reservoir", "share"])
    if reservoirs.resource_code.duplicated().any() or set(reservoirs.resource_code) != set(
        resources_hydro.resource_code
    ):
        raise ValueError(
            "Every hydro resource must map to exactly one reservoir (no unmodelled cascades)."
        )
    if not set(rivers.reservoir).issubset(reservoirs.reservoir):
        raise ValueError("River allocation references unknown reservoirs")
    rivers["share"] = pd.to_numeric(rivers.share, errors="raise")
    if (rivers.share <= 0).any() or not np.allclose(rivers.groupby("river").share.sum(), 1.0):
        raise ValueError(
            "Shares for every selected river must be positive and sum to 1 (no double counting)."
        )
    volume = load_metric(folder, "VoluUtilDiarEner", "Embalse", "energy_mwh")
    capacity = load_metric(folder, "CapaUtilDiarEner", "Embalse", "energy_mwh")
    inflows = load_metric(folder, "AporEner", "Rio", "energy_mwh")
    prior = pd.DatetimeIndex([index[0].normalize() - pd.Timedelta(days=1)])
    hydro_rows, inflow, hydro_availability = (
        [],
        pd.DataFrame(index=index),
        pd.DataFrame(index=index),
    )
    for reservoir, group in reservoirs.groupby("reservoir"):
        resources = resources_hydro[resources_hydro.resource_code.isin(group.resource_code)]
        if resources.bus.nunique() != 1:
            raise ValueError(
                "One reservoir feeding multiple electrical buses needs a Store+Links cascade model; "
                "this adapter intentionally refuses to duplicate stored energy."
            )
        name = "Reservoir_" + reservoir
        energy_capacity = series_for(capacity, reservoir, index, True)
        if not np.allclose(energy_capacity, energy_capacity.iloc[0]):
            raise ValueError(
                "Changing useful reservoir capacity needs explicit bounds; not silently flattened."
            )
        initial = series_for(volume, reservoir, prior, True).iloc[0]
        if not 0 <= initial <= energy_capacity.iloc[0]:
            raise ValueError("Observed stored energy is outside reservoir capacity")
        selected = rivers[rivers.reservoir.eq(reservoir)]
        if selected.empty:
            raise ValueError(f"Reservoir {reservoir} has no reviewed river allocation.")
        inflow[name] = sum(
            series_for(inflows, r.river, index, True) * r.share / 24 for r in selected.itertuples()
        )
        power_capacity = sum(capacities[code] for code in resources.resource_code)
        hydro_availability[name] = power_capacity / power_capacity.max()
        hydro_rows.append(
            {
                "name": name,
                "bus": resources.bus.iloc[0],
                "carrier": "hydro",
                "p_nom": power_capacity.max(),
                "e_nom": energy_capacity.iloc[0],
                "soc_initial": initial,
                "marginal_cost": np.average(
                    resources.marginal_cost.astype(float), weights=resources.p_nom
                ),
            }
        )
    weights = _reviewed_csv(user / "load_weights.csv", ["bus", "weight"])
    total = system_series(folder, config["inputs"]["demand_metric"], "hourly_mw", index)
    demand = allocate_demand(total, weights, n.buses.index)
    return (
        generators,
        pd.DataFrame(hydro_rows),
        demand,
        inflow,
        availability[generators.name],
        hydro_availability,
    )


def prepare_inputs(root: Path, config: dict, output: Path) -> None:
    n = pypsa.Network(output / "base.nc")
    index = snapshots(config)
    profiles = read_timeseries(output / "renewable_profiles.csv", index)
    mode = config["inputs"]["mode"]
    if mode != "demo":
        hydro_entity = "Sistema" if mode == "xm_hybrid" else "Embalse"
        required = [
            (config["inputs"]["demand_metric"], "Sistema"),
            ("VoluUtilDiarEner", hydro_entity),
            ("CapaUtilDiarEner", hydro_entity),
            ("AporEner", "Sistema" if mode == "xm_hybrid" else "Rio"),
        ]
        if mode == "xm_mapped":
            required.append(("CapEfecNeta", "Recurso"))
        verify_processed(root / config["inputs"]["xm_dir"], required)
    if mode in {"demo", "xm_hybrid"}:
        data = _demo_inputs(root, config, n, index)
    elif mode == "xm_mapped":
        # Additional reviewed resource profiles can supply e.g. run-of-river shapes.
        extra = root / config["inputs"]["user_dir"] / "generator_profiles.csv"
        if extra.exists():
            additions = read_timeseries(extra, index)
            if set(additions) & set(profiles):
                raise ValueError("Duplicate additional profile names")
            profiles = pd.concat([profiles, additions], axis=1)
        data = _mapped_inputs(root, config, n, index, profiles)
    else:
        raise ValueError(f"Unknown inputs.mode {mode}")
    generators, hydro, demand, baseline_inflow, availability, hydro_availability = data
    fixed = config["investment"]["demo_fixed_renewables_mw"]
    if mode == "xm_mapped" and fixed:
        raise ValueError("Research inputs must not silently add demo renewable capacity")
    for candidate in config["investment"]["candidates"]:
        if candidate["name"] not in fixed or fixed[candidate["name"]] <= 0:
            continue
        row = {
            "name": candidate["name"],
            "bus": candidate["bus"],
            "carrier": candidate["carrier"],
            "p_nom": fixed[candidate["name"]],
            "marginal_cost": 0,
            "efficiency": 1,
            "profile": candidate["profile"],
        }
        generators = pd.concat([generators, pd.DataFrame([row])], ignore_index=True)
        availability[row["name"]] = profiles[row["profile"]]
    for frame, context in [
        (demand, "demand"),
        (baseline_inflow, "inflow"),
        (availability, "availability"),
        (hydro_availability, "hydro availability"),
    ]:
        if not np.isfinite(frame.to_numpy(dtype=float)).all() or (frame < 0).any().any():
            raise ValueError(f"Invalid {context}")
    if (availability > 1 + 1e-8).any().any() or (hydro_availability > 1 + 1e-8).any().any():
        raise ValueError("Availability exceeds 1")
    if not set(generators.bus).union(hydro.bus).issubset(n.buses.index):
        raise ValueError("An input asset references an unknown bus")
    if generators.name.duplicated().any() or hydro.name.duplicated().any():
        raise ValueError("Duplicate asset names")
    if (hydro.p_nom <= 0).any() or (hydro.e_nom <= 0).any():
        raise ValueError("Hydro turbine and storage capacities must be positive")
    multiplier = config["hydro"]["inflow_multiplier"]
    if multiplier < 0 or not np.isfinite(multiplier):
        raise ValueError("Hydro inflow multiplier must be finite and non-negative")
    hydro["baseline_inflow_mwh"] = hydro.name.map(baseline_inflow.sum())
    hydro["terminal_min_mwh"] = hydro.soc_initial
    generators.to_csv(output / "generators.csv", index=False)
    hydro.to_csv(output / "hydro.csv", index=False)
    for name, frame in [
        ("demand", demand),
        ("inflow", baseline_inflow * multiplier),
        ("generator_availability", availability),
        ("hydro_availability", hydro_availability),
    ]:
        frame.index.name = "snapshot"
        frame.to_csv(output / f"{name}.csv")
    climate = root / config["climate"]["sites"]
    paths = [output / "base.nc", output / "renewable_profiles.csv", climate]
    if mode != "demo":
        paths += list((root / config["inputs"]["xm_dir"]).glob("*"))
    if mode == "xm_mapped":
        paths += list((root / config["inputs"]["user_dir"]).glob("*.csv"))
    write_json(
        output / "input_provenance.json",
        {
            "mode": mode,
            "label": config["run"]["label"],
            "inputs": record_inputs(root, paths),
            "units": "MW, MWh, USD per MWh; no automatic COP/USD conversion",
            "hydro_energy_basis": "Electrical-equivalent reservoir energy: efficiency_dispatch=1 (do not count conversion twice).",
            "demand_allocation": "Fixed normalized bus weights; not measured nodal demand.",
            "hybrid_warning": "National reservoir filling/inflow-to-storage ratios applied to assumed model reservoirs; "
            "source fleet/costs/spatial weights are illustrative."
            if mode == "xm_hybrid"
            else None,
            "generation_use": "XM Gene is an observed validation reference, NEVER hydro inflow or renewable potential.",
            "availability": "Mapped conventional units use historical daily net capacity, not forced historical dispatch. "
            "DispoReal is downloaded for review/validation, not automatically imputed where absent.",
        },
    )
