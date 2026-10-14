"""PyPSA/Linopy operational and vintage-based multi-investment optimization."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

import pandas as pd
import pypsa
import xarray as xr

from .io import read_timeseries, snapshots, write_json


def annuity(rate: float, years: int) -> float:
    if rate < 0 or years <= 0:
        raise ValueError("Annuity requires non-negative rate and positive lifetime")
    return 1 / years if rate == 0 else rate / (1 - (1 + rate) ** -years)


def period_weights(periods, years, rate):
    if len(periods) != len(years) or not periods or rate < 0:
        raise ValueError("Invalid investment-period settings")
    if any(int(y) != y or y <= 0 for y in years):
        raise ValueError("Period year counts must be positive integers")
    if sorted(set(periods)) != periods or any(int(p) != p for p in periods):
        raise ValueError("Investment periods must be strictly increasing integer years")
    if any(periods[i] + years[i] != periods[i + 1] for i in range(len(periods) - 1)):
        raise ValueError("Investment years must cover consecutive, non-overlapping calendar blocks")
    first = periods[0]
    objective = [
        sum((1 + rate) ** -(y - first) for y in range(p, p + count))
        for p, count in zip(periods, years)
    ]
    return pd.DataFrame(
        {"years": years, "objective": objective}, index=pd.Index(periods, name="period")
    )


def _repeat(values: pd.DataFrame | pd.Series, n: pypsa.Network):
    if isinstance(n.snapshots, pd.MultiIndex):
        expanded = pd.concat(
            {p: values for p in n.investment_periods}, names=["period", "timestep"]
        )
        expanded.index = n.snapshots
        return expanded
    return values.set_axis(n.snapshots)


def _cost(candidate, config):
    return candidate["overnight_usd_per_mw"] * (
        annuity(config["investment"]["discount_rate"], candidate["lifetime"])
        + candidate["fom_fraction"]
    )


def assemble_network(root: Path, config: dict, resources: Path) -> pypsa.Network:
    n = pypsa.Network(resources / "base.nc")
    index = snapshots(config)
    n.set_snapshots(index)
    spec = config["investment"]
    if spec["enabled"]:
        n.set_investment_periods(spec["periods"])
        n.investment_period_weightings = period_weights(
            spec["periods"], spec["years"], spec["discount_rate"]
        )
        if len(index) < 8760 and not spec["annualize_short_horizon"]:
            raise ValueError(
                "Short investment horizons need explicit annualize_short_horizon=true. "
                "Never compare one-day OPEX directly against annual CAPEX."
            )
        weight = 8760 / len(index) if spec["annualize_short_horizon"] else 1.0
        n.snapshot_weightings.loc[:, ["objective", "generators"]] = weight
        # Repetition weights count economics/annual energy, NOT elapsed hours in
        # a storage transition. One actual sampled hour advances SOC by one hour.
        n.snapshot_weightings.loc[:, "stores"] = 1.0
    carriers = {
        "hydro",
        "gas",
        "oil",
        "coal",
        "solar",
        "wind",
        "battery",
        "load_shedding",
        "ror",
        "biomass",
    }
    for carrier in sorted(carriers - set(n.carriers.index)):
        n.add("Carrier", carrier)
    demand = read_timeseries(resources / "demand.csv", index)
    demand = _repeat(demand, n)
    if spec["enabled"]:
        growth = pd.Series(
            [
                (1 + spec["demand_growth"]) ** (p - spec["periods"][0])
                for p in n.snapshots.get_level_values("period")
            ],
            index=n.snapshots,
        )
        demand = demand.mul(growth, axis=0)
    for bus in demand:
        n.add("Load", "Demand_" + bus, bus=bus, p_set=demand[bus])
    generators = pd.read_csv(resources / "generators.csv", keep_default_na=False)
    availability = _repeat(read_timeseries(resources / "generator_availability.csv", index), n)
    for row in generators.to_dict("records"):
        if row["carrier"] not in n.carriers.index:
            n.add("Carrier", row["carrier"])
        n.add(
            "Generator",
            row["name"],
            bus=row["bus"],
            carrier=row["carrier"],
            p_nom=row["p_nom"],
            marginal_cost=row["marginal_cost"],
            efficiency=row["efficiency"],
            p_max_pu=availability[row["name"]],
        )
    hydro = pd.read_csv(resources / "hydro.csv", keep_default_na=False)
    inflow = _repeat(read_timeseries(resources / "inflow.csv", index), n)
    hydro_availability = _repeat(read_timeseries(resources / "hydro_availability.csv", index), n)
    terminal = config["hydro"]["terminal"]
    if terminal not in {"initial_min", "cyclic"}:
        raise ValueError("hydro.terminal must be initial_min or cyclic")
    for row in hydro.to_dict("records"):
        n.add(
            "StorageUnit",
            row["name"],
            bus=row["bus"],
            carrier="hydro",
            p_nom=row["p_nom"],
            max_hours=row["e_nom"] / row["p_nom"],
            p_min_pu=0,  # NO pumping from grid
            p_max_pu=hydro_availability[row["name"]],
            inflow=inflow[row["name"]],
            state_of_charge_initial=row["soc_initial"] if terminal != "cyclic" else 0,
            efficiency_store=1,
            efficiency_dispatch=1,
            state_of_charge_initial_per_period=bool(spec["enabled"]) and terminal != "cyclic",
            cyclic_state_of_charge=terminal == "cyclic" and not spec["enabled"],
            cyclic_state_of_charge_per_period=bool(spec["enabled"]) and terminal == "cyclic",
            marginal_cost=row["marginal_cost"],
        )
    for battery in config["storage"]["batteries"]:
        if battery["bus"] not in n.buses.index:
            raise ValueError("Battery references an unknown bus")
        attrs = {
            k: battery[k]
            for k in ("bus", "p_nom", "max_hours", "efficiency_store", "efficiency_dispatch")
        }
        n.add(
            "StorageUnit",
            battery["name"],
            carrier="battery",
            cyclic_state_of_charge=not spec["enabled"],
            cyclic_state_of_charge_per_period=bool(spec["enabled"]),
            marginal_cost=0.5,
            **attrs,
        )
    groups = []
    if spec["enabled"]:
        profiles = _repeat(read_timeseries(resources / "renewable_profiles.csv", index), n)
        for candidate in spec["candidates"]:
            if candidate["bus"] not in n.buses.index:
                raise ValueError("Candidate references an unknown bus")
            names = []
            for period in spec["periods"]:
                name = f"{candidate['name']}__{period}"
                n.add(
                    "Generator",
                    name,
                    bus=candidate["bus"],
                    carrier=candidate["carrier"],
                    p_nom_extendable=True,
                    p_nom_min=0,
                    p_nom_max=candidate["max_mw"],
                    p_max_pu=profiles[candidate["profile"]],
                    build_year=period,
                    lifetime=candidate["lifetime"],
                    capital_cost=_cost(candidate, config),
                    marginal_cost=0,
                )
                names.append(name)
            existing = (
                float(n.generators.loc[candidate["name"], "p_nom"])
                if candidate["name"] in n.generators.index
                else 0.0
            )
            groups.append(
                {
                    "component": "Generator",
                    "label": candidate["name"],
                    "names": names,
                    "limit": candidate["max_mw"],
                    "existing": existing,
                }
            )
        for candidate in spec.get("battery_candidates", []):
            names = []
            for period in spec["periods"]:
                name = f"{candidate['name']}__{period}"
                n.add(
                    "StorageUnit",
                    name,
                    bus=candidate["bus"],
                    carrier="battery",
                    p_nom_extendable=True,
                    p_nom_max=candidate["max_new_mw"],
                    max_hours=candidate["max_hours"],
                    efficiency_store=candidate["efficiency_store"],
                    efficiency_dispatch=candidate["efficiency_dispatch"],
                    cyclic_state_of_charge=False,
                    cyclic_state_of_charge_per_period=True,
                    build_year=period,
                    lifetime=candidate["lifetime"],
                    capital_cost=_cost(candidate, config),
                    marginal_cost=0.5,
                )
                names.append(name)
            groups.append(
                {
                    "component": "StorageUnit",
                    "label": candidate["name"],
                    "names": names,
                    "limit": candidate["max_new_mw"],
                    "existing": 0.0,
                }
            )
        for candidate in spec.get("transmission_candidates", []):
            if candidate["from_link"] not in n.links.index:
                raise ValueError(
                    "Transport expansion must reference an existing Link; AC expansion is not auto-converted."
                )
            base = n.links.loc[candidate["from_link"]]
            names = []
            for period in spec["periods"]:
                name = f"{candidate['name']}__{period}"
                n.add(
                    "Link",
                    name,
                    bus0=base.bus0,
                    bus1=base.bus1,
                    carrier="transport",
                    p_min_pu=-1,
                    efficiency=1,
                    p_nom_extendable=True,
                    p_nom_max=candidate["max_new_mw"],
                    build_year=period,
                    lifetime=candidate["lifetime"],
                    capital_cost=_cost(candidate, config),
                )
                names.append(name)
            groups.append(
                {
                    "component": "Link",
                    "label": candidate["name"],
                    "names": names,
                    "limit": candidate["max_new_mw"],
                    "existing": 0.0,
                }
            )
    if config["solver"]["allow_load_shedding"]:
        bound = max(1.0, float(demand.sum(axis=1).max()) * 1.1)
        for bus in n.buses.index:
            n.add(
                "Generator",
                "Unserved_" + bus,
                bus=bus,
                carrier="load_shedding",
                p_nom=bound,
                marginal_cost=config["solver"]["voll_usd_per_mwh"],
            )
    n.meta = {
        **n.meta,
        "run": config["run"],
        "data_mode": config["inputs"]["mode"],
        "snapshot_timezone": "America/Bogota (naive wall time)",
        "currency": "illustrative USD",
        "investment_enabled": spec["enabled"],
        "potential_groups": groups,
        "hydro_constraints": hydro.to_dict("records"),
        "config": config,
        "versions": {
            name: version(name) for name in ("pypsa", "linopy", "highspy", "pandas", "numpy")
        },
    }
    return n


def extra_constraints(n: pypsa.Network, sns):
    """Water budgets and terminal SOC apply separately in each investment period."""
    config = n.meta["config"]
    multi = isinstance(sns, pd.MultiIndex)
    periods = n.investment_periods if multi else [None]
    hydro = n.meta["hydro_constraints"]
    budget_fraction = config["hydro"]["energy_budget_fraction"]
    if budget_fraction is not None and not 0 <= budget_fraction <= 1:
        raise ValueError("Hydro energy budget fraction must be in [0,1]")
    for period in periods:
        group = sns[sns.get_level_values("period") == period] if multi else sns
        for row in hydro:
            name = row["name"]
            if config["hydro"]["terminal"] == "initial_min":
                soc = n.model["StorageUnit-state_of_charge"].sel(snapshot=group[-1], name=name)
                n.model.add_constraints(
                    soc >= row["terminal_min_mwh"], name=f"Hydro-terminal-{name}-{period}"
                )
            if budget_fraction is not None:
                dispatch = n.model["StorageUnit-p_dispatch"].sel(snapshot=group, name=name)
                hours = xr.DataArray(
                    n.snapshot_weightings.loc[group, "stores"].to_numpy(),
                    dims=["snapshot"],
                    coords={"snapshot": group},
                )
                n.model.add_constraints(
                    (dispatch * hours).sum() <= row["baseline_inflow_mwh"] * budget_fraction,
                    name=f"Hydro-energy-budget-{name}-{period}",
                )
    for group in n.meta["potential_groups"]:
        variable = n.model[f"{group['component']}-p_nom"]
        table = n.components[group["component"]].static
        for period in n.investment_periods:
            active = [
                name
                for name in group["names"]
                if table.at[name, "build_year"]
                <= period
                < table.at[name, "build_year"] + table.at[name, "lifetime"]
            ]
            if active:
                # Physical potential is shared by all active vintages, not reset for each build year.
                n.model.add_constraints(
                    variable.sel(name=active).sum() <= group["limit"] - group["existing"],
                    name=f"Shared-potential-{group['component']}-{group['label']}-{period}",
                )


def solve(root: Path, config: dict, resources: Path, results: Path) -> pypsa.Network:
    results.mkdir(parents=True, exist_ok=True)
    n = assemble_network(root, config, resources)
    n.export_to_netcdf(resources / "prepared.nc")
    status, condition = n.optimize(
        solver_name=config["solver"]["name"],
        multi_investment_periods=config["investment"]["enabled"],
        extra_functionality=extra_constraints,
        include_objective_constant=False,
        solver_options={"threads": config["solver"]["threads"]},
        log_to_console=False,
    )
    summary = {
        "status": status,
        "termination_condition": condition,
        "objective_usd": float(n.objective) if status == "ok" else None,
        "objective_scope": "Discounted annualized modeled costs over configured period blocks"
        if config["investment"]["enabled"]
        else "Operating cost over modeled hours (not annual)",
        "versions": n.meta["versions"],
        "config": config,
    }
    write_json(results / "solver.json", summary)
    if status != "ok" or condition != "optimal":
        raise RuntimeError(
            f"Optimization failed: {status}/{condition}; see solver.json. "
            "Review islands, reservoir boundaries and dispatch availability; no results were accepted."
        )
    from .results import validate_solution

    summary["qa"] = validate_solution(n, config["solver"]["balance_tolerance_mw"])
    write_json(results / "solver.json", summary)
    n.export_to_netcdf(results / "network.nc")
    return n
