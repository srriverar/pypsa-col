"""PyPSA-col — Streamlit dashboard with a faithful PyPSA-CL GUI as tab 1.

Runs PyPSA + HiGHS in the same process (unlike Netlify). Deploy:

    streamlit run app.py
    # or push this repo and set Streamlit Cloud main file = app.py

Tab 1 clones src/GUI.py / the browser GUI: presets C1–C3 / U1–U3, epoch queue,
six locked selectors, constraints, solver, sequential/parallel run_config, then
``gui_core.execute_run`` (levers + optimize + osm-interactive figures).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
os.environ.setdefault("MPLBACKEND", "Agg")

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from pypsa_col.gui_core import (
    ALL_GLOBAL_NAMES,
    BASE_COLORS,
    NETWORKS,
    PRESET_NAMES,
    SCENARIO_MAP,
    SCENARIO_NAMES,
    epoch_name_for,
    execute_run,
    flatten_user_data,
    suggested_end_date,
)
from pypsa_col.plotting import NICE_NAME, STACK_ORDER, WORKSHOP_COLORS

NAVY = BASE_COLORS["fondo_azul_oscuro"]
CYAN = BASE_COLORS["cyan"]
ORANGE = BASE_COLORS["orange"]
MINT = BASE_COLORS["mint"]
SBG = BASE_COLORS["section_bg"]
INK = "#1b2a41"
PAPER = "#f4f1ea"
CARD = "#ffffff"

# XM/dashboard sheets are a fixed extract, not "last month".
DATA_WINDOW_START = "2024-01-01 00:00"
DATA_WINDOW_END = "2024-01-02 23:00"
XM_BUNDLE_START = "2023-12-31"
XM_BUNDLE_END = "2024-01-02"
DATA_TZ = "America/Bogota"

st.set_page_config(
    page_title="PyPSA-col — SIN Colombia",
    page_icon="🇨🇴",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _css() -> None:
    st.markdown(
        f"""
<style>
.stApp {{ background: {PAPER}; color: {INK}; }}
section[data-testid="stSidebar"] {{ background: {CARD}; }}
h1, h2, h3 {{ color: {INK} !important; }}
p, li, label, span, div {{ color: inherit; }}
[data-testid="stMarkdown"] p, [data-testid="stMarkdown"] li {{ color: {INK}; }}
[data-testid="stCaption"] {{ color: #3d4f63 !important; }}
[data-testid="stWidgetLabel"] p {{ color: {INK} !important; font-weight: 600; }}
div[data-testid="stMetricValue"] {{ color: #8a3b0f; }}
div[data-testid="stMetricLabel"] {{ color: #3d4f63; }}
.legend-box {{
  background: {CARD}; border: 1px solid #d9d2c5; border-left: 5px solid #b85716;
  padding: 10px 14px; color: {INK}; font-size: 0.95rem; line-height: 1.5;
}}
.date-box {{
  background: #fff8e8; border: 1px solid #e0c48a; border-left: 5px solid #b85716;
  padding: 10px 14px; color: {INK}; font-size: 0.95rem; line-height: 1.45;
  margin: 0 0 12px 0;
}}
</style>
""",
        unsafe_allow_html=True,
    )


def _data_window_banner(meta: dict | None = None) -> None:
    meta = meta or {}
    start = meta.get("start") or DATA_WINDOW_START
    end = meta.get("end") or DATA_WINDOW_END
    source = meta.get("source") or "extracto empaquetado"
    live = "live" in str(source).lower() or "SINERGOX" in str(source)
    title = (
        "Ventana de datos — último mes cerrado (D-1), como dashboard-sin-nodal"
        if live
        else "Ventana de datos — extracto de respaldo (no es el mes calendario actual)"
    )
    st.markdown(
        f"""
<div class="date-box">
<b>{title}</b><br>
Periodo: <b>{start} → {end}</b> ({DATA_TZ}). Convención XM: últimos 30 días hasta <b>ayer (D-1)</b>,
no “hoy” (la API publica el día en curso incompleto).<br>
Fuente: {source}.
La pestaña GUI (PyPSA-COL) usa la red PyPSA ya resuelta; estas hojas leen XM.
</div>
""",
        unsafe_allow_html=True,
    )


def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("epochs", [])
    ss.setdefault("scenarios", [])
    ss.setdefault("locked", False)
    ss.setdefault("global_scenario", PRESET_NAMES[0])
    ss.setdefault("custom_name", "")
    ss.setdefault("start_date", date(2026, 1, 1))
    ss.setdefault("rep_years", 2)
    ss.setdefault("rep_months", 6)
    ss.setdefault("rep_days", 1)
    ss.setdefault("epoch_name", epoch_name_for(0))
    ss.setdefault("last_outdir", None)
    ss.setdefault("last_error", None)
    ss.setdefault("run_log", "")
    vals = SCENARIO_MAP[PRESET_NAMES[0]]
    ss.setdefault("demand_scenario", vals["demand"])
    ss.setdefault("climate_scenario", vals["climate"])
    ss.setdefault("hydrology_scenario", vals["hydrology"])
    ss.setdefault("generation_investment_cost_scenario", vals["generation_investment_cost"])
    ss.setdefault("storage_investment_cost_scenario", vals["storage_investment_cost"])
    ss.setdefault("fuel_price_scenario", vals["fuel_price"])


def _apply_preset(name: str) -> None:
    if name == "Otro":
        return
    vals = SCENARIO_MAP[name]
    st.session_state.demand_scenario = vals["demand"]
    st.session_state.climate_scenario = vals["climate"]
    st.session_state.hydrology_scenario = vals["hydrology"]
    st.session_state.generation_investment_cost_scenario = vals["generation_investment_cost"]
    st.session_state.storage_investment_cost_scenario = vals["storage_investment_cost"]
    st.session_state.fuel_price_scenario = vals["fuel_price"]


def _settings_from_widgets() -> dict:
    gs = st.session_state.global_scenario
    label = (st.session_state.custom_name.strip() or "Otro") if gs == "Otro" else gs
    return {
        "global_scenario": label,
        "demand_scenario": st.session_state.demand_scenario,
        "climate_scenario": st.session_state.climate_scenario,
        "hydrology_scenario": st.session_state.hydrology_scenario,
        "generation_investment_cost_scenario": st.session_state.generation_investment_cost_scenario,
        "storage_investment_cost_scenario": st.session_state.storage_investment_cost_scenario,
        "fuel_price_scenario": st.session_state.fuel_price_scenario,
        "network": st.session_state.network_key,
        "solver_name": st.session_state.solver_name,
        "solver_threads": int(st.session_state.solver_threads),
        "solver_mip_gap": float(st.session_state.mip_gap),
        "linearized_unit_commitment": bool(st.session_state.lin_uc),
        "constraint_max_emissions": False,
        "max_emissions_MtCO2_year": 0.0,
        "constraint_max_load_lost": bool(st.session_state.cb_load_lost),
        "max_load_lost_GWh_year": float(st.session_state.max_load_lost) / 1000.0,
        "constraint_discrete_transmission_expansion": bool(st.session_state.cb_discrete_tx),
        "constraint_fnce": bool(st.session_state.cb_fnce),
        "fnce_pct": float(st.session_state.fnce_pct),
        "coal_phase_out": bool(st.session_state.cb_coal),
    }


def _add_epoch() -> None:
    name = st.session_state.epoch_name.strip()
    if not name:
        st.session_state.last_error = "Por favor ingrese un nombre para la época."
        return
    if st.session_state.global_scenario == "Otro" and not st.session_state.custom_name.strip():
        st.session_state.last_error = 'Debe ingresar un nombre para el escenario "Otro".'
        return
    epochs = st.session_state.epochs
    if not epochs:
        start = st.session_state.start_date
    else:
        prev = datetime.strptime(epochs[-1]["end_date"], "%Y-%m-%d").date()
        start = prev + timedelta(days=1)
        st.session_state.start_date = start
    rep_y = int(st.session_state.rep_years)
    end_s = suggested_end_date(str(start), rep_y)
    ep = {
        "name": name,
        "start_date": start.isoformat() if hasattr(start, "isoformat") else str(start)[:10],
        "end_date": end_s,
        "representative_years": rep_y,
        "representative_months": int(st.session_state.rep_months),
        "representative_days": int(st.session_state.rep_days),
        **_settings_from_widgets(),
    }
    epochs.append(ep)
    st.session_state.locked = True
    nxt = datetime.strptime(end_s, "%Y-%m-%d").date() + timedelta(days=1)
    st.session_state.start_date = nxt
    st.session_state.rep_years = 5
    st.session_state.rep_months = 6
    st.session_state.rep_days = 1
    st.session_state.epoch_name = epoch_name_for(len(epochs))
    st.session_state.last_error = None


def _remove_epoch() -> None:
    if not st.session_state.epochs:
        st.session_state.last_error = "Seleccione una época para eliminar."
        return
    idx = int(st.session_state.get("epoch_pick", 0))
    if 0 <= idx < len(st.session_state.epochs):
        st.session_state.epochs.pop(idx)
    st.session_state.epoch_name = epoch_name_for(len(st.session_state.epochs))
    if not st.session_state.epochs:
        st.session_state.locked = False
        st.session_state.start_date = date(2026, 1, 1)
    st.session_state.last_error = None


def _add_scenario() -> bool:
    if not st.session_state.epochs:
        st.session_state.last_error = (
            "Debe añadir al menos una época antes de agregar el escenario a la cola."
        )
        return False
    label = st.session_state.epochs[0]["global_scenario"]
    if label in [s["global_scenario"] for s in st.session_state.scenarios]:
        st.session_state.last_error = (
            f'Ya hay un escenario "{label}" en la cola. '
            'Para agregar una variante use "Otro" con un nombre distinto.'
        )
        return False
    st.session_state.scenarios.append(
        {"global_scenario": label, "epochs": [dict(e) for e in st.session_state.epochs]}
    )
    st.session_state.epochs = []
    st.session_state.locked = False
    st.session_state.custom_name = ""
    st.session_state.start_date = date(2026, 1, 1)
    st.session_state.rep_years = 2
    st.session_state.rep_months = 6
    st.session_state.rep_days = 1
    st.session_state.epoch_name = epoch_name_for(0)
    st.session_state.last_error = None
    return True


def _remove_scenario() -> None:
    if not st.session_state.scenarios:
        st.session_state.last_error = "Seleccione un escenario para eliminar de la cola."
        return
    idx = int(st.session_state.get("scenario_pick", 0))
    if 0 <= idx < len(st.session_state.scenarios):
        st.session_state.scenarios.pop(idx)
    st.session_state.last_error = None


def _run_all() -> None:
    if st.session_state.epochs:
        if not _add_scenario():
            return
    if not st.session_state.scenarios:
        st.session_state.last_error = (
            "Debe agregar al menos un escenario (con al menos una época) antes de ejecutar."
        )
        return
    try:
        workers = max(1, int(st.session_state.max_workers))
        ram = float(st.session_state.ram_limit)
        if not (10 <= ram <= 100):
            raise ValueError
    except ValueError:
        st.session_state.last_error = (
            "Revise la configuración de ejecución: Max parallel ≥ 1 y RAM entre 10 y 100."
        )
        return
    run_config = {
        "execution_mode": "parallel" if st.session_state.exec_mode == "Paralelo" else "sequential",
        "max_parallel_scenarios": workers,
        "ram_limit_pct": ram,
    }
    user_data = flatten_user_data(st.session_state.scenarios, run_config)
    try:
        outdir = execute_run(ROOT, user_data)
        st.session_state.last_outdir = str(outdir)
        st.session_state.last_error = None
        st.session_state.run_log = f"OK · {outdir}"
    except Exception as exc:  # noqa: BLE001
        st.session_state.last_error = str(exc)
        st.session_state.run_log = f"ERROR · {exc}"


def _figure_dir() -> Path | None:
    if st.session_state.last_outdir:
        p = Path(st.session_state.last_outdir)
        dirs = sorted(p.glob("s*_e*"))
        if dirs:
            return dirs[-1]
    bundled = ROOT / "data" / "streamlit" / "figures"
    if bundled.exists():
        return bundled
    osm = ROOT / "results" / "osm-interactive"
    return osm if osm.exists() else None


def _show_png(path: Path, caption: str) -> None:
    if path.exists():
        st.image(str(path), caption=caption, use_container_width=True)
    else:
        st.info(f"Aún no hay {path.name}. Corra un escenario en la GUI.")


def _show_html(path: Path, height: int = 540) -> None:
    if not path.exists():
        st.info(f"Aún no hay {path.name}.")
        return
    html = path.read_text(encoding="utf-8", errors="ignore")
    if len(html) > 4_500_000:
        st.caption(f"{path.name} es grande ({len(html)//1024} kB); se incrusta igual.")
    components.html(html, height=height, scrolling=True)


def _legend() -> None:
    st.markdown(
        """
<div class="legend-box">
<b>Cómo leer los círculos</b><br>
<span style="color:#f4a261">● Naranja</span> = <b>demanda</b> (DemaReal nacional partida entre barras). Todo bus tiene uno.<br>
<span style="color:#2a9d8f">● Verde-azulado</span> = <b>generación</b> (CEN de plantas XM colgadas a esa barra). Solo aparece donde hay planta.<br>
El <b>tamaño es proporcional al MW</b>. Interactivos:
<code>explore_load</code> = solo demanda;
<code>explore_capacity</code> = tartas por tecnología (colores workshop);
<code>explore_flow</code> = tamaño = generación, color de línea = carga %.<br>
Contorno geoBoundaries + San Andrés. Rojo = 500 kV, azul = 220/230 kV.
</div>
""",
        unsafe_allow_html=True,
    )


def tab_gui() -> None:
    st.markdown(
        "Interfaz al estilo **PyPSA-CL `src/GUI.py`** (PELP Chile), personalizada para el SIN. "
        "Los paquetes C1–C3 / U1–U3 **rellenan y bloquean** los seis selectores; "
        "**Otro** los libera. **Run all scenarios** llama a HiGHS de verdad."
    )
    if st.session_state.last_error:
        st.error(st.session_state.last_error)

    left, mid, right = st.columns([1.05, 1.15, 0.95], gap="medium")

    with left:
        st.subheader("Configuración temporal")
        st.text_input("Epoch name:", key="epoch_name")
        st.date_input("Start date", key="start_date")
        end_s = suggested_end_date(str(st.session_state.start_date), int(st.session_state.rep_years))
        st.caption(f"End date (se sincroniza con representative years): **{end_s}**")
        st.selectbox("Representative years", [1, 2, 3, 4, 5], key="rep_years")
        st.selectbox("Representative months", [1, 2, 3, 4, 6, 12], key="rep_months")
        st.selectbox("Representative days", [1, 4], key="rep_days")
        net_labels = {k: v["label"] for k, v in NETWORKS.items()}
        st.selectbox(
            "Red Colombia",
            list(NETWORKS),
            format_func=lambda k: net_labels[k],
            key="network_key",
        )
        st.caption("Added epochs:")
        if st.session_state.epochs:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "i": i + 1,
                            "name": e["name"],
                            "start": e["start_date"],
                            "end": e["end_date"],
                            "yrs": e["representative_years"],
                            "months": e["representative_months"],
                            "days": e["representative_days"],
                        }
                        for i, e in enumerate(st.session_state.epochs)
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
            st.selectbox(
                "Época seleccionada",
                list(range(len(st.session_state.epochs))),
                format_func=lambda i: st.session_state.epochs[i]["name"],
                key="epoch_pick",
            )
        else:
            st.caption("Ninguna época aún.")
        b1, b2 = st.columns(2)
        b1.button("Add Epoch", type="primary", on_click=_add_epoch)
        b2.button("Remove Selected", on_click=_remove_epoch)

        st.subheader("Restricciones adicionales")
        st.checkbox("Maximum load lost [MWh/year]", key="cb_load_lost")
        st.number_input("MWh/year:", min_value=0.0, value=2000.0, key="max_load_lost")
        st.checkbox("Discrete transmission expansion", key="cb_discrete_tx")
        st.checkbox("Meta FNCE (renovables no convencionales)", key="cb_fnce")
        st.number_input("FNCE %:", min_value=0.0, max_value=100.0, value=20.0, key="fnce_pct")
        st.checkbox("Cierre de carbón (phase-out UPME)", key="cb_coal")

        st.subheader("Configuración de optimización")
        st.selectbox("Solver name", ["highs", "cbc", "gurobi", "cplex"], key="solver_name")
        st.number_input("Threads", min_value=1, max_value=32, value=min(2, os.cpu_count() or 2), key="solver_threads")
        st.number_input("MIP gap", min_value=0.0, max_value=1.0, value=0.1, key="mip_gap")
        st.checkbox("Linearized unit commitment", value=True, key="lin_uc")

    with mid:
        st.subheader("Configuración de escenario")
        st.selectbox(
            "Global scenario:",
            ALL_GLOBAL_NAMES,
            key="global_scenario",
            disabled=st.session_state.locked,
            on_change=lambda: _apply_preset(st.session_state.global_scenario),
        )
        if st.session_state.locked:
            st.warning(
                "⚠ Locked after first epoch – add scenario to queue or remove all epochs to change"
            )
        if st.session_state.global_scenario == "Otro":
            st.text_input("Custom name:", key="custom_name")
        locked_sel = st.session_state.global_scenario != "Otro"
        st.selectbox("Demand scenario", SCENARIO_NAMES["demand"], key="demand_scenario", disabled=locked_sel)
        st.selectbox("Hydrology scenario", SCENARIO_NAMES["hydrology"], key="hydrology_scenario", disabled=locked_sel)
        st.selectbox("Climate scenario", SCENARIO_NAMES["climate"], key="climate_scenario", disabled=locked_sel)
        st.selectbox(
            "Generation investment cost",
            SCENARIO_NAMES["generation_investment_cost"],
            key="generation_investment_cost_scenario",
            disabled=locked_sel,
        )
        st.selectbox(
            "Storage investment cost",
            SCENARIO_NAMES["storage_investment_cost"],
            key="storage_investment_cost_scenario",
            disabled=locked_sel,
        )
        st.selectbox("Fuel price scenario", SCENARIO_NAMES["fuel_price"], key="fuel_price_scenario", disabled=locked_sel)

        st.subheader("Cola de escenarios a ejecutar")
        if st.session_state.scenarios:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "i": i + 1,
                            "global_scenario": s["global_scenario"],
                            "epochs": len(s["epochs"]),
                            "start": s["epochs"][0]["start_date"],
                            "end": s["epochs"][-1]["end_date"],
                        }
                        for i, s in enumerate(st.session_state.scenarios)
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
            st.selectbox(
                "Escenario seleccionado",
                list(range(len(st.session_state.scenarios))),
                format_func=lambda i: st.session_state.scenarios[i]["global_scenario"],
                key="scenario_pick",
            )
        else:
            st.caption("Cola vacía.")
        c1, c2 = st.columns(2)
        c1.button("Add scenario to queue", on_click=_add_scenario)
        c2.button("Remove scenario", on_click=_remove_scenario)

        st.subheader("Configuración de ejecución")
        st.selectbox("Execution mode", ["Secuencial", "Paralelo"], key="exec_mode")
        st.number_input("Max parallel scenarios", min_value=1, value=2, key="max_workers")
        st.number_input("RAM limit [% of total]", min_value=10.0, max_value=100.0, value=85.0, key="ram_limit")
        st.caption(
            "Paralelo: en Streamlit Cloud la corrida es secuencial dentro de esta sesión "
            "(un proceso). HiGHS corre aquí mismo. OSM 251 barras ~1 s de solve + figuras."
        )
        st.button("Run all scenarios", type="primary", on_click=_run_all)
        if st.session_state.run_log:
            st.success(st.session_state.run_log)

        js = None
        if st.session_state.scenarios or st.session_state.epochs:
            preview = list(st.session_state.scenarios)
            if st.session_state.epochs:
                preview = preview + [
                    {
                        "global_scenario": _settings_from_widgets()["global_scenario"],
                        "epochs": st.session_state.epochs,
                    }
                ]
            js = json.dumps(
                flatten_user_data(
                    preview,
                    {
                        "execution_mode": "sequential",
                        "max_parallel_scenarios": 1,
                        "ram_limit_pct": 85,
                    },
                ),
                ensure_ascii=False,
                indent=2,
            )
            st.download_button(
                "Descargar scenario.json (contrato PyPSA-CL)",
                js.encode("utf-8"),
                file_name="pypsa-col-scenario.json",
                mime="application/json",
            )

    with right:
        st.subheader("SIN Colombia")
        mapp = ROOT / "data" / "streamlit" / "figures" / "sin_network.png"
        if not mapp.exists():
            mapp = ROOT / "data" / "gui" / "sin_network.png"
        if mapp.exists():
            st.image(str(mapp), caption="naranja = demanda · verde = generación · 500 kV rojo / 220-230 azul")
        st.caption(
            "Equivale a `sen_network.png` de PyPSA-CL. Malla OSM 251 barras o 7 nodos dashboard-SIN."
        )

    # Figures from last HiGHS run
    st.divider()
    st.header("Figuras de la simulación (estilo osm-interactive)")
    _legend()
    figdir = _figure_dir()
    if figdir is None:
        st.info("Corra un escenario para materializar las figuras, o use los PNG empaquetados.")
        return
    st.caption(f"Fuente: `{figdir}`")
    st.subheader("0. Mapa de Colombia")
    _show_png(figdir / "colombia_map.png", "naranja = demanda, verde = generación")
    st.subheader("1. LMP sobre Colombia")
    _show_png(figdir / "lmp.png", "anillo = demanda, relleno = generación, color = LMP")
    st.subheader("2. Carga nodal — n.explore(bus_size=load)")
    _show_html(figdir / "explore_load.html")
    st.subheader("3. Capacidad por tecnología (tartas)")
    st.caption("Paleta workshop: Gas tomato, carbón dimgrey, hidro teal, solar gold, eólica royalblue.")
    _show_html(figdir / "explore_capacity.html")
    st.subheader("4. Flujos — line_flow + line_cmap=plasma")
    _show_html(figdir / "explore_flow.html")
    st.subheader("5. Despacho")
    _show_png(figdir / "dispatch.png", "colores workshop PyPSA Labs")


# Same public API as dashboard-sin-nodal (servapibi.xm.com.co), last closed month D-1.
_XM_API = "https://servapibi.xm.com.co"
_XM_FEEDS = (
    ("listado", "ListadoRecursos", "Sistema", "lists"),
    ("cen", "CapEfecNeta", "Recurso", "daily"),
    ("gene", "Gene", "Recurso", "hourly"),
    ("dema", "DemaReal", "Sistema", "hourly"),
    ("gene_sis", "Gene", "Sistema", "hourly"),
    ("precio", "PrecBolsNaci", "Sistema", "hourly"),
)


def _xm_closed_window(days: int = 30) -> tuple[str, str]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _xm_post(kind: str, metric: str, entity: str, start: str, end: str) -> dict:
    if kind == "lists":
        body = {"MetricId": metric, "Entity": entity}
        url = f"{_XM_API}/lists"
    else:
        body = {
            "MetricId": metric,
            "Entity": entity,
            "StartDate": start,
            "EndDate": end,
            "Filter": [],
        }
        url = f"{_XM_API}/{kind}"
    resp = requests.post(url, json=body, timeout=90)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict) or "Items" not in payload:
        raise RuntimeError(f"XM {metric}/{entity}: respuesta inesperada")
    return payload


def _xm_melt(payload: dict, metric: str, entity: str, kind: str) -> pd.DataFrame:
    rows = []
    for item in payload.get("Items") or []:
        day = item.get("Date")
        entities = (
            item.get("HourlyEntities")
            or item.get("DailyEntities")
            or item.get("ListEntities")
            or item.get("ListsEntities")
            or []
        )
        for ent in entities:
            values = ent.get("Values", ent)
            if not isinstance(values, dict):
                continue
            code = str(
                next(
                    (values[k] for k in ("code", "Code", "Name", "name") if k in values),
                    ent.get("Id", entity),
                )
            )
            common = {
                "metric": metric,
                "entity": entity,
                "entity_code": code,
                "unit": "",
                "timezone": "America/Bogota",
            }
            if kind == "hourly":
                stamp0 = pd.Timestamp(str(day)[:10])
                for hour in range(1, 25):
                    key = f"Hour{hour:02d}"
                    if key not in values:
                        continue
                    rows.append(
                        {
                            **common,
                            "timestamp": stamp0 + pd.Timedelta(hours=hour - 1),
                            "value": pd.to_numeric(values[key], errors="coerce"),
                        }
                    )
            elif kind == "lists":
                rows.append({**common, "as_of": day, **values})
            else:
                val = values.get("Value", values.get("value"))
                rows.append(
                    {
                        **common,
                        "timestamp": pd.Timestamp(str(day)[:10]),
                        "value": pd.to_numeric(val, errors="coerce"),
                    }
                )
    return pd.DataFrame(rows)


def _load_metric_folder(folder: Path) -> dict:
    out = {}
    mapping = {
        "listado": "ListadoRecursos__Sistema.csv",
        "cen": "CapEfecNeta__Recurso.csv",
        "gene": "Gene__Recurso.csv",
        "dema": "DemaReal__Sistema.csv",
        "gene_sis": "Gene__Sistema.csv",
        "precio": "PrecBolsNaci__Sistema.csv",
    }
    for key, name in mapping.items():
        path = folder / name
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype={"entity_code": str}, keep_default_na=False, na_values=[""])
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        out[key] = df
    return out


def _fetch_xm_last_month(dest: Path, days: int = 30) -> dict:
    """dashboard-sin-nodal convention: last `days` ending yesterday (D-1)."""
    start, end = _xm_closed_window(days)
    dest.mkdir(parents=True, exist_ok=True)
    notes = []
    saved = []
    for key, metric, entity, kind in _XM_FEEDS:
        try:
            payload = _xm_post(kind, metric, entity, start, end)
            df = _xm_melt(payload, metric, entity, kind)
            if df.empty:
                notes.append(f"{metric}/{entity}: vacío")
                continue
            df.to_csv(dest / f"{metric}__{entity}.csv", index=False)
            saved.append({"metric": metric, "entity": entity, "rows": int(len(df))})
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{metric}/{entity}: {exc}")
    meta = {
        "start": start,
        "end": end,
        "timezone": "America/Bogota",
        "days": days,
        "source": "XM SINERGOX live (servapibi.xm.com.co, D-1, dashboard-sin-nodal)",
        "datasets": saved,
        "notes": notes,
    }
    (dest / "window.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


@st.cache_data(ttl=6 * 3600, show_spinner="Descargando último mes XM (ventana D-1, 30 días)…")
def _xm_dashboard(nonce: int = 0):
    """Live last-month XM like dashboard-sin-nodal; fallback to bundled extract."""
    live_dir = ROOT / "data" / "streamlit" / "xm_last_month"
    bundle = ROOT / "data" / "streamlit" / "xm"
    meta: dict = {}
    need = nonce > 0 or not (live_dir / "DemaReal__Sistema.csv").exists()
    if need:
        try:
            meta = _fetch_xm_last_month(live_dir, days=30)
        except Exception as exc:  # noqa: BLE001
            meta = {
                "source": "fallback bundle ene-2024",
                "error": str(exc),
                "start": XM_BUNDLE_START,
                "end": XM_BUNDLE_END,
            }
    elif (live_dir / "window.json").exists():
        meta = json.loads((live_dir / "window.json").read_text(encoding="utf-8"))
    folder = live_dir if (live_dir / "DemaReal__Sistema.csv").exists() else bundle
    if folder == bundle:
        meta.setdefault("source", "extracto empaquetado 2023-12-31 → 2024-01-02")
        meta.setdefault("start", XM_BUNDLE_START)
        meta.setdefault("end", XM_BUNDLE_END)
    tables = _load_metric_folder(folder)
    if "dema" in tables and not tables["dema"].empty:
        idx = pd.DatetimeIndex(
            sorted(pd.to_datetime(tables["dema"]["timestamp"]).unique()), name="snapshot"
        )
    else:
        idx = pd.DatetimeIndex([], name="snapshot")
    meta["folder"] = str(folder)
    meta["n_hours"] = int(len(idx))
    return tables, idx, meta


def _dashboard_payload():
    return _xm_dashboard(nonce=int(st.session_state.get("xm_nonce", 0)))


def tab_generacion() -> None:
    st.markdown("Pestaña **⚡ Generación** al estilo dashboard-sin-nodal: catálogo XM, mix y CEN.")
    c_a, c_b = st.columns([3, 1])
    with c_b:
        if st.button("Actualizar último mes XM", key="btn_xm_gen"):
            st.session_state.xm_nonce = int(st.session_state.get("xm_nonce", 0)) + 1
            _xm_dashboard.clear()
            st.rerun()
    try:
        tables, idx, meta = _dashboard_payload()
        _data_window_banner(meta)
        from pypsa_col.dashboard_sin import assemble_plants

        plants = assemble_plants(tables, idx if len(idx) else tables["cen"].index[:1])
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudieron leer las tablas XM: {exc}")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Plantas XM", f"{len(plants):,}")
    c2.metric("CEN", f"{plants['cen_mw'].sum():,.0f} MW")
    c3.metric("Energía ventana", f"{plants['gene_mwh'].sum()/1000:,.1f} GWh")
    c4.metric("Tecnologías", plants["carrier"].nunique())
    mix = plants.groupby("carrier")["cen_mw"].sum().sort_values(ascending=False)
    st.bar_chart(mix.rename(index=lambda x: NICE_NAME.get(x, x)))
    zona = st.multiselect("Filtrar zona", sorted(plants["zona"].dropna().unique()), default=[])
    car = st.multiselect("Filtrar tecnología", sorted(plants["carrier"].dropna().unique()), default=[])
    view = plants
    if zona:
        view = view[view["zona"].isin(zona)]
    if car:
        view = view[view["carrier"].isin(car)]
    show_cols = [c for c in ["Nombre_Planta", "zona", "carrier", "cen_mw", "gene_mwh", "cf"] if c in view.columns]
    if not show_cols:
        show_cols = list(view.columns)[:8]
    st.dataframe(view[show_cols], use_container_width=True, hide_index=True)


def tab_demanda() -> None:
    st.markdown("Pestaña **📈 Demanda**: DemaReal nacional (XM) partida con `PESO_DEMANDA` del dashboard.")
    try:
        tables, idx, meta = _dashboard_payload()
        _data_window_banner(meta)
        from pypsa_col.dashboard_sin import PESO_DEMANDA, demand_by_zone

        dem = demand_by_zone(tables["dema"], idx)
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        return
    st.line_chart(dem)
    st.caption("MW por subregión declarada (no son zonas oficiales XM/UPME).")
    st.bar_chart(pd.Series(PESO_DEMANDA, name="peso"))
    tot = dem.sum().sum() / 1000.0
    st.metric("Energía ventana", f"{tot:,.2f} GWh")
    st.dataframe(dem, use_container_width=True)


def tab_explorador() -> None:
    st.markdown("Pestaña **🏭 Explorador de planta** (dashboard-sin-nodal).")
    try:
        tables, idx, meta = _dashboard_payload()
        _data_window_banner(meta)
        from pypsa_col.dashboard_sin import assemble_plants

        plants = assemble_plants(tables, idx)
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        return
    names = plants["Nombre_Planta"].astype(str).tolist() if "Nombre_Planta" in plants.columns else plants.index.astype(str).tolist()
    pick = st.selectbox("Planta", names)
    row = plants[plants["Nombre_Planta"].astype(str) == pick].iloc[0] if "Nombre_Planta" in plants.columns else plants.iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("CEN MW", f"{float(row.get('cen_mw', 0)):.1f}")
    c2.metric("Energía MWh", f"{float(row.get('gene_mwh', 0)):.0f}")
    c3.metric("CF", f"{float(row.get('cf', 0)):.2f}")
    st.json(
        {
            k: (None if pd.isna(v) else (v.item() if hasattr(v, "item") else v))
            for k, v in row.items()
            if k in {"zona", "carrier", "Codigo_Planta", "cen_mw", "gene_mwh", "cf"}
        }
    )
    gene = tables["gene"].copy()
    code = str(row.get("Codigo_Planta", ""))
    gene["entity_code"] = gene["entity_code"].astype(str)
    sub = gene[gene["entity_code"] == code]
    if sub.empty:
        st.info("Sin serie Gene para este recurso en la ventana.")
        return
    sub = sub.copy()
    sub["mw"] = sub["value"] / 1000.0
    st.line_chart(sub.set_index("timestamp")["mw"])


def tab_red() -> None:
    st.markdown("**Grid2Poster** (OSM Colombia, adaptación colombiacongestionV2) y topología 7 nodos.")
    poster = ROOT / "data" / "streamlit" / "figures" / "grid2poster_colombia.png"
    alt = ROOT / "results" / "demo" / "grid2poster.png"
    shown = poster if poster.exists() else alt
    if shown.exists():
        st.image(
            str(shown),
            caption="Grid2Poster · Colombia · tema electric_midnight · geometría OSM (ODbL) · no es un diagrama unifilar oficial.",
            use_container_width=True,
        )
    else:
        st.info("No hay PNG de Grid2Poster. Pulse renderizar si el source está clonado.")
    if st.button("Renderizar Grid2Poster ahora"):
        try:
            from pypsa_col.io import load_config
            from pypsa_col.poster import render_grid2poster

            cfg = load_config(ROOT / "config" / "demo.yaml")
            dest = ROOT / "data" / "streamlit" / "figures"
            dest.mkdir(parents=True, exist_ok=True)
            render_grid2poster(ROOT, cfg, dest)
            produced = dest / "grid2poster.png"
            if produced.exists():
                produced.replace(poster)
            st.success("Grid2Poster actualizado.")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.warning(f"No se pudo renderizar (¿falta external/colombiacongestionV2?): {exc}")
    st.divider()
    from pypsa_col.dashboard_sin import RAMAS, ZONAS

    z = pd.DataFrame(
        [{"zona": k, "label": v["label"], "lon": v["x"], "lat": v["y"]} for k, v in ZONAS.items()]
    )
    st.subheader("7 subregiones dashboard-SIN (declaradas, no oficiales)")
    st.dataframe(z, hide_index=True, use_container_width=True)
    r = pd.DataFrame(RAMAS, columns=["from", "to", "NTC_MW", "nombre"])
    st.dataframe(r, hide_index=True, use_container_width=True)
    st.map(z.rename(columns={"lat": "lat", "lon": "lon"}), latitude="lat", longitude="lon", size=200)
    st.caption("Advertencia: subregiones y NTC son supuestos del tablero, no un registro PARATEC/UPME.")
    m = ROOT / "data" / "streamlit" / "figures" / "sin_network.png"
    if m.exists():
        st.image(str(m), caption="Malla OSM PyPSA (naranja demanda / verde generación)")


def tab_resultados() -> None:
    st.markdown("CSV estilo PyPSA-CL (`generation_results`, `system_costs`, …) de la última corrida HiGHS.")
    st.caption("Esta hoja no es XM del último mes: son salidas del solver de la pestaña GUI.")
    out = st.session_state.last_outdir
    if not out:
        st.info("Todavía no hay corrida en esta sesión. Use la pestaña GUI → Run all scenarios.")
        bundled = ROOT / "results" / "osm-interactive"
        if (bundled / "summary.json").exists():
            st.json(json.loads((bundled / "summary.json").read_text()))
        return
    p = Path(out)
    st.code(str(p))
    costs = p / "system_costs.csv"
    if costs.exists():
        st.dataframe(pd.read_csv(costs), use_container_width=True)
    for ep in sorted(p.glob("s*_e*")):
        st.subheader(ep.name)
        for csv in [
            "system_costs.csv",
            "installed_capacity.csv",
            "energy_balance_gwh.csv",
            "run_metadata_log.csv",
            "nodal_marginal_prices.csv",
        ]:
            f = ep / csv
            if f.exists():
                with st.expander(csv):
                    st.dataframe(pd.read_csv(f), use_container_width=True)
        gen = ep / "generation_results.csv"
        if gen.exists():
            st.download_button(
                f"Descargar {ep.name}/generation_results.csv",
                gen.read_bytes(),
                file_name=f"{ep.name}_generation_results.csv",
                mime="text/csv",
                key=f"dl-{ep.name}",
            )


def tab_metodo() -> None:
    st.markdown(
        """
**PyPSA-col** reutiliza [colombiacongestionV2](https://github.com/srriverar/colombiacongestionV2)
y las reglas declaradas de [dashboard-sin-nodal](https://github.com/srriverar/dashboard-sin-nodal).
La GUI sigue [PyPSA-CL GUI.py](https://github.com/paredes-vergara/PyPSA-CL/blob/main/src/GUI.py).

| Palanca | Efecto en el LP |
| --- | --- |
| Demanda Baja/Media/Alta | escala `loads_t.p_set` |
| Hidrología seca / media / húmeda | escala `p_max_pu` hidro |
| Niño / Niña | ajusta hidrología |
| Precio combustible Alto/Medio/Bajo | escala `marginal_cost` térmico |
| Cierre de carbón | `p_nom` carbón = 0 |
| Capex generación/almacenamiento | se registra en el JSON (GEP completo tipo PELP aún no) |

Solver por defecto: **HiGHS**. Las épocas usan los snapshots ya contenidos en `network.nc`
como periodo representativo.

```bash
streamlit run app.py
python src/main.py --scenario-json pypsa-col-scenario.json
PYTHONPATH=src python -m pypsa_col gui
snakemake -s workflow/Snakefile.osm.smk --cores 2
```
"""
    )
    from matplotlib.colors import to_hex

    palette = pd.DataFrame(
        [
            {
                "carrier": NICE_NAME.get(k, k),
                "workshop": v,
                "hex": to_hex(v),
            }
            for k, v in WORKSHOP_COLORS.items()
            if k in STACK_ORDER
        ]
    )
    st.dataframe(palette, hide_index=True, use_container_width=True)
    st.color_picker("Workshop Gas (hex)", to_hex(WORKSHOP_COLORS["Gas"]), disabled=True)


def main() -> None:
    _css()
    _init_state()
    logo = ROOT / "data" / "streamlit" / "figures" / "logo.png"
    cols = st.columns([1, 4])
    with cols[0]:
        if logo.exists():
            st.image(str(logo), use_container_width=True)
    with cols[1]:
        st.title("PyPSA-col — Long-term Power Systems Planning in Colombia")
        st.caption(
            "SIN · XM DemaReal / CEN · malla OSM · HiGHS  ·  GUI fiel a PyPSA-CL  ·  "
            "esta app **sí corre el solver** (no es el sitio estático de Netlify).  "
            "Hojas XM (Generación, Demanda, Explorador): **último mes cerrado D-1** "
            "(como dashboard-sin-nodal). Red SIN: Grid2Poster OSM."
        )

    t_gui, t_gen, t_dem, t_exp, t_red, t_res, t_doc = st.tabs(
        [
            "🎛️ GUI (PyPSA-COL)",
            "⚡ Generación",
            "📈 Demanda",
            "🏭 Explorador de planta",
            "🔌 Red SIN",
            "📂 Resultados HiGHS",
            "ℹ️ Método",
        ]
    )
    with t_gui:
        tab_gui()
    with t_gen:
        tab_generacion()
    with t_dem:
        tab_demanda()
    with t_exp:
        tab_explorador()
    with t_red:
        tab_red()
    with t_res:
        tab_resultados()
    with t_doc:
        tab_metodo()


if __name__ == "__main__":
    main()
