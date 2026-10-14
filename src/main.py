"""PyPSA-col entry point, parallel to PyPSA-CL ``src/main.py``.

    python src/main.py
        Opens the configuration GUI. In a desktop session this is Tkinter
        (``GUI.py``, Chile layout). Without a display, or with ``--web``, it
        serves the same screen in the browser.

    python src/main.py --scenario-json path.json
        Headless single-scenario run (Chile ``--scenario-json`` contract).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from pypsa_col.gui_core import execute_run  # noqa: E402


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PyPSA-col GUI / scenario driver")
    p.add_argument("--scenario-json", help="Headless: run one queued configuration")
    p.add_argument("--web", action="store_true", help="Force the browser GUI")
    p.add_argument("--tk", action="store_true", help="Force the Tkinter GUI")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=7860)
    return p.parse_args()


def main() -> None:
    args = _parse()
    if args.scenario_json:
        with open(args.scenario_json, encoding="utf-8") as fh:
            user_data = json.load(fh)
        out = os.environ.get("PYPSA_COL_OUTPUTS_DIR")
        execute_run(_PROJECT_ROOT, user_data, Path(out) if out else None)
        return

    use_web = args.web or (not args.tk and not os.environ.get("DISPLAY"))
    if use_web:
        from pypsa_col.web_gui import main as web_main

        web_main(host=args.host, port=args.port, root=_PROJECT_ROOT)
        return

    from GUI import run_gui

    user_data = run_gui()
    if not user_data or not user_data.get("epochs"):
        print("GUI cerrada sin cola de escenarios.")
        return
    execute_run(_PROJECT_ROOT, user_data)


if __name__ == "__main__":
    main()
