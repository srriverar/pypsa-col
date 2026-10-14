#!/usr/bin/env python3
"""Publication-style atlas of the four solved PyPSA-col examples (offline)."""
from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, FancyBboxPatch, FancyArrowPatch
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
OUT = RES / "atlas"
OUT.mkdir(parents=True, exist_ok=True)

# PyPSA-Eur / PyPSA-USA technology colours
C = {
    "hydro": "#2980b9",
    "wind": "#235ebc",
    "solar": "#f9d71c",
    "gas": "#d35050",
    "coal": "#545454",
    "oil": "#c77e3a",
    "battery": "#4ce0b3",
    "load_shedding": "#c0392b",
    "demand": "#2c3e50",
    "transport": "#7f8c8d",
}
STACK = ["hydro", "coal", "gas", "oil", "solar", "wind", "battery", "load_shedding"]
LABEL = {
    "hydro": "Hidro",
    "coal": "Carbón",
    "gas": "Gas",
    "oil": "Diésel / fuelóleo",
    "solar": "Solar",
    "wind": "Eólico",
    "battery": "Batería",
    "load_shedding": "Demanda no atendida",
}
HUB_XY = {
    "La Guajira": (-72.55, 11.55),
    "Cesar": (-73.55, 9.35),
    "Caribe": (-75.52, 10.40),
    "Antioquia": (-75.05, 7.05),
    "Medellin": (-75.58, 6.22),
    "Bogota": (-74.08, 4.65),
    "Tolima": (-75.22, 4.40),
}
BG = "#f6f3ee"
INK = "#1b2a41"
MUTED = "#5c6b7a"

plt.rcParams.update(
    {
        "figure.facecolor": BG,
        "axes.facecolor": "#fffcf7",
        "axes.edgecolor": "#d9d2c5",
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "grid.color": "#e4ddd0",
        "grid.linewidth": 0.7,
        "font.size": 10.5,
        "axes.titlesize": 13.5,
        "axes.titleweight": "semibold",
        "figure.dpi": 140,
        "savefig.dpi": 160,
        "savefig.bbox": "tight",
        "savefig.facecolor": BG,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
    }
)


def load_carrier(run: str) -> pd.DataFrame:
    path = RES / run / "dispatch_by_carrier_mw.csv"
    raw = pd.read_csv(path)
    if "timestep" in raw.columns:
        raw["snapshot"] = pd.to_datetime(raw["timestep"])
        return raw
    raw["snapshot"] = pd.to_datetime(raw["snapshot"])
    raw["period"] = "operational"
    return raw


def energy_mwh(df: pd.DataFrame) -> pd.Series:
    cols = [c for c in STACK if c in df.columns]
    return df[cols].clip(lower=0).sum()


def save(fig, name: str) -> Path:
    path = OUT / name
    fig.savefig(path, pad_inches=0.25)
    plt.close(fig)
    return path


def fig_objective_cards():
    fig, ax = plt.subplots(figsize=(12.4, 5.6))
    ax.set_xlim(0, 12.4)
    ax.set_ylim(0, 5.6)
    ax.axis("off")
    fig.suptitle(
        "Cuatro corridas, tres unidades distintas — no comparar el objetivo a ciegas",
        x=0.02,
        ha="left",
        fontsize=15,
        color=INK,
    )
    cards = [
        (0.25, "demo", "Despacho 48 h\nsintético", "1,56 mill. USD", "OPEX de 48 horas",
         "Demanda 152 GWh · 0 % no servida\nHidro 72 % de la energía", "#1b6b93"),
        (3.30, "el-nino", "Misma demanda\nsequía hipotética", "3,27 mill. USD", "OPEX de 48 horas",
         "Hidro −37 % · gas y carbón suben\nCosto ×2,1 vs. demo", "#b85c38"),
        (6.35, "investment2030", "Expansión 2026–2030\nbloque repetido", "1 364 mill. USD",
         "CAPEX anualizado + OPEX\ndescontado (otra unidad)",
         "Solar + eólico + refuerzo\nCesar–Caribe · 0 % no servida", "#2e6b4f"),
        (9.40, "xm-example", "Demanda XM real\nflota ilustrativa", "1 853 mill. USD",
         "OPEX 48 h + VOLL 10 000\nUSD/MWh de racionamiento",
         "48,8 % no atendida:\ncobertura incompleta, no un apagón", "#8b2e3b"),
    ]
    for x, rid, title, value, unit, note, accent in cards:
        box = FancyBboxPatch(
            (x, 0.35), 2.85, 4.55, boxstyle="round,pad=0.04,rounding_size=0.12",
            facecolor="white", edgecolor=accent, linewidth=1.6,
        )
        ax.add_patch(box)
        ax.add_patch(plt.Rectangle((x, 4.62), 2.85, 0.28, color=accent, zorder=3))
        ax.text(x + 0.18, 4.68, rid, color="white", fontsize=9, fontweight="bold", zorder=4)
        ax.text(x + 0.18, 3.95, title, fontsize=11, fontweight="semibold", va="top")
        ax.text(x + 0.18, 2.55, value, fontsize=15, fontweight="bold", color=accent)
        ax.text(x + 0.18, 1.95, unit, fontsize=8.4, color=MUTED, va="top")
        ax.text(x + 0.18, 0.55, note, fontsize=8.2, color=INK, va="bottom")
    return save(fig, "01_objetivos.png")


def fig_energy_mix():
    demo, nino, xm = (energy_mwh(load_carrier(r)) for r in ("demo", "el-nino", "xm-example"))
    demand = {
        "demo": 151566.2,
        "el-nino": 151566.2,
        "xm-example": 377568.2,
    }
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 5.2), sharey=False)
    fig.suptitle("Mezcla energética de 48 h  ·  lectura tipo PyPSA-Eur (stacked bar)", fontsize=14)
    series = [("demo", demo, "Demo sintético"), ("el-nino", nino, "El Niño hipotético"),
              ("xm-example", xm, "XM híbrido")]
    for ax, (key, ser, title) in zip(axes, series):
        bottom = 0.0
        tot = ser.sum()
        for tech in STACK:
            val = float(ser.get(tech, 0.0))
            if val <= 1e-6:
                continue
            ax.bar(0, val / 1000, bottom=bottom / 1000, color=C[tech], width=0.62,
                   edgecolor="white", linewidth=0.4, label=LABEL[tech])
            if val / tot > 0.06:
                ax.text(0, (bottom + val / 2) / 1000, f"{100 * val / demand[key]:.0f}%",
                        ha="center", va="center", fontsize=8.5, color="white" if tech not in {"solar"} else INK,
                        fontweight="bold")
            bottom += val
        ax.axhline(demand[key] / 1000, color=INK, ls="--", lw=1.0)
        ax.text(0.42, demand[key] / 1000 + 4, f"demanda {demand[key]/1000:.0f} GWh",
                fontsize=8, color=INK)
        ax.set_title(title)
        ax.set_xticks([])
        ax.set_xlim(-0.7, 0.7)
        ax.set_ylabel("Energía (GWh en 48 h)")
        ax.grid(axis="y")
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))
    handles, labels = axes[2].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout()
    return save(fig, "02_mezcla_energia.png")


def stacked_dispatch(ax, df: pd.DataFrame, title: str, show_demand=True):
    t = df["snapshot"]
    bottom = np.zeros(len(df))
    for tech in STACK:
        if tech not in df.columns:
            continue
        y = np.clip(df[tech].to_numpy(float), 0, None)
        if y.max() < 1e-6:
            continue
        ax.fill_between(t, bottom, bottom + y, color=C[tech], lw=0, label=LABEL[tech])
        bottom += y
    if show_demand:
        load_cols = [c for c in df.columns if c.startswith("Demand_")]
        # demand overlaid from separate file by caller if needed
    ax.set_title(title)
    ax.set_ylabel("MW")
    ax.grid(axis="y")
    ax.margins(x=0)


def fig_dispatch_compare():
    fig, axes = plt.subplots(3, 1, figsize=(12.4, 9.6), sharex=False)
    fig.suptitle("Despacho horario apilado  ·  el gráfico clásico de PyPSA", fontsize=14)
    titles = {
        "demo": "Demo — hidro cubre el valle; gas solo al mediodía; Caribe se congestiona",
        "el-nino": "El Niño — presupuesto hidro recortado; carbón y gas entran de base",
        "xm-example": "XM híbrido — la flota ilustrativa no alcanza la demanda nacional observada",
    }
    for ax, run in zip(axes, ("demo", "el-nino", "xm-example")):
        df = load_carrier(run)
        stacked_dispatch(ax, df, titles[run])
        load = pd.read_csv(RES / run / "load_mw.csv", index_col=0, parse_dates=True)
        ax.plot(load.index, load.sum(axis=1), color=INK, lw=1.35, label="Demanda")
        ax.legend(loc="upper left", ncol=4, fontsize=8)
    axes[-1].set_xlabel("Hora local colombiana (America/Bogota)")
    fig.tight_layout()
    return save(fig, "03_despacho.png")


def fig_drought_story():
    demo = load_carrier("demo")
    nino = load_carrier("el-nino")
    fig, axes = plt.subplots(2, 2, figsize=(12.4, 7.6))
    fig.suptitle("Qué cambia en El Niño: no es más demanda, es menos agua", fontsize=14)
    # hydro vs thermal energy
    ax = axes[0, 0]
    cats = ["Hidro", "Térmico\n(gas+carbón+diésel)", "Renovables\nvariables"]
    d_vals = [109204, 11778 + 0 + 758, 7535 + 22291]
    n_vals = [68640, 39658 + 12685 + 758, 7535 + 22291]
    x = np.arange(3)
    ax.bar(x - 0.18, np.array(d_vals) / 1000, 0.34, color="#1b6b93", label="demo")
    ax.bar(x + 0.18, np.array(n_vals) / 1000, 0.34, color="#b85c38", label="el-nino")
    ax.set_xticks(x, cats)
    ax.set_ylabel("GWh en 48 h")
    ax.set_title("Sustitución de energía")
    ax.legend()
    ax.grid(axis="y")
    # SOC
    ax = axes[0, 1]
    for run, ls, col in (("demo", "-", "#1b6b93"), ("el-nino", "--", "#b85c38")):
        soc = pd.read_csv(RES / run / "state_of_charge_mwh.csv", index_col=0, parse_dates=True)
        hydro = soc[[c for c in soc.columns if c.startswith("Hydro")]].sum(axis=1) / 1000
        ax.plot(hydro.index, hydro, ls=ls, color=col, lw=2, label=run)
    ax.set_title("Energía embalsada (GWh)")
    ax.set_ylabel("GWh")
    ax.legend()
    ax.grid(True)
    ax.tick_params(axis="x", labelrotation=15)
    # prices
    ax = axes[1, 0]
    for run, col in (("demo", "#1b6b93"), ("el-nino", "#b85c38")):
        p = pd.read_csv(RES / run / "prices_usd_per_mwh.csv", index_col=0, parse_dates=True)
        ax.plot(p.index, p["Caribe"], color=col, lw=2, label=f"{run} · Caribe")
        ax.plot(p.index, p["Bogota"], color=col, lw=1.2, ls=":", label=f"{run} · Bogotá")
    ax.set_title("Precio nodal del modelo (USD/MWh)")
    ax.set_ylabel("USD/MWh")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True)
    ax = axes[1, 1]
    ax.axis("off")
    text = (
        "Misma demanda: 151,6 GWh en 48 h.\n\n"
        "Hidro cae 109 → 69 GWh (−37 %).\n"
        "El hueco lo llenan gas (12 → 40 GWh)\n"
        "y carbón (0 → 13 GWh).\n\n"
        "OPEX: 1,56 → 3,27 mill. USD (×2,1).\n\n"
        "Caribe sigue aislado por el corredor\n"
        "Cesar–Caribe al 100 %: el precio allí\n"
        "toca 120 USD/MWh al mediodía.\n\n"
        "Es un estrés hipotético, no un\n"
        "reanálisis calibrado de un Niño real."
    )
    ax.text(0.02, 0.98, text, va="top", fontsize=11, family="DejaVu Sans", wrap=True)
    fig.tight_layout()
    return save(fig, "04_elnino.png")


def fig_xm_gap():
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.4), gridspec_kw={"width_ratios": [1.15, 1]})
    fig.suptitle("XM híbrido: el número grande del objetivo es racionamiento modelado, no el SIN real", fontsize=13)
    df = load_carrier("xm-example")
    ax = axes[0]
    stacked_dispatch(ax, df, "Despacho 48 h  ·  el rojo es load-shedding a 10 000 USD/MWh")
    load = pd.read_csv(RES / "xm-example" / "load_mw.csv", index_col=0, parse_dates=True)
    ax.plot(load.index, load.sum(axis=1), color=INK, lw=1.4, label="Demanda XM (DemaReal)")
    ax.legend(loc="upper left", ncol=3, fontsize=8)
    ax.set_xlabel("Hora local")
    ax = axes[1]
    ax.axis("off")
    rows = [
        ("Demanda observada (48 h)", "378 GWh"),
        ("Generación de la flota ilustrativa", "193 GWh"),
        ("No atendida", "184 GWh  (48,8 %)"),
        ("Hidro modelada", "11 GWh"),
        ("Precio tope (VOLL)", "10 000 USD/MWh"),
        ("Objetivo", "1 853 mill. USD"),
    ]
    y = 0.92
    ax.text(0.0, y, "Por qué el objetivo explota", fontsize=13, fontweight="bold")
    y -= 0.10
    for k, v in rows:
        ax.text(0.0, y, k, fontsize=10.5, color=MUTED)
        ax.text(1.0, y, v, fontsize=11, fontweight="semibold", ha="right")
        y -= 0.10
    ax.text(
        0.0, 0.08,
        "La demanda es nacional (XM). La flota sigue\n"
        "siendo el juguete de 7 nodos. El modelo declara\n"
        "el faltante en vez de ocultarlo. No es un\n"
        "diagnóstico de apagones en Colombia.",
        fontsize=9.5, color=INK, va="bottom",
    )
    fig.tight_layout()
    return save(fig, "05_xm_cobertura.png")


def fig_network():
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 6.8))
    fig.suptitle("Red de 7 hubs  ·  el cuello de botella Cesar–Caribe explica casi todo", fontsize=14)
    br = pd.read_csv(RES / "demo" / "branches.csv")
    load = pd.read_csv(RES / "demo" / "load_mw.csv", index_col=0).max()
    demand = {k.replace("Demand_", ""): float(v) for k, v in load.items()}
    gen_at = {
        "La Guajira": ("eólico 800 MW", C["wind"]),
        "Cesar": ("solar 400 + carbón 300", C["solar"]),
        "Caribe": ("gas 500 + diésel 200", C["gas"]),
        "Antioquia": ("hidro 4 200 MW", C["hydro"]),
        "Medellin": ("hidro 200 + gas 300", C["hydro"]),
        "Bogota": ("gas 800 + solar Santander 200", C["gas"]),
        "Tolima": ("hidro 600 + gas 300", C["hydro"]),
    }
    ax = axes[0]
    ax.set_title("Demo · utilización pico del corredor")
    for _, row in br.iterrows():
        x0, y0 = HUB_XY[row.bus0]
        x1, y1 = HUB_XY[row.bus1]
        u = float(row.peak_utilization_percent) / 100
        color = "#c0392b" if u >= 0.95 else "#e67e22" if u >= 0.70 else "#27ae60"
        ax.plot([x0, x1], [y0, y1], color=color, lw=1.2 + 4 * u, solid_capstyle="round", zorder=1)
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        if row["name"] in {"Cesar_Caribe", "Ant_Bog_500", "Colectora"}:
            ax.text(mx + 0.12, my + 0.22, f"{u:.0%}", fontsize=7.5, ha="left", color=color, fontweight="bold")
    label_xy = {
        "La Guajira": (0.0, 0.42),
        "Cesar": (0.38, 0.12),
        "Caribe": (-0.55, 0.05),
        "Antioquia": (0.42, 0.18),
        "Medellin": (-0.62, -0.05),
        "Bogota": (0.48, -0.05),
        "Tolima": (-0.55, -0.28),
    }
    for hub, xy in HUB_XY.items():
        size = 0.12 + 0.28 * (demand.get(hub, 0) / 2000)
        ax.add_patch(Circle(xy, size, facecolor="white", edgecolor=INK, lw=1.4, zorder=3))
        dx, dy = label_xy[hub]
        ax.text(xy[0] + dx, xy[1] + dy, hub, ha="center", va="center", fontsize=8, fontweight="semibold")
    ax.set_xlim(-77.3, -71.3)
    ax.set_ylim(3.3, 12.6)
    ax.set_aspect("equal")
    ax.axis("off")
    legend = [
        Line2D([0], [0], color="#c0392b", lw=4, label="≥ 95 % pico (saturado)"),
        Line2D([0], [0], color="#e67e22", lw=3, label="70–95 %"),
        Line2D([0], [0], color="#27ae60", lw=2, label="< 70 %"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=8, bbox_to_anchor=(1.02, 0.02))
    ax = axes[1]
    ax.set_title("Dónde está la demanda vs. el recurso")
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    txt = (
        "Demanda pico del demo\n"
        "  Bogotá     2 000 MW\n"
        "  Caribe     1 200 MW\n"
        "  Medellín     800 MW\n"
        "  Tolima       400 MW\n"
        "  Guajira/Cesar/Antioquia   0 MW de carga\n\n"
        "El viento está en La Guajira, el sol en Cesar\n"
        "y Santander (inyectado en Bogotá), la hidro\n"
        "grande en Antioquia. Caribe solo se alimenta\n"
        "por un enlace de 600 MW: 48/48 horas al 100 %.\n\n"
        "Por eso el modelo de inversión refuerza\n"
        "Cesar–Caribe (+725 MW a 2030) y no Colectora:\n"
        "el cuello no era sacar el viento, era meterlo\n"
        "al Caribe.\n\n"
        "Geografía OSM ≠ conectividad eléctrica.\n"
        "Estos 7 hubs son transporte sin pérdidas."
    )
    ax.text(0.02, 0.98, txt, va="top", fontsize=10.5, family="DejaVu Sans")
    fig.tight_layout()
    return save(fig, "06_red.png")


def fig_investment():
    cap = pd.read_csv(RES / "investment2030" / "active_capacities.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.8))
    fig.suptitle("Expansión 2026–2030  ·  capacidad nueva que el óptimo sí construye", fontsize=14)
    years = [2026, 2028, 2030]
    builds = {
        "Solar Cesar": [789.10, 789.10, 789.10],
        "Solar Santander": [979.29, 979.29 + 320.71, 979.29 + 320.71],
        "Eólico Guajira": [0.0, 140.70, 140.70 + 319.74],
        "Cesar–Caribe extra": [587.73, 587.73 + 60.13, 587.73 + 60.13 + 76.71],
        "Batería Caribe": [0, 0, 0],
        "Colectora extra": [0, 0, 0],
    }
    colors_b = {
        "Solar Cesar": C["solar"],
        "Solar Santander": "#e3c117",
        "Eólico Guajira": C["wind"],
        "Cesar–Caribe extra": "#8e44ad",
        "Batería Caribe": C["battery"],
        "Colectora extra": "#95a5a6",
    }
    ax = axes[0]
    x = np.arange(len(years))
    bottom = np.zeros(3)
    order = ["Solar Cesar", "Solar Santander", "Eólico Guajira", "Cesar–Caribe extra"]
    for name in order:
        y = np.array(builds[name])
        ax.bar(x, y, bottom=bottom, color=colors_b[name], width=0.55, label=name, edgecolor="white")
        bottom += y
    ax.set_xticks(x, years)
    ax.set_ylabel("MW acumulados construidos")
    ax.set_title("Vintages que el solver elige")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(axis="y")
    ax = axes[1]
    # annual energy from 48h * 182.5
    d = load_carrier("investment2030")
    w = 182.5
    rows = []
    for year, sub in d.groupby("period"):
        e = energy_mwh(sub) * w / 1e6  # TWh
        e["demanda"] = {2026: 27.661, 2028: 29.061, 2030: 30.532}[int(year)]
        rows.append(e)
    mix = pd.DataFrame(rows, index=years)
    bottom = np.zeros(3)
    for tech in ["hydro", "solar", "wind", "gas", "coal", "oil"]:
        y = mix[tech].to_numpy() if tech in mix else np.zeros(3)
        if y.max() < 1e-4:
            continue
        ax.bar(x, y, bottom=bottom, color=C[tech], width=0.55, label=LABEL[tech], edgecolor="white")
        bottom += y
    ax.plot(x, mix["demanda"], "ko--", lw=1.4, ms=6, label="Demanda anual")
    ax.set_xticks(x, years)
    ax.set_ylabel("TWh / año (bloque × 182,5)")
    ax.set_title("Energía anualizada — hidro topeada, solar/eólico crecen")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(axis="y")
    fig.tight_layout()
    return save(fig, "07_inversion.png")


def fig_prices_heatmap():
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.2))
    fig.suptitle("Precios nodales del modelo  ·  no son el Precio de Bolsa XM", fontsize=14)
    buses = ["La Guajira", "Cesar", "Caribe", "Antioquia", "Medellin", "Bogota", "Tolima"]
    cmap = LinearSegmentedColormap.from_list("pypsa", ["#f7f4ef", "#f1c40f", "#e67e22", "#c0392b"])
    for ax, run, title, vmax in (
        (axes[0], "demo", "Demo (USD/MWh)", 130),
        (axes[1], "el-nino", "El Niño (USD/MWh)", 130),
    ):
        p = pd.read_csv(RES / run / "prices_usd_per_mwh.csv", index_col=0, parse_dates=True)[buses]
        im = ax.imshow(p.T, aspect="auto", cmap=cmap, vmin=0, vmax=vmax, interpolation="nearest")
        ax.set_yticks(range(len(buses)), buses, fontsize=8)
        ax.set_title(title)
        n = len(p)
        ax.set_xticks([0, 12, 24, 36, 47], ["01-01 00", "12h", "01-02 00", "12h", "23h"])
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    fig.tight_layout()
    return save(fig, "08_precios.png")


def fig_qa():
    fig, ax = plt.subplots(figsize=(12.4, 4.8))
    runs = ["demo", "el-nino", "investment2030", "xm-example"]
    nodal = [5.68e-13, 3.41e-13, 6.54e-13, 5.68e-13]
    water = [2.91e-11, 2.01e-11, 6.09e-11, 2.25e-11]
    x = np.arange(len(runs))
    ax.bar(x - 0.18, nodal, 0.34, color="#1b6b93", label="Residuo nodal máximo (MW)")
    ax.bar(x + 0.18, water, 0.34, color="#2e6b4f", label="Residuo de embalse máximo (MWh)")
    ax.axhline(1e-5, color="#c0392b", ls="--", lw=1.2, label="Tolerancia 1×10⁻⁵")
    ax.set_yscale("log")
    ax.set_xticks(x, runs)
    ax.set_ylabel("Error absoluto")
    ax.set_title("Control de calidad físico — como en PyPSA-Eur: el óptimo también tiene que cuadrar energía")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, which="both", axis="y")
    ax.set_ylim(1e-14, 3e-5)
    fig.text(
        0.5, -0.02,
        "Un residuo de 10⁻¹³ MW es ruido de punto flotante, no un desbalance real. "
        "Las cuatro corridas terminaron optimal y pasaron la validación independiente antes de aceptar el NetCDF.",
        ha="center", fontsize=8.5, color=MUTED,
    )
    fig.tight_layout()
    return save(fig, "09_qa.png")


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def mime(path: Path) -> str:
    return {".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".pdf": "application/pdf"}[path.suffix]


def img_tag(path: Path, alt: str) -> str:
    return f'<img src="data:{mime(path)};base64,{b64(path)}" alt="{alt}">'


def write_html(paths: dict[str, Path]) -> Path:
    poster = RES / "demo" / "grid2poster.png"
    dispatch_demo = RES / "demo" / "dispatch.png"
    dispatch_nino = RES / "el-nino" / "dispatch.png"
    dispatch_inv = RES / "investment2030" / "dispatch.png"
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Atlas de resultados PyPSA-col</title>
<style>
:root {{
  --ink:#1b2a41; --muted:#5c6b7a; --bg:#f6f3ee; --card:#fffdf9;
  --line:#e4ddd0; --hydro:#2980b9; --accent:#1b6b93; --warn:#8b2e3b;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; font-family:"Source Serif 4", "Iowan Old Style", Georgia, serif;
  background:var(--bg); color:var(--ink); line-height:1.55;
}}
header {{
  background:#152238; color:#f6f3ee; padding:48px 8vw 36px;
}}
header p.kicker {{ letter-spacing:.16em; text-transform:uppercase; font-size:12px; color:#9ab; margin:0 0 10px;
  font-family: ui-sans-serif, system-ui, sans-serif; }}
h1 {{ font-weight:600; font-size:clamp(28px,4vw,44px); line-height:1.15; margin:0 0 12px; }}
.sub {{ max-width:720px; color:#d9e2ea; font-size:18px; }}
main {{ max-width:1100px; margin:0 auto; padding:28px 20px 80px; }}
h2 {{ font-size:28px; margin:48px 0 12px; }}
h3 {{ font-size:20px; margin:28px 0 8px; }}
p, li {{ font-size:17px; }}
.note {{
  background:#fff; border-left:4px solid var(--accent); padding:12px 16px; margin:18px 0;
}}
.warn {{
  background:#fbeaea; border-left:4px solid var(--warn); padding:12px 16px; margin:18px 0;
}}
img {{ width:100%; height:auto; border-radius:10px; border:1px solid var(--line); background:#fff; }}
figure {{ margin:22px 0 8px; }}
figcaption {{ font-family: ui-sans-serif, system-ui, sans-serif; font-size:13px; color:var(--muted); margin-top:8px; }}
table {{ border-collapse:collapse; width:100%; background:#fff; font-family: ui-sans-serif, system-ui, sans-serif; font-size:14px; }}
th, td {{ border-bottom:1px solid var(--line); padding:8px 10px; text-align:left; }}
th {{ background:#ece6da; }}
td.num, th.num {{ text-align:right; font-variant-numeric: tabular-nums; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
@media (max-width:800px) {{ .grid {{ grid-template-columns:1fr; }} }}
footer {{ color:var(--muted); font-size:13px; font-family: ui-sans-serif, system-ui, sans-serif; margin-top:48px; }}
code {{ background:#ece6da; padding:1px 5px; border-radius:4px; font-size:90%; }}
</style>
</head>
<body>
<header>
  <p class="kicker">PyPSA-col · atlas de resultados · 2026</p>
  <h1>Cómo se leen estos cuatro óptimos, al estilo PyPSA-Eur y PyPSA-USA</h1>
  <p class="sub">No se empieza por el número del objetivo. Se empieza por la pregunta que cada corrida sabe responder,
  luego el mix, el despacho, la red, los precios nodales y, al final, el control de calidad físico.</p>
</header>
<main>
<h2>1. Cuatro experimentos, no cuatro pronósticos</h2>
<p>En PyPSA-Eur un escenario <em>overnight</em> y un escenario de transición 2030 no se restan como si fueran la misma
cosa. Aquí ocurre lo mismo. Los cuatro NetCDF son óptimos de HiGHS, con residuos de 10<sup>−13</sup>, pero
<strong>no hablan las mismas unidades ni cubren el mismo sistema</strong>.</p>
<figure>
{img_tag(paths['obj'], 'Tarjetas de los cuatro objetivos')}
<figcaption>Figura 1. El objetivo es el valor de la función que el solver minimizó. Mezclar OPEX de 48 h con CAPEX
anualizado descontado, o con racionamiento a 10 000 USD/MWh, es un error de interpretación, no un resultado.</figcaption>
</figure>
<table>
<thead><tr><th>Corrida</th><th>Pregunta que sí responde</th><th>Qué no es</th></tr></thead>
<tbody>
<tr><td><code>demo</code></td><td>¿Cómo despacha una flota ilustrativa de 7 hubs en 48 h húmedas?</td>
<td>El costo real del SIN colombiano.</td></tr>
<tr><td><code>el-nino</code></td><td>¿Qué pasa si recortamos el agua y mantenemos la misma demanda?</td>
<td>Un Niño histórico reconstruido.</td></tr>
<tr><td><code>investment2030</code></td><td>¿Qué capacidad nueva elige un modelo de foresight perfecto con un bloque climático repetido?</td>
<td>Un plan de expansión UPME ni una proyección de precios.</td></tr>
<tr><td><code>xm-example</code></td><td>¿Qué se ve al inyectar DemaReal nacional sobre esa misma flota de juguete?</td>
<td>Adequacy ni apagones observados.</td></tr>
</tbody>
</table>

<h2>2. La figura que PyPSA siempre muestra primero: el mix</h2>
<p>PyPSA-Eur publica barras apiladas de energía anual por portador. Aquí el horizonte es de 48 horas, así que las
unidades son GWh de ventana, no TWh/año — salvo en inversión, donde el bloque se multiplica por 182,5.</p>
<figure>
{img_tag(paths['mix'], 'Mezcla energética de tres corridas de 48 h')}
<figcaption>Figura 2. Demo y El Niño comparten demanda (152 GWh). XM no: su demanda observada es 378 GWh. Por eso
el rojo de racionamiento aparece solo ahí.</figcaption>
</figure>
<ul>
<li><strong>Demo:</strong> hidro 109 GWh (72 %), eólico 22, viento y sol cubren el pico, gas 12 GWh, carbón 0.
Costo 1,56 millones USD.</li>
<li><strong>El Niño:</strong> hidro cae a 69 GWh. Entran 40 GWh de gas y 13 GWh de carbón. Costo 3,27 millones USD,
el doble, <em>con la misma demanda</em>.</li>
<li><strong>XM:</strong> la flota ilustrativa produce ~193 GWh frente a 378 GWh pedidos. El modelo raciona 184 GWh
(48,8 %) a un VOLL de 10 000 USD/MWh. Ese VOLL domina el objetivo de 1 853 millones.</li>
</ul>

<h2>3. Despacho horario: la firma visual de PyPSA</h2>
<p>El stacked area (abajo hidro, luego térmicas, arriba variables) es el gráfico de cabecera de PyPSA-Eur y PyPSA-USA.
La línea negra es la demanda. Si la pila no llega a la línea, hay racionamiento.</p>
<figure>
{img_tag(paths['disp'], 'Tres despachos apilados')}
<figcaption>Figura 3. En el demo el gas solo aparece al mediodía, cuando Caribe está saturado. En El Niño el carbón
es generación de base. En XM el rojo nunca desaparece: falta capacidad, no “mala operación”.</figcaption>
</figure>
<div class="grid">
<figure>{img_tag(dispatch_demo, 'Despacho original demo con embalses y precios')}</figure>
<figure>{img_tag(dispatch_nino, 'Despacho original El Niño')}</figure>
</div>
<figcaption>Figura 4. Salidas nativas de PyPSA-col (despacho + embalse + precio nodal). El panel de precios del demo
muestra a Caribe desacoplado: 10 USD/MWh en el interior, 50–120 en la costa. Eso es congestión, no un precio de bolsa.</figcaption>

<h2>4. Historia didáctica A — sequía</h2>
<p>Comparar demo y El Niño es lo más parecido a un <em>sensitivity case</em> de PyPSA-Eur: se cambia un supuesto
(el agua) y se deja el resto igual. El aumento de costo es entonces atribuible.</p>
<figure>
{img_tag(paths['nino'], 'Comparación demo vs El Niño')}
<figcaption>Figura 5. Sustitución hidro → térmico, embalses, precios. Caribe permanece caro porque el enlace de 600 MW
sigue lleno; la sequía no construye líneas, solo encarece el hueco térmico.</figcaption>
</figure>
<div class="note">Regla de lectura: si dos corridas no comparten demanda, topología, horizonte y definición de costos,
no se reporta un “ahorro” ni un “incremento” como porcentaje del objetivo.</div>

<h2>5. Historia didáctica B — el híbrido XM no es el SIN</h2>
<figure>
{img_tag(paths['xm'], 'Cobertura XM')}
<figcaption>Figura 6. DemaReal nacional sobre 5 GW ilustrativos de térmica + 5 GW de hidro + 1,4 GW renovables.
El racionamiento es un semáforo de cobertura, deliberadamente visible.</figcaption>
</figure>
<div class="warn">Interpretar el 48,8 % como “Colombia racionó la mitad de la energía el 1–2 de enero de 2024”
sería falso. XM midió la demanda; el modelo no tiene el parque nacional ni las importaciones ni las pérdidas del STN.</div>

<h2>6. Historia didáctica C — expansión, como PyPSA-Eur myopic/foresight</h2>
<p>PyPSA-Eur muestra capacidad instalada por año de construcción (<em>vintage</em>). El óptimo de 2030 aquí elige
solar pronto, eólico más tarde y refuerzo del corredor que ya estaba saturado. No elige batería en Caribe ni ampliar
Colectora: el solver puede construirlos y el costo dice que no hace falta bajo estos supuestos.</p>
<figure>
{img_tag(paths['inv'], 'Capacidad nueva e energía anualizada')}
<figcaption>Figura 7. Izquierda: MW acumulados que sí se construyen. Derecha: TWh/año = energía del bloque de 48 h
× 182,5. La hidro queda topeada en 18,2 TWh/año (inflow × 0,8). La demanda crece 27,7 → 30,5 TWh; el hueco lo cubren
sol y viento, no racionamiento.</figcaption>
</figure>
<table>
<thead><tr><th>Activo nuevo</th><th class="num">2026</th><th class="num">2028</th><th class="num">2030</th><th>Lectura</th></tr></thead>
<tbody>
<tr><td>Solar Cesar</td><td class="num">789 MW</td><td class="num">—</td><td class="num">—</td><td>Se construye de una vez, cerca de la demanda costera.</td></tr>
<tr><td>Solar Santander (en Bogotá)</td><td class="num">979 MW</td><td class="num">+321 MW</td><td class="num">—</td><td>El interior también necesita energía diurna.</td></tr>
<tr><td>Eólico Guajira</td><td class="num">0</td><td class="num">+141 MW</td><td class="num">+320 MW</td><td>Más tarde: primero hay que poder sacarlo hacia el Caribe.</td></tr>
<tr><td>Cesar–Caribe extra</td><td class="num">588 MW</td><td class="num">+60 MW</td><td class="num">+77 MW</td><td>El cuello de botella; se refuerza en los tres vintage.</td></tr>
<tr><td>Batería Caribe / Colectora extra</td><td class="num">0</td><td class="num">0</td><td class="num">0</td><td>Candidatos activos, no seleccionados. Eso también es un resultado.</td></tr>
</tbody>
</table>
<figure>
{img_tag(dispatch_inv, 'Despacho de inversión por periodos')}
<figcaption>Figura 8. Tres bloques de 48 h, uno por año de inversión. Visualmente aparece más amarillo (solar) y más
verde-azul (eólico) hacia 2030; la hidro se mantiene plana porque el presupuesto de agua no crece.</figcaption>
</figure>
<div class="note">El bloque climático de 48 h repetido <em>no</em> representa estacionalidad. No use estos MW para
dimensionar almacenamiento de semanas ni reserva de El Niño real. PyPSA-Eur usa al menos recortes climáticos de un
año (a menudo varios) precisamente por eso.</div>

<h2>7. Red y mapa, como el poster de PyPSA</h2>
<p>PyPSA-Eur colorea las líneas por carga y pone tartas de capacidad en los nodos. Grid2Poster hace la geografía OSM;
el modelo eléctrico de estos ejemplos son <strong>siete hubs unidos por Links bidireccionales sin pérdidas</strong>.
El mapa bonito no es la topología que se optimizó.</p>
<figure>
{img_tag(paths['net'], 'Esquema de 7 hubs y cuellos de botella')}
<figcaption>Figura 9. Cesar–Caribe al 100 % las 48 horas del demo. Colectora (Guajira→Cesar) apenas al 53 %:
el viento sí sale de La Guajira; no entra del todo al Caribe.</figcaption>
</figure>
<figure>
{img_tag(poster, 'Grid2Poster Colombia con carga modelada')}
<figcaption>Figura 10. Poster geográfico. Rojo ≥ 95 % de utilización <em>del modelo</em>. Incluye ZNI en recuadros,
que en estos corridos no están conectadas eléctricamente. Leyenda del propio renderer: no son flujos medidos.</figcaption>
</figure>

<h2>8. Precios nodales: la señal de congestión</h2>
<p>En PyPSA el precio es el dual de la balanza de potencia en cada barra (<code>buses_t.marginal_price</code>).
Si dos nodos tienen el mismo precio, no hay congestión entre ellos. Si Caribe se dispara y Bogotá no, el enlace
está saturado.</p>
<figure>
{img_tag(paths['px'], 'Mapas de calor de precios nodales')}
<figcaption>Figura 11. Demo: interior ~10 USD/MWh (hidro marginal); Caribe 50–120. El Niño: todo el sistema se encarece
porque el agua ya no es barata, y Caribe sigue por encima. No convertir a COP ni comparar con PrecBolsNaci.</figcaption>
</figure>

<h2>9. Control de calidad — la parte aburrida que PyPSA se toma en serio</h2>
<figure>
{img_tag(paths['qa'], 'Residuos nodales y de embalse')}
<figcaption>Figura 12. Residuo nodal máximo 3–7×10⁻¹³ MW frente a una tolerancia de 10⁻⁵. Balance de agua
~10⁻¹¹ MWh. Cero bombeo hidroeléctrico (el modelo lo prohíbe). Las cuatro corridas: status optimal.</figcaption>
</figure>
<table>
<thead>
<tr><th>Corrida</th><th>Interpretación</th><th class="num">Objetivo</th><th class="num">Residuo nodal</th>
<th class="num">Residuo agua</th><th class="num">No servida</th></tr>
</thead>
<tbody>
<tr><td>demo</td><td>OPEX 48 h sintético</td><td class="num">1 562 249 USD</td><td class="num">5,68×10⁻¹³ MW</td>
<td class="num">2,91×10⁻¹¹ MWh</td><td class="num">0 %</td></tr>
<tr><td>el-nino</td><td>OPEX 48 h, sequía hipotética</td><td class="num">3 272 572 USD</td><td class="num">3,41×10⁻¹³ MW</td>
<td class="num">2,01×10⁻¹¹ MWh</td><td class="num">0 %</td></tr>
<tr><td>investment2030</td><td>CAPEX anualizado + OPEX descontado</td><td class="num">1 364 154 419 USD</td>
<td class="num">6,54×10⁻¹³ MW</td><td class="num">6,09×10⁻¹¹ MWh</td><td class="num">0 %</td></tr>
<tr><td>xm-example</td><td>OPEX 48 h + VOLL</td><td class="num">1 853 360 880 USD</td><td class="num">5,68×10⁻¹³ MW</td>
<td class="num">2,25×10⁻¹¹ MWh</td><td class="num">48,8 %</td></tr>
</tbody>
</table>

<h2>10. Cómo lo presentaría un paper al estilo PyPSA-Eur</h2>
<ol>
<li><strong>Figura de red</strong> con capacidad y carga — aquí, Fig. 9–10.</li>
<li><strong>Mix y despacho</strong> — Fig. 2–4. Siempre con la demanda dibujada encima.</li>
<li><strong>Sensibilidad</strong> (El Niño) como diferencia respecto al caso base, no como número suelto — Fig. 5.</li>
<li><strong>Path de inversión</strong> por vintage y por tecnología — Fig. 7. Reportar también lo que <em>no</em> se construye.</li>
<li><strong>Precios o duales</strong> solo para hablar de congestión, con la salvedad de unidades — Fig. 11.</li>
<li><strong>Anexo de QA</strong> — Fig. 12. Un óptimo que no cierra energía no se publica.</li>
</ol>
<div class="warn">Estos resultados son un andamiaje de investigación. No son un modelo nacional validado, ni 147 barras
oficiales, ni las 18 subáreas de UPME, ni un pronóstico 2030. El solar de Santander se inyecta en Bogotá porque así lo
define la topología legado; está documentado a propósito.</div>

<footer>
Atlas generado offline a partir de <code>results/*/summary.json</code>, series horarias y Grid2Poster.
Objetivos y residuos copiados de las corridas verificadas. No hay datos inventados ni ERA5 real en estos cuatro ejemplos.
</footer>
</main>
</body>
</html>
"""
    dest = OUT / "informe.html"
    dest.write_text(html, encoding="utf-8")
    return dest


def main():
    paths = {
        "obj": fig_objective_cards(),
        "mix": fig_energy_mix(),
        "disp": fig_dispatch_compare(),
        "nino": fig_drought_story(),
        "xm": fig_xm_gap(),
        "net": fig_network(),
        "inv": fig_investment(),
        "px": fig_prices_heatmap(),
        "qa": fig_qa(),
    }
    html = write_html(paths)
    print("Wrote", html)
    for k, p in paths.items():
        print(k, p.stat().st_size)


if __name__ == "__main__":
    main()
