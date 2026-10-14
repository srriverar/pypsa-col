import json

import numpy as np
import pandas as pd
import pytest

from pypsa_col.io import deep_merge
from pypsa_col.network import aggregate_regions, physical_candidate, seven_hub, topology_report
from pypsa_col.source import verify_source


def test_source_pin_actual_counts_and_routing(workspace):
    root, config = workspace
    verify_source(root, config)
    inventory = json.loads((root / "resources/source/inventory.json").read_text())
    assert inventory["osm_lines"] == 2333
    assert inventory["osm_substations"] == 771
    assert inventory["substations_tagged_220_230_500"] == 127
    assert len(inventory["grid2poster_themes"]) == 18
    routes = json.loads((root / "resources/source/routes.geojson").read_text())
    assert len(routes["features"]) == 7
    assert inventory["routing"]["enlaces_con_ruta_osm"] == 7


def test_transport_has_no_reverse_efficiency_gain(workspace):
    root, _ = workspace
    n = seven_hub(root)
    assert len(n.buses) == len(n.links) == 7
    assert np.allclose(n.links.efficiency, 1)
    assert np.allclose(n.links.p_min_pu, -1)
    assert n.meta["electrical_kvl"] is False
    assert topology_report(n)["connected_components"] == 1


@pytest.fixture(scope="module")
def physical(workspace):
    root, config = workspace
    return physical_candidate(
        root, deep_merge(config, {"network": {"mode": "physical"}}), root / "physical-test"
    )


def test_voltage_levels_not_connected_without_transformer(physical):
    n = physical
    assert len(n.transformers) == 0
    assert all(
        n.buses.loc[r.bus0, "v_nom"] == n.buses.loc[r.bus1, "v_nom"] for r in n.lines.itertuples()
    )
    assert (n.lines.x > 0).all() and (n.lines.s_nom > 0).all()
    assert topology_report(n)["connected_components"] == 20
    assert len(n.buses) == 272
    assert len(n.lines) == 337
    assert n.meta["parameters_reviewed"] is False


def test_reviewed_region_transport_reduction(physical):
    names = physical.buses.index
    mapping = pd.DataFrame(
        {
            "bus": names,
            "region": ["fixture_A" if i % 2 else "fixture_B" for i in range(len(names))],
            "reviewed": True,
            "source": "synthetic test mapping — NOT official regions",
        }
    )
    n = aggregate_regions(physical, mapping, expected=2)
    assert len(n.buses) == 2
    assert n.meta["electrical_kvl"] is False
    assert (n.links.efficiency == 1).all()
    with pytest.raises(ValueError, match="Expected 18"):
        aggregate_regions(physical, mapping, expected=18)
    with pytest.raises(ValueError, match="every voltage-level"):
        aggregate_regions(physical, mapping.iloc[:-1], expected=2)
    mapping.loc[0, "reviewed"] = False
    with pytest.raises(ValueError, match="reviewed=true"):
        aggregate_regions(physical, mapping, expected=2)
