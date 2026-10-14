"""Execute the user's Grid2Poster renderer and overlay modeled corridor results."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
import pypsa

from .io import write_json
from .results import active_assets, groups
from .source import upstream_modules


def route_utilization(n, properties):
    """Aggregate parallel vintage Links on the same corridor, with activity masks."""
    b0, b1 = properties["bus0"], properties["bus1"]
    forward = n.links.index[n.links.bus0.eq(b0) & n.links.bus1.eq(b1)]
    reverse = n.links.index[n.links.bus0.eq(b1) & n.links.bus1.eq(b0)]
    selected = forward.union(reverse)
    if not len(selected):
        return None
    ratios = []
    for period, sns in groups(n):
        active = selected[active_assets(n.links.loc[selected], period)]
        if not len(active):
            continue
        signs = pd.Series([1 if name in forward else -1 for name in active], index=active)
        flow = n.links_t.p0.loc[sns, active].mul(signs).sum(axis=1)
        capacity = n.links.loc[active, "p_nom_opt"].sum()
        if capacity > 1e-8:
            ratios.extend((flow.abs() / capacity * 100).tolist())
    return max(ratios) if ratios else 0.0


def render_grid2poster(root: Path, config: dict, results: Path) -> dict:
    _, paratec, poster = upstream_modules(root / config["source"]["path"])
    spec = config["poster"]
    if spec["theme"] not in poster.available_themes():
        raise ValueError(f"Unknown grid2poster theme {spec['theme']}")
    results.mkdir(parents=True, exist_ok=True)
    dataset = poster.osm_snapshot_dataset(incluir_insular=spec["include_zni_inset"])
    fig, stats = poster.render_poster(
        dataset,
        theme=spec["theme"],
        paper=spec["paper"],
        dpi=spec["dpi"],
        titulo="COLOMBIA",
        subtitulo="PyPSA-col · OSM geometry / illustrative model",
        creditos="© OpenStreetMap contributors (ODbL) · Grid2Poster (MIT) · S. Rivera / PyPSA-col",
        incluir_san_andres=spec["include_zni_inset"],
        mostrar_subestaciones=False,
        mostrar_centrales=False,
    )
    ax = fig.axes[0]
    routes_used = []
    if spec["congestion_overlay"] and (results / "network.nc").exists():
        n = pypsa.Network(results / "network.nc")
        routes = json.loads((root / "resources/source/routes.geojson").read_text())["features"]
        for feature in routes:
            props = feature["properties"]
            utilization = route_utilization(n, props)
            if utilization is None:
                continue
            color, label = paratec.color_congestion(utilization)
            coordinates = np.asarray(feature["geometry"]["coordinates"])
            real_route = props["estado_ruta"].startswith("ruta OSM")
            ax.plot(
                coordinates[:, 0],
                coordinates[:, 1],
                color=color,
                linewidth=1.6,
                alpha=0.96,
                zorder=10,
                linestyle="-" if real_route else "--",
            )
            routes_used.append(
                {
                    "corridor": props["enlace"],
                    "peak_model_utilization_percent": utilization,
                    "cartographic_route_status": props["estado_ruta"],
                    "osm_ids": props["osm_ids"],
                    "label": label,
                }
            )
        if routes_used:
            handles = [
                Line2D([0], [0], color="#2ECC71", lw=2, label="<50%"),
                Line2D([0], [0], color="#F39C12", lw=2, label="50–90%"),
                Line2D([0], [0], color="#E74C3C", lw=2, label="≥90%"),
            ]
            # Use upstream colors for exact thresholds in the exported legend.
            handles = [
                Line2D([0], [0], color=color, lw=2, label=f"≥{threshold:g}%")
                for threshold, color, _ in paratec.ESCALA_CONGESTION
                if threshold <= 100
            ]
            legend = ax.legend(
                handles=handles,
                loc="upper center",
                bbox_to_anchor=(0.5, 0.967),
                ncol=min(5, len(handles)),
                frameon=False,
                fontsize=7,
                title="MODEL corridor loading — not observed physical-line flows",
                title_fontsize=8,
            )
            theme = poster.get_theme(spec["theme"])
            for text in [*legend.get_texts(), legend.get_title()]:
                text.set_color(theme.text)
            legend.set_zorder(30)
    for fmt in ("png", "pdf", "svg"):
        fig.savefig(results / f"grid2poster.{fmt}", dpi=spec["dpi"], facecolor=fig.get_facecolor())
    plt.close(fig)
    stats.update(
        {
            "modeled_routes": routes_used,
            "renderer": "external/colombiacongestionV2/tools/grid2poster_col.py",
            "map_caution": "Cartographic paths may overlap and mix voltages. Never use them as circuit-flow observations.",
            "zni": "San Andres and Providencia inset only; no fictitious SIN connections.",
        }
    )
    write_json(results / "grid2poster.json", stats)
    return stats
