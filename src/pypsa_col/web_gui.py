"""Browser GUI for PyPSA-col, layout cloned from PyPSA-CL ``src/GUI.py``.

Chile's interface is Tkinter (no live preview in this sandbox). This module
serves the same three-column configuration screen over HTTP so it can run as
the Arena live preview, while ``src/GUI.py`` remains the desktop twin.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

from .gui_core import execute_run, flatten_user_data, presets_payload

_FIG_NAMES = (
    "colombia_map.png",
    "lmp.png",
    "dispatch.png",
    "explore_load.html",
    "explore_capacity.html",
    "explore_flow.html",
    "report.html",
)


def _collect_figures(root: Path, outdir: Path) -> list[dict]:
    items = []
    if not outdir.exists():
        return items
    for ep_dir in sorted(outdir.glob("s*_e*")):
        if not ep_dir.is_dir():
            continue
        base = f"/outputs/{outdir.name}/{ep_dir.name}"
        rec = {"epoch": ep_dir.name, "base": base}
        for name in _FIG_NAMES:
            if (ep_dir / name).exists():
                rec[name] = f"{base}/{name}"
        items.append(rec)
    return items


_LOCK = threading.Lock()
_PROGRESS = {"status": "idle", "message": "GUI lista."}
_THREAD: threading.Thread | None = None
_OUTDIR: Path | None = None


def _root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def create_app(root: Path | None = None) -> Flask:
    root = Path(root or _root_from_here())
    static = Path(__file__).resolve().parent / "gui_static"
    gui_data = root / "data" / "gui"

    app = Flask(
        __name__,
        static_folder=str(static),
        static_url_path="/static",
    )
    app.config["ROOT"] = root
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    @app.after_request
    def _headers(resp):
        resp.headers["Cache-Control"] = "no-store"
        # Preview is iframed; do not block embedding.
        resp.headers.pop("X-Frame-Options", None)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    @app.get("/")
    def index():
        return send_from_directory(static, "index.html")

    @app.get("/assets/logo_pypsa_col.png")
    def logo():
        return send_file(gui_data / "logo_pypsa_col.png", mimetype="image/png")

    @app.get("/assets/sin_network.png")
    def sin_map():
        p = gui_data / "sin_network.png"
        if not p.exists():
            p = root / "results" / "osm-interactive" / "colombia_map.png"
        return send_file(p, mimetype="image/png")

    @app.get("/assets/dashboard_red.png")
    def dash_map():
        p = root / "results" / "dashboard-sin" / "red.png"
        return send_file(p, mimetype="image/png")

    @app.get("/api/presets")
    def presets():
        return jsonify(presets_payload())

    @app.get("/api/progress")
    def progress():
        payload = dict(_PROGRESS)
        if _OUTDIR and _OUTDIR.exists():
            pj = _OUTDIR / "progress.json"
            if pj.exists():
                try:
                    payload.update(json.loads(pj.read_text(encoding="utf-8")))
                except ValueError:
                    pass
            payload["outdir"] = (
                str(_OUTDIR.relative_to(root)) if _OUTDIR.is_relative_to(root) else str(_OUTDIR)
            )
            costs = _OUTDIR / "system_costs.csv"
            if costs.exists():
                import pandas as pd

                payload["costs"] = pd.read_csv(costs).to_dict(orient="records")
                if payload.get("status") == "running":
                    payload["status"] = "done"
                    payload["message"] = "Corrida terminada."
            payload["figures"] = _collect_figures(root, _OUTDIR)
            for png in _OUTDIR.glob("**/dispatch.png"):
                rel = png.relative_to(_OUTDIR)
                payload["dispatch_url"] = f"/outputs/{_OUTDIR.name}/{rel.as_posix()}"
                break
        return jsonify(payload)

    @app.get("/outputs/<path:rest>")
    def outputs(rest: str):
        return send_from_directory(root / "outputs", rest)

    @app.post("/api/run")
    def run():
        global _THREAD, _OUTDIR, _PROGRESS
        body = request.get_json(force=True) or {}
        scenarios = body.get("scenarios") or []
        run_config = body.get("run_config") or {"execution_mode": "sequential"}
        if not scenarios:
            return jsonify({"error": "Cola vacía."}), 400
        user_data = flatten_user_data(scenarios, run_config)
        with _LOCK:
            if _THREAD and _THREAD.is_alive():
                return jsonify({"error": "Ya hay una corrida en curso."}), 409

            def _job():
                global _PROGRESS
                try:
                    execute_run(root, user_data, _OUTDIR)
                    _PROGRESS = {"status": "done", "message": "Corrida terminada."}
                except Exception as exc:
                    _PROGRESS = {"status": "error", "message": str(exc)}

            from .gui_core import run_folder_name

            _OUTDIR = root / "outputs" / run_folder_name(user_data)
            _PROGRESS = {"status": "running", "message": "Arrancando…"}
            _THREAD = threading.Thread(target=_job, daemon=True)
            _THREAD.start()
        return jsonify({"ok": True, "outdir": str(_OUTDIR)})

    return app


def main(host: str = "0.0.0.0", port: int = 7860, root: Path | None = None) -> None:
    app = create_app(root)
    print(f"PyPSA-col GUI  http://{host}:{port}", flush=True)
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
