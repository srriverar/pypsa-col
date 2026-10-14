"""Explicit opt-in external contract smoke test; normal CI remains offline."""

import os

import pytest

from pypsa_col.xm import XMClient


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("PYPSA_COL_RUN_LIVE") != "1", reason="set PYPSA_COL_RUN_LIVE=1 to contact XM"
)
def test_live_xm_catalog_and_national_demand(tmp_path):
    client = XMClient(tmp_path, timeout=30)
    catalog = client.catalog()
    rows = client.download("DemaReal", "Sistema", "2024-01-01", "2024-01-01", catalog)
    assert len(rows) == 24
    assert rows.value.notna().all()
    assert (rows.value > 0).all()
    assert set(rows.unit) == {"kWh"}
