"""Configuration, integrity checks and machine-readable provenance."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


def deep_merge(base: dict, patch: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(path: str | Path, _seen: set | None = None) -> dict:
    path = Path(path).resolve()
    seen = set() if _seen is None else set(_seen)
    if path in seen:
        raise ValueError(f"Cyclic config inheritance: {path}")
    seen.add(path)
    config = yaml.safe_load(path.read_text()) or {}
    parent = config.pop("extends", None)
    if parent:
        config = deep_merge(load_config(path.parent / parent, seen), config)
    if config.get("snapshots", {}).get("timezone") != "America/Bogota":
        raise ValueError("Snapshots must be naive Colombian wall time (America/Bogota).")
    rid = config["run"]["id"]
    if not rid or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in rid):
        raise ValueError("run.id must contain only lower-case letters, digits, '-' or '_'.")
    return config


def snapshots(config: dict) -> pd.DatetimeIndex:
    spec = config["snapshots"]
    start, end = pd.Timestamp(spec["start"]), pd.Timestamp(spec["end"])
    if (
        start.tzinfo
        or end.tzinfo
        or start > end
        or start != start.floor("h")
        or end != end.floor("h")
    ):
        raise ValueError("Use an increasing range of timezone-naive whole hours.")
    return pd.date_range(start, end, freq="h", name="snapshot")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_clean(v) for v in value]
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, (Path, pd.Timestamp)):
        return str(value)
    return value


def write_json(path: str | Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(_clean(data), indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    tmp.replace(path)


def require_columns(frame: pd.DataFrame, columns, context: str) -> None:
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"{context}: missing columns {sorted(missing)}")


def check_reviewed(frame: pd.DataFrame, context: str) -> None:
    require_columns(frame, ["reviewed", "source"], context)
    ok = frame.reviewed.astype(str).str.lower().isin(["true", "1", "yes"])
    if not ok.all() or frame.source.fillna("").str.strip().eq("").any():
        raise ValueError(f"{context}: all rows require reviewed=true and a non-empty source.")


def read_timeseries(path: str | Path, expected: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    frame.index.name = "snapshot"
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f"{path}: duplicate or unordered timestamps")
    if expected is not None:
        frame = frame.reindex(expected)
    if frame.isna().any().any() or not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ValueError(f"{path}: missing or non-finite time-series values; no implicit filling.")
    return frame


def record_inputs(root: Path, paths) -> list[dict]:
    records = []
    for path in sorted({Path(p).resolve() for p in paths}):
        if path.is_file():
            try:
                label = str(path.relative_to(root.resolve()))
            except ValueError:
                label = str(path)
            records.append({"path": label, "sha256": sha256(path), "bytes": path.stat().st_size})
    return records
