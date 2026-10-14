"""Use the user's pinned repository directly, without executing its Streamlit app.

The upstream routing graph is a CARTOGRAPHIC heuristic. It must not be reused as
an electrical topology: it merges nearby vertices even across voltage levels.
Physical-network construction lives separately in ``network.py``.
"""

from __future__ import annotations

import ast
import importlib
import json
import operator
import sys
from pathlib import Path

import pandas as pd

from .io import sha256, write_json


def verify_source(root: Path, config: dict) -> dict:
    source = root / config["source"]["path"]
    lock = json.loads((root / config["source"]["lock"]).read_text())["colombiacongestionV2"]
    for filename, expected in lock["files"].items():
        path = source / filename
        if not path.exists() or sha256(path) != expected:
            raise ValueError(
                f"Pinned source missing or changed: {path}. "
                "Run scripts/bootstrap_sources.py or review and update the lock."
            )
    return lock


def upstream_modules(source: Path):
    source = source.resolve()
    # Upstream internally imports `tools.gis_data`. Avoid importing app.py and
    # detect a pre-existing unrelated `tools` package rather than monkey-patching it.
    if "tools" in sys.modules:
        file = Path(sys.modules["tools"].__file__).resolve()
        if source not in file.parents:
            raise RuntimeError("An unrelated `tools` package is already imported.")
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    return tuple(
        importlib.import_module(f"tools.{name}")
        for name in ("gis_data", "paratec_join", "grid2poster_col")
    )


def _literal_expression(node: ast.AST, defaults: dict):
    """Tiny safe AST evaluator: literals, default names, arithmetic and max only."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in defaults:
        return defaults[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult, ast.Div):
        op = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
        }[type(node.op)]
        return op(
            _literal_expression(node.left, defaults), _literal_expression(node.right, defaults)
        )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "max":
        return max(_literal_expression(arg, defaults) for arg in node.args)
    raise ValueError(f"Unexpected upstream expression; review source drift: {ast.dump(node)}")


def legacy_tables(source: Path, paratec) -> tuple[pd.DataFrame, ...]:
    tree = ast.parse((source / "app.py").read_text())
    function = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_congestion_model"
    )
    names = [a.arg for a in function.args.args][-len(function.args.defaults) :]
    defaults = dict(zip(names, map(ast.literal_eval, function.args.defaults)))
    buses = pd.DataFrame(
        [
            {
                "name": name,
                "x": a.lon,
                "y": a.lat,
                "v_nom": 230.0,
                "source_anchor": a.subestacion,
                "anchor_kv": a.kv,
            }
            for name, a in paratec.ANCLAS_MODELO.items()
        ]
    )
    links, generators, loads = [], [], []
    for node in function.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            fname = call.func.id if isinstance(call.func, ast.Name) else ""
            if fname == "add_link":
                name, b0, b1, capacity, legacy_eff = [
                    _literal_expression(x, defaults) for x in call.args
                ]
                links.append(
                    {
                        "name": name,
                        "bus0": b0,
                        "bus1": b1,
                        "p_nom": capacity,
                        "voltage_kv": paratec.KV_CORREDOR[name],
                        "upstream_efficiency_not_used": legacy_eff,
                    }
                )
            elif fname == "add_gen":
                name, bus, capacity, cost = [
                    _literal_expression(x, defaults) for x in call.args[:4]
                ]
                carrier = name.split("_")[0].lower()
                carrier = {"thermal": "gas", "diesel": "oil"}.get(carrier, carrier)
                generators.append(
                    {
                        "name": name,
                        "bus": bus,
                        "carrier": carrier,
                        "p_nom": capacity,
                        "marginal_cost": cost,
                        "efficiency": 1.0,
                        "profile": "",
                    }
                )
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.BinOp):
            target = node.targets[0]
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "demand_arr"
            ):
                bus = ast.literal_eval(target.slice)
                loads.append(
                    {"bus": bus, "peak_mw": _literal_expression(node.value.left, defaults)}
                )
    loads = pd.DataFrame(loads)
    loads["weight"] = loads.peak_mw / loads.peak_mw.sum()
    if len(buses) != 7 or len(links) != 7 or len(generators) != 12:
        raise ValueError("Unexpected legacy model structure: review extraction.")
    return buses, pd.DataFrame(links), pd.DataFrame(generators), loads


def audit_source(root: Path, config: dict, output: Path | None = None) -> dict:
    lock = verify_source(root, config)
    source = root / config["source"]["path"]
    output = output or root / "resources/source"
    output.mkdir(parents=True, exist_ok=True)
    gis, paratec, poster = upstream_modules(source)
    buses, links, generators, loads = legacy_tables(source, paratec)
    for name, table in [
        ("buses", buses),
        ("links", links),
        ("generators", generators),
        ("load_weights", loads),
    ]:
        table.to_csv(output / f"{name}.csv", index=False)
    graph = paratec.construir_grafo()
    anchors = paratec.resolver_anclas(graph)
    anchors.to_csv(output / "anchors.csv")
    congestion = {
        row["name"]: {"bus0": row["bus0"], "bus1": row["bus1"], "capacity_MW": row["p_nom"]}
        for row in links.to_dict("records")
    }
    routes, quality = paratec.unir_congestion(congestion, graph, anchors)
    quality.to_csv(output / "routing_quality.csv", index=False)
    route_features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[lon, lat] for lat, lon in route["coords"]],
            },
            "properties": {k: v for k, v in route.items() if k != "coords"},
        }
        for route in routes
    ]
    write_json(output / "routes.geojson", {"type": "FeatureCollection", "features": route_features})
    lines, subs, plants = gis.lineas_df(), gis.subestaciones_df(), gis.centrales_df()
    for name, frame in [("substations_osm", subs), ("plants_osm", plants)]:
        frame.to_csv(output / f"{name}.csv", index=False)
    stats = {
        "upstream": {"url": lock["url"], "commit": lock["commit"]},
        "all_source_files_sha256_verified": len(lock["files"]),
        "osm_lines": len(lines),
        "osm_substations": len(subs),
        "osm_plants": len(plants),
        "substations_by_tagged_kv": subs.groupby("kv").size().to_dict(),
        "substations_tagged_220_230_500": int(subs.kv.isin([220, 230, 500]).sum()),
        "line_segments_tagged_220_230_500": int(lines.kv.isin([220, 230, 500]).sum()),
        "grid2poster_themes": list(poster.available_themes()),
        "snapshot_declared_metadata": gis.kpis(),
        "routing": paratec.reporte_calidad(routes, anchors),
        "legacy_backend": "scipy.optimize.linprog / HiGHS (not PyPSA in this revision)",
        "legacy_topology": "seven hubs; transport links; capacity and cost assumptions",
        "cautions": [
            "OSM feature count is NOT the number of electrical buses or commissioned circuits.",
            "The supplied snapshot does not establish a validated 147-bus SIN network.",
            "Routing graph is ONLY for mapping, never electrical connectivity or branch ratings.",
            "Same circuit can appear in several cartographic routes; do not add route lengths.",
            "No official 18-subarea membership table was found in the source repository.",
            "San Andres/Providencia are shown as ZNI insets, not electrically attached to SIN.",
            "Original costs are inherited numerical assumptions, relabelled USD for demos only.",
            "Bidirectional links are lossless here; reverse use of efficiency<1 would create energy.",
        ],
    }
    write_json(output / "inventory.json", stats)
    return stats
