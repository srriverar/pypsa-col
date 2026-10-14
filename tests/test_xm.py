import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import requests

from pypsa_col.inputs import series_for
from pypsa_col.xm import (
    XMClient,
    XMError,
    catalog_frame,
    convert_units,
    date_chunks,
    decode_json,
    normalize,
)

FIXTURES = Path(__file__).parent / "fixtures"
HOURLY = {
    "MetricId": "DemaReal",
    "Entity": "Sistema",
    "Type": "HourlyEntities",
    "MetricUnits": "kWh",
}


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def test_legacy_catalog_is_double_encoded():
    raw = json.dumps(json.dumps({"Gene": [[0, "Generation", "Sistema", "Horaria"]]}))
    assert isinstance(decode_json(raw), dict)
    assert catalog_frame(raw).iloc[0].Type == "HourlyEntities"


def test_live_catalog_structure():
    frame = catalog_frame(fixture("xm_catalog_excerpt.json"))
    assert frame.loc[frame.MetricId.eq("DemaReal"), "MetricUnits"].iloc[0] == "kWh"
    assert not frame.duplicated(["MetricId", "Entity"]).any()


def test_real_hourly_fixture_time_and_units():
    frame = normalize(fixture("xm_demand_2024_01_01.json"), HOURLY)
    assert len(frame) == 24
    assert frame.timestamp.iloc[0] == pd.Timestamp("2024-01-01 00:00")
    assert frame.timestamp.iloc[-1] == pd.Timestamp("2024-01-01 23:00")
    assert frame.entity_code.unique().tolist() == ["Sistema"]
    converted = convert_units(frame, "hourly_mw")
    assert converted.value.iloc[0] == pytest.approx(7236.89331)
    assert frame.value.iloc[0] == pytest.approx(7236893.31)  # input not mutated


def test_daily_flat_and_nested_shapes():
    spec = {
        "MetricId": "CapEfecNeta",
        "Entity": "Recurso",
        "Type": "DailyEntities",
        "MetricUnits": "kW",
    }
    frame = normalize(fixture("xm_capacity_excerpt.json"), spec)
    assert frame.entity_code.iloc[0] == "2QBW"
    assert convert_units(frame, "power_mw").value.iloc[0] == pytest.approx(19.9)
    nested = {
        "Items": [
            {
                "Date": "2024-01-01",
                "DailyEntities": [{"Id": "Recurso", "Values": {"Code": "PLANT", "Value": "100"}}],
            }
        ]
    }
    assert normalize(nested, spec).value.iloc[0] == 100


def test_reservoir_name_not_generic_id():
    spec = {
        "MetricId": "VoluUtilDiarEner",
        "Entity": "Embalse",
        "Type": "DailyEntities",
        "MetricUnits": "kWh",
    }
    frame = normalize(fixture("xm_reservoir_excerpt.json"), spec)
    assert frame.entity_code.iloc[0] == "AGREGADO BOGOTA"
    assert convert_units(frame, "energy_mwh").value.iloc[0] > 1e6


def test_current_lists_exact_duplicates_only():
    spec = {
        "MetricId": "ListadoRecursos",
        "Entity": "Sistema",
        "Type": "ListsEntities",
        "MetricUnits": "",
    }
    payload = {
        "Items": [
            {
                "Date": "2026-10-12",
                "ListEntities": [
                    {"Id": "Sistema", "Values": {"Code": "P", "Name": "Fixture plant"}},
                    {"Id": "Sistema", "Values": {"Code": "P", "Name": "Fixture plant"}},
                ],
            }
        ]
    }
    frame = normalize(payload, spec)
    assert len(frame) == 1 and frame.attrs["exact_list_duplicates_removed"] == 1
    payload["Items"][0]["ListEntities"][1]["Values"]["Name"] = "Conflicting name"
    with pytest.raises(XMError, match="duplicate"):
        normalize(payload, spec)


def test_missing_hour_does_not_shift_or_fill():
    payload = fixture("xm_demand_2024_01_01.json")
    del payload["Items"][0]["HourlyEntities"][0]["Values"]["Hour02"]
    with pytest.raises(XMError, match="Hour02"):
        normalize(payload, HOURLY)


def test_null_hour_stays_missing_and_model_rejects():
    payload = fixture("xm_demand_2024_01_01.json")
    payload["Items"][0]["HourlyEntities"][0]["Values"]["Hour02"] = None
    frame = normalize(payload, HOURLY)
    assert np.isnan(frame.value.iloc[1])
    with pytest.raises(ValueError, match="Incomplete"):
        series_for(frame, "Sistema", pd.date_range("2024-01-01", periods=24, freq="h"))


def test_duplicate_time_series_rejected():
    payload = fixture("xm_demand_2024_01_01.json")
    payload["Items"].append(copy.deepcopy(payload["Items"][0]))
    with pytest.raises(XMError, match="duplicate"):
        normalize(payload, HOURLY)


def test_units_cannot_silently_cross_dimensions():
    frame = pd.DataFrame({"unit": ["m3"], "value": [100.0]})
    with pytest.raises(XMError, match="Cannot convert"):
        convert_units(frame, "energy_mwh")
    frame = pd.DataFrame({"unit": ["COP/kWh"], "value": [320]})
    assert convert_units(frame, "price_cop_mwh").value.iloc[0] == 320000


def test_ambiguous_xm_percent_is_refused():
    frame = pd.DataFrame({"metric": ["PorcVoluUtilDiar"], "unit": ["%"], "value": [0.63]})
    with pytest.raises(XMError, match="labelled percent"):
        convert_units(frame, "fraction")


@pytest.mark.parametrize(
    "start,end",
    [("2024-01-01", "2024-02-29"), ("2023-12-31", "2024-01-01"), ("2024-02-29", "2024-02-29")],
)
def test_chunks_exact_no_overlap_including_leap_day(start, end):
    chunks = list(date_chunks(start, end))
    result = pd.DatetimeIndex([])
    for first, last in chunks:
        block = pd.date_range(first, last)
        assert 1 <= len(block) <= 30
        result = result.append(block)
    assert result.equals(pd.date_range(start, end))
    assert not result.has_duplicates


def test_invalid_chunk_request():
    with pytest.raises(ValueError):
        list(date_chunks("2024-01-02", "2024-01-01"))
    with pytest.raises(ValueError):
        list(date_chunks("2024-01-01", "2024-02-01", 31))


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        response = requests.Response()
        response.status_code = 200
        response.url = url
        response._content = (FIXTURES / "xm_demand_2024_01_01.json").read_bytes()
        return response


def test_cached_post_offline_replay_and_tamper(tmp_path):
    body = {
        "MetricId": "DemaReal",
        "Entity": "Sistema",
        "StartDate": "2024-01-01",
        "EndDate": "2024-01-01",
        "Filter": [],
    }
    session = FakeSession()
    client = XMClient(tmp_path, session=session)
    a = client.request("hourly", body)
    assert len(session.calls) == 1
    assert session.calls[0][2] == (10, 60)
    replay = XMClient(tmp_path, offline=True, session=FakeSession())
    assert replay.request("hourly", body) == a
    assert not replay.session.calls
    path = next(p for p in (tmp_path / "DemaReal").glob("*.json") if ".metadata." not in p.name)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(XMError, match="integrity"):
        replay.request("hourly", body)


def test_offline_cache_miss_and_unknown_entity(tmp_path):
    client = XMClient(tmp_path, offline=True)
    with pytest.raises(XMError, match="cache miss"):
        client.request("daily", {"MetricId": "AporEner"})
    with pytest.raises(XMError, match="unique definition"):
        client.download("DemaReal", "Embalse", "2024-01-01", "2024-01-01", pd.DataFrame([HOURLY]))


def test_processed_manifest_rejects_mixed_revision(tmp_path):
    from pypsa_col.io import sha256, write_json
    from pypsa_col.xm import verify_processed

    table = tmp_path / "DemaReal__Sistema.csv"
    table.write_text("value\n100\n")
    write_json(
        tmp_path / "manifest.json",
        {"datasets": [{"metric": "DemaReal", "entity": "Sistema", "sha256": sha256(table)}]},
    )
    assert verify_processed(tmp_path, [("DemaReal", "Sistema")])
    table.write_text("value\n200\n")
    with pytest.raises(XMError, match="integrity failure"):
        verify_processed(tmp_path)
