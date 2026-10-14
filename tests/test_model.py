import copy

import numpy as np
import pandas as pd
import pypsa
import pytest

from pypsa_col.climate import build_profiles
from pypsa_col.inputs import allocate_demand, prepare_inputs
from pypsa_col.io import deep_merge
from pypsa_col.model import annuity, assemble_network, period_weights, solve
from pypsa_col.network import build_base
from pypsa_col.results import validate_solution


def prepare(root, config, run_id):
    config = deep_merge(config, {"run": {"id": run_id}})
    resources = root / "resources" / run_id
    build_base(root, config, resources)
    build_profiles(root, config, resources)
    prepare_inputs(root, config, resources)
    return config, resources


@pytest.fixture(scope="module")
def solved_demo(workspace):
    root, config = workspace
    config, resources = prepare(root, config, "test-demo")
    n = solve(root, config, resources, root / "results/test-demo")
    return root, config, resources, n


@pytest.mark.integration
def test_demo_optimal_balanced_and_hydro_nonpumping(solved_demo):
    _, _, _, n = solved_demo
    assert n.objective > 0
    assert validate_solution(n)["passed"]
    shed = n.generators.index[n.generators.carrier == "load_shedding"]
    assert n.generators_t.p[shed].abs().sum().sum() < 1e-5
    hydro = n.storage_units.carrier.eq("hydro")
    assert (n.storage_units.loc[hydro, "p_min_pu"] == 0).all()
    assert (n.storage_units.loc[hydro, "efficiency_dispatch"] == 1).all()
    assert not n.buses_t.marginal_price.empty
    for name in n.storage_units.index[hydro]:
        assert (
            n.storage_units_t.state_of_charge[name].iloc[-1]
            >= n.storage_units.loc[name, "state_of_charge_initial"] - 1e-5
        )


def test_netcdf_roundtrip_and_omitted_zero_charging(solved_demo):
    root, _, _, _ = solved_demo
    n = pypsa.Network(root / "results/test-demo/network.nc")
    assert validate_solution(n)["passed"]


@pytest.mark.integration
def test_drought_water_budgets_and_cost_increase(solved_demo):
    root, base, _, normal = solved_demo
    config = deep_merge(
        base, {"hydro": {"inflow_multiplier": 0.55, "energy_budget_fraction": 0.55}}
    )
    config, resources = prepare(root, config, "test-drought")
    n = solve(root, config, resources, root / "results/test-drought")
    assert n.objective > normal.objective
    hydro = pd.read_csv(resources / "hydro.csv").set_index("name")
    for name in hydro.index:
        assert (
            n.storage_units_t.p_dispatch[name].sum()
            <= hydro.loc[name, "baseline_inflow_mwh"] * 0.55 + 1e-5
        )
    assert validate_solution(n)["passed"]


@pytest.mark.integration
def test_multi_period_vintages_lifetimes_and_shared_limits(workspace):
    root, base = workspace
    config = deep_merge(
        base,
        {
            "investment": {"enabled": True, "annualize_short_horizon": True},
            "hydro": {"terminal": "cyclic"},
        },
    )
    config = copy.deepcopy(config)
    for candidate in config["investment"]["candidates"]:
        candidate["overnight_usd_per_mw"] = 1000  # deliberately cheap to exercise build decisions
        candidate["lifetime"] = 2  # exact period-boundary retirement
    config, resources = prepare(root, config, "test-investment")
    n = solve(root, config, resources, root / "results/test-investment")
    assert list(n.investment_periods) == [2026, 2028, 2030]
    assert n.snapshot_weightings.groupby(level=0).generators.sum().eq(8760).all()
    assert n.snapshot_weightings.stores.eq(1).all()
    assert n.generators.loc[n.generators.p_nom_extendable, "p_nom_opt"].sum() > 1
    for candidate in config["investment"]["candidates"]:
        for period in n.investment_periods:
            names = [
                f"{candidate['name']}__{year}"
                for year in n.investment_periods
                if year <= period < year + 2
            ]
            used = (
                n.generators.loc[names, "p_nom_opt"].sum()
                + n.generators.loc[candidate["name"], "p_nom"]
            )
            assert used <= candidate["max_mw"] + 1e-5
        assert n.generators_t.p.loc[2028, f"{candidate['name']}__2026"].abs().max() < 1e-5
        assert n.generators_t.p.loc[2026, f"{candidate['name']}__2028"].abs().max() < 1e-5
    assert validate_solution(n)["passed"]
    assert validate_solution(pypsa.Network(root / "results/test-investment/network.nc"))["passed"]


def test_initial_per_period_is_not_overridden_by_cyclic(workspace):
    root, config = workspace
    config = deep_merge(config, {"investment": {"enabled": True, "annualize_short_horizon": True}})
    config, resources = prepare(root, config, "test-initial-period")
    n = assemble_network(root, config, resources)
    hydro = n.storage_units[n.storage_units.carrier.eq("hydro")]
    assert hydro.state_of_charge_initial_per_period.all()
    assert not hydro.cyclic_state_of_charge_per_period.any()


def test_annualization_is_explicit(workspace):
    root, config = workspace
    config = deep_merge(config, {"investment": {"enabled": True, "annualize_short_horizon": False}})
    config, resources = prepare(root, config, "test-no-annualization")
    with pytest.raises(ValueError, match="annualize_short_horizon"):
        assemble_network(root, config, resources)


def test_weighting_and_annuity_math():
    assert annuity(0, 20) == 0.05
    expected = sum(1 / 1.05**i for i in range(5))
    assert period_weights([2026, 2028, 2030], [2, 2, 1], 0.05).objective.sum() == pytest.approx(
        expected
    )
    with pytest.raises(ValueError, match="consecutive"):
        period_weights([2026, 2028], [1, 1], 0.05)


def test_load_allocation_conserves_and_rejects_bad_weights():
    total = pd.Series([100.0, 200.0], index=pd.date_range("2024-01-01", periods=2, freq="h"))
    weights = pd.DataFrame({"bus": ["A", "B"], "weight": [0.3, 0.7]})
    result = allocate_demand(total, weights, ["A", "B", "C"])
    assert np.allclose(result.sum(axis=1), total)
    assert result.C.eq(0).all()
    weights.loc[0, "weight"] = 0.4
    with pytest.raises(ValueError, match="sum to 1"):
        allocate_demand(total, weights, ["A", "B"])
