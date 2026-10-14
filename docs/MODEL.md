# Model formulation and scope

## Variables, units and balance

Power is MW, electrical-equivalent energy is MWh, branch nameplates are MW for
transport Links and MVA for physical Lines/Transformers. Objective costs are
**illustrative USD**, with a common assumed price basis. No exchange-rate or
inflation transformation is implied by reusing legacy demonstration cost numbers.

For each bus and hourly snapshot, generation + net storage injection − load −
outgoing branch injections = 0. Explicit high-penalty load shedding is a separate
`Generator` carrier `load_shedding`. It is reported separately, never presented
as real generation. Turning it off can make an incomplete network infeasible;
non-optimal solver status aborts the run.

Generators obey `0 ≤ p[t] ≤ p_nom * p_max_pu[t]`. PyPSA handles passive AC-network
Kirchhoff voltage constraints on the physical candidate; the seven-hub and regional
transport representations only enforce flow limits and nodal balance. There is
no nonlinear AC-voltage/reactive-power validation, N-1 security, unit commitment,
reserve requirement or detailed transmission loss model in this release.

## Reservoir hydro

Hydro uses `StorageUnit` with `p_min_pu=0` so the reservoir **cannot charge from the
electricity grid**. For a sampled one-hour interval:

```text
e[t] = e[t-1] + inflow[t] - dispatch[t] - spill[t]
0 ≤ e[t] ≤ p_nom * max_hours = e_nom
0 ≤ dispatch[t] ≤ turbine_MW * availability[t]
```

The general PyPSA equation also supports charge/discharge efficiencies and standing
losses. XM useful energy and `AporEner` are treated here as **electrical-equivalent**
energy; `efficiency_dispatch=1` avoids counting turbine efficiency twice. Water
in m³, river discharge in m³/s, variable heads and cascades require a different
physical conversion, not this simplified energy-store equation.

Daily inflow MWh is spread uniformly over the day's 24 local hours. This exactly
conserves the reported daily energy but is not a measured hourly hydrograph.
Initial stored energy uses the **preceding day's** observation in `xm_mapped`,
not an end-of-day value from the first dispatch day. This is an explicit boundary
convention that researchers must verify against the source reporting practice.
No initial water is created from realized historical generation.

### Terminal conditions

- `initial_min`: final reservoir energy is at least initial energy; prevents a
  short dispatch horizon from draining free water. In multi-period mode this
  boundary is imposed separately in each period, with repeated initial energy.
- `cyclic`: end state equals starting state; initial observation is deliberately
  ignored. The representative-block investment demonstration cycles independently
  within each modeled period, not across unrelated investment years.

For real seasonal planning use a long chronological horizon and justified future
water values/terminal targets rather than a repeated two-day cycle.

### Hypothetical El Niño constraints

The El Niño configuration is a **stress-test assumption**, not an estimated
climatological effect. It supplies both:

1. An inflow multiplier `α` (0.55 in the delivered stress test).
2. A custom Linopy cap per reservoir and period:

```text
sum_t dispatch[t] * physical_hours[t] ≤ β * baseline_inflow_energy
```

`baseline_inflow_energy` is calculated before applying `α`; therefore using
`α=β=0.55` does not accidentally square the drought factor. Terminal constraints
and the energy cap may be redundant in some cases, which is acceptable and
explicit. Either factor can be varied separately for sensitivity analysis.

Batteries allow both charging and discharging with efficiencies, maximum hours
and cyclic boundaries. Simultaneous operation is not explicitly prohibited by a
binary variable; positive losses and positive cycling cost discourage it under
this LP's nonnegative-cost assumptions. Revisit that behavior for negative-price
or subsidy cases.

## Perfect-foresight investment periods to 2030

The example has periods `[2026, 2028, 2030]` representing `[2, 2, 1]` calendar years:
2026–2027, 2028–2029 and 2030. It covers the modeled years through 2030 inclusive,
not an undefined infinite terminal block. Period blocks must be consecutive.

For discount rate `r`:

```text
period_objective_weight[p] = sum_y_in_block (1+r)^(-(y - first_year))
annualized_capital_cost = overnight_USD_per_MW * (annuity(r, lifetime) + FOM_fraction)
```

Generator, battery and transport-expansion candidates have independent vintage
variables, `build_year` and `lifetime`. A 2028 vintage cannot operate in 2026;
a vintage with lifetime 2 built in 2026 cannot operate in 2028. Tests exercise
both zero-before-build and zero-after-retirement dispatch. Existing demo assets
have unlimited modeled life; real studies must supply their retirement assumptions.
Retirement within a multi-year block is not resolved subannually; align periods
with material commissioning/retirement decisions or use a finer time structure.

A shared technical-potential constraint limits the **sum of active vintages** at
each renewable site, including the configured existing capacity. Without this,
each period could erroneously install the site's full potential again. Battery
and transport candidates likewise share a `max_new_mw` cap across active vintages.
Transport expansion is additional symmetric lossless Links; automatic AC line
expansion/reinforcement equivalencing is not implemented.

The objective charges annualized CAPEX/FOM in each period where a vintage is active,
plus weighted OPEX. It does not charge the entire overnight CAPEX at build year
and then annualized CAPEX again. This is an annualized-service-cost convention;
there is no separate terminal salvage value or post-2030 operating-cost model.
Do not compare it directly with an overnight-cashflow NPV without reconciling the
accounting convention and horizon truncation.

## Short-horizon scaling — crucial distinction

The delivered investment example repeats one contiguous **48-hour** synthetic
weather block and uses a hypothetical 20% inflow reduction. Per modeled year:

```text
snapshot_weightings.objective = 8760 / 48
snapshot_weightings.generators = 8760 / 48
snapshot_weightings.stores = 1 hour
```

The economic and annual-energy weights represent repetitions; they **do not**
make a single storage transition last 182.5 hours. Hydro energy budgets use the
physical sampled hours, separately for each investment period. Typical period
`years` are kept separate from economic discount weights.

The current multi-period convenience mode repeats one weather chronology across
periods and scales demand by the configured annual growth. It does not implement
period-specific climate ensembles or disjoint representative-day storage linking.
Use full chronological profiles (typically 8,760 hours), multi-year sensitivity
runs and a deliberate temporal-aggregation method for research. Leap-year 8,784-hour
inputs are supported as raw hourly chronology; choose and document whether you
retain all hours or normalize annual economic weights to 8,760.

A short expansion horizon without explicit `annualize_short_horizon=true` is
rejected. The pure dispatch demo has no capacity decision and reports only the
modeled-window OPEX, not an annual system cost.

## Price interpretation and post-solve validation

Use `network.buses_t.marginal_price`; the pasted `p_marginal_pricing` attribute is
not a PyPSA result field. PyPSA handles objective/period-weight normalization of
these nodal balance duals. These prices are model shadow prices, not Colombia's
actual national bolsa settlement prices. XM reference prices remain COP/MWh.
No default FX conversion or claim of observed nodal Colombian prices is made.

Accepted runs require solver status `ok/optimal` and independently recomputed:

- Nodal MW residuals.
- Storage/water MWh residuals, including cyclic period boundaries and efficiencies.
- Branch thermal/transfer limit violations.
- No hydro charging from the grid.
- Hydro terminal energy and custom drought budget compliance.

Default numerical tolerance is `1e-5` in the relevant physical units. NetCDF can
omit all-zero storage charging/spill columns; the reporter restores those **output
zeros**, not missing raw observations. Failures abort with diagnostics.

The pinned Linopy 0.10 stack emits transition warnings about future `v1` semantics.
This tested PyPSA 1.2.4 implementation relies on the default legacy semantics;
do **not** opt into Linopy `v1` without adapting PyPSA's MultiIndex/masked-variable
constraints and rerunning the full test suite. Upgrade the pinned solver stack
as a reviewed change, not an untested major dependency bump.
