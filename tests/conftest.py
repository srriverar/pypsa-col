from pathlib import Path

import pytest

from pypsa_col.io import deep_merge, load_config
from pypsa_col.source import audit_source

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def workspace(tmp_path_factory):
    root = tmp_path_factory.mktemp("pypsa_col")
    config = deep_merge(
        load_config(ROOT / "config/demo.yaml"),
        {
            "source": {
                "path": str(ROOT / "external/colombiacongestionV2"),
                "lock": str(ROOT / "config/sources.lock.json"),
            },
            "climate": {"sites": str(ROOT / "data/reference/renewable_sites.geojson")},
        },
    )
    audit_source(root, config)
    return root, config
