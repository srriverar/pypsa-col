"""Atlite wind/PV profiles, with explicit UTC-to-Colombia alignment and no fallback."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from .io import sha256, snapshots, write_json


def utc_window(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    if index.tz is not None:
        raise ValueError("Expected naive Colombian wall time")
    return index.tz_localize("America/Bogota").tz_convert("UTC").tz_localize(None)


def to_colombia(frame: pd.DataFrame, expected: pd.DatetimeIndex) -> pd.DataFrame:
    result = frame.copy()
    result.index = pd.DatetimeIndex(result.index)
    result.index = result.index.tz_localize("UTC").tz_convert("America/Bogota").tz_localize(None)
    result = result.reindex(expected)
    if result.isna().any().any():
        raise ValueError("ERA5 profiles do not cover every Colombian hour (check +5h UTC padding).")
    if not np.isfinite(result.to_numpy()).all():
        raise ValueError("Non-finite renewable capacity factors")
    if (result < -1e-8).any().any() or (result > 1 + 1e-8).any().any():
        raise ValueError("Capacity factors outside [0,1]")
    return result.clip(0, 1)


def prepare_cutout(root: Path, config: dict) -> Path:
    import atlite
    import geopandas as gpd

    spec = config["climate"]
    if spec["mode"] != "era5":
        raise ValueError("build-cutout is only for climate.mode=era5")
    path = root / spec["cutout"]
    if not path.exists() and not (
        os.environ.get("CDSAPI_KEY") or Path.home().joinpath(".cdsapirc").exists()
    ):
        raise RuntimeError(
            "ERA5 requires CDS credentials outside the repository and accepted dataset terms. "
            "See docs/CLIMATE.md. Synthetic substitution is deliberately disabled."
        )
    regions = gpd.read_file(root / spec["sites"]).to_crs(4326)
    xmin, ymin, xmax, ymax = regions.total_bounds
    utc = utc_window(snapshots(config))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        cutout = atlite.Cutout(path)
    else:
        cutout = atlite.Cutout(
            path,
            module="era5",
            x=slice(xmin - 0.25, xmax + 0.25),
            y=slice(ymin - 0.25, ymax + 0.25),
            time=slice(str(utc[0]), str(utc[-1])),
            dx=spec["dx"],
            dy=spec["dy"],
        )
    if not pd.DatetimeIndex(utc).isin(pd.DatetimeIndex(cutout.data.time.values)).all():
        raise ValueError("Existing cutout has a different time range; use a new cutout filename.")
    # Atlite handles CDS retrieval and variables. Calls can take hours on CDS queues.
    cutout.prepare(features=["wind", "influx", "temperature", "height"])
    write_json(
        path.with_suffix(".manifest.json"),
        {
            "module": "era5",
            "atlite_version": atlite.__version__,
            "sha256": sha256(path),
            "utc_start": str(utc[0]),
            "utc_end": str(utc[-1]),
            "sites_sha256": sha256(root / spec["sites"]),
            "spatial_resolution_degrees": [spec["dx"], spec["dy"]],
            "source": "Copernicus Climate Data Store ERA5 single levels",
        },
    )
    return path


def profiles_from_cutout(root: Path, config: dict) -> pd.DataFrame:
    import atlite
    import geopandas as gpd

    spec = config["climate"]
    path = root / spec["cutout"]
    if not path.exists():
        raise FileNotFoundError(
            "ERA5 cutout missing; run build-cutout first. No synthetic fallback."
        )
    cutout = atlite.Cutout(path)
    sites = gpd.read_file(root / spec["sites"]).to_crs(4326).set_index("name")
    if sites.index.has_duplicates or set(sites.carrier) - {"wind", "solar"}:
        raise ValueError("Sites need unique names and wind/solar carriers")
    from shapely.geometry import box

    extent = box(*cutout.grid.total_bounds)
    if not sites.geometry.map(extent.covers).all():
        raise ValueError("Cutout does not fully cover every site polygon; use a wider cutout.")
    cell_area_km2 = cutout.grid.to_crs(6933).area.to_numpy() / 1e6
    frames = []
    for carrier, region in sites.groupby("carrier"):
        matrix = cutout.indicatormatrix(region.geometry).multiply(cell_area_km2).tocsr()
        if (np.asarray(matrix.sum(axis=1)).ravel() <= 0).any():
            raise ValueError("A renewable site has no overlap with ERA5 cells")
        idx = pd.Index(region.index, name="site")
        kwargs = dict(matrix=matrix, index=idx, per_unit=True, show_progress=False)
        if carrier == "wind":
            result = cutout.wind(turbine=spec["turbine"], **kwargs)
        else:
            result = cutout.pv(
                panel=spec["panel"],
                orientation={"slope": spec["pv_slope"], "azimuth": spec["pv_azimuth"]},
                **kwargs,
            )
        frame = result.transpose("time", "site").to_pandas()
        frames.append(frame)
    return to_colombia(pd.concat(frames, axis=1), snapshots(config))


def build_profiles(root: Path, config: dict, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    index = snapshots(config)
    mode = config["climate"]["mode"]
    if mode == "synthetic":
        h = index.hour.to_numpy()
        t = np.arange(len(index))
        sun = np.maximum(0.0, np.sin(np.pi * (h - 6) / 12))
        frame = pd.DataFrame(
            {
                "wind_guajira": 0.55 + 0.15 * np.sin(2 * np.pi * t / 31),
                "solar_cesar": 0.85 * sun,
                "solar_santander": 0.78 * sun,
            },
            index=index,
        )
        source = "DETERMINISTIC SYNTHETIC profiles. Not ERA5, observations, or bankable yields."
    elif mode == "era5":
        frame = profiles_from_cutout(root, config)
        source = (
            "Atlite/ERA5; area-weighted within illustrative boxes, NOT land-eligibility-weighted."
        )
    else:
        raise ValueError(f"Unknown climate mode {mode}")
    frame.index.name = "snapshot"
    frame.to_csv(output / "renewable_profiles.csv")
    metadata = {
        "mode": mode,
        "source": source,
        "timezone": "America/Bogota",
        "settings": config["climate"],
        "sites_sha256": sha256(root / config["climate"]["sites"]),
        "mean_capacity_factors": frame.mean().to_dict(),
    }
    if mode == "era5":
        metadata["cutout_sha256"] = sha256(root / config["climate"]["cutout"])
    write_json(output / "climate_provenance.json", metadata)
    return output / "renewable_profiles.csv"
