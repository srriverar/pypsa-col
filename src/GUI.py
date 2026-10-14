"""Graphical configuration interface for the PyPSA-col expansion / dispatch model.

Desktop twin of PyPSA-CL ``src/GUI.py`` (Paredes-Vergara, PELP Chile), customised
for Colombia's SIN. Preset packages C1–C3 / U1–U3 auto-fill and lock the six
component selectors; *Otro* unlocks free configuration.

``run_gui`` returns a dictionary with a ``scenarios`` list and a flattened
``epochs`` list (same contract as PyPSA-CL). In this sandbox use the web GUI:

    PYTHONPATH=src python -m pypsa_col gui
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pypsa_col.gui_core import (  # noqa: E402
    ALL_GLOBAL_NAMES,
    BASE_COLORS,
    PRESET_NAMES,
    SCENARIO_MAP,
    SCENARIO_NAMES,
    epoch_name_for,
    flatten_user_data,
    suggested_end_date,
)

try:
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover
    Image = ImageTk = None

try:
    from tkcalendar import DateEntry
except Exception:  # pragma: no cover
    DateEntry = None


class Epoch:
    def __init__(self, name, start_date, end_date, rep_years, rep_months, rep_days, settings=None):
        self.name = name
        self.start_date = start_date
        self.end_date = end_date
        self.rep_years = rep_years
        self.rep_months = rep_months
        self.rep_days = rep_days
        self.settings = settings or {}


def run_gui():
    THEME = {
        "fondo_principal": "fondo_azul_oscuro",
        "titulo": "cyan",
        "texto_principal": "white",
        "campo_activo": "mint",
        "boton_principal": "orange",
        "boton_hover": "green",
    }

    def color(role):
        return BASE_COLORS[THEME[role]]

    SBG = BASE_COLORS["section_bg"]
    WHITE = BASE_COLORS["white"]
    CYAN = BASE_COLORS["cyan"]
    MINT = BASE_COLORS["mint"]
    DARK = BASE_COLORS["fondo_azul_oscuro"]
    ORANGE = BASE_COLORS["orange"]

    result = {}
    epochs = []
    scenarios = []

    def get_current_epoch_settings():
        gs = global_scenario_var.get()
        global_label = (
            (custom_scenario_name_var.get().strip() or "Otro") if gs == "Otro" else gs
        )
        return {
            "global_scenario": global_label,
            "demand_scenario": demand_scenario.get(),
            "climate_scenario": climate_scenario.get(),
            "hydrology_scenario": hydrology_scenario.get(),
            "generation_investment_cost_scenario": generation_investment_cost_scenario.get(),
            "storage_investment_cost_scenario": storage_investment_cost_scenario.get(),
            "fuel_price_scenario": fuel_price_scenario.get(),
            "network": network_var.get(),
            "solver_name": solver_name.get(),
            "solver_threads": int(entry_threads.get()),
            "solver_mip_gap": float(entry_mip_gap.get()),
            "linearized_unit_commitment": linearized_uc_var.get(),
            "constraint_max_emissions": False,
            "max_emissions_MtCO2_year": 0.0,
            "constraint_max_load_lost": cb_load_lost.get(),
            "max_load_lost_GWh_year": float(entry_load_lost.get()),
            "constraint_discrete_transmission_expansion": cb_discrete_transmission.get(),
            "constraint_fnce": cb_fnce.get(),
            "fnce_pct": float(entry_fnce.get()),
            "coal_phase_out": cb_coal.get(),
        }

    def build_epoch_dicts():
        return [
            {
                "name": ep.name,
                "start_date": ep.start_date.strftime("%Y-%m-%d")
                if hasattr(ep.start_date, "strftime")
                else str(ep.start_date),
                "end_date": ep.end_date.strftime("%Y-%m-%d")
                if hasattr(ep.end_date, "strftime")
                else str(ep.end_date),
                "representative_years": ep.rep_years,
                "representative_months": ep.rep_months,
                "representative_days": ep.rep_days,
                **ep.settings,
            }
            for ep in epochs
        ]

    def add_scenario_to_queue():
        if not epochs:
            messagebox.showerror(
                "Error", "Debe añadir al menos una época antes de agregar el escenario a la cola."
            )
            return False
        label = epochs[0].settings.get("global_scenario", "")
        if label in [s["global_scenario"] for s in scenarios]:
            messagebox.showerror(
                "Error",
                f'Ya hay un escenario "{label}" en la cola.\n'
                'Para agregar una variante use "Otro" con un nombre distinto.',
            )
            return False
        scenarios.append({"global_scenario": label, "epochs": build_epoch_dicts()})
        epochs.clear()
        update_epoch_listbox()
        update_scenario_listbox()
        global_scenario_combo.config(state="readonly")
        _update_global_lock_label(locked=False)
        custom_scenario_name_var.set("")
        _set_date(cal_inicio, "2026-01-01")
        years_var.set("2")
        months_var.set("6")
        days_var.set("1")
        try:
            sync_end_date_with_years()
        except Exception:
            pass
        suggest_epoch_name()
        return True

    def confirmar():
        if epochs and not add_scenario_to_queue():
            return
        if not scenarios:
            messagebox.showerror(
                "Error", "Debe agregar al menos un escenario (con al menos una época) antes de ejecutar."
            )
            return
        try:
            _max_workers = max(1, int(entry_max_workers.get()))
            _ram_limit = float(entry_ram_limit.get())
            if not (10 <= _ram_limit <= 100):
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Error",
                "Revise la configuracion de ejecucion:\n"
                "- Max parallel scenarios debe ser un entero >= 1\n"
                "- RAM limit debe ser un porcentaje entre 10 y 100",
            )
            return
        run_config = {
            "execution_mode": "parallel" if execution_mode_var.get() == "Paralelo" else "sequential",
            "max_parallel_scenarios": _max_workers,
            "ram_limit_pct": _ram_limit,
        }
        result.update(flatten_user_data(scenarios, run_config))
        root.destroy()

    root = tk.Tk()
    root.title("PyPSA-col - a tool for Long-term Power Systems Planning in Colombia")
    root.configure(bg=color("fondo_principal"))
    root.geometry("1350x900")
    root.resizable(True, True)

    outer_frame = tk.Frame(root, bg=color("fondo_principal"))
    outer_frame.pack(fill="both", expand=True)
    canvas = tk.Canvas(outer_frame, bg=color("fondo_principal"), highlightthickness=0)
    vscrollbar = ttk.Scrollbar(outer_frame, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vscrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    vscrollbar.grid(row=0, column=1, sticky="ns")
    outer_frame.rowconfigure(0, weight=1)
    outer_frame.columnconfigure(0, weight=1)
    container = tk.Frame(canvas, bg=color("fondo_principal"))
    canvas.create_window((0, 0), window=container, anchor="nw")
    container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    inner = tk.Frame(container, bg=color("fondo_principal"))
    inner.pack(padx=20, pady=10)

    style = ttk.Style(root)
    style.theme_use("default")
    style.configure(
        "TLabel",
        background=color("fondo_principal"),
        foreground=color("texto_principal"),
        font=("Verdana", 10),
    )
    style.configure(
        "TCombobox",
        fieldbackground=MINT,
        background=MINT,
        foreground=BASE_COLORS["black"],
        font=("Verdana", 9),
    )
    style.configure(
        "Section.TLabelframe",
        background=SBG,
        foreground=CYAN,
        font=("Verdana", 9, "bold"),
        relief="groove",
        bordercolor=BASE_COLORS["section_border"],
    )
    style.configure(
        "Section.TLabelframe.Label",
        background=SBG,
        foreground=CYAN,
        font=("Verdana", 9, "bold"),
    )

    _src_dir = os.path.dirname(os.path.abspath(__file__))
    _data_dir = os.path.join(os.path.abspath(os.path.join(_src_dir, os.pardir)), "data", "gui")

    header_frame = tk.Frame(inner, bg=color("fondo_principal"))
    header_frame.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 4))
    header_inner = tk.Frame(header_frame, bg=color("fondo_principal"))
    header_inner.grid(row=0, column=0)

    _logo_path = os.path.join(_data_dir, "logo_pypsa_col.png")
    if Image and os.path.exists(_logo_path):
        try:
            _logo_raw = Image.open(_logo_path)
            _logo_w = 220
            _logo_h = int(_logo_w * _logo_raw.height / max(_logo_raw.width, 1))
            logo_photo = ImageTk.PhotoImage(_logo_raw.resize((_logo_w, _logo_h), Image.LANCZOS))
            logo_label = tk.Label(header_inner, image=logo_photo, bg=color("fondo_principal"))
            logo_label.image = logo_photo
            logo_label.grid(row=0, column=0, padx=(0, 24), sticky="w")
        except Exception as e:
            print(f"No se pudo cargar el logo: {e}")

    title = tk.Label(
        header_inner,
        text="PyPSA-col - a tool for Long-term Power Systems Planning in Colombia",
        bg=color("fondo_principal"),
        fg=color("titulo"),
        font=("Verdana", 15, "bold"),
    )
    title.grid(row=0, column=1, sticky="w")
    tk.Frame(header_frame, bg=CYAN, height=2).grid(row=1, column=0, sticky="ew", pady=(8, 10))

    def add_row_in(frame, label_text, widget, row, bg):
        tk.Label(frame, text=label_text, bg=bg, fg=WHITE, font=("Verdana", 9)).grid(
            row=row, column=0, padx=(6, 8), pady=4, sticky="e"
        )
        widget.grid(row=row, column=1, padx=(0, 6), pady=4, sticky="w")

    def add_entry_row(frame, label_text, default, row, width=8):
        tk.Label(frame, text=label_text, bg=SBG, fg=MINT, font=("Verdana", 9)).grid(
            row=row, column=0, padx=(6, 8), pady=4, sticky="e"
        )
        var = tk.StringVar(value=str(default))
        tk.Entry(
            frame, textvariable=var, bg=MINT, fg=DARK, font=("Verdana", 9), width=width, relief="flat", bd=2
        ).grid(row=row, column=1, padx=(0, 6), pady=4, sticky="w")
        return var

    def _make_date(parent, value):
        if DateEntry is not None:
            w = DateEntry(parent, date_pattern="yyyy-mm-dd")
            w.set_date(value)
            return w
        w = tk.Entry(parent, bg=MINT, fg=DARK, font=("Verdana", 9), width=14, relief="flat", bd=2)
        w.insert(0, value)
        return w

    def _get_date(w):
        if DateEntry is not None and isinstance(w, DateEntry):
            return w.get_date()
        return datetime.strptime(w.get(), "%Y-%m-%d").date()

    def _set_date(w, value):
        if DateEntry is not None and hasattr(w, "set_date"):
            w.set_date(value)
        else:
            w.delete(0, tk.END)
            w.insert(0, str(value)[:10])

    left_col = tk.Frame(inner, bg=color("fondo_principal"))
    left_col.grid(row=1, column=0, padx=(0, 10), sticky="n")
    mid_col = tk.Frame(inner, bg=color("fondo_principal"))
    mid_col.grid(row=1, column=1, padx=(0, 10), sticky="n")
    right_col = tk.Frame(inner, bg=color("fondo_principal"))
    right_col.grid(row=1, column=2, padx=(10, 0), sticky="n")

    frame_temporal = ttk.LabelFrame(
        left_col, text="Configuracion temporal", style="Section.TLabelframe", padding=(12, 8)
    )
    frame_temporal.pack(fill="x", pady=(0, 10))
    epoch_name_var = tk.StringVar()

    def suggest_epoch_name():
        epoch_name_var.set(epoch_name_for(len(epochs)))

    suggest_epoch_name()
    tk.Label(frame_temporal, text="Epoch name:", bg=SBG, fg=WHITE, font=("Verdana", 9)).grid(
        row=0, column=0, padx=(6, 8), pady=4, sticky="e"
    )
    tk.Entry(
        frame_temporal,
        textvariable=epoch_name_var,
        bg=MINT,
        fg=DARK,
        font=("Verdana", 9),
        width=22,
        relief="flat",
        bd=2,
    ).grid(row=0, column=1, padx=(0, 6), pady=4, sticky="w")

    cal_inicio = _make_date(frame_temporal, "2026-01-01")
    add_row_in(frame_temporal, "Start date", cal_inicio, 1, SBG)
    cal_final = _make_date(frame_temporal, "2027-12-31")
    add_row_in(frame_temporal, "End date", cal_final, 2, SBG)
    years_var = tk.StringVar(value="2")
    years_combo = ttk.Combobox(
        frame_temporal, textvariable=years_var, values=list(range(1, 6)), state="readonly", width=12
    )
    add_row_in(frame_temporal, "Representative years", years_combo, 3, SBG)
    months_var = tk.StringVar(value="6")
    months_combo = ttk.Combobox(
        frame_temporal, textvariable=months_var, values=[1, 2, 3, 4, 6, 12], state="readonly", width=12
    )
    add_row_in(frame_temporal, "Representative months", months_combo, 4, SBG)
    days_var = tk.StringVar(value="1")
    days_combo = ttk.Combobox(
        frame_temporal, textvariable=days_var, values=[1, 4], state="readonly", width=12
    )
    add_row_in(frame_temporal, "Representative days", days_combo, 5, SBG)
    network_var = tk.StringVar(value="osm-mesh")
    network_combo = ttk.Combobox(
        frame_temporal,
        textvariable=network_var,
        values=["osm-mesh", "dashboard-sin"],
        state="readonly",
        width=18,
    )
    add_row_in(frame_temporal, "Red Colombia", network_combo, 6, SBG)

    def sync_end_date_with_years(event=None):
        try:
            start_date = _get_date(cal_inicio)
            _set_date(cal_final, suggested_end_date(str(start_date), int(years_var.get())))
        except Exception:
            pass

    years_combo.bind("<<ComboboxSelected>>", sync_end_date_with_years)

    def add_epoch():
        name = epoch_name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Por favor ingrese un nombre para la época.")
            return
        if global_scenario_var.get() == "Otro" and not custom_scenario_name_var.get().strip():
            messagebox.showerror("Error", 'Debe ingresar un nombre para el escenario "Otro".')
            return
        if len(epochs) == 0:
            start_date = _get_date(cal_inicio)
        else:
            prev = epochs[-1].end_date
            if hasattr(prev, "year"):
                start_date = prev + timedelta(days=1)
            else:
                start_date = datetime.strptime(str(prev), "%Y-%m-%d").date() + timedelta(days=1)
            _set_date(cal_inicio, start_date)
        rep_years = int(years_var.get())
        end_s = suggested_end_date(str(start_date), rep_years)
        end_date = datetime.strptime(end_s, "%Y-%m-%d").date()
        _set_date(cal_final, end_date)
        ep = Epoch(
            name=name,
            start_date=start_date if hasattr(start_date, "year") else datetime.strptime(str(start_date)[:10], "%Y-%m-%d").date(),
            end_date=end_date,
            rep_years=rep_years,
            rep_months=int(months_var.get()),
            rep_days=int(days_var.get()),
            settings=get_current_epoch_settings(),
        )
        epochs.append(ep)
        if len(epochs) == 1:
            global_scenario_combo.config(state="disabled")
            _update_global_lock_label(locked=True)
        next_date = end_date + timedelta(days=1)
        _set_date(cal_inicio, next_date)
        years_var.set("5" if len(epochs) >= 1 else "1")
        months_var.set("6")
        days_var.set("1")
        suggest_epoch_name()
        update_epoch_listbox()

    tk.Label(frame_temporal, text="Added epochs:", bg=SBG, fg=CYAN, font=("Verdana", 9, "bold")).grid(
        row=7, column=0, columnspan=2, padx=6, pady=(6, 2), sticky="w"
    )
    epoch_listbox = tk.Listbox(
        frame_temporal,
        width=52,
        height=4,
        bg="#061260",
        fg=WHITE,
        font=("Verdana", 8),
        selectbackground=CYAN,
        selectforeground=DARK,
        relief="flat",
        bd=2,
    )
    epoch_listbox.grid(row=8, column=0, columnspan=2, padx=6, pady=(0, 6), sticky="ew")

    def update_epoch_listbox():
        epoch_listbox.delete(0, tk.END)
        for i, ep in enumerate(epochs, 1):
            epoch_listbox.insert(
                tk.END,
                f"{i}. {ep.name} | {ep.start_date} - {ep.end_date} | "
                f"{ep.rep_years} rep.yrs | {ep.rep_months} rep.months | {ep.rep_days} rep.days",
            )

    def remove_epoch():
        sel = epoch_listbox.curselection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione una época para eliminar.")
            return
        epochs.pop(sel[0])
        update_epoch_listbox()
        suggest_epoch_name()
        if not epochs:
            global_scenario_combo.config(state="readonly")
            _update_global_lock_label(locked=False)

    btns_epoch = tk.Frame(frame_temporal, bg=SBG)
    btns_epoch.grid(row=9, column=0, columnspan=2, pady=(4, 4))
    tk.Button(
        btns_epoch,
        text="Add Epoch",
        command=add_epoch,
        bg=ORANGE,
        fg=DARK,
        font=("Verdana", 9, "bold"),
        relief="flat",
        padx=8,
        pady=4,
        cursor="hand2",
    ).grid(row=0, column=0, padx=(0, 6))
    tk.Button(
        btns_epoch,
        text="Remove Selected",
        command=remove_epoch,
        bg=BASE_COLORS["green"],
        fg=DARK,
        font=("Verdana", 8, "bold"),
        relief="flat",
        padx=6,
        pady=3,
        cursor="hand2",
    ).grid(row=0, column=1)

    frame_restricciones = ttk.LabelFrame(
        left_col, text="Restricciones adicionales", style="Section.TLabelframe", padding=(14, 10)
    )
    frame_restricciones.pack(fill="x", pady=(0, 10))
    cb_load_lost = tk.BooleanVar(value=False)
    tk.Checkbutton(
        frame_restricciones,
        text="Maximum load lost [MWh/year]",
        variable=cb_load_lost,
        bg=SBG,
        fg=WHITE,
        selectcolor=DARK,
        font=("Verdana", 10, "bold"),
        anchor="w",
    ).grid(row=0, column=0, sticky="w", padx=8)
    entry_load_lost = add_entry_row(frame_restricciones, "MWh/year:", 2000, 1, width=9)
    cb_discrete_transmission = tk.BooleanVar(value=False)
    tk.Checkbutton(
        frame_restricciones,
        text="Discrete transmission expansion",
        variable=cb_discrete_transmission,
        bg=SBG,
        fg=WHITE,
        selectcolor=DARK,
        font=("Verdana", 10, "bold"),
        anchor="w",
    ).grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 2))
    cb_fnce = tk.BooleanVar(value=False)
    tk.Checkbutton(
        frame_restricciones,
        text="Meta FNCE",
        variable=cb_fnce,
        bg=SBG,
        fg=WHITE,
        selectcolor=DARK,
        font=("Verdana", 10, "bold"),
        anchor="w",
    ).grid(row=3, column=0, sticky="w", padx=8)
    entry_fnce = add_entry_row(frame_restricciones, "FNCE %:", 20, 4, width=9)
    cb_coal = tk.BooleanVar(value=False)
    tk.Checkbutton(
        frame_restricciones,
        text="Cierre de carbón (phase-out UPME)",
        variable=cb_coal,
        bg=SBG,
        fg=WHITE,
        selectcolor=DARK,
        font=("Verdana", 10, "bold"),
        anchor="w",
    ).grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 2))

    frame_optimizer = ttk.LabelFrame(
        left_col, text="Configuracion de optimizacion", style="Section.TLabelframe", padding=(12, 8)
    )
    frame_optimizer.pack(fill="x", pady=(0, 10))
    solver_name = tk.StringVar(value="highs")
    add_row_in(
        frame_optimizer,
        "Solver name",
        ttk.Combobox(
            frame_optimizer,
            textvariable=solver_name,
            values=["cbc", "highs", "gurobi", "cplex"],
            state="readonly",
            width=12,
        ),
        0,
        SBG,
    )
    entry_threads = add_entry_row(frame_optimizer, "Threads", os.cpu_count() or 2, 1, width=8)
    entry_mip_gap = add_entry_row(frame_optimizer, "MIP gap", 0.1, 2, width=8)
    linearized_uc_var = tk.BooleanVar(value=True)
    tk.Checkbutton(
        frame_optimizer,
        text="Linearized unit commitment",
        variable=linearized_uc_var,
        bg=SBG,
        fg=WHITE,
        selectcolor=DARK,
        font=("Verdana", 9),
        anchor="w",
    ).grid(row=3, column=0, columnspan=2, padx=6, pady=4, sticky="w")

    frame_scenario = ttk.LabelFrame(
        mid_col, text="Configuracion de escenario", style="Section.TLabelframe", padding=(12, 8)
    )
    frame_scenario.pack(fill="x", pady=(0, 10))
    global_scenario_var = tk.StringVar(value=PRESET_NAMES[0])
    tk.Label(frame_scenario, text="Global scenario:", bg=SBG, fg=CYAN, font=("Verdana", 9, "bold")).grid(
        row=0, column=0, padx=(6, 8), pady=(6, 2), sticky="e"
    )
    global_scenario_combo = ttk.Combobox(
        frame_scenario, textvariable=global_scenario_var, values=ALL_GLOBAL_NAMES, state="readonly", width=36
    )
    global_scenario_combo.grid(row=0, column=1, padx=(0, 6), pady=(6, 2), sticky="w")
    lbl_global_lock = tk.Label(frame_scenario, text="", bg=SBG, fg=ORANGE, font=("Verdana", 7, "italic"))
    lbl_global_lock.grid(row=1, column=0, columnspan=2, sticky="e", padx=6)

    def _update_global_lock_label(locked: bool):
        lbl_global_lock.config(
            text="⚠  Locked after first epoch – add scenario to queue or remove all epochs to change"
            if locked
            else ""
        )

    custom_scenario_name_var = tk.StringVar(value="")
    lbl_custom_name = tk.Label(
        frame_scenario, text="Custom name:", bg=SBG, fg=ORANGE, font=("Verdana", 9, "italic")
    )
    entry_custom_name = tk.Entry(
        frame_scenario,
        textvariable=custom_scenario_name_var,
        bg=MINT,
        fg=DARK,
        font=("Verdana", 9),
        width=30,
        relief="flat",
        bd=2,
    )
    demand_scenario = tk.StringVar()
    hydrology_scenario = tk.StringVar()
    climate_scenario = tk.StringVar()
    generation_investment_cost_scenario = tk.StringVar()
    storage_investment_cost_scenario = tk.StringVar()
    fuel_price_scenario = tk.StringVar()
    demand_combo = ttk.Combobox(
        frame_scenario, textvariable=demand_scenario, values=SCENARIO_NAMES["demand"], state="disabled", width=28
    )
    add_row_in(frame_scenario, "Demand scenario", demand_combo, 4, SBG)
    hydrology_combo = ttk.Combobox(
        frame_scenario,
        textvariable=hydrology_scenario,
        values=SCENARIO_NAMES["hydrology"],
        state="disabled",
        width=28,
    )
    add_row_in(frame_scenario, "Hydrology scenario", hydrology_combo, 5, SBG)
    climate_combo = ttk.Combobox(
        frame_scenario, textvariable=climate_scenario, values=SCENARIO_NAMES["climate"], state="disabled", width=28
    )
    add_row_in(frame_scenario, "Climate scenario", climate_combo, 6, SBG)
    gen_cost_combo = ttk.Combobox(
        frame_scenario,
        textvariable=generation_investment_cost_scenario,
        values=SCENARIO_NAMES["generation_investment_cost"],
        state="disabled",
        width=28,
    )
    add_row_in(frame_scenario, "Generation investment cost", gen_cost_combo, 7, SBG)
    sto_cost_combo = ttk.Combobox(
        frame_scenario,
        textvariable=storage_investment_cost_scenario,
        values=SCENARIO_NAMES["storage_investment_cost"],
        state="disabled",
        width=28,
    )
    add_row_in(frame_scenario, "Storage investment cost", sto_cost_combo, 8, SBG)
    fuel_combo = ttk.Combobox(
        frame_scenario, textvariable=fuel_price_scenario, values=SCENARIO_NAMES["fuel_price"], state="disabled", width=28
    )
    add_row_in(frame_scenario, "Fuel price scenario", fuel_combo, 9, SBG)
    _component_combos = [demand_combo, hydrology_combo, climate_combo, gen_cost_combo, sto_cost_combo, fuel_combo]

    def on_global_scenario_change(event=None):
        sel = global_scenario_var.get()
        if sel == "Otro":
            lbl_custom_name.grid(row=2, column=0, padx=(6, 8), pady=2, sticky="e")
            entry_custom_name.grid(row=2, column=1, padx=(0, 6), pady=2, sticky="w")
            for cb in _component_combos:
                cb.config(state="readonly")
        else:
            lbl_custom_name.grid_remove()
            entry_custom_name.grid_remove()
            vals = SCENARIO_MAP[sel]
            demand_scenario.set(vals["demand"])
            climate_scenario.set(vals["climate"])
            hydrology_scenario.set(vals["hydrology"])
            generation_investment_cost_scenario.set(vals["generation_investment_cost"])
            storage_investment_cost_scenario.set(vals["storage_investment_cost"])
            fuel_price_scenario.set(vals["fuel_price"])
            for cb in _component_combos:
                cb.config(state="disabled")

    global_scenario_combo.bind("<<ComboboxSelected>>", on_global_scenario_change)
    on_global_scenario_change()

    frame_queue = ttk.LabelFrame(
        mid_col, text="Cola de escenarios a ejecutar", style="Section.TLabelframe", padding=(12, 8)
    )
    frame_queue.pack(fill="x", pady=(0, 10))
    tk.Label(frame_queue, text="Queued scenarios:", bg=SBG, fg=CYAN, font=("Verdana", 9, "bold")).grid(
        row=0, column=0, columnspan=2, padx=6, pady=(4, 2), sticky="w"
    )
    scenario_listbox = tk.Listbox(
        frame_queue,
        width=52,
        height=4,
        bg="#061260",
        fg=WHITE,
        font=("Verdana", 8),
        selectbackground=CYAN,
        selectforeground=DARK,
        relief="flat",
        bd=2,
    )
    scenario_listbox.grid(row=1, column=0, columnspan=2, padx=6, pady=(0, 6), sticky="ew")

    def update_scenario_listbox():
        scenario_listbox.delete(0, tk.END)
        for i, sc in enumerate(scenarios, 1):
            n_ep = len(sc["epochs"])
            first = sc["epochs"][0]["start_date"]
            last = sc["epochs"][-1]["end_date"]
            scenario_listbox.insert(tk.END, f"{i}. {sc['global_scenario']} | {n_ep} epoch(s) | {first} - {last}")

    def remove_scenario():
        sel = scenario_listbox.curselection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione un escenario para eliminar de la cola.")
            return
        scenarios.pop(sel[0])
        update_scenario_listbox()

    btns_queue = tk.Frame(frame_queue, bg=SBG)
    btns_queue.grid(row=2, column=0, columnspan=2, pady=4)
    tk.Button(
        btns_queue,
        text="Add scenario to queue",
        command=add_scenario_to_queue,
        bg=ORANGE,
        fg=DARK,
        font=("Verdana", 9, "bold"),
        relief="flat",
        padx=8,
        pady=4,
        cursor="hand2",
    ).grid(row=0, column=0, padx=(0, 6))
    tk.Button(
        btns_queue,
        text="Remove Selected",
        command=remove_scenario,
        bg=BASE_COLORS["green"],
        fg=DARK,
        font=("Verdana", 8, "bold"),
        relief="flat",
        padx=6,
        pady=3,
        cursor="hand2",
    ).grid(row=0, column=1)

    frame_exec = ttk.LabelFrame(
        mid_col, text="Configuracion de ejecucion", style="Section.TLabelframe", padding=(12, 8)
    )
    frame_exec.pack(fill="x", pady=(0, 10))
    execution_mode_var = tk.StringVar(value="Secuencial")
    add_row_in(
        frame_exec,
        "Execution mode",
        ttk.Combobox(
            frame_exec,
            textvariable=execution_mode_var,
            values=["Secuencial", "Paralelo"],
            state="readonly",
            width=12,
        ),
        0,
        SBG,
    )
    entry_max_workers = add_entry_row(frame_exec, "Max parallel scenarios", 2, 1, width=8)
    entry_ram_limit = add_entry_row(frame_exec, "RAM limit [% of total]", 85, 2, width=8)
    tk.Button(
        mid_col,
        text="Run all scenarios",
        command=confirmar,
        bg=ORANGE,
        fg=DARK,
        font=("Verdana", 10, "bold"),
        relief="flat",
        padx=20,
        pady=10,
        cursor="hand2",
        width=30,
    ).pack(fill="x", pady=(10, 0))

    _net_path = os.path.join(_data_dir, "sin_network.png")
    if Image and os.path.exists(_net_path):
        try:
            _net_raw = Image.open(_net_path)
            _net_h = 620
            _net_w = int(_net_h * _net_raw.width / max(_net_raw.height, 1))
            net_photo = ImageTk.PhotoImage(_net_raw.resize((_net_w, _net_h), Image.LANCZOS))
            net_label = tk.Label(right_col, image=net_photo, bg=color("fondo_principal"))
            net_label.image = net_photo
            net_label.pack(fill="both", expand=True)
        except Exception as e:
            print(f"No se pudo cargar el mapa del SIN: {e}")

    root.mainloop()
    return result


if __name__ == "__main__":
    print(run_gui())
