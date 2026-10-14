# Changelog

## 0.1.0 — 2026-10-12

Initial runnable research scaffold built against the locked ColombiaCongestionV2 source.

- PyPSA dispatch and multi-period generator/battery/transport investment vintages.
- Energy-limited non-pumping hydro, terminal conditions and Linopy drought budgets.
- Live XM catalog/metric ingestion, raw cache/provenance and strict dimensional handling.
- Verified handling of legacy double-encoded catalog, flat daily entity records,
  exact duplicate list metadata, missing resource observations and percentage ambiguity.
- Same-voltage physical OSM candidates, reviewed engineering/crosswalk contracts,
  and explicitly non-AC 18-region transport aggregation.
- Atlite/ERA5 adapters with correct timezone conversion and credential gating.
- Direct Grid2Poster integration, source-route quality reports and attributed artifacts.
- CLI, Snakemake DAG, CI definition, tests and self-contained reports.

This version does not claim an official/validated full SIN network or forecast.
See docs/RESEARCH_READINESS.md for acceptance gates and exclusions.
