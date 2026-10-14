"""Repository CLI. All paths in a study config are relative to --root."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from .io import load_config, sha256, write_json

COMMANDS = [
    "run",
    "audit-source",
    "download-xm",
    "build-cutout",
    "build-profiles",
    "build-network",
    "prepare-inputs",
    "solve",
    "report",
    "poster",
    "inspect-paratec",
    "mesh",
    "attach-mesh",
    "solve-mesh",
    "explore",
    "mesh-stats",
    "mesh-report",
    "gui",
]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="PyPSA-col — reproducible Colombian energy-system workflows"
    )
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--config", default="config/demo.yaml", help="Study YAML, relative to root")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--refresh", action="store_true", help="Refresh XM cache instead of replaying"
    )
    parser.add_argument(
        "--if-needed", action="store_true", help="Skip XM download for purely synthetic inputs"
    )
    parser.add_argument(
        "--file", type=Path, help="CSV/XLSX PARATEC export to inspect (never auto-approved)"
    )
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--host", default="0.0.0.0", help="GUI bind host")
    parser.add_argument("--port", type=int, default=7860, help="GUI bind port")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.command == "gui":
        from .web_gui import main as gui_main

        gui_main(host=args.host, port=args.port, root=root)
        return 0
    config = load_config(root / args.config)
    resources = root / "resources" / config["run"]["id"]
    results = root / "results" / config["run"]["id"]
    resources.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        if args.command in {"audit-source", "run"}:
            from .source import audit_source

            audit_source(root, config)
        if args.command == "download-xm" or (
            args.command == "run" and config["inputs"]["mode"] != "demo"
        ):
            if args.if_needed and config["inputs"]["mode"] == "demo":
                stamp = {
                    "status": "skipped",
                    "reason": "pure synthetic demo; no XM data dependency",
                }
            else:
                from .xm import download_bundle

                manifest = download_bundle(root, config, args.refresh)
                stamp = {
                    "status": "observed_xm_data",
                    "datasets": len(manifest["datasets"]),
                    "manifest_sha256": sha256(
                        root / config["xm"]["processed_dir"] / "manifest.json"
                    ),
                }
            write_json(resources / "xm_ready.json", stamp)
        if args.command in {"build-network", "run"}:
            from .network import build_base

            build_base(root, config, resources)
        if args.command == "build-cutout" or (
            args.command == "run" and config["climate"]["mode"] == "era5"
        ):
            from .climate import prepare_cutout

            prepare_cutout(root, config)
        if args.command in {"build-profiles", "run"}:
            from .climate import build_profiles

            build_profiles(root, config, resources)
        if args.command in {"prepare-inputs", "run"}:
            from .inputs import prepare_inputs

            prepare_inputs(root, config, resources)
        if args.command in {"solve", "run"}:
            from .model import solve

            solve(root, config, resources, results)
        if args.command in {"poster", "run"}:
            from .poster import render_grid2poster

            render_grid2poster(root, config, results)
        if args.command in {"report", "run"}:
            from .results import write_results

            write_results(root, config, resources, results)
            print(f"Report: {results / 'report.html'}")
        if args.command in {
            "mesh",
            "attach-mesh",
            "solve-mesh",
            "explore",
            "mesh-stats",
            "mesh-report",
        }:
            from .osm_mesh import stage

            stage(
                {
                    "mesh": "mesh",
                    "attach-mesh": "attach",
                    "solve-mesh": "solve",
                    "explore": "explore",
                    "mesh-stats": "stats",
                    "mesh-report": "report",
                }[args.command],
                root,
                config,
            )
        if args.command == "inspect-paratec":
            from .source import upstream_modules, verify_source

            if args.file is None:
                raise ValueError("inspect-paratec needs --file path/to/export.csv or .xlsx")
            verify_source(root, config)
            _, paratec, _ = upstream_modules(root / config["source"]["path"])
            table = paratec.cargar_paratec_csv(str(root / args.file))
            table.to_csv(resources / "paratec_normalized_UNREVIEWED.csv", index=False)
            write_json(
                resources / "paratec_detected_columns.json",
                {
                    "input_sha256": sha256(root / args.file),
                    "detected_columns": table.attrs.get("columnas_detectadas", {}),
                    "warning": "Name normalization only. r/x may be ohms or per-unit, corriente is NOT MVA. "
                    "Confirm base voltage/MVA, thermal units and endpoint IDs before using reviewed schemas.",
                },
            )
        write_json(resources / "resolved_config.json", config)
    except Exception as exc:
        if args.debug:
            raise
        parser.exit(2, f"PyPSA-col {args.command} failed: {exc}\nUse --debug for a traceback.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
