# Delivery validation

Executed for the **2026-10-12 America/Phoenix** delivery (UTC execution date 2026-10-13).

## Environment

- Python 3.13.16 on Linux x86_64.
- PyPSA 1.2.4; Linopy 0.10.0; HiGHS/highspy 1.15.1; pandas 2.3.3.
- Atlite 0.7.0; Snakemake 9.27.0.
- Full development environment: `requirements-lock.txt`.

## Checks actually run

```bash
pip install -e '.[workflow,climate,dev]'
python scripts/bootstrap_sources.py
ruff check src scripts tests
ruff format --check src scripts tests
python -m compileall -q src scripts
PYPSA_COL_RUN_LIVE=1 pytest -q --disable-warnings --junitxml=docs/test-results.xml
snakemake -s workflow/Snakefile --config study=config/demo.yaml --cores 2
snakemake -s workflow/Snakefile --config study=config/xm-example.yaml --cores 2
pypsa-col run --config config/el-nino.yaml
pypsa-col run --config config/investment2030.yaml
```

**40 tests passed**, 0 failures, 0 errors, 0 skipped in the opt-in live run. Normal `pytest` runs 39 offline tests and skips the one external XM test. The suite includes mapped-input synthetic fixtures, drought/water budgets, investment lifetimes and potentials, NetCDF round trips, source topology, unit parsing, cached/mixed-revision integrity checks and Atlite conversion on synthetic weather.

Both actual Snakemake DAGs completed **9/9 jobs**. An immediate repeated demo DAG reported **Nothing to be done**. The source bootstrap verified all **45 pinned source files**. Formatting/lint/compilation checks passed.

Known third-party NumPy/pandas deprecation and Linopy legacy-semantics transition warnings were emitted. They are documented rather than interpreted as numerical failures; physical residuals are independently checked. The matrix CI file is included but **remote CI was not run**. Python 3.11 is declared/CI-configured, not claimed locally tested.

## Solved examples

| Run | Data/model interpretation | Objective (illustrative USD) | Max nodal residual (MW) | Max storage residual (MWh) |
|---|---|---:|---:|---:|
| demo | Synthetic 48h dispatch | 1,562,249.22 | 5.68e-13 | 2.91e-11 |
| el-nino | Hypothetical drought, 48h dispatch | 3,272,571.60 | 3.41e-13 | 2.01e-11 |
| investment2030 | Repeated-block annualized/disc. 2026–2030 expansion | 1,364,154,419.34 | 6.54e-13 | 6.09e-11 |
| xm-example | Observed national inputs + illustrative partial fleet | 1,853,360,880.36 | 5.68e-13 | 2.25e-11 |

**Objectives are not comparable across different horizons/data coverage.** The dispatch windows report OPEX, while expansion reports discounted annualized modeled costs. All runs terminated optimal and passed the 1e-5 physical-unit tolerance.

Demo, drought and all three investment periods have zero unserved energy at the tested assumptions. The XM hybrid has about **48.8% modeled unmet demand** because its partial source fleet and assumed hydro energy stores are not a national reconstruction. This is an intentionally exposed coverage mismatch, **not a claim about Colombian outages or adequacy**.

The investment example makes positive solar, wind and corridor expansion decisions; battery candidates are allowed but are not necessarily selected. Those values are solver demonstrations, not investment recommendations.

## Live XM and real cache replay

- Downloaded 17 metric/entity datasets with **44,906 normalized records**.
- Observation window 2023-12-31–2024-01-02; API current-list as-of date 2026-10-12.
- Independently replayed all 17 cached datasets offline, reproducing 44,906 rows without HTTP.
- Raw payload and processed-table checksum verification passed.
- Missing values: 3,534 for Gene/Recurso; 16,409 for DispoReal/Recurso, preserved as missing.
- Removed exact list metadata duplicates: 2 resource rows, 6 reservoir rows; originals retained raw.
- On 72 matched reservoir observations, treating the wire percentage as a fraction has maximum ratio error **4.895e-6**; dividing it by 100 gives error **0.9288**. Model uses stored/useful energy ratio instead.

## Grid and maps

- Source audit: 2,333 line features, 771 substations, 297 plants; 127 substations tagged 220/230/500 kV.
- Physical-candidate build executed: 272 voltage/junction buses, 337 retained Lines, 20 components, no inferred transformers.
- Geographic routing: 7/7 legacy corridors have an upstream OSM heuristic route. This is not validation of electrical circuit identity.
- Grid2Poster produced PNG/PDF/SVG maps from the original Colombian renderer. A delivered dispatch plot and poster were visually inspected.
- 18-region reduction was unit-tested on a **synthetic mapping**, including failure on incomplete/wrong region counts. No official 18-region map was supplied or claimed.

## Explicitly not executed/validated

- No genuine ERA5 retrieval (no CDS credential/terms acceptance supplied); synthetic-weather Atlite conversion passed.
- No full reviewed physical SIN or authoritative 18-subarea optimization (engineering data/crosswalks absent).
- No claim of official 147-bus topology, calibrated historical dispatch, policy forecast, reserve/N-1 security or hydro-cascade model.
- No remote GitHub publication, remote CI execution or DOI registration.

See `RESEARCH_READINESS.md` for the acceptance gates before using this scaffold in academic conclusions.
