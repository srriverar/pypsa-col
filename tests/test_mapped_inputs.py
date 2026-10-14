from pathlib import Path

import numpy as np
import pandas as pd
import pypsa
import pytest

from pypsa_col.inputs import _mapped_inputs
from pypsa_col.io import deep_merge


def write_metric(folder: Path, metric, entity, unit, values):
    rows = [
        {
            "metric": metric,
            "entity": entity,
            "unit": unit,
            "timezone": "America/Bogota",
            "timestamp": date,
            "entity_code": code,
            "value": value,
        }
        for date, code, value in values
    ]
    pd.DataFrame(rows).to_csv(folder / f"{metric}__{entity}.csv", index=False)


@pytest.fixture
def mapped_case(tmp_path, workspace):
    _, base = workspace
    folder, user = tmp_path / "xm", tmp_path / "user"
    folder.mkdir()
    user.mkdir()
    for name, columns in {
        "resource_busmap": [
            {
                "resource_code": "G",
                "name": "Gas",
                "bus": "A",
                "carrier": "gas",
                "marginal_cost": 50,
                "efficiency": 0.5,
                "profile": "",
            },
            {
                "resource_code": "H",
                "name": "Hydro",
                "bus": "A",
                "carrier": "hydro",
                "marginal_cost": 5,
                "efficiency": 1.0,
                "profile": "",
            },
        ],
        "reservoir_map": [{"reservoir": "LAKE", "resource_code": "H"}],
        "river_map": [{"river": "RIVER", "reservoir": "LAKE", "share": 1.0}],
        "load_weights": [{"bus": "A", "weight": 1.0}],
    }.items():
        table = pd.DataFrame(columns)
        table["source"] = "synthetic test fixture, not Colombian data"
        table["reviewed"] = True
        table.to_csv(user / f"{name}.csv", index=False)
    write_metric(
        folder,
        "CapEfecNeta",
        "Recurso",
        "kW",
        [("2024-01-01", "G", 100000), ("2024-01-01", "H", 50000)],
    )
    write_metric(folder, "VoluUtilDiarEner", "Embalse", "kWh", [("2023-12-31", "LAKE", 500000)])
    write_metric(folder, "CapaUtilDiarEner", "Embalse", "kWh", [("2024-01-01", "LAKE", 1000000)])
    write_metric(folder, "AporEner", "Rio", "kWh", [("2024-01-01", "RIVER", 24000)])
    index = pd.date_range("2024-01-01", periods=24, freq="h", name="snapshot")
    write_metric(folder, "DemaReal", "Sistema", "kWh", [(t, "Sistema", 100000) for t in index])
    config = deep_merge(base, {"inputs": {"mode": "xm_mapped", "xm_dir": "xm", "user_dir": "user"}})
    n = pypsa.Network()
    n.add("Bus", "A")
    return tmp_path, config, n, index, pd.DataFrame(index=index)


def test_mapped_hydro_power_energy_and_demand_units(mapped_case):
    generators, hydro, demand, inflow, availability, hydro_availability = _mapped_inputs(
        *mapped_case
    )
    assert generators.p_nom.iloc[0] == 100  # 100000 kW -> 100 MW
    assert hydro.p_nom.iloc[0] == 50
    assert hydro.e_nom.iloc[0] == 1000  # reservoir energy, not turbine power
    assert hydro.soc_initial.iloc[0] == 500
    assert inflow.iloc[:, 0].eq(1).all()  # 24000 kWh/day / 1000 / 24
    assert inflow.sum().iloc[0] == 24
    assert demand.sum().sum() == 2400
    assert np.allclose(availability, 1)
    assert np.allclose(hydro_availability, 1)


def test_mapped_fleet_cannot_silently_drop_a_resource(mapped_case):
    root, *_ = mapped_case
    p = root / "user/resource_busmap.csv"
    df = pd.read_csv(p)
    df[df.resource_code != "G"].to_csv(p, index=False)
    with pytest.raises(ValueError, match="lack a reviewed busmap"):
        _mapped_inputs(*mapped_case)


def test_mapped_unreviewed_entries_are_refused(mapped_case):
    root, *_ = mapped_case
    p = root / "user/resource_busmap.csv"
    df = pd.read_csv(p)
    df.loc[0, "reviewed"] = False
    df.to_csv(p, index=False)
    with pytest.raises(ValueError, match="reviewed=true"):
        _mapped_inputs(*mapped_case)


def test_river_double_counting_is_refused(mapped_case):
    root, *_ = mapped_case
    p = root / "user/river_map.csv"
    df = pd.read_csv(p)
    pd.concat([df, df]).to_csv(p, index=False)
    with pytest.raises(ValueError, match="no double counting"):
        _mapped_inputs(*mapped_case)


def test_initial_reservoir_state_requires_previous_day(mapped_case):
    root, *_ = mapped_case
    p = root / "xm/VoluUtilDiarEner__Embalse.csv"
    df = pd.read_csv(p)
    df["timestamp"] = "2024-01-01"
    df.to_csv(p, index=False)
    with pytest.raises(ValueError, match="Incomplete"):
        _mapped_inputs(*mapped_case)
