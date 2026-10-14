"""Build a PyPSA example from dashboard-sin-nodal conventions + cached XM tables.

The Streamlit app (https://dashboard-sin-nodal.streamlit.app/) exposes:
  - tab ⚡ Generación: plant catalog, technology mix, hourly profiles
  - tab 📈 Demanda: national DemaReal (not filtered by plant)
  - Explorador de planta: per-resource energy and hourly mean profile
  - 7 declared subregions (NOT official XM/UPME zones), toponymic plant mapping,
    demand shares and NTC-style corridors

This module reuses those *declared* rules on the already-downloaded XM bundle.
It does not import the Streamlit app, does not run its custom dual-ascent OPF,
and does not treat toponymy as an official geocoder.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa

from .io import snapshots, write_json
from .plotting import NICE_NAME, STACK_ORDER, WORKSHOP_COLORS
from .xm import load_metric

# ---------------------------------------------------------------------------
# Copied from dashboard-sin-nodal/app.py (commit 514cc091), with attribution.
# The app itself labels these as board assumptions, not official geography.
# ---------------------------------------------------------------------------
ZONAS = {
    "GUJ": {"label": "La Guajira–Cesar–Magdalena", "x": -72.90, "y": 11.20},
    "CAR": {"label": "Caribe (Atlántico–Bolívar–Córdoba)", "x": -75.00, "y": 10.40},
    "NOR": {"label": "Nordeste (Antioquia–Santanderes–Eje)", "x": -75.30, "y": 6.55},
    "CEN": {"label": "Centro (Bogotá–Cundinamarca–Boyacá)", "x": -74.08, "y": 4.71},
    "OCC": {"label": "Occidente–Pacífico (Valle–Cauca–Chocó)", "x": -76.52, "y": 3.45},
    "SUR": {"label": "Sur (Huila–Nariño–Putumayo)", "x": -75.30, "y": 2.45},
    "ORI": {"label": "Orinoquía (Meta–Casanare–Arauca)", "x": -72.40, "y": 4.80},
}
PESO_DEMANDA = {
    "CEN": 0.26,
    "CAR": 0.21,
    "NOR": 0.24,
    "OCC": 0.12,
    "SUR": 0.08,
    "ORI": 0.045,
    "GUJ": 0.045,
}
RAMAS = (
    ("GUJ", "CAR", 2600.0, "Riohacha–Barranquilla"),
    ("CAR", "CEN", 1750.0, "Costa–Centro"),
    ("CAR", "NOR", 2100.0, "Caribe–Nordeste"),
    ("NOR", "CEN", 2900.0, "Chivor/Sogamoso–Bogotá"),
    ("NOR", "OCC", 1450.0, "Nordeste–Valle"),
    ("OCC", "SUR", 1250.0, "Valle–Cauca–Huila"),
    ("SUR", "CEN", 1550.0, "Paicol–Chipaque"),
    ("CEN", "ORI", 850.0, "Centro–Yopal"),
)
KEYWORDS_ZONA = {
    "GUJ": (
        "GUAJIRA", "CERREJON", "MAICAO", "URIBIA", "MANAURE", "RIOHACHA", "RIO HACHA",
        "BOSCONIA", "LA JAGUA", "TEPUY", "GUAYEPO", "TERMOSIERRA", "SAMAMBA",
        "URIANA", "PATIRIA", "TABORDO", "POTRERILLOS", "GUINEA",
    ),
    "CAR": (
        "BARRANQUILLA", "CARTAGENA", "GECELCA", "TERMOBARRANCA", "SANTA MARTA",
        "MOMPOX", "CALAMAR", "SAN JORGE", "CANAL DEL DIQUE", "SITIONUEVO",
        "LA CEIBA", "CARACOLI", "TEBSA", "FLORES 1", "FLORES I", "FLORES 4",
        "TERMOCANDELARIA", "PROELECTRICA", "TERMOEMCALI",
    ),
    "NOR": (
        "ITUANGO", "GUATAPE", "GUATAPÉ", "PORCE", "SAN CARLOS", "TASAJERA",
        "GUADALUPE", "PLAYAS", "LA MIEL", "MIEL I", "NARE", "RIO CLARO",
        "RIOCLARO", "PAGUA", "BETANIA", "TOLEDO", "YALI", "CALIMA",
        "TERMOFLORES", "FLORES", "SANTA RITA",
    ),
    "CEN": (
        "CHIVOR", "SOGAMOSO", "GUAVIO", "PAIPA", "ZIPAQUIRA", "ZIPA", "TASAJERO",
        "TEBSAB", "QUIMBO", "BOGOTA", "BOGOTÁ", "TORCA", "CHIQUINQUIRA",
        "TERMOPAIPA", "GECELCA 3", "TERMOSOCHAGOCIA",
    ),
    "OCC": (
        "TERMOVALLE", "EMCALI", "YUMBO", "BUGA", "PRADERA", "DAGUA", "SALVAJINA",
        "ALTOANCHICAYA", "ALTO ANCHICAYA", "BAJO ANCHICAYA", "URRA", "URRÁ",
        "RIOPAILA", "INCAUCA",
    ),
    "SUR": (
        "PASTO", "MOCOA", "NARIÑO", "PUTUMAYO", "HUILA", "GARZON", "EL QUIMBO",
        "AMOYA", "AMOYÁ", "SAN FRANCISCO",
    ),
    "ORI": (
        "YOPAL", "ARAUCA", "VICHADA", "META", "CASANARE", "APIAY", "TERMOYOPAL",
        "GIBRALTAR",
    ),
}

MARGINAL_USD = {
    "Solar": 0.1,
    "Wind Onshore": 0.1,
    "Run of River": 8.0,
    "Storage Hydro": 15.0,
    "Waste": 48.0,
    "Hard Coal": 42.0,
    "Gas": 65.0,
    "Oil": 140.0,
    "Other": 90.0,
    "load shedding": 10_000.0,
}
CO2 = {
    "Solar": 0.0,
    "Wind Onshore": 0.0,
    "Run of River": 0.0,
    "Storage Hydro": 0.0,
    "Waste": 0.024,
    "Hard Coal": 0.336,
    "Gas": 0.200,
    "Oil": 0.270,
    "Other": 0.250,
    "load shedding": 0.0,
}


def carrier_of(row: pd.Series) -> str:
    tech = str(row.get("Tecnologia", "")).upper().strip()
    rec = str(row.get("Tipo_Recurso", "")).upper()
    fuel = str(row.get("Fuente_Energia", "")).upper()
    if tech in {"SOLAR"} or fuel == "RAD SOLAR":
        return "Solar"
    if tech in {"EOLICA"} or fuel == "VIENTO":
        return "Wind Onshore"
    if tech in {"COGENERADOR"} or fuel in {"BAGAZO", "BIOMASA", "BIOGAS"}:
        return "Waste"
    if fuel in {"CARBON"}:
        return "Hard Coal"
    if fuel in {"GAS"}:
        return "Gas"
    if fuel in {"ACPM", "JET-A1", "COMBUSTOLEO", "GLP"}:
        return "Oil"
    if tech in {"HIDRAULICA", "HIDROELÉCTRICA"} or fuel == "AGUA":
        if "FILO" in rec:
            return "Run of River"
        return "Storage Hydro"
    if tech in {"TERMICA", "TÉRMICA"}:
        return "Gas"
    return "Other"


def zona_por_nombre(nombre: str) -> str | None:
    n = str(nombre).upper()
    for zona, keys in KEYWORDS_ZONA.items():
        if any(k in n for k in keys):
            return zona
    return None


def dim_plantas(listado: pd.DataFrame) -> pd.DataFrame:
    out = listado.rename(
        columns={
            "Code": "Codigo_Planta",
            "Name": "Nombre_Planta",
            "Type": "Tecnologia",
            "EnerSource": "Fuente_Energia",
            "RecType": "Tipo_Recurso",
            "CompanyCode": "Codigo_Agente",
            "Disp": "Tipo_Despacho",
            "State": "Estado",
        }
    ).copy()
    out["Codigo_Planta"] = out["Codigo_Planta"].astype(str).str.strip()
    out["Tecnologia"] = out["Tecnologia"].astype(str).str.strip().str.upper()
    out["Fuente_Energia"] = out["Fuente_Energia"].astype(str).str.strip().str.upper()
    out["Tipo_Recurso"] = out["Tipo_Recurso"].astype(str).str.strip().str.upper()
    out = out.drop_duplicates("Codigo_Planta")
    out["carrier"] = out.apply(carrier_of, axis=1)
    out["zona_toponimia"] = out["Nombre_Planta"].map(zona_por_nombre)
    return out


def assign_zones(plants: pd.DataFrame) -> pd.DataFrame:
    """Keep toponymic hits; split leftover CEN like the dashboard (proportional)."""
    out = plants.copy()
    located = out["zona_toponimia"].notna()
    out["zona"] = out["zona_toponimia"]
    out["asignacion"] = np.where(located, "toponimia", "reparto proporcional")
    weights = out.loc[located].groupby("zona")["cen_mw"].sum()
    if weights.sum() <= 0:
        weights = pd.Series({z: 1.0 for z in ZONAS})
    probs = (weights / weights.sum()).reindex(list(ZONAS), fill_value=0.0)
    rng = np.random.default_rng(7)  # stable, documented seed — not a geocoder
    missing = out.index[~located]
    if len(missing):
        # Capacity-weighted random zone so the *fleet* matches dashboard shares;
        # individual unmapped plants are not claimed as sited.
        draw = rng.choice(probs.index.to_numpy(), size=len(missing), p=probs.to_numpy())
        out.loc[missing, "zona"] = draw
    return out


def load_tables(root: Path, config: dict) -> dict[str, pd.DataFrame]:
    folder = root / config["inputs"]["xm_dir"]
    return {
        "listado": load_metric(folder, "ListadoRecursos", "Sistema"),
        "cen": load_metric(folder, "CapEfecNeta", "Recurso"),
        "gene": load_metric(folder, "Gene", "Recurso"),
        "dema": load_metric(folder, "DemaReal", "Sistema"),
        "gene_sis": load_metric(folder, "Gene", "Sistema"),
        "precio": load_metric(folder, "PrecBolsNaci", "Sistema"),
    }


def assemble_plants(tables: dict[str, pd.DataFrame], index: pd.DatetimeIndex) -> pd.DataFrame:
    dim = dim_plantas(tables["listado"])
    cen = tables["cen"].copy()
    cen["entity_code"] = cen["entity_code"].astype(str)
    cap = cen.groupby("entity_code")["value"].max().rename("cen_kw") / 1.0
    dim = dim.merge(cap, left_on="Codigo_Planta", right_index=True, how="left")
    dim["cen_mw"] = dim["cen_kw"].fillna(0.0) / 1000.0
    dim = dim[dim["cen_mw"] > 0].copy()
    dim = assign_zones(dim)
    gene = tables["gene"].copy()
    gene["entity_code"] = gene["entity_code"].astype(str)
    gene["timestamp"] = pd.to_datetime(gene["timestamp"])
    window = gene[gene["timestamp"].isin(index)]
    energy = window.groupby("entity_code")["value"].sum().rename("gene_kwh")
    dim = dim.merge(energy, left_on="Codigo_Planta", right_index=True, how="left")
    dim["gene_mwh"] = dim["gene_kwh"].fillna(0.0) / 1000.0
    dim["hours"] = len(index)
    dim["cf"] = np.where(dim["cen_mw"] > 0, dim["gene_mwh"] / (dim["cen_mw"] * len(index)), 0.0)
    return dim.sort_values("gene_mwh", ascending=False)


def demand_by_zone(dema: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    series = dema.copy()
    series["timestamp"] = pd.to_datetime(series["timestamp"])
    mw = series.set_index("timestamp")["value"].reindex(index) / 1000.0
    if mw.isna().any():
        raise ValueError("DemaReal does not cover every modelled hour")
    frame = pd.DataFrame({z: mw * w for z, w in PESO_DEMANDA.items()})
    frame.index = index
    return frame


def observed_zone_carrier(gene: pd.DataFrame, plants: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    g = gene.copy()
    g["entity_code"] = g["entity_code"].astype(str)
    g["timestamp"] = pd.to_datetime(g["timestamp"])
    g = g[g["timestamp"].isin(index)]
    meta = plants.set_index("Codigo_Planta")[["zona", "carrier", "cen_mw"]]
    g = g.merge(meta, left_on="entity_code", right_index=True, how="inner")
    g["mw"] = g["value"] / 1000.0
    return g.groupby(["timestamp", "zona", "carrier"])["mw"].sum().unstack("carrier").fillna(0.0)


def build_network(plants: pd.DataFrame, demand: pd.DataFrame, observed: pd.DataFrame) -> pypsa.Network:
    n = pypsa.Network(name="PyPSA-col × dashboard-sin-nodal (XM plants + DemaReal)")
    n.set_snapshots(demand.index)
    for name, color in WORKSHOP_COLORS.items():
        if name in n.carriers.index:
            continue
        n.add(
            "Carrier",
            name,
            color=color,
            nice_name=NICE_NAME.get(name, name),
            co2_emissions=CO2.get(name, 0.0),
        )
    for z, spec in ZONAS.items():
        n.add("Bus", z, x=spec["x"], y=spec["y"], v_nom=230, carrier="AC")
    for z in ZONAS:
        n.add("Load", f"load_{z}", bus=z, p_set=demand[z].to_numpy())
        n.add(
            "Generator",
            f"shed_{z}",
            bus=z,
            carrier="load shedding",
            p_nom=demand[z].max() * 1.5,
            marginal_cost=MARGINAL_USD["load shedding"],
        )
    for a, b, cap, name in RAMAS:
        n.add(
            "Link",
            name,
            bus0=a,
            bus1=b,
            p_nom=cap,
            p_min_pu=-1,
            efficiency=1,
            carrier="AC",
        )
    grouped = plants.groupby(["zona", "carrier"], as_index=False).agg(
        cen_mw=("cen_mw", "sum"), n_plants=("Codigo_Planta", "nunique")
    )
    for row in grouped.itertuples():
        series = pd.Series(0.0, index=demand.index)
        if row.carrier in observed.columns:
            try:
                series = observed.xs(row.zona, level="zona")[row.carrier].reindex(demand.index).fillna(0.0)
            except (KeyError, TypeError, ValueError):
                series = pd.Series(0.0, index=demand.index)
        p_nom = max(float(row.cen_mw), float(series.max()), 1e-3)
        if row.carrier in {"Gas", "Hard Coal", "Oil", "Waste", "Other"}:
            p_max = pd.Series(1.0, index=demand.index)
            p_nom = max(float(row.cen_mw), 1e-3)
        else:
            p_max = (series / p_nom).clip(lower=0, upper=1)
        n.add(
            "Generator",
            f"{row.carrier}@{row.zona}",
            bus=row.zona,
            carrier=row.carrier,
            p_nom=p_nom,
            p_max_pu=p_max,
            marginal_cost=MARGINAL_USD.get(row.carrier, 90.0),
        )
    n.meta = {
        "topology": "dashboard_sin_nodal_7_subregions",
        "electrical_kvl": False,
        "geography": "declared dashboard toponymy + demand shares; not official XM zones",
        "source": "srriverar/dashboard-sin-nodal@514cc091 + XM cached bundle",
    }
    return n


def solve_network(n: pypsa.Network) -> tuple[pypsa.Network, str, str]:
    status, condition = n.optimize(solver_name="highs", log_to_console=False)
    if status != "ok" or condition != "optimal":
        raise RuntimeError(f"Dashboard-SIN PyPSA solve failed: {status}/{condition}")
    return n, status, condition


def plant_explorer_table(plants: pd.DataFrame, gene: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    g = gene.copy()
    g["entity_code"] = g["entity_code"].astype(str)
    g["timestamp"] = pd.to_datetime(g["timestamp"])
    g = g[g["timestamp"].isin(index)]
    g["mw"] = g["value"] / 1000.0
    g["hour"] = g["timestamp"].dt.hour
    profile = g.groupby(["entity_code", "hour"])["mw"].mean().unstack("hour")
    table = plants.merge(profile, left_on="Codigo_Planta", right_index=True, how="left")
    return table.sort_values("gene_mwh", ascending=False)


def fig_dispatch(n: pypsa.Network, path: Path, observed_mix: pd.Series | None = None) -> Path:
    p = n.generators_t.p.T.groupby(n.generators.carrier).sum().T
    cols = [c for c in STACK_ORDER if c in p.columns]
    fig, ax = plt.subplots(figsize=(11.5, 4.6))
    bottom = np.zeros(len(p))
    t = p.index
    for c in cols:
        y = p[c].clip(lower=0).to_numpy()
        ax.fill_between(t, bottom, bottom + y, color=WORKSHOP_COLORS.get(c, "#888"), label=NICE_NAME.get(c, c), lw=0)
        bottom += y
    demand = n.loads_t.p_set.sum(axis=1)
    ax.plot(demand.index, demand.to_numpy(), color="black", lw=1.4, label="Demanda XM (DemaReal)")
    ax.set_ylabel("MW")
    ax.set_title("Despacho PyPSA  ·  colores del workshop PyPSA Labs")
    ax.legend(ncol=4, fontsize=8, loc="upper left")
    ax.grid(axis="y", alpha=0.35)
    ax.margins(x=0)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="#f7f4ef")
    plt.close(fig)
    return path


def fig_network(n: pypsa.Network, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8.6, 9.2))
    ax.set_title("7 subregiones del tablero  ·  tartas = CEN modelada (colores workshop)")
    # Links
    for name, row in n.links.iterrows():
        x0, y0 = n.buses.loc[row.bus0, ["x", "y"]]
        x1, y1 = n.buses.loc[row.bus1, ["x", "y"]]
        flow = n.links_t.p0[name].abs().mean() if name in n.links_t.p0 else 0.0
        ax.plot([x0, x1], [y0, y1], color="crimson", lw=1 + 4 * min(flow / max(row.p_nom, 1), 1), alpha=0.7, zorder=1)
    # Pies
    for bus in n.buses.index:
        gens = n.generators[n.generators.bus == bus]
        gens = gens[~gens.carrier.eq("load shedding")]
        sizes = gens.groupby("carrier").p_nom.sum()
        total = float(sizes.sum()) or 1.0
        x, y = n.buses.loc[bus, ["x", "y"]]
        r = 0.18 + 0.55 * np.sqrt(total / n.generators.p_nom.max())
        start = 0.0
        for carrier, mw in sizes.items():
            frac = float(mw) / total
            wedge = plt.matplotlib.patches.Wedge(
                (x, y), r, start * 360, (start + frac) * 360,
                facecolor=WORKSHOP_COLORS.get(carrier, "#ccc"),
                edgecolor="white", lw=0.4, zorder=3,
            )
            ax.add_patch(wedge)
            start += frac
        ax.text(x, y - r - 0.12, f"{bus}\n{total:.0f} MW", ha="center", va="top", fontsize=8)
    ax.set_aspect("equal")
    ax.set_xlim(-78.2, -71.4)
    ax.set_ylim(1.4, 12.4)
    ax.axis("off")
    handles = [
        plt.matplotlib.patches.Patch(color=WORKSHOP_COLORS[c], label=NICE_NAME.get(c, c))
        for c in sizes.index.union(n.generators.carrier.unique()) if c in WORKSHOP_COLORS and c != "load shedding"
    ]
    # unique carriers on network
    carriers = sorted(set(n.generators.carrier) - {"load shedding"})
    handles = [
        plt.matplotlib.patches.Patch(color=WORKSHOP_COLORS.get(c, "#ccc"), label=NICE_NAME.get(c, c))
        for c in carriers
        if c in WORKSHOP_COLORS
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="#f7f4ef")
    plt.close(fig)
    return path


def fig_mix(observed: pd.Series, modelled: pd.Series, path: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.6), sharey=True)
    for ax, series, title in (
        (axes[0], observed, "Observado XM  ·  pestaña Generación"),
        (axes[1], modelled, "Óptimo PyPSA  ·  misma demanda"),
    ):
        bottom = 0.0
        tot = max(float(series.sum()), 1e-9)
        for c in STACK_ORDER:
            if c not in series.index or series[c] <= 1e-6:
                continue
            ax.bar(0, series[c], bottom=bottom, color=WORKSHOP_COLORS.get(c, "#888"), width=0.55, label=NICE_NAME.get(c, c))
            if series[c] / tot > 0.05:
                ax.text(0, bottom + series[c] / 2, f"{100 * series[c] / tot:.0f}%", ha="center", va="center", fontsize=8)
            bottom += series[c]
        ax.set_title(title)
        ax.set_xticks([])
        ax.set_ylabel("GWh en 48 h")
        ax.grid(axis="y", alpha=0.3)
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.02), fontsize=8)
    fig.suptitle("Mix energético  ·  paleta workshop PyPSA (Carrier.color)")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="#f7f4ef")
    plt.close(fig)
    return path


def fig_plants(explorer: pd.DataFrame, path: Path, top: int = 15) -> Path:
    top_df = explorer.head(top)
    colors = [WORKSHOP_COLORS.get(c, "#888") for c in top_df["carrier"]]
    fig, ax = plt.subplots(figsize=(10.8, 5.8))
    ax.barh(top_df["Nombre_Planta"].astype(str).str[:32][::-1], top_df["gene_mwh"][::-1], color=colors[::-1])
    ax.set_xlabel("MWh observados en la ventana (Gene/Recurso)")
    ax.set_title("Explorador de planta  ·  top 15 por energía XM")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="#f7f4ef")
    plt.close(fig)
    return path


def fig_plant_profile(explorer: pd.DataFrame, path: Path) -> Path:
    hours = [c for c in explorer.columns if isinstance(c, (int, np.integer))]
    fig, axes = plt.subplots(2, 2, figsize=(10.8, 6.4), sharex=True)
    axes = axes.ravel()
    for ax, (_, row) in zip(axes, explorer.head(4).iterrows()):
        y = [row.get(h, np.nan) for h in range(24)]
        ax.bar(range(24), y, color=WORKSHOP_COLORS.get(row["carrier"], "#888"))
        ax.set_title(f"{row['Nombre_Planta'][:40]}  ·  {row['carrier']}")
        ax.set_ylabel("MW medio")
        ax.grid(axis="y", alpha=0.3)
    axes[2].set_xlabel("Hora local")
    axes[3].set_xlabel("Hora local")
    fig.suptitle("Explorador de planta  ·  perfil horario medio (como la app)")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="#f7f4ef")
    plt.close(fig)
    return path


def fig_demand(demand: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(11.2, 4.4))
    palette = ["#4c72b0", "#dd8452", "#55a868", "#c44e52", "#8172b3", "#937860", "#da8bc3"]
    ax.stackplot(demand.index, *[demand[z] for z in ZONAS], labels=[f"{z} {PESO_DEMANDA[z]:.0%}" for z in ZONAS], colors=palette, lw=0)
    ax.plot(demand.index, demand.sum(axis=1), color="black", lw=1.3, label="DemaReal nacional")
    ax.set_ylabel("MW")
    ax.set_title("Demanda  ·  DemaReal x pesos del tablero (pestana Demanda)")
    ax.legend(ncol=4, fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    ax.margins(x=0)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="#f7f4ef")
    plt.close(fig)
    return path


def write_report(out: Path, summary: dict, images: dict[str, Path]) -> Path:
    def tag(p: Path) -> str:
        import base64

        return f'<img src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode("ascii")}" style="width:100%;border-radius:8px">'

    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>PyPSA-col × dashboard-sin-nodal</title>
<style>
body{{font-family:Georgia,serif;background:#f6f3ee;color:#1b2a41;max-width:980px;margin:0 auto;padding:28px}}
h1{{font-size:30px}} img{{margin:12px 0}} .note{{background:#fff;border-left:4px solid tomato;padding:10px 14px}}
table{{border-collapse:collapse;width:100%;background:#fff;font-family:sans-serif;font-size:14px}}
td,th{{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left}} th{{background:#ece6da}}
</style></head><body>
<h1>Nuevo ejemplo: plantas y demanda del tablero SIN nodal, resueltas en PyPSA</h1>
<p>Fuente de reglas: <code>srriverar/dashboard-sin-nodal</code> @ 514cc091 y
<a href="https://dashboard-sin-nodal.streamlit.app/">dashboard-sin-nodal.streamlit.app</a>
(pestañas <b>⚡ Generación</b>, <b>📈 Demanda</b> y <b>Explorador de planta</b>).
Colores: workshop PyPSA Labs (<code>Carrier.color</code> = tomato, gold, teal, royalblue, dimgrey…).</p>
<div class="note">Las 7 subregiones y los pesos de demanda son <b>supuestos declarados del tablero</b>,
no una clasificación oficial XM/UPME. La API abierta no trae coordenadas de planta; el tablero usa
toponimia del nombre. PyPSA-col replica esa regla y reporta la cobertura.</div>
<table>
<tr><th>Indicador</th><th>Valor</th></tr>
<tr><td>Plantas con CEN &gt; 0</td><td>{summary['n_plants']}</td></tr>
<tr><td>CEN total</td><td>{summary['cen_mw']:.0f} MW</td></tr>
<tr><td>Cobertura toponímica</td><td>{summary['toponymy_pct']:.1f} % del CEN</td></tr>
<tr><td>Demanda 48 h</td><td>{summary['demand_gwh']:.1f} GWh</td></tr>
<tr><td>No atendida (modelo)</td><td>{summary['unserved_gwh']:.2f} GWh ({100*summary['unserved_fraction']:.1f} %)</td></tr>
<tr><td>Objetivo</td><td>{summary['objective_usd']:,.0f} USD ilustrativos</td></tr>
<tr><td>Status</td><td>{summary['status']}</td></tr>
</table>
<h2>Demanda (pestaña 📈)</h2>
{tag(images['demand'])}
<h2>Despacho PyPSA (colores del workshop)</h2>
{tag(images['dispatch'])}
<h2>Mix observado vs óptimo</h2>
{tag(images['mix'])}
<h2>Red de 7 subregiones</h2>
{tag(images['network'])}
<h2>Explorador de planta</h2>
{tag(images['plants'])}
{tag(images['profiles'])}
<p style="color:#5c6b7a;font-size:13px">Hidro y renovables se limitan al perfil observado (Gene/Recurso) para no inventar
sol/viento/agua. Las térmicas pueden despachar hasta su CEN. Eso convierte el LP en un despacho económico
del parque térmico dada la generación variable ya medida — la lectura didáctica de un notebook PyPSA de dispatch.</p>
</body></html>"""
    dest = out / "informe.html"
    dest.write_text(html, encoding="utf-8")
    return dest


def run(root: Path, config: dict) -> dict:
    index = snapshots(config)
    tables = load_tables(root, config)
    plants = assemble_plants(tables, index)
    demand = demand_by_zone(tables["dema"], index)
    observed = observed_zone_carrier(tables["gene"], plants, index)
    n = build_network(plants, demand, observed)
    n, status, condition = solve_network(n)
    out = root / "results" / config["run"]["id"]
    out.mkdir(parents=True, exist_ok=True)
    resources = root / "resources" / config["run"]["id"]
    resources.mkdir(parents=True, exist_ok=True)
    plants.to_csv(resources / "dim_plantas.csv", index=False)
    demand.to_csv(resources / "demanda_zonal_mw.csv")
    explorer = plant_explorer_table(plants, tables["gene"], index)
    explorer.to_csv(resources / "explorador_planta.csv", index=False)
    n.export_to_netcdf(out / "network.nc")
    modelled = n.generators_t.p.T.groupby(n.generators.carrier).sum().T.clip(lower=0).sum() / 1000.0
    obs_energy = (
        tables["gene"].assign(timestamp=lambda d: pd.to_datetime(d["timestamp"]))
    )
    obs_energy = obs_energy[obs_energy["timestamp"].isin(index)]
    obs_join = obs_energy.merge(
        plants[["Codigo_Planta", "carrier"]], left_on="entity_code", right_on="Codigo_Planta", how="inner"
    )
    observed_mix = obs_join.groupby("carrier")["value"].sum() / 1e6  # GWh
    images = {
        "dispatch": fig_dispatch(n, out / "dispatch.png"),
        "network": fig_network(n, out / "red.png"),
        "mix": fig_mix(observed_mix, modelled.drop(labels=["load shedding"], errors="ignore"), out / "mix.png"),
        "plants": fig_plants(explorer, out / "plantas.png"),
        "profiles": fig_plant_profile(explorer, out / "perfiles_planta.png"),
        "demand": fig_demand(demand, out / "demanda.png"),
    }
    shed = modelled.get("load shedding", 0.0)
    demand_gwh = float(demand.sum().sum() / 1000.0)
    located = plants.loc[plants["asignacion"] == "toponimia", "cen_mw"].sum()
    summary = {
        "n_plants": int(len(plants)),
        "cen_mw": float(plants["cen_mw"].sum()),
        "toponymy_pct": float(100 * located / max(plants["cen_mw"].sum(), 1e-9)),
        "demand_gwh": demand_gwh,
        "unserved_gwh": float(shed),
        "unserved_fraction": float(shed / max(demand_gwh, 1e-9)),
        "objective_usd": float(n.objective),
        "status": status,
        "termination": condition,
        "carriers": {k: float(v) for k, v in modelled.items()},
        "warning": "Dashboard subregions and demand shares are declared assumptions, not official XM geography.",
    }
    write_json(out / "summary.json", summary)
    write_report(out, summary, images)
    return summary
