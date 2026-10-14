import numpy as np
import pandas as pd
import pytest

from pypsa_col.climate import build_profiles, profiles_from_cutout, to_colombia, utc_window
from pypsa_col.io import deep_merge, snapshots


def test_local_hour_alignment_not_host_timezone():
    local = pd.date_range("2024-01-01", periods=48, freq="h")
    utc = utc_window(local)
    assert utc[0] == pd.Timestamp("2024-01-01 05:00")
    assert utc[-1] == pd.Timestamp("2024-01-03 04:00")
    values = pd.DataFrame({"solar": np.arange(48) / 48}, index=utc)
    assert to_colombia(values, local).index.equals(local)
    with pytest.raises(ValueError, match="every Colombian hour"):
        to_colombia(values.iloc[:-1], local)


def test_synthetic_is_labelled_and_solar_dark_at_midnight(workspace):
    root, config = workspace
    output = root / "profiles-test"
    build_profiles(root, config, output)
    frame = pd.read_csv(output / "renewable_profiles.csv", index_col=0, parse_dates=True)
    assert frame.min().min() >= 0 and frame.max().max() <= 1
    assert frame.loc[frame.index.hour == 0, "solar_cesar"].eq(0).all()
    assert "SYNTHETIC" in (output / "climate_provenance.json").read_text()


def test_missing_era5_never_falls_back(workspace):
    root, config = workspace
    config = deep_merge(config, {"climate": {"mode": "era5", "cutout": "cutouts/absent.nc"}})
    pytest.importorskip("atlite")
    with pytest.raises(FileNotFoundError, match="No synthetic fallback"):
        profiles_from_cutout(root, config)


@pytest.mark.integration
def test_atlite_conversion_on_synthetic_weather_not_real_era5(workspace):
    atlite = pytest.importorskip("atlite")
    import xarray as xr

    root, config = workspace
    local = snapshots(config)
    utc = utc_window(local)
    cutout_path = root / "synthetic-weather-fixture.nc"
    cutout = atlite.Cutout(
        cutout_path,
        module="era5",
        x=slice(-74.5, -71.0),
        y=slice(6.0, 12.5),
        time=slice(str(utc[0]), str(utc[-1])),
    )
    data = cutout.data
    coords = {name: data.coords[name] for name in ["time", "y", "x"]}
    shape = tuple(len(coords[k]) for k in coords)
    variables = {
        "wnd100m": 7.0,
        "wnd_shear_exp": 0.14,
        "wnd_azimuth": 0,
        "roughness": 0.1,
        "influx_toa": 1000,
        "influx_direct": 500,
        "influx_diffuse": 100,
        "albedo": 0.2,
        "solar_altitude": 0.8,
        "solar_azimuth": 3.14,
        "temperature": 298,
        "height": 50,
    }
    for name, value in variables.items():
        data[name] = xr.DataArray(
            np.full(shape, value, dtype=float), coords=coords, dims=list(coords)
        )
    data.attrs["prepared_features"] = ["wind", "influx", "temperature", "height"]
    data.to_netcdf(cutout_path)
    config = deep_merge(config, {"climate": {"mode": "era5", "cutout": str(cutout_path)}})
    result = profiles_from_cutout(root, config)
    assert result.shape == (48, 3)
    assert set(result.columns) == {"wind_guajira", "solar_cesar", "solar_santander"}
    assert np.isfinite(result.to_numpy()).all()
    assert result.min().min() >= 0 and result.max().max() <= 1
