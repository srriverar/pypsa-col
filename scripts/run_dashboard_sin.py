#!/usr/bin/env python3
"""Solve and plot the dashboard-sin-nodal × PyPSA example (offline XM cache)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pypsa_col.dashboard_sin import run
from pypsa_col.io import load_config


def main():
    config = load_config(ROOT / "config/dashboard-sin.yaml")
    summary = run(ROOT, config)
    print("status", summary["status"], summary.get("termination"))
    print("plants", summary["n_plants"], "CEN_MW", round(summary["cen_mw"], 1))
    print("toponymy_pct", round(summary["toponymy_pct"], 1))
    print("demand_gwh", round(summary["demand_gwh"], 2), "unserved", round(summary["unserved_gwh"], 2))
    print("objective_usd", summary["objective_usd"])
    print("carriers_gwh", {k: round(v, 2) for k, v in summary["carriers"].items()})
    print("report", ROOT / "results/dashboard-sin/informe.html")


if __name__ == "__main__":
    main()
