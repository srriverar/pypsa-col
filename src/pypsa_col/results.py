"""Physical residual checks, transparent summaries, and offline HTML reports."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa

from .inputs import system_series
from .io import write_json

COLORS = {
    "hydro": "#257ba5",
    "gas": "#d39b64",
    "coal": "#5d6067",
    "oil": "#998373",
    "wind": "#5db69d",
    "solar": "#e5be54",
    "battery": "#bba4ce",
    "load_shedding": "#dc5b5b",
}


def groups(n):
    if isinstance(n.snapshots, pd.MultiIndex):
        return [
            (int(p), n.snapshots[n.snapshots.get_level_values("period") == p])
            for p in n.investment_periods
        ]
    return [("operational", n.snapshots)]


def active_assets(table: pd.DataFrame, period):
    if period == "operational":
        return pd.Series(True, index=table.index)
    return (table.build_year <= period) & (table.build_year + table.lifetime > period)


def nodal_residual(n: pypsa.Network) -> pd.DataFrame:
    residual = pd.DataFrame(0.0, index=n.snapshots, columns=n.buses.index)
    for table, time, sign in [
        (n.generators, n.generators_t.p, 1),
        (n.loads, n.loads_t.p, -1),
        (n.storage_units, n.storage_units_t.p, 1),
        (n.stores, n.stores_t.p, 1),
    ]:
        for name, row in table.iterrows():
            residual[row.bus] += sign * time[name]
    for table, time in [
        (n.lines, n.lines_t),
        (n.links, n.links_t),
        (n.transformers, n.transformers_t),
    ]:
        for name, row in table.iterrows():
            residual[row.bus0] -= time.p0[name]
            residual[row.bus1] -= time.p1[name]
    return residual


def charge_power(n: pypsa.Network) -> pd.DataFrame:
    """PyPSA NetCDF omits zero p_store outputs; absent columns imply zero."""
    frame = n.storage_units_t.p_store.reindex(
        index=n.snapshots, columns=n.storage_units.index, fill_value=0.0
    )
    if frame.isna().any().any():
        raise ValueError("Non-finite storage charging output")
    return frame.astype(float)


def storage_residual(n: pypsa.Network) -> pd.DataFrame:
    residual = pd.DataFrame(0.0, index=n.snapshots, columns=n.storage_units.index)
    inflow = n.get_switchable_as_dense("StorageUnit", "inflow")
    # NetCDF omits all-zero output columns. Restore PyPSA's output defaults,
    # not missing observations from raw data.
    charge = charge_power(n)
    for period, sns in groups(n):
        for name, row in n.storage_units.iterrows():
            if not active_assets(n.storage_units, period).loc[name]:
                continue
            soc = n.storage_units_t.state_of_charge.loc[sns, name]
            previous = soc.shift(1)
            cyclic = row.cyclic_state_of_charge or (
                period != "operational" and row.cyclic_state_of_charge_per_period
            )
            previous.iloc[0] = soc.iloc[-1] if cyclic else row.state_of_charge_initial
            hours = n.snapshot_weightings.loc[sns, "stores"]
            spill = n.storage_units_t.spill.reindex(index=sns, columns=[name], fill_value=0)[
                name
            ].fillna(0)
            delta = hours * (
                inflow.loc[sns, name]
                + row.efficiency_store * charge.loc[sns, name]
                - n.storage_units_t.p_dispatch.loc[sns, name] / row.efficiency_dispatch
                - spill
            )
            residual.loc[sns, name] = soc - previous * (1 - row.standing_loss) ** hours - delta
    return residual


def validate_solution(n: pypsa.Network, tolerance=1e-5) -> dict:
    residual = nodal_residual(n)
    water = storage_residual(n)
    max_balance = float(residual.abs().max().max())
    max_storage = float(water.abs().max().max()) if water.size else 0.0
    max_flow_violation = 0.0
    for table, time, attribute, pu in [
        (n.lines, n.lines_t, "s_nom_opt", "s_max_pu"),
        (n.transformers, n.transformers_t, "s_nom_opt", "s_max_pu"),
        (n.links, n.links_t, "p_nom_opt", "p_max_pu"),
    ]:
        if len(table):
            bounds = table[attribute] * table[pu]
            max_flow_violation = max(
                max_flow_violation, float((time.p0.abs() - bounds).max().max())
            )
    hydro_ids = n.storage_units.index[n.storage_units.carrier.eq("hydro")]
    pumping = float(charge_power(n)[hydro_ids].abs().to_numpy().max()) if len(hydro_ids) else 0.0
    terminal_violation = 0.0
    budget_violation = 0.0
    conf = n.meta.get("config", {})
    for _, sns in groups(n):
        for row in n.meta.get("hydro_constraints", []):
            if conf["hydro"]["terminal"] == "initial_min":
                terminal_violation = max(
                    terminal_violation,
                    row["terminal_min_mwh"]
                    - float(n.storage_units_t.state_of_charge.loc[sns[-1], row["name"]]),
                )
            fraction = conf["hydro"]["energy_budget_fraction"]
            if fraction is not None:
                used = (
                    n.storage_units_t.p_dispatch.loc[sns, row["name"]]
                    * n.snapshot_weightings.loc[sns, "stores"]
                ).sum()
                budget_violation = max(
                    budget_violation, used - row["baseline_inflow_mwh"] * fraction
                )
    checks = {
        "max_nodal_residual_mw": max_balance,
        "max_storage_residual_mwh": max_storage,
        "max_branch_bound_violation_mw": max(0.0, max_flow_violation),
        "hydro_grid_charging_mw": pumping,
        "max_terminal_violation_mwh": max(0.0, terminal_violation),
        "max_hydro_budget_violation_mwh": max(0.0, budget_violation),
    }
    if any(not np.isfinite(v) or v > tolerance for v in checks.values()):
        raise ValueError(f"Post-solve physical checks FAILED: {checks}")
    return {**checks, "tolerance": tolerance, "passed": True}


def branch_summary(n: pypsa.Network) -> pd.DataFrame:
    rows = []
    for period, sns in groups(n):
        for kind, table, dynamic, attr in [
            ("Link", n.links, n.links_t, "p_nom_opt"),
            ("Line", n.lines, n.lines_t, "s_nom_opt"),
            ("Transformer", n.transformers, n.transformers_t, "s_nom_opt"),
        ]:
            for name in table.index[active_assets(table, period)]:
                row = table.loc[name]
                bound = row[attr] * row.get("s_max_pu", row.get("p_max_pu", 1.0))
                flow = dynamic.p0.loc[sns, name]
                util = flow.abs() / bound if bound > 1e-8 else flow.abs() * 0
                rows.append(
                    {
                        "period": period,
                        "component": kind,
                        "name": name,
                        "bus0": row.bus0,
                        "bus1": row.bus1,
                        "capacity_mw_or_mva": row[attr],
                        "peak_utilization_percent": float(util.max() * 100),
                        "binding_sample_hours": int((util >= 0.999).sum()),
                        "mean_abs_flow_mw": flow.abs().mean(),
                    }
                )
    return pd.DataFrame(rows)


def dispatch_by_carrier(n):
    dispatch = n.generators_t.p.T.groupby(n.generators.carrier).sum().T
    store = n.storage_units_t.p_dispatch.T.groupby(n.storage_units.carrier).sum().T
    return dispatch.add(store, fill_value=0)


def write_results(root: Path, config: dict, resources: Path, results: Path, n=None) -> dict:
    n = n if n is not None else pypsa.Network(results / "network.nc")
    qa = validate_solution(n, config["solver"]["balance_tolerance_mw"])
    nodal_residual(n).to_csv(results / "nodal_residual_mw.csv")
    storage_residual(n).to_csv(results / "storage_residual_mwh.csv")
    tables = {
        "dispatch_mw": n.generators_t.p,
        "storage_dispatch_mw": n.storage_units_t.p_dispatch,
        "storage_charge_mw": charge_power(n),
        "state_of_charge_mwh": n.storage_units_t.state_of_charge,
        "prices_usd_per_mwh": n.buses_t.marginal_price,
        "load_mw": n.loads_t.p,
        "link_flows_mw": n.links_t.p0,
        "line_flows_mw": n.lines_t.p0,
        "dispatch_by_carrier_mw": dispatch_by_carrier(n),
    }
    for name, table in tables.items():
        table.to_csv(results / f"{name}.csv")
    branch_summary(n).to_csv(results / "branches.csv", index=False)
    energy, capacities = [], []
    shed = n.generators.index[n.generators.carrier.eq("load_shedding")]
    for period, sns in groups(n):
        weight = n.snapshot_weightings.loc[sns, "generators"]
        demand = float(n.loads_t.p.loc[sns].sum(axis=1).mul(weight).sum())
        unserved = float(n.generators_t.p.loc[sns, shed].sum(axis=1).mul(weight).sum())
        hydro_ids = n.storage_units.index[n.storage_units.carrier.eq("hydro")]
        hydro_mwh = float(
            n.storage_units_t.p_dispatch.loc[sns, hydro_ids].sum(axis=1).mul(weight).sum()
        )
        energy.append(
            {
                "period": period,
                "represented_hours": float(weight.sum()),
                "demand_mwh": demand,
                "unserved_mwh": unserved,
                "unserved_fraction": unserved / demand if demand else 0,
                "hydro_generation_mwh": hydro_mwh,
                "energy_scope": "per modeled year" if period != "operational" else "modeled window",
            }
        )
        for kind, table in [
            ("Generator", n.generators),
            ("StorageUnit", n.storage_units),
            ("Link", n.links),
        ]:
            for name in table.index[active_assets(table, period)]:
                row = table.loc[name]
                capacities.append(
                    {
                        "period": period,
                        "component": kind,
                        "name": name,
                        "carrier": row.carrier,
                        "p_nom_mw": row.p_nom_opt,
                        "build_year": row.build_year,
                        "lifetime": row.lifetime,
                        "extendable": row.p_nom_extendable,
                    }
                )
    pd.DataFrame(energy).to_csv(results / "energy_by_period.csv", index=False)
    pd.DataFrame(capacities).to_csv(results / "active_capacities.csv", index=False)
    summary = {
        "run": config["run"],
        "data_mode": config["inputs"]["mode"],
        "objective_usd": float(n.objective),
        "qa": qa,
        "energy_by_period": energy,
        "buses": len(n.buses),
        "snapshots": len(n.snapshots),
        "warning": "Demonstration/hybrid outcomes are NOT estimates of actual Colombian system costs or reliability.",
        "topology": n.meta["topology"],
        "price_interpretation": "Model nodal marginal prices, not XM's national market price. No COP/USD conversion performed.",
    }
    if config["inputs"]["mode"] != "demo":
        folder = root / config["inputs"]["xm_dir"]
        idx = n.snapshots.get_level_values(-1).unique()
        observed = pd.DataFrame(index=idx)
        observed["xm_demand_mw"] = system_series(folder, "DemaReal", "hourly_mw", idx)
        observed["xm_generation_mw"] = system_series(folder, "Gene", "hourly_mw", idx)
        observed["xm_price_cop_per_mwh"] = system_series(
            folder, "PrecBolsNaci", "price_cop_mwh", idx
        )
        observed.to_csv(results / "xm_observed_reference.csv")
        summary["xm_reference_note"] = (
            "Observed national demand/generation/price; not a calibrated model fit. "
            "Imports, losses and demand definitions prevent assuming demand=Gene."
        )
    write_json(results / "summary.json", summary)
    plot_dispatch(n, results / "dispatch.png")
    render_html(root, config, resources, results, summary)
    return summary


def plot_dispatch(n: pypsa.Network, path: Path):
    period, sns = groups(n)[-1]
    time = sns.get_level_values(-1) if isinstance(sns, pd.MultiIndex) else sns
    data = dispatch_by_carrier(n).loc[sns]
    data.index = time
    data = data.loc[:, data.abs().max() > 1e-6]
    fig, axes = plt.subplots(
        3,
        1,
        figsize=(11.8, 8.6),
        sharex=True,
        gridspec_kw={"height_ratios": [2, 1, 1]},
        layout="constrained",
    )
    fig.set_facecolor("#faf9f5")
    for ax in axes:
        ax.set_facecolor("#faf9f5")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.12)
    axes[0].stackplot(
        time,
        *[data[c] for c in data],
        labels=list(data),
        colors=[COLORS.get(c, "#999999") for c in data],
        alpha=0.95,
    )
    load = n.loads_t.p.loc[sns].sum(axis=1)
    charge = n.storage_units_t.p_store.loc[sns].sum(axis=1)
    axes[0].plot(time, load + charge, color="#102f3e", lw=1.2, label="load + storage charging")
    axes[0].set_ylabel("MW")
    axes[0].legend(loc="upper left", ncol=4, fontsize=8)
    axes[0].set_title(
        f"PyPSA-col | {n.meta['run']['id']} | {period}\nIllustrative modeled dispatch, not measured SIN dispatch",
        loc="left",
        fontsize=13,
        color="#102f3e",
        pad=12,
    )
    for name in n.storage_units.index[n.storage_units.carrier.eq("hydro")]:
        axes[1].plot(time, n.storage_units_t.state_of_charge.loc[sns, name] / 1000, label=name)
    axes[1].set_ylabel("Reservoir GWh")
    axes[1].legend(loc="upper left", fontsize=8, ncol=3)
    for bus in n.buses.index[:7]:
        axes[2].plot(time, n.buses_t.marginal_price.loc[sns, bus], lw=1.1, label=bus)
    axes[2].set_ylabel("Model USD/MWh")
    axes[2].set_xlabel("Colombian local time (America/Bogota)")
    axes[2].legend(loc="upper left", fontsize=8, ncol=4)
    fig.savefig(path, dpi=145)
    plt.close(fig)


def image_uri(path: Path):
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def render_html(root: Path, config: dict, resources: Path, results: Path, summary=None):
    summary = summary or json.loads((results / "summary.json").read_text())
    poster = results / "grid2poster.png"
    inventory = json.loads((root / "resources/source/inventory.json").read_text())
    energy = pd.DataFrame(summary["energy_by_period"])
    table = energy[["period", "demand_mwh", "unserved_mwh", "hydro_generation_mwh"]].to_html(
        index=False, float_format=lambda x: f"{x:,.1f}", border=0, classes="data"
    )
    poster_html = (
        f'<img src="{image_uri(poster)}" alt="Grid2Poster Colombia OSM network with modeled corridor overlay">'
        if poster.exists()
        else "<p>Run the poster stage to render the map.</p>"
    )
    label = html.escape(config["run"]["label"])
    doc = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PyPSA-col · {html.escape(config["run"]["id"])}</title><style>
:root{{--ink:#163544;--blue:#217fa0;--paper:#f5f3ed;--line:#d6dedb}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 system-ui,sans-serif}}main{{max-width:1180px;margin:auto;padding:40px 36px}}header{{border-top:5px solid var(--blue);padding-top:24px}}.eyebrow{{font-size:12px;letter-spacing:3px;text-transform:uppercase;color:#58828b}}h1{{font-size:64px;line-height:1.05;letter-spacing:-3px;margin:20px 0}}h2{{font-size:26px;letter-spacing:-.8px;margin-top:36px}}.lede{{font-size:20px;max-width:870px;color:#526a70}}.badge{{background:#ddece7;padding:5px 10px;border-radius:3px;font-size:12px;text-transform:uppercase;letter-spacing:1px}}.warning{{border-left:4px solid #d39b64;background:#eee5d6;padding:16px 22px;margin:26px 0}}.metrics{{display:grid;grid-template-columns:repeat(3,1fr);border-block:1px solid var(--line);padding:24px 0;gap:20px}}.metric strong{{display:block;font-size:35px;font-weight:500}}.metric small{{color:#687e80}}img{{max-width:100%;height:auto}}.cols{{display:grid;grid-template-columns:1fr 1fr;gap:40px;align-items:start}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border-bottom:1px solid var(--line);padding:10px 9px;text-align:right}}td:first-child,th:first-child{{text-align:left}}pre{{background:#173744;color:#e5f1f1;padding:18px;overflow:auto;border-radius:5px;font:13px/1.65 ui-monospace,monospace}}footer{{margin-top:48px;padding-top:18px;border-top:1px solid var(--line);color:#658087;font-size:12px}}.small{{font-size:13px;color:#587077}}@media(max-width:700px){{main{{padding:22px 16px}}h1{{font-size:47px}}.cols,.metrics{{grid-template-columns:1fr}}table{{font-size:11px}}}}
</style><main><header><div class="eyebrow">Colombian power-system research · reproducible run</div><h1>PyPSA-col</h1><span class="badge">{html.escape(summary["data_mode"])} · optimal · physical checks passed</span><p class="lede">{label}</p></header>
<div class="warning"><strong>Research software, not a validated national planning model.</strong> Demo fleet capacities, costs, nodal demand allocations and site potentials are assumptions. Hybrid runs retain these limitations even when their national XM inputs are observed. Unserved energy in these examples is not an estimate of real SIN shortages.</div>
<div class="metrics"><div class="metric"><strong>{summary["buses"]}</strong><small>modeled buses · {html.escape(summary["topology"])}</small></div><div class="metric"><strong>{summary["snapshots"]}</strong><small>modeled snapshots · local Colombia time</small></div><div class="metric"><strong>{summary["qa"]["max_nodal_residual_mw"]:.1e}</strong><small>maximum nodal residual · MW</small></div></div>
<h2>01 / Dispatch, reservoir states & shadow prices</h2><img src="{image_uri(results / "dispatch.png")}" alt="Model dispatch, reservoir energy and nodal price time series">
<p class="small">The final investment period is plotted for multi-period runs. Model prices use buses_t.marginal_price; they are not XM national clearing prices. Objective: {summary["objective_usd"]:,.2f} illustrative USD — {"discounted modeled 2026–2030 cost" if config["investment"]["enabled"] else "operating cost for the sampled window"}.</p>
{table}<p class="small">Energy is for each modeled year in investment runs (annual repetition weights), otherwise the modeled window. Full hourly CSVs, branch results and NetCDF networks are alongside this report.</p>
<h2>02 / Grounded in your repository</h2><div class="cols"><div>{poster_html}</div><div><h3>Data before diagrams</h3><p>The pinned ColombiaCongestionV2 source contains {inventory["osm_lines"]:,} OSM line features, {inventory["osm_substations"]:,} substation features and {inventory["osm_plants"]:,} plant features. {inventory["substations_tagged_220_230_500"]} substations carry 220/230/500 kV tags.</p><p>Grid2Poster is executed directly through your offline Colombian renderer, preserving its voltage tiers, themes, geographic boundary and ZNI insets. Corridor colors come from this PyPSA solve; routes come from your PARATEC/OSM matching code.</p><p><strong>Do not read this map as measured congestion on physical lines.</strong> Routes are heuristic and may overlap. The routing graph is never used to create the electrical topology. Dashed routes, if present, denote geometric fallback rather than an OSM path.</p><h3>From 7 hubs to reviewed topology</h3><p>The physical adapter keeps voltage levels separate, reports islands, and requires supplied transformer connections and reviewed line parameters for a research run. An 18-region reduction requires a complete, cited busmap; neither official membership nor a 147-bus count is invented.</p></div></div>
<h2>03 / Reproduce this run</h2><pre>python -m venv .venv\nsource .venv/bin/activate\npip install -e '.[workflow,climate,dev]'\npython scripts/bootstrap_sources.py\npypsa-col run --config config/{html.escape(config["run"]["id"])}.yaml\npytest -q</pre>
<p>See <code>README.md</code>, <code>docs/DATA.md</code>, <code>docs/NETWORK.md</code>, <code>docs/MODEL.md</code> and <code>docs/GRID2POSTER.md</code> for data contracts and assumptions. ERA5 is credential-gated; the delivered demo never calls Copernicus.</p>
<footer>Source commit {inventory["upstream"]["commit"]} · OSM © contributors (ODbL) · Grid2Poster © Open Energy Transition / Tobias Augspurger (MIT) · Colombia adaptation: Prof. Sergio Rivera. New PyPSA-col code: MIT; separate data terms apply. This HTML is self-contained and requires no network access.</footer></main></html>'''
    (results / "report.html").write_text(doc)
