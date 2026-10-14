# From executable scaffold to an academic PyPSA-col release

## Delivered and executable

- Pinned source clone/snapshot integrity verification, source audit and legacy-model extraction.
- Live XM client, 17 actually downloaded example datasets, raw hashes, unit/missingness QA.
- Conservative 220/230/500 kV OSM candidate construction and topology/parameter quality reports.
- Reviewed electrical override, transformer, resource, reservoir, river and regional busmap contracts.
- Seven-hub PyPSA dispatch, non-pumping reservoir hydro, battery losses and explicit unmet demand.
- Custom per-reservoir Linopy energy budgets and period-wise terminal conditions.
- Multi-period generator/battery/transport vintages, lifetimes, shared potentials and discounted annual costs.
- Atlite conversion path and synthetic-weather integration test; CDS credential-gated cutout preparation.
- Direct Grid2Poster rendering with source themes, routed overlays, metadata and original attribution.
- CLI, Snakemake DAG, offline tests, CI definition, self-contained reports and solved NetCDF examples.

## Not delivered as validated facts

- An official 147-bus electrical asset register or commissioned historical SIN topology.
- An official 18-subarea membership file or independently validated boundary overlay.
- Official transformer impedances, line circuit ratings, outage schedules or N-1 limits.
- A complete reviewed historical XM resource-to-bus/cascade map or measured nodal load dataset.
- Actual ERA5 cutouts, vetted land-eligibility masks or empirically calibrated renewable biases.
- Validated fuel/fixed/variable costs, currency conversion/inflation, retirement schedules or policy trajectories.
- Calibrated El Niño forecasts, reserve/security constraints, unit commitment, market rules or sector coupling.
- Hydro cascade routing, water head effects, environmental flow rules or downstream release coupling.
- A published paper/DOI, registered project affiliation, remote GitHub push or remote CI results.

## Recommended acceptance gates before a paper

### A. Data and rights

Approve the user-repository license and applicable XM/CDS/OSM/boundary terms.
Archive permitted input data with immutable checksums; separate restricted
engineering exports. Use dated authoritative station/circuit and subarea tables.

### B. Electrical validation

Reconcile station voltage levels, duplicate OSM geometry, cross-border assets,
commissioning years and transformer connections. Replace every default parameter
with a reviewed value or an explicit justified uncertainty distribution. Explain
every retained island/leaf and every removed self-loop. Compare with official
network counts and corridor/circuit summaries by matched asset ID, not km alone.

### C. Time-series and fleet validation

Map all historical capacity resources, withdrawals, commissioning changes and
outages. Reconcile `Gene`, demand, losses, imports and exports under their actual
measurement boundaries. Do not claim a match by scaling an incomplete fleet to
demand after seeing the result. Treat incomplete availability observations openly.

### D. Hydrology and climate

Verify prior-day reservoir conventions, useful energy ratings, river coverage and
cascade conservation. Add downstream water transfers, environmental release and
terminal water value assumptions as required. Validate multi-year ERA5 resource
profiles against observations; assess coincident drought/demand/wind/solar risk.

### E. Economics and policy

Use a stated currency/price year and financial convention. Check capital-cost
annualization, asset lifetimes, terminal effects and allowed reinforcements.
Model relevant reliability, reserve, environmental and policy constraints before
claiming least-cost national pathways. Separate cost-optimal screening from
market prices, siting consent, deliverability or investment decisions.

### F. Verification and reproducibility

Reproduce historical dispatch and independent operational/market statistics on
out-of-sample windows; report errors rather than only visual similarity. Compare
full and clustered network outcomes. Run grid-resolution, temporal-resolution,
solver-tolerance, weather-year, cost and drought sensitivity studies. Archive the
code commit, environment, study YAMLs, data manifests and complete result tables.

Until these gates are met, publish software demonstrations with limitations,
not purported official SIN forecasts or historical congestion/reliability findings.
