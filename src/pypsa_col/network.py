"""Seven-hub transport, conservative OSM candidates, and reviewed regional reduction."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import pypsa
from pyproj import Transformer
from scipy.spatial import cKDTree

from .io import check_reviewed, require_columns, write_json
from .source import upstream_modules


def topology_report(n: pypsa.Network) -> dict:
    graph = nx.Graph()
    graph.add_nodes_from(n.buses.index)
    for frame in (n.lines, n.links, n.transformers):
        graph.add_edges_from(zip(frame.bus0, frame.bus1))
    components = sorted(nx.connected_components(graph), key=lambda x: (-len(x), sorted(x)))
    return {
        "buses": len(n.buses),
        "lines": len(n.lines),
        "links": len(n.links),
        "transformers": len(n.transformers),
        "connected_components": len(components),
        "component_sizes": [len(c) for c in components],
        "isolated_buses": sorted(nx.isolates(graph)),
        "degree_one_buses": sorted(k for k, v in graph.degree if v == 1),
        "warning": "Connectivity is a QA measure, not validation of electrical equivalence.",
    }


def seven_hub(root: Path) -> pypsa.Network:
    n = pypsa.Network(name="PyPSA-col seven-hub transport demonstration")
    n.add("Carrier", "AC")
    n.add("Carrier", "transport")
    source = root / "resources/source"
    for row in pd.read_csv(source / "buses.csv").to_dict("records"):
        n.add("Bus", row["name"], x=row["x"], y=row["y"], v_nom=row["v_nom"], carrier="AC")
    for row in pd.read_csv(source / "links.csv").to_dict("records"):
        n.add(
            "Link",
            row["name"],
            bus0=row["bus0"],
            bus1=row["bus1"],
            p_nom=row["p_nom"],
            p_min_pu=-1,
            efficiency=1,
            carrier="transport",
        )
    n.meta = {
        "topology": "seven_hub_transport",
        "electrical_kvl": False,
        "ratings": "illustrative source dashboard assumptions",
        "losses": "lossless in both directions; no unphysical reverse-link gains",
    }
    return n


def _component_labels(points: np.ndarray, radius: float) -> list[int]:
    parent = list(range(len(points)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    if len(points):
        for a, b in sorted(cKDTree(points).query_pairs(radius)):
            a, b = find(a), find(b)
            parent[max(a, b)] = min(a, b)
    return [find(i) for i in range(len(points))]


def physical_candidate(root: Path, config: dict, output: Path) -> pypsa.Network:
    gis, paratec, _ = upstream_modules(root / config["source"]["path"])
    spec = config["network"]
    lines = gis.lineas_df()
    lines = lines[lines.kv.isin(spec["voltages_kv"])].sort_values("id").copy()
    subs = gis.subestaciones_df().sort_values("id").copy()
    # Project to metre coordinates; longitude/latitude distances are NOT metres.
    project = Transformer.from_crs(4326, 9377, always_xy=True)
    end_rows = []
    for row in lines.to_dict("records"):
        for end, (lon, lat) in enumerate([row["_coords"][0], row["_coords"][-1]]):
            px, py = project.transform(lon, lat)
            end_rows.append(
                {
                    "line_id": int(row["id"]),
                    "end": end,
                    "kv": float(row["kv"]),
                    "lon": lon,
                    "lat": lat,
                    "px": px,
                    "py": py,
                }
            )
    endpoints = pd.DataFrame(end_rows)
    endpoints["bus"] = ""
    endpoints["station_distance_m"] = np.nan
    buses = {}
    for kv, group in endpoints.groupby("kv", sort=True):
        # A max-voltage tag does not prove all busbars exist. Membership in a
        # higher-voltage station is explicitly an inference; levels stay separate.
        eligible = subs[subs.kv >= kv].copy()
        if len(eligible):
            sx, sy = project.transform(eligible.lon.to_numpy(), eligible.lat.to_numpy())
            dist, near = cKDTree(np.column_stack([sx, sy])).query(group[["px", "py"]])
            for idx, distance, pos in zip(group.index, dist, near):
                if distance > spec["substation_snap_m"]:
                    continue
                station = eligible.iloc[pos]
                sid = f"{station.osm_type}_{int(station.id)}"
                name = f"station_{sid}_{int(kv)}"
                endpoints.loc[idx, ["bus", "station_distance_m"]] = [name, distance]
                buses[name] = {
                    "x": float(station.lon),
                    "y": float(station.lat),
                    "v_nom": kv,
                    "station_id": sid,
                    "station_name": station.nombre,
                    "kind": "inferred_station_voltage_bus",
                    "station_tag_kv": float(station.kv),
                }
        unmatched = endpoints.loc[group.index]
        unmatched = unmatched[unmatched.bus.eq("")]
        labels = _component_labels(unmatched[["px", "py"]].to_numpy(), spec["endpoint_snap_m"])
        for label in sorted(set(labels)):
            members = unmatched.iloc[np.flatnonzero(np.asarray(labels) == label)]
            name = f"junction_{int(kv)}_{int(members.index.min())}"
            endpoints.loc[members.index, "bus"] = name
            buses[name] = {
                "x": float(members.lon.mean()),
                "y": float(members.lat.mean()),
                "v_nom": kv,
                "station_id": "",
                "station_name": "",
                "kind": "unverified_osm_endpoint_junction",
                "station_tag_kv": 0.0,
            }
    n = pypsa.Network(name="PyPSA-col OSM electrical candidate — UNVALIDATED")
    n.add("Carrier", "AC")
    for name, attributes in buses.items():
        n.add("Bus", name, carrier="AC", **{k: attributes[k] for k in ("x", "y", "v_nom")})
    details, rejected = [], []
    indexed = endpoints.set_index(["line_id", "end"])
    for row in lines.to_dict("records"):
        b0, b1 = [indexed.loc[(int(row["id"]), end), "bus"] for end in (0, 1)]
        if b0 == b1 or row["km"] <= 0:
            rejected.append({"osm_id": row["id"], "reason": "self_loop_after_snap_or_zero_length"})
            continue
        name = f"osm_line_{int(row['id'])}"
        circuits = max(1, int(row.get("circuitos", 1)))
        params = paratec.params_de(row["kv"])
        # These are Ohms/Siemens, NOT per-unit. Circuit factors applied ONCE.
        r = params.r_ohm_km * row["km"] / circuits
        x = params.x_ohm_km * row["km"] / circuits
        b = params.b_us_km * row["km"] * circuits * 1e-6
        n.add(
            "Line",
            name,
            bus0=b0,
            bus1=b1,
            r=r,
            x=x,
            b=b,
            s_nom=params.mva_circuito * circuits,
            length=row["km"],
            carrier="AC",
        )
        details.append(
            {
                "line_id": name,
                "osm_id": row["id"],
                "bus0": b0,
                "bus1": b1,
                "kv": row["kv"],
                "km": row["km"],
                "circuits": circuits,
                "r_ohm": r,
                "x_ohm": x,
                "b_siemens": b,
                "s_nom_mva": params.mva_circuito * circuits,
                "parameter_status": "engineering_default_NOT_official",
                "source": "colombiacongestionV2/tools/paratec_join.py PARAMETROS_TIPICOS",
                "reviewed": False,
            }
        )
    line_details = pd.DataFrame(details).set_index("line_id")
    if spec.get("line_overrides"):
        overrides = pd.read_csv(root / spec["line_overrides"])
        required = ["line_id", "r_ohm", "x_ohm", "b_siemens", "s_nom_mva"]
        require_columns(overrides, required, "line overrides")
        check_reviewed(overrides, "line overrides")
        if overrides.line_id.duplicated().any() or set(overrides.line_id) != set(n.lines.index):
            raise ValueError(
                "Line overrides must uniquely cover every candidate line, without extras."
            )
        overrides = overrides.set_index("line_id").reindex(n.lines.index)
        if (overrides.x_ohm <= 0).any() or (overrides.s_nom_mva <= 0).any():
            raise ValueError("Line x_ohm and s_nom_mva must be positive.")
        if not np.isfinite(overrides[required[1:]].to_numpy()).all() or (overrides.r_ohm < 0).any():
            raise ValueError("Non-finite/negative line parameters")
        for col, attr in [
            ("r_ohm", "r"),
            ("x_ohm", "x"),
            ("b_siemens", "b"),
            ("s_nom_mva", "s_nom"),
        ]:
            n.lines.loc[overrides.index, attr] = overrides[col]
            line_details.loc[overrides.index, col] = overrides[col]
        line_details["parameter_status"] = "user_reviewed"
        line_details["source"] = overrides.source
        line_details["reviewed"] = True
    if spec.get("transformers"):
        tf = pd.read_csv(root / spec["transformers"])
        require_columns(tf, ["name", "bus0", "bus1", "s_nom_mva", "x_pu", "r_pu"], "transformers")
        check_reviewed(tf, "transformers")
        if tf.name.duplicated().any():
            raise ValueError("Duplicate transformer names")
        for row in tf.to_dict("records"):
            if row["bus0"] not in n.buses.index or row["bus1"] not in n.buses.index:
                raise ValueError("Transformer references an unknown voltage-level bus")
            if (
                row["bus0"] == row["bus1"]
                or min(row["s_nom_mva"], row["x_pu"]) <= 0
                or row["r_pu"] < 0
            ):
                raise ValueError("Invalid transformer parameters")
            n.add(
                "Transformer",
                row["name"],
                bus0=row["bus0"],
                bus1=row["bus1"],
                s_nom=row["s_nom_mva"],
                x=row["x_pu"],
                r=row["r_pu"],
            )
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame.from_dict(buses, orient="index").rename_axis("bus").to_csv(
        output / "physical_buses.csv"
    )
    line_details.to_csv(output / "physical_lines.csv")
    endpoints.to_csv(output / "endpoint_matches.csv", index=False)
    pd.DataFrame(rejected, columns=["osm_id", "reason"]).to_csv(
        output / "rejected_lines.csv", index=False
    )
    n.meta = {
        "topology": "osm_candidate",
        "electrical_kvl": True,
        "parameters_reviewed": bool(spec.get("line_overrides")),
        "transformers_supplied": bool(spec.get("transformers")),
        "warning": "Endpoints only; same-voltage snapping; no crossing/transformer inference. "
        "Islands retained. Raw OSM does not establish commissioning or a validated SIN.",
    }
    return n


def aggregate_regions(n: pypsa.Network, mapping: pd.DataFrame, expected: int | None = 18):
    """Cut-set capacity aggregation, explicitly a TRANSPORT model, not AC equivalencing."""
    require_columns(mapping, ["bus", "region"], "busmap")
    check_reviewed(mapping, "regional busmap")
    if mapping.bus.duplicated().any() or set(mapping.bus) != set(n.buses.index):
        raise ValueError("Reviewed busmap must cover every voltage-level bus exactly once.")
    if mapping.region.isna().any() or mapping.region.astype(str).str.strip().eq("").any():
        raise ValueError("Empty region names")
    if expected is not None and mapping.region.nunique() != expected:
        raise ValueError(
            f"Expected {expected} approved regions, received {mapping.region.nunique()}."
        )
    if len(n.generators) or len(n.loads) or len(n.storage_units) or len(n.stores):
        raise ValueError("Cluster topology before attaching time series and generating units.")
    busmap = mapping.set_index("bus").region
    m = pypsa.Network(name="PyPSA-col reviewed regional transport aggregation")
    m.add("Carrier", "AC")
    m.add("Carrier", "transport")
    for region, members in busmap.groupby(busmap):
        points = n.buses.loc[members.index]
        m.add("Bus", region, x=points.x.mean(), y=points.y.mean(), v_nom=230, carrier="AC")
    cuts = {}
    for frame, attribute in [(n.lines, "s_nom"), (n.transformers, "s_nom"), (n.links, "p_nom")]:
        for row in frame.to_dict("records"):
            b0, b1 = sorted([busmap[row["bus0"]], busmap[row["bus1"]]])
            if b0 != b1:
                cuts[(b0, b1)] = cuts.get((b0, b1), 0) + row[attribute]
    for i, ((b0, b1), capacity) in enumerate(sorted(cuts.items())):
        m.add(
            "Link",
            f"regional_cut_{i}",
            bus0=b0,
            bus1=b1,
            p_nom=capacity,
            p_min_pu=-1,
            efficiency=1,
            carrier="transport",
        )
    m.meta = {
        "topology": "regional_cutset_transport",
        "electrical_kvl": False,
        "region_count": mapping.region.nunique(),
        "mapping": "user supplied and reviewed",
        "warning": "Sum of crossing nameplate MVA used as lossless MW transfer bound. "
        "NOT an N-1 transfer capability, PTDF or official market-zone model.",
        "parent_topology": n.meta,
    }
    return m


def build_base(root: Path, config: dict, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    mode = config["network"]["mode"]
    if mode == "seven_hub":
        n = seven_hub(root)
    elif mode in {"physical", "clustered"}:
        n = physical_candidate(root, config, output)
        if mode == "clustered":
            if not config["network"].get("busmap"):
                raise ValueError(
                    "Clustering requires a reviewed busmap; official 18-region labels are not invented."
                )
            n = aggregate_regions(
                n,
                pd.read_csv(root / config["network"]["busmap"]),
                config["network"]["expected_regions"],
            )
    else:
        raise ValueError(f"Unknown network mode {mode}")
    write_json(output / "topology_report.json", {**topology_report(n), "metadata": n.meta})
    n.export_to_netcdf(output / "base.nc")
    return output / "base.nc"
