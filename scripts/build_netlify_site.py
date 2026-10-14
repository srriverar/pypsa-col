#!/usr/bin/env python3
"""Rebuild the static Netlify folder (`site/`) from GUI assets + osm-interactive figures."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from pypsa_col.gui_core import presets_payload

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "assets").mkdir(parents=True)
    (SITE / "results" / "osm-interactive").mkdir(parents=True)

    shutil.copy2(ROOT / "data" / "gui" / "logo_pypsa_col.png", SITE / "assets" / "logo_pypsa_col.png")
    shutil.copy2(ROOT / "data" / "gui" / "sin_network.png", SITE / "assets" / "sin_network.png")
    dash = ROOT / "results" / "dashboard-sin" / "red.png"
    if dash.exists():
        shutil.copy2(dash, SITE / "assets" / "dashboard_red.png")

    src = ROOT / "results" / "osm-interactive"
    for name in (
        "colombia_map.png",
        "lmp.png",
        "dispatch.png",
        "explore_load.html",
        "explore_capacity.html",
        "explore_flow.html",
        "report.html",
    ):
        p = src / name
        if p.exists():
            shutil.copy2(p, SITE / "results" / "osm-interactive" / name)

    (SITE / "presets.json").write_text(
        json.dumps(presets_payload(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    html_src = ROOT / "src" / "pypsa_col" / "gui_static" / "index.html"
    html = html_src.read_text(encoding="utf-8")
    html = html.replace('src="/assets/', 'src="assets/')
    html = html.replace(
        'src = v === "dashboard-sin" ? "/assets/dashboard_red.png" : "/assets/sin_network.png"',
        'src = v === "dashboard-sin" ? "assets/dashboard_red.png" : "assets/sin_network.png"',
    )
    html = html.replace('fetch("/api/presets")', 'fetch("presets.json")')
    print("Wrote", SITE, "files", len(list(SITE.rglob("*"))))
    # Keep the hand-tuned site/index.html if it already has Netlify patches.
    # This script only refreshes assets + presets; copy index if missing.
    dst = SITE / "index.html"
    if not dst.exists():
        dst.write_text(html, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
