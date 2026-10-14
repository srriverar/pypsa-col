"""OSM-wide Colombian mesh (more buses) + XM/dashboard plants and demand.

Worldwide source: OpenStreetMap power features shipped in ColombiaCongestionV2
(global OSM schema, Colombia extract). Plants: OSM `centrales` coordinates plus
XM ListadoRecursos/CapEfecNeta/Gene from the dashboard-sin-nodal contract.
Demand: DemaReal allocated with the dashboard's declared zonal shares.

Same-station 220/230/500 kV buses are linked with **engineering-default
transformers** so the mesh is one solvable component. That is an assumption,
not an official PARATEC transformer register.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
import networkx as nx
import numpy as np
import pandas as pd
import pydeck as pdk
import pypsa
from pyproj import Transformer
from scipy.spatial import cKDTree

from .dashboard_sin import (
    PESO_DEMANDA,
    ZONAS,
    assemble_plants,
    carrier_of,
    demand_by_zone,
    load_tables,
)
from .io import load_config, snapshots, write_json
from .plotting import NICE_NAME, STACK_ORDER, WORKSHOP_COLORS
from .source import verify_source

def _geo_rings(geom) -> list[np.ndarray]:
    kind = geom["type"]
    rings: list[np.ndarray] = []
    if kind == "Polygon":
        rings.append(np.asarray(geom["coordinates"][0], float))
    elif kind == "MultiPolygon":
        for poly in geom["coordinates"]:
            rings.append(np.asarray(poly[0], float))
    elif kind == "GeometryCollection":
        for child in geom.get("geometries", []):
            rings.extend(_geo_rings(child))
    return rings


def colombia_geojson(root: Path, config: dict) -> dict:
    """Mainland + Caribbean islands from the pinned OSM/geoBoundaries snapshot."""
    base = root / config["source"]["path"] / "data/reference"
    features = []
    for name in ("colombia_boundary_full.geojson", "san_andres_boundary.geojson"):
        path = base / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        features.extend(payload.get("features", []))
    return {"type": "FeatureCollection", "features": features}


def draw_colombia(ax, root: Path, config: dict, *, fill="#e7efe4", edge="#2f4a3c", lw=0.9):
    geo = colombia_geojson(root, config)
    for feat in geo["features"]:
        for ring in _geo_rings(feat["geometry"]):
            ax.add_patch(
                MplPolygon(
                    ring,
                    closed=True,
                    facecolor=fill,
                    edgecolor=edge,
                    linewidth=lw,
                    zorder=0,
                    alpha=0.95,
                )
            )
    ax.set_facecolor("#d7e6f0")  # water


def _colombia_layer(root: Path, config: dict) -> pdk.Layer:
    return pdk.Layer(
        "GeoJsonLayer",
        data=colombia_geojson(root, config),
        stroked=True,
        filled=True,
        get_fill_color=[198, 219, 191, 210],
        get_line_color=[47, 74, 60, 255],
        get_line_width=2500,
        line_width_min_pixels=1.4,
        pickable=False,
    )


OSM_FUEL = {
    "hydro": None,  # refined by metodo
    "solar": "Solar",
    "wind": "Wind Onshore",
    "gas": "Gas",
    "coal": "Hard Coal",
    "oil": "Oil",
    "diesel": "Oil",
    "biofuel": "Waste",
    "biomass": "Waste",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = text.upper()
    for token in (
        "CENTRAL", "HIDROELECTRICA", "HIDROELECTRICO", "TERMOELECTRICA", "TERMOMECANICA",
        "PARQUE", "EOLICO", "SOLAR", "GENERACION", "PLANTA",
    ):
        text = text.replace(token, " ")
    return " ".join(text.split())


def _carrier_osm(props: dict) -> str:
    fuel = str(props.get("fuente_energia") or "").lower()
    method = str(props.get("metodo") or "").lower()
    if fuel == "hydro":
        if "run" in method or "stream" in method:
            return "Run of River"
        return "Storage Hydro"
    return OSM_FUEL.get(fuel, "Other")


def load_osm_plants(root: Path, config: dict) -> pd.DataFrame:
    path = root / config["source"]["path"] / "data/geo/centrales_osm.geojson"
    geo = json.loads(path.read_text())
    rows = []
    for feat in geo["features"]:
        p = feat["properties"]
        lon, lat = feat["geometry"]["coordinates"][:2]
        rows.append(
            {
                "osm_id": p.get("id"),
                "nombre_osm": p.get("nombre") or "",
                "carrier": _carrier_osm(p),
                "osm_mw": float(p.get("mw") or 0.0),
                "lon": float(lon),
                "lat": float(lat),
                "key": _norm(p.get("nombre") or ""),
            }
        )
    return pd.DataFrame(rows)


def build_connected_mesh(root: Path, config: dict, output: Path) -> pypsa.Network:
    """Reuse the physical OSM candidate and add same-station transformers."""
    from .network import physical_candidate, topology_report

    verify_source(root, config)
    raw_dir = output / "raw_candidate"
    raw_dir.mkdir(parents=True, exist_ok=True)
    physical_candidate(root, config, raw_dir)
    buses = pd.read_csv(raw_dir / "physical_buses.csv")
    lines = pd.read_csv(raw_dir / "physical_lines.csv")
    graph = nx.Graph()
    graph.add_nodes_from(buses.bus)
    graph.add_edges_from(zip(lines.bus0, lines.bus1, strict=False))
    transformers = []
    grouped = buses[buses.station_id.fillna("").ne("")].groupby("station_id")
    for station_id, group in grouped:
        names = group.sort_values("v_nom").bus.tolist()
        volts = group.sort_values("v_nom").v_nom.tolist()
        for i in range(len(names) - 1):
            transformers.append(
                {
                    "name": f"xfmr_{station_id}_{int(volts[i])}_{int(volts[i + 1])}",
                    "bus0": names[i],
                    "bus1": names[i + 1],
                    "v0": float(volts[i]),
                    "v1": float(volts[i + 1]),
                    "station_id": station_id,
                }
            )
            graph.add_edge(names[i], names[i + 1])
    giant = max(nx.connected_components(graph), key=len)
    keep = buses[buses.bus.isin(giant)].copy()
    keep_lines = lines[lines.bus0.isin(giant) & lines.bus1.isin(giant)].copy()
    keep_xf = [t for t in transformers if t["bus0"] in giant and t["bus1"] in giant]
    n = pypsa.Network(name="PyPSA-col OSM mesh (worldwide OSM extract, Colombia)")
    for name, color in WORKSHOP_COLORS.items():
        if name not in n.carriers.index:
            n.add("Carrier", name, color=color, nice_name=NICE_NAME.get(name, name))
    for row in keep.to_dict("records"):
        n.add("Bus", row["bus"], x=row["x"], y=row["y"], v_nom=row["v_nom"], carrier="AC")
    for row in keep_lines.to_dict("records"):
        n.add(
            "Line",
            row["line_id"],
            bus0=row["bus0"],
            bus1=row["bus1"],
            r=max(float(row["r_ohm"]), 1e-4),
            x=max(float(row["x_ohm"]), 1e-3),
            b=float(row["b_siemens"]),
            s_nom=float(row["s_nom_mva"]),
            length=float(row["km"]),
            carrier="AC",
        )
    for xf in keep_xf:
        n.add(
            "Transformer",
            xf["name"],
            bus0=xf["bus0"],
            bus1=xf["bus1"],
            s_nom=400.0,
            x=0.12,
            r=0.003,
            tap_ratio=1.0,
        )
    n.meta = {
        "topology": "osm_mesh_transformers_assumed",
        "worldwide_source": "OpenStreetMap power features (Colombia extract)",
        "buses_kept": int(len(keep)),
        "buses_dropped_islands": int(len(buses) - len(keep)),
        "transformers_assumed": len(keep_xf),
        "warning": "Transformers are same-station engineering defaults, not a PARATEC register.",
    }
    output.mkdir(parents=True, exist_ok=True)
    n.export_to_netcdf(output / "mesh.nc")
    keep.to_csv(output / "mesh_buses.csv", index=False)
    keep_lines.to_csv(output / "mesh_lines.csv", index=False)
    pd.DataFrame(keep_xf).to_csv(output / "mesh_transformers.csv", index=False)
    write_json(
        output / "mesh_topology.json",
        {
            **n.meta,
            **topology_report(n),
            "components_after_transformers": nx.number_connected_components(graph),
            "giant_component": int(len(giant)),
        },
    )
    return n


def _nearest_bus(n: pypsa.Network, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    project = Transformer.from_crs(4326, 9377, always_xy=True)
    bx, by = project.transform(n.buses.x.to_numpy(), n.buses.y.to_numpy())
    px, py = project.transform(lon, lat)
    _, idx = cKDTree(np.column_stack([bx, by])).query(np.column_stack([px, py]))
    return n.buses.index.to_numpy()[idx]


def attach_plants_and_demand(root: Path, config: dict, resources: Path) -> pypsa.Network:
    n = pypsa.Network()
    n.import_from_netcdf(resources / "mesh.nc")
    index = snapshots(config)
    n.set_snapshots(index)
    tables = load_tables(root, config)
    xm_plants = assemble_plants(tables, index)
    osm_plants = load_osm_plants(root, config)
    xm_plants["key"] = xm_plants["Nombre_Planta"].map(_norm)
    osm_idx = osm_plants[osm_plants.key.ne("")].drop_duplicates("key").set_index("key")
    xm_plants["lon"] = np.nan
    xm_plants["lat"] = np.nan
    xm_plants["geo_source"] = "unmatched"
    for i, row in xm_plants.iterrows():
        key = row["key"]
        hit = None
        if key and key in osm_idx.index:
            hit = osm_idx.loc[key]
        elif key:
            contains = [k for k in osm_idx.index if key in k or k in key]
            if len(contains) == 1:
                hit = osm_idx.loc[contains[0]]
        if hit is None:
            continue
        if isinstance(hit, pd.DataFrame):
            hit = hit.iloc[0]
        xm_plants.at[i, "lon"] = hit["lon"]
        xm_plants.at[i, "lat"] = hit["lat"]
        xm_plants.at[i, "geo_source"] = "osm_name_match"
    # Unmatched XM: place at the dashboard-zone centroid (declared, not surveyed).
    for i, row in xm_plants[xm_plants.lon.isna()].iterrows():
        zona = row.get("zona") or "CEN"
        spec = ZONAS.get(zona, ZONAS["CEN"])
        xm_plants.at[i, "lon"] = spec["x"]
        xm_plants.at[i, "lat"] = spec["y"]
        xm_plants.at[i, "geo_source"] = f"zone_centroid_{zona}"
    xm_plants["bus"] = _nearest_bus(n, xm_plants.lon.to_numpy(), xm_plants.lat.to_numpy())
    grouped = xm_plants.groupby(["bus", "carrier"], as_index=False).agg(
        p_nom=("cen_mw", "sum"), n_plants=("Codigo_Planta", "nunique"), gene_mwh=("gene_mwh", "sum")
    )
    gene = tables["gene"].copy()
    gene["entity_code"] = gene["entity_code"].astype(str)
    gene["timestamp"] = pd.to_datetime(gene["timestamp"])
    gene = gene[gene["timestamp"].isin(index)]
    meta = xm_plants.set_index("Codigo_Planta")[["bus", "carrier", "cen_mw"]]
    gene = gene.merge(meta, left_on="entity_code", right_index=True, how="inner")
    gene["mw"] = gene["value"] / 1000.0
    profiles = gene.groupby(["timestamp", "bus", "carrier"])["mw"].sum().rename("mw")
    for row in grouped.itertuples():
        p_nom = max(float(row.p_nom), 1e-3)
        try:
            series = profiles.xs((row.bus, row.carrier), level=("bus", "carrier"))
            series = series.reindex(index).fillna(0.0)
        except (KeyError, TypeError, ValueError):
            series = pd.Series(0.0, index=index)
        if row.carrier in {"Gas", "Hard Coal", "Oil", "Waste", "Other"}:
            p_max = pd.Series(1.0, index=index)
        else:
            p_max = (series / p_nom).clip(0, 1)
        n.add(
            "Generator",
            f"{row.carrier}@{row.bus}"[:120],
            bus=row.bus,
            carrier=row.carrier,
            p_nom=p_nom,
            p_max_pu=p_max,
            marginal_cost={
                "Solar": 0.1,
                "Wind Onshore": 0.1,
                "Run of River": 8.0,
                "Storage Hydro": 15.0,
                "Waste": 48.0,
                "Hard Coal": 42.0,
                "Gas": 65.0,
                "Oil": 140.0,
                "Other": 90.0,
            }.get(row.carrier, 90.0),
        )
    # Demand: DemaReal × dashboard shares, then equal split among buses of that zone.
    demand_z = demand_by_zone(tables["dema"], index)
    project = Transformer.from_crs(4326, 9377, always_xy=True)
    zx, zy = [], []
    znames = list(ZONAS)
    for z in znames:
        x, y = project.transform(ZONAS[z]["x"], ZONAS[z]["y"])
        zx.append(x)
        zy.append(y)
    bx, by = project.transform(n.buses.x.to_numpy(), n.buses.y.to_numpy())
    _, zid = cKDTree(np.column_stack([zx, zy])).query(np.column_stack([bx, by]))
    n.buses["zona"] = [znames[i] for i in zid]
    counts = n.buses.zona.value_counts()
    for bus, zona in n.buses.zona.items():
        share = demand_z[zona] / max(int(counts[zona]), 1)
        n.add("Load", f"load_{bus}"[:120], bus=bus, p_set=share.to_numpy())
        n.add(
            "Generator",
            f"shed_{bus}"[:120],
            bus=bus,
            carrier="load shedding",
            p_nom=float(share.max()) * 2 + 50,
            marginal_cost=10_000.0,
        )
    resources.mkdir(parents=True, exist_ok=True)
    xm_plants.to_csv(resources / "plants_attached.csv", index=False)
    n.buses.to_csv(resources / "buses_zoned.csv")
    n.export_to_netcdf(resources / "prepared.nc")
    write_json(
        resources / "attach_report.json",
        {
            "xm_plants": int(len(xm_plants)),
            "osm_name_matched": int((xm_plants.geo_source == "osm_name_match").sum()),
            "zone_centroid": int(xm_plants.geo_source.str.startswith("zone_centroid").sum()),
            "generators": int(len(n.generators)),
            "loads": int(len(n.loads)),
            "buses": int(len(n.buses)),
            "lines": int(len(n.lines)),
            "transformers": int(len(n.transformers)),
        },
    )
    return n


def solve_mesh(root: Path, config: dict, resources: Path, results: Path) -> pypsa.Network:
    n = pypsa.Network()
    n.import_from_netcdf(resources / "prepared.nc")
    n.calculate_dependent_values()
    status, condition = n.optimize(
        solver_name="highs", log_to_console=False, include_objective_constant=False
    )
    results.mkdir(parents=True, exist_ok=True)
    write_json(
        results / "solver.json",
        {
            "status": status,
            "termination_condition": condition,
            "objective_usd": float(n.objective) if status == "ok" else None,
            "buses": int(len(n.buses)),
            "lines": int(len(n.lines)),
            "transformers": int(len(n.transformers)),
            "generators": int(len(n.generators)),
        },
    )
    if status != "ok" or condition != "optimal":
        raise RuntimeError(f"OSM mesh solve failed: {status}/{condition}")
    n.export_to_netcdf(results / "network.nc")
    return n


def _deck_html(deck, path: Path, root: Path, config: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    land = _colombia_layer(root, config)
    deck.layers = [land, *list(deck.layers or [])]
    deck.to_html(str(path), open_browser=False, notebook_display=False, offline=True)
    return path


def explore_maps(root: Path, config: dict, results: Path, n: pypsa.Network | None = None) -> dict[str, Path]:
    if n is None:
        n = pypsa.Network()
        n.import_from_netcdf(results / "network.nc")
    for name, color in WORKSHOP_COLORS.items():
        if name not in n.carriers.index:
            n.add("Carrier", name, color=color, nice_name=NICE_NAME.get(name, name))
        else:
            n.carriers.loc[name, "color"] = color
    load = n.loads_t.p_set.sum(axis=0)
    load.index = n.loads.bus.to_numpy()
    load = load.groupby(level=0).sum()
    capacities = n.generators[~n.generators.carrier.eq("load shedding")].groupby(
        ["bus", "carrier"]
    ).p_nom.sum()
    hour0 = n.snapshots[0]
    if len(n.lines) and hasattr(n, "lines_t") and not n.lines_t.p0.empty:
        loading = (n.lines_t.p0.loc[hour0].abs() / n.lines.s_nom.replace(0, np.nan) * 100).fillna(0)
    else:
        loading = pd.Series(dtype=float)
    gen_mw = (
        n.generators[~n.generators.carrier.eq("load shedding")]
        .groupby("bus")
        .p_nom.sum()
        .reindex(n.buses.index)
        .fillna(0.0)
    )
    out = {}
    # bus_size is km² in n.explore(); scale so a 500 MW site is a large marker.
    out["explore_load.html"] = _deck_html(
        n.explore(bus_size=(load / 48).clip(lower=1) * 4.0, map_style="none"),
        results / "explore_load.html",
        root,
        config,
    )
    out["explore_capacity.html"] = _deck_html(
        n.explore(bus_size=capacities.clip(lower=1) * 3.5, map_style="none"),
        results / "explore_capacity.html",
        root,
        config,
    )
    if len(n.lines) and hasattr(n, "lines_t") and not n.lines_t.p0.empty:
        flow_deck = n.explore(
            bus_size=gen_mw.clip(lower=5) * 3.0,
            line_color=loading,
            line_flow=n.lines_t.p0.loc[hour0] / 50,
            line_cmap="plasma",
            line_width=n.lines.s_nom / 250,
            map_style="none",
        )
    else:
        flow_deck = n.explore(bus_size=gen_mw.clip(lower=5) * 3.0, map_style="none")
    out["explore_flow.html"] = _deck_html(
        flow_deck,
        results / "explore_flow.html",
        root,
        config,
    )
    return out


def _bus_demand_mw(n: pypsa.Network) -> pd.Series:
    dem = n.loads_t.p_set.mean()
    dem.index = n.loads.bus.to_numpy()
    return dem.groupby(level=0).mean().reindex(n.buses.index).fillna(0.0)


def _bus_generation_mw(n: pypsa.Network) -> pd.Series:
    gens = n.generators[~n.generators.carrier.eq("load shedding")]
    return gens.groupby("bus").p_nom.sum().reindex(n.buses.index).fillna(0.0)


def _marker_size(series: pd.Series, smin: float, smax: float) -> pd.Series:
    peak = float(series.max()) or 1.0
    return smin + (smax - smin) * (series / peak).clip(0, 1)


def fig_colombia_network(n: pypsa.Network, root: Path, config: dict, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8.6, 10.6))
    draw_colombia(ax, root, config)
    kv_color = {220.0: "#7eb8da", 230.0: "#2c7fb8", 500.0: "#c0392b"}
    edges = list(n.lines.iterrows()) if len(n.lines) else []
    if not edges and len(n.links):
        edges = list(n.links.iterrows())
    for _, row in edges:
        v = float(n.buses.v_nom.get(row.bus0, 230))
        ax.plot(
            [n.buses.x[row.bus0], n.buses.x[row.bus1]],
            [n.buses.y[row.bus0], n.buses.y[row.bus1]],
            color=kv_color.get(v, "#4a6fa5"),
            lw=0.7 if v < 400 else 1.8,
            zorder=2,
            solid_capstyle="round",
        )
    demand = _bus_demand_mw(n)
    generation = _bus_generation_mw(n)
    ax.scatter(
        n.buses.x,
        n.buses.y,
        s=_marker_size(demand, 70, 1400),
        facecolors="#f4a261",
        edgecolors="#b85716",
        linewidths=1.1,
        alpha=0.55,
        zorder=3,
        label="Demanda (tamaño = MW medio)",
    )
    ax.scatter(
        n.buses.x,
        n.buses.y,
        s=_marker_size(generation, 0, 1100),
        facecolors="#2a9d8f",
        edgecolors="#155e56",
        linewidths=0.9,
        alpha=0.85,
        zorder=4,
        label="Generación (tamaño = MW de CEN)",
    )
    ax.set_xlim(-80.2, -66.4)
    ax.set_ylim(-5.1, 13.3)
    ax.set_aspect("equal")
    ax.set_title("Colombia  ·  naranja = demanda, verde = generación")
    ax.set_xlabel("longitud")
    ax.set_ylabel("latitud")
    handles = [
        plt.Line2D([0], [0], color="#7eb8da", lw=2, label="220 kV"),
        plt.Line2D([0], [0], color="#2c7fb8", lw=2, label="230 kV"),
        plt.Line2D([0], [0], color="#c0392b", lw=2.4, label="500 kV"),
        plt.Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor="#f4a261",
            markeredgecolor="#b85716",
            markersize=14,
            label="Demanda (DemaReal repartida)",
        ),
        plt.Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor="#2a9d8f",
            markeredgecolor="#155e56",
            markersize=14,
            label="Generación (CEN de plantas XM)",
        ),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=True, fontsize=8)
    ax.text(
        0.99,
        0.02,
        "Todo bus tiene demanda.\nSolo algunos tienen planta.\nTamaño ∝ MW.",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color="#1b2a41",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#d9d2c5", alpha=0.92),
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="#f7f4ef")
    plt.close(fig)
    return path


def static_and_stats(root: Path, config: dict, results: Path) -> None:
    n = pypsa.Network()
    n.import_from_netcdf(results / "network.nc")
    fig_colombia_network(n, root, config, results / "colombia_map.png")
    fig, ax = plt.subplots(figsize=(8.2, 10.2))
    draw_colombia(ax, root, config)
    prices = n.buses_t.marginal_price.mean()
    for _, row in n.lines.iterrows():
        ax.plot(
            [n.buses.x[row.bus0], n.buses.x[row.bus1]],
            [n.buses.y[row.bus0], n.buses.y[row.bus1]],
            color="#8aa0b0",
            lw=0.45,
            zorder=1,
        )
    demand = _bus_demand_mw(n)
    generation = _bus_generation_mw(n)
    ax.scatter(
        n.buses.x,
        n.buses.y,
        s=_marker_size(demand, 80, 1200),
        facecolors="none",
        edgecolors="#b85716",
        linewidths=1.4,
        zorder=3,
    )
    sc = ax.scatter(
        n.buses.x,
        n.buses.y,
        c=prices.reindex(n.buses.index),
        cmap="plasma",
        s=_marker_size(generation, 90, 900),
        alpha=0.92,
        zorder=4,
        edgecolors="white",
        linewidths=0.4,
    )
    fig.colorbar(sc, ax=ax, label="Color del círculo = LMP medio (USD/MWh ilustrativo)", shrink=0.55)
    ax.set_title("LMP: color = precio; tamaño relleno = generación; anillo = demanda")
    ax.set_xlim(-80.2, -66.4)
    ax.set_ylim(-5.1, 13.3)
    ax.set_aspect("equal")
    ax.set_xlabel("longitud")
    ax.set_ylabel("latitud")
    from matplotlib.lines import Line2D

    ax.legend(
        handles=[
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="none",
                markeredgecolor="#b85716",
                markersize=10,
                label="Anillo naranja = demanda",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="#f6c445",
                markeredgecolor="white",
                markersize=10,
                label="Relleno = generación (color = LMP)",
            ),
        ],
        loc="lower left",
        fontsize=8,
        frameon=True,
    )
    fig.tight_layout()
    fig.savefig(results / "lmp.png", dpi=150, facecolor="#f7f4ef")
    plt.close(fig)
    p = n.generators_t.p.T.groupby(n.generators.carrier).sum().T.clip(lower=0)
    fig, ax = plt.subplots(figsize=(11.2, 4.4))
    bottom = np.zeros(len(p))
    for c in STACK_ORDER:
        if c not in p.columns:
            continue
        y = p[c].to_numpy()
        ax.fill_between(p.index, bottom, bottom + y, color=WORKSHOP_COLORS.get(c, "#888"), label=NICE_NAME.get(c, c), lw=0)
        bottom += y
    ax.plot(n.loads_t.p_set.sum(axis=1), color="black", lw=1.2, label="DemaReal")
    ax.set_ylabel("MW")
    ax.set_title("Despacho OSM-mesh  ·  colores workshop PyPSA Labs")
    ax.legend(ncol=4, fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    ax.margins(x=0)
    fig.tight_layout()
    fig.savefig(results / "dispatch.png", dpi=140, facecolor="#f7f4ef")
    plt.close(fig)
    energy = p.sum() / 1000.0
    energy.to_csv(results / "energy_balance_gwh.csv")
    opex = (n.generators_t.p * n.generators.marginal_cost).sum().groupby(n.generators.carrier).sum()
    opex.to_csv(results / "opex_usd.csv")
    # statistics module table if present
    try:
        bal = n.statistics.energy_balance().div(1e3).round(2)
        bal.to_csv(results / "statistics_energy_balance.csv")
        n.statistics.opex().round(1).to_csv(results / "statistics_opex.csv")
    except Exception as exc:  # noqa: BLE001
        write_json(results / "statistics_skipped.json", {"reason": str(exc)})
    shed = float(p.get("load shedding", pd.Series(dtype=float)).sum() / 1000.0) if "load shedding" in p else 0.0
    write_json(
        results / "summary.json",
        {
            "run": config["run"]["id"],
            "buses": int(len(n.buses)),
            "lines": int(len(n.lines)),
            "transformers": int(len(n.transformers)),
            "objective_usd": float(n.objective),
            "demand_gwh": float(n.loads_t.p_set.sum().sum() / 1000.0),
            "unserved_gwh": shed,
            "carriers_gwh": {k: float(v) for k, v in energy.items()},
            "warning": n.meta.get("warning") if isinstance(n.meta, dict) else "OSM mesh",
        },
    )


def fig_lmp(n: pypsa.Network, root: Path, config: dict, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8.2, 10.2))
    draw_colombia(ax, root, config)
    prices = n.buses_t.marginal_price.mean() if hasattr(n, "buses_t") else pd.Series(dtype=float)
    edges = list(n.lines.iterrows()) if len(n.lines) else list(n.links.iterrows()) if len(n.links) else []
    for _, row in edges:
        ax.plot(
            [n.buses.x[row.bus0], n.buses.x[row.bus1]],
            [n.buses.y[row.bus0], n.buses.y[row.bus1]],
            color="#8aa0b0",
            lw=0.45,
            zorder=1,
        )
    demand = _bus_demand_mw(n)
    generation = _bus_generation_mw(n)
    ax.scatter(
        n.buses.x,
        n.buses.y,
        s=_marker_size(demand, 80, 1200),
        facecolors="none",
        edgecolors="#b85716",
        linewidths=1.4,
        zorder=3,
    )
    sc = ax.scatter(
        n.buses.x,
        n.buses.y,
        c=prices.reindex(n.buses.index) if len(prices) else "#f6c445",
        cmap="plasma",
        s=_marker_size(generation, 90, 900),
        alpha=0.92,
        zorder=4,
        edgecolors="white",
        linewidths=0.4,
    )
    if len(prices):
        fig.colorbar(sc, ax=ax, label="Color del círculo = LMP medio (USD/MWh ilustrativo)", shrink=0.55)
    ax.set_title("LMP: color = precio; tamaño relleno = generación; anillo = demanda")
    ax.set_xlim(-80.2, -66.4)
    ax.set_ylim(-5.1, 13.3)
    ax.set_aspect("equal")
    ax.set_xlabel("longitud")
    ax.set_ylabel("latitud")
    from matplotlib.lines import Line2D

    ax.legend(
        handles=[
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="none",
                markeredgecolor="#b85716",
                markersize=10,
                label="Anillo naranja = demanda",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="#f6c445",
                markeredgecolor="white",
                markersize=10,
                label="Relleno = generación (color = LMP)",
            ),
        ],
        loc="lower left",
        fontsize=8,
        frameon=True,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="#f7f4ef")
    plt.close(fig)
    return path


def fig_dispatch(n: pypsa.Network, path: Path, title: str = "Despacho") -> Path:
    p = n.generators_t.p.T.groupby(n.generators.carrier).sum().T.clip(lower=0)
    fig, ax = plt.subplots(figsize=(11.2, 4.4))
    bottom = np.zeros(len(p))
    for c in STACK_ORDER:
        if c not in p.columns:
            continue
        y = p[c].to_numpy()
        ax.fill_between(
            p.index, bottom, bottom + y, color=WORKSHOP_COLORS.get(c, "#888"), label=NICE_NAME.get(c, c), lw=0
        )
        bottom += y
    extra = [c for c in p.columns if c not in STACK_ORDER]
    for c in extra:
        y = p[c].to_numpy()
        ax.fill_between(p.index, bottom, bottom + y, color=WORKSHOP_COLORS.get(c, "#888"), label=NICE_NAME.get(c, c), lw=0)
        bottom += y
    if hasattr(n, "loads_t") and not n.loads_t.p_set.empty:
        ax.plot(n.loads_t.p_set.sum(axis=1), color="black", lw=1.2, label="DemaReal")
    ax.set_ylabel("MW")
    ax.set_title(title)
    ax.legend(ncol=4, fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    ax.margins(x=0)
    fig.tight_layout()
    fig.savefig(path, dpi=140, facecolor="#f7f4ef")
    plt.close(fig)
    return path


def write_figures_report(results: Path, summary: dict, heading: str | None = None) -> Path:
    """osm-interactive report body, without requiring mesh attach JSON."""
    heading = heading or "Red OSM compleja de Colombia · mapas interactivos n.explore()"
    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>PyPSA-col · figuras de simulación</title>
<style>
body{{font-family:Georgia,serif;max-width:1080px;margin:0 auto;padding:24px;background:#f6f3ee;color:#1b2a41}}
iframe{{width:100%;height:540px;border:1px solid #d9d2c5;border-radius:8px;background:#fff}}
.note{{background:#fff;border-left:4px solid crimson;padding:10px 14px;margin:12px 0}}
table{{border-collapse:collapse;width:100%;background:#fff;font-family:sans-serif;font-size:14px}}
td,th{{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left}}
a{{color:#1b6b93}}
img.map{{width:100%;border-radius:8px;background:#f7f4ef}}
</style></head><body>
<h1>{heading}</h1>
<table>
<tr><th>Indicador</th><th>Valor</th></tr>
<tr><td>Barras</td><td>{summary.get("buses", "")}</td></tr>
<tr><td>Líneas</td><td>{summary.get("lines", "")}</td></tr>
<tr><td>Demanda</td><td>{float(summary.get("demand_gwh") or 0):.1f} GWh</td></tr>
<tr><td>No atendida</td><td>{float(summary.get("unserved_gwh") or 0):.2f} GWh</td></tr>
<tr><td>Objetivo</td><td>{float(summary.get("objective_usd") or 0):,.0f} USD ilustrativos</td></tr>
<tr><td>Escenario</td><td>{summary.get("global_scenario", "")} · {summary.get("epoch", "")}</td></tr>
</table>
<h2>0. Mapa de Colombia</h2>
<p><img class="map" src="colombia_map.png" alt="Mapa de Colombia"></p>
<div class="note">
<b>Cómo leer los círculos</b><br>
<span style="color:#b85716">● Naranja</span> = <b>demanda</b> (DemaReal nacional partida entre barras).
Todo bus tiene uno.<br>
<span style="color:#155e56">● Verde-azulado</span> = <b>generación</b> (CEN de plantas XM colgadas a esa barra).
Solo aparece donde hay planta.<br>
El <b>tamaño es proporcional al MW</b> (demanda media o capacidad instalada).
En los mapas interactivos: <code>explore_load</code> = solo demanda;
<code>explore_capacity</code> = tartas de generación por tecnología (colores workshop);
<code>explore_flow</code> = tamaño = generación, color de línea = carga %.
</div>
<p>Contorno continental (geoBoundaries) y San Andrés/Providencia (OSM). Rojo = 500 kV, azul = 220/230 kV.</p>
<h2>1. LMP sobre Colombia</h2>
<p><img class="map" src="lmp.png" alt="LMP sobre mapa de Colombia"></p>
<h2>2. Carga nodal — <code>n.explore(bus_size=load)</code></h2>
<p><a href="explore_load.html">Abrir mapa interactivo</a></p>
<iframe src="explore_load.html"></iframe>
<h2>3. Capacidad por tecnología (tartas) — <code>n.explore(bus_size=capacities)</code></h2>
<p>Paleta workshop: Gas tomato, carbón dimgrey, hidro teal, solar gold, eólica royalblue.</p>
<p><a href="explore_capacity.html">Abrir mapa interactivo</a></p>
<iframe src="explore_capacity.html"></iframe>
<h2>4. Flujos — <code>line_flow</code> + <code>line_cmap=plasma</code></h2>
<p><a href="explore_flow.html">Abrir mapa interactivo</a></p>
<iframe src="explore_flow.html"></iframe>
<h2>5. Despacho</h2>
<p><img class="map" src="dispatch.png" alt="dispatch"></p>
</body></html>"""
    dest = results / "report.html"
    dest.write_text(html, encoding="utf-8")
    return dest


def emit_run_figures(
    n: pypsa.Network,
    root: Path,
    config: dict,
    results: Path,
    *,
    heading: str | None = None,
) -> dict[str, Path]:
    """Write the full osm-interactive figure pack next to a solved network."""
    results.mkdir(parents=True, exist_ok=True)
    n.export_to_netcdf(results / "network.nc")
    out: dict[str, Path] = {}
    out["colombia_map.png"] = fig_colombia_network(n, root, config, results / "colombia_map.png")
    out["lmp.png"] = fig_lmp(n, root, config, results / "lmp.png")
    out["dispatch.png"] = fig_dispatch(
        n, results / "dispatch.png", title=heading or "Despacho  ·  colores workshop PyPSA Labs"
    )
    p = n.generators_t.p.T.groupby(n.generators.carrier).sum().T.clip(lower=0)
    energy = p.sum() / 1000.0
    energy.to_csv(results / "energy_balance_gwh.csv")
    shed = float(p["load shedding"].sum() / 1000.0) if "load shedding" in p.columns else 0.0
    try:
        obj = float(n.objective)
    except Exception:
        obj = 0.0
    summary = {
        "buses": int(len(n.buses)),
        "lines": int(len(n.lines) or len(n.links)),
        "objective_usd": obj,
        "demand_gwh": float(n.loads_t.p_set.sum().sum() / 1000.0) if not n.loads_t.p_set.empty else 0.0,
        "unserved_gwh": shed,
        "carriers_gwh": {k: float(v) for k, v in energy.items()},
        "global_scenario": (heading or ""),
        "epoch": "",
    }
    write_json(results / "summary.json", summary)
    try:
        out.update(explore_maps(root, config, results, n=n))
    except Exception as exc:  # noqa: BLE001
        write_json(results / "explore_skipped.json", {"reason": str(exc)})
    out["report.html"] = write_figures_report(results, summary, heading=heading)
    return out


def write_report(root: Path, config: dict, resources: Path, results: Path) -> Path:
    summary = json.loads((results / "summary.json").read_text())
    attach = json.loads((resources / "attach_report.json").read_text())
    topo = json.loads((resources / "mesh_topology.json").read_text())
    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>PyPSA-col OSM mesh interactivo</title>
<style>
body{{font-family:Georgia,serif;max-width:1080px;margin:0 auto;padding:24px;background:#f6f3ee;color:#1b2a41}}
iframe{{width:100%;height:540px;border:1px solid #d9d2c5;border-radius:8px;background:#fff}}
.note{{background:#fff;border-left:4px solid crimson;padding:10px 14px}}
table{{border-collapse:collapse;width:100%;background:#fff;font-family:sans-serif;font-size:14px}}
td,th{{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left}}
a{{color:#1b6b93}}
img{{width:100%;border-radius:8px}}
</style></head><body>
<h1>Red OSM compleja de Colombia · mapas interactivos <code>n.explore()</code></h1>
<p>Fuentes mundiales: <b>OpenStreetMap</b> (extracto Colombia en
<code>colombiacongestionV2</code>). Plantas y demanda: XM vía
<code>dashboard-sin-nodal</code> (pestañas Generación / Demanda / explorador de planta).
Colores: workshop PyPSA Labs. Flujo: <b>Snakemake completo</b>.</p>
<div class="note">Los transformadores 220/230/500 kV en la misma subestación OSM son
<b>valores de ingeniería por defecto</b> para conectar capas de tensión. No son un
registro PARATEC. Islas residuales se descartaron; el componente gigante tiene
{summary['buses']} barras, {summary['lines']} líneas y {topo.get('transformers_assumed', '?')} transformadores.</div>
<table>
<tr><th>Indicador</th><th>Valor</th></tr>
<tr><td>Barras (componente gigante)</td><td>{summary['buses']}</td></tr>
<tr><td>Líneas OSM</td><td>{summary['lines']}</td></tr>
<tr><td>Transformadores supuestos</td><td>{topo.get('transformers_assumed')}</td></tr>
<tr><td>Plantas XM colgadas</td><td>{attach['xm_plants']} (OSM-match {attach['osm_name_matched']}, centroide zonal {attach['zone_centroid']})</td></tr>
<tr><td>Demanda 48 h</td><td>{summary['demand_gwh']:.1f} GWh</td></tr>
<tr><td>No atendida</td><td>{summary['unserved_gwh']:.2f} GWh</td></tr>
<tr><td>Objetivo</td><td>{summary['objective_usd']:,.0f} USD ilustrativos</td></tr>
</table>
<h2>0. Mapa de Colombia</h2>
<p><img src="colombia_map.png" alt="Mapa de Colombia con la malla OSM"></p>
<div class="note">
<b>Cómo leer los círculos</b><br>
<span style="color:#b85716">● Naranja</span> = <b>demanda</b> (DemaReal nacional partida entre barras).
Todo bus tiene uno.<br>
<span style="color:#155e56">● Verde-azulado</span> = <b>generación</b> (CEN de plantas XM colgadas a esa barra).
Solo aparece donde hay planta.<br>
El <b>tamaño es proporcional al MW</b> (demanda media o capacidad instalada).
En los mapas interactivos: <code>explore_load</code> = solo demanda;
<code>explore_capacity</code> = tartas de generación por tecnología (colores workshop);
<code>explore_flow</code> = tamaño = generación, color de línea = carga %.
</div>
<p>Contorno continental (geoBoundaries) y San Andrés/Providencia (OSM). Rojo = 500 kV, azul = 220/230 kV.</p>
<h2>1. LMP sobre Colombia</h2>
<p><img src="lmp.png" alt="LMP sobre mapa de Colombia"></p>
<h2>2. Carga nodal — <code>n.explore(bus_size=load)</code></h2>
<p><a href="explore_load.html">Abrir mapa interactivo</a></p>
<iframe src="explore_load.html"></iframe>
<h2>3. Capacidad por tecnología (tartas) — <code>n.explore(bus_size=capacities)</code></h2>
<p>Paleta workshop: Gas tomato, carbón dimgrey, hidro teal, solar gold, eólica royalblue.</p>
<p><a href="explore_capacity.html">Abrir mapa interactivo</a></p>
<iframe src="explore_capacity.html"></iframe>
<h2>4. Flujos — <code>line_flow</code> + <code>line_cmap=plasma</code></h2>
<p><a href="explore_flow.html">Abrir mapa interactivo</a></p>
<iframe src="explore_flow.html"></iframe>
<h2>5. Despacho</h2>
<p><img src="dispatch.png" alt="dispatch"></p>
<p style="color:#5c6b7a;font-size:13px">Pydeck se exportó con <code>offline=True</code>.
El estilo de mapa mundial (Carto/OSM tiles) necesita red; las capas de buses y líneas
van embebidas. Ejecutar:
<code>snakemake -s workflow/Snakefile.osm.smk --cores 2</code></p>
</body></html>"""
    dest = results / "report.html"
    dest.write_text(html, encoding="utf-8")
    return dest


def stage(name: str, root: Path, config: dict) -> None:
    resources = root / "resources" / config["run"]["id"]
    results = root / "results" / config["run"]["id"]
    resources.mkdir(parents=True, exist_ok=True)
    if name == "mesh":
        build_connected_mesh(root, config, resources)
    elif name == "attach":
        attach_plants_and_demand(root, config, resources)
    elif name == "solve":
        solve_mesh(root, config, resources, results)
    elif name == "explore":
        explore_maps(root, config, results)
    elif name == "stats":
        static_and_stats(root, config, results)
    elif name == "report":
        write_report(root, config, resources, results)
    else:
        raise ValueError(name)
