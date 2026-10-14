"""Full Snakemake DAG for the OSM-mesh interactive example.

From the repository root:

    snakemake -s workflow/Snakefile.osm.smk --cores 2
"""
from pathlib import Path
import sys

STUDY = "config/osm-interactive.yaml"
RID = "osm-interactive"
P = f"resources/{RID}"
R = f"results/{RID}"
PY = sys.executable
ENV = "PYTHONPATH=src"
CODE = [str(p) for p in Path("src/pypsa_col").glob("*.py")]
OSM = [
    "external/colombiacongestionV2/data/geo/lineas_osm.geojson",
    "external/colombiacongestionV2/data/geo/subestaciones_osm.geojson",
    "external/colombiacongestionV2/data/geo/centrales_osm.geojson",
]
XM = [
    "data/processed/xm/ListadoRecursos__Sistema.csv",
    "data/processed/xm/CapEfecNeta__Recurso.csv",
    "data/processed/xm/Gene__Recurso.csv",
    "data/processed/xm/DemaReal__Sistema.csv",
]


rule all:
    input:
        f"{R}/report.html",
        f"{R}/summary.json",
        f"{R}/network.nc",
        f"{R}/explore_load.html",
        f"{R}/explore_capacity.html",
        f"{R}/explore_flow.html",
        f"{R}/lmp.png",
        f"{R}/colombia_map.png",
        f"{R}/dispatch.png",
        f"{R}/energy_balance_gwh.csv",


rule mesh:
    input:
        OSM, "config/sources.lock.json", CODE, STUDY
    output:
        f"{P}/mesh.nc",
        f"{P}/mesh_topology.json",
        f"{P}/mesh_buses.csv",
        f"{P}/mesh_lines.csv",
        f"{P}/mesh_transformers.csv",
    shell:
        "{ENV} {PY:q} -m pypsa_col mesh --config {STUDY:q}"


rule attach:
    input:
        rules.mesh.output, XM, CODE, STUDY
    output:
        f"{P}/prepared.nc",
        f"{P}/plants_attached.csv",
        f"{P}/attach_report.json",
        f"{P}/buses_zoned.csv",
    shell:
        "{ENV} {PY:q} -m pypsa_col attach-mesh --config {STUDY:q}"


rule solve:
    input:
        rules.attach.output, CODE, STUDY
    output:
        f"{R}/network.nc",
        f"{R}/solver.json",
    threads: 2
    shell:
        "{ENV} {PY:q} -m pypsa_col solve-mesh --config {STUDY:q}"


rule explore:
    input:
        rules.solve.output, CODE, STUDY
    output:
        f"{R}/explore_load.html",
        f"{R}/explore_capacity.html",
        f"{R}/explore_flow.html",
    shell:
        "{ENV} {PY:q} -m pypsa_col explore --config {STUDY:q}"


rule stats:
    input:
        rules.solve.output, CODE, STUDY
    output:
        f"{R}/lmp.png",
        f"{R}/colombia_map.png",
        f"{R}/dispatch.png",
        f"{R}/energy_balance_gwh.csv",
        f"{R}/opex_usd.csv",
        f"{R}/summary.json",
    shell:
        "{ENV} {PY:q} -m pypsa_col mesh-stats --config {STUDY:q}"


rule report:
    input:
        rules.explore.output, rules.stats.output, f"{P}/attach_report.json", f"{P}/mesh_topology.json", CODE
    output:
        f"{R}/report.html",
    shell:
        "{ENV} {PY:q} -m pypsa_col mesh-report --config {STUDY:q}"
