"""XM SINERGOX API with verified caching, bounded chunks and explicit units.

The request contract is based on EquipoAnaliticaXM/API_XM (see sources.lock).
The live metric catalog, not integer positions in its legacy JSON, defines each
(metric, entity) pair. API_XM's legacy metricasAPI.json is itself a JSON string;
``decode_json`` deliberately handles that double encoding.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .io import require_columns, sha256, utc_now, write_json

BASE_URL = "https://servapibi.xm.com.co"
ENDPOINTS = {
    "HourlyEntities": "hourly",
    "DailyEntities": "daily",
    "MonthlyEntities": "monthly",
    "AnnualEntities": "annual",
    "ListsEntities": "lists",
    "ListEntities": "lists",
}


class XMError(RuntimeError):
    """Missing data, changed schema, invalid catalog or failed XM request."""


def decode_json(value):
    for _ in range(3):
        if isinstance(value, (str, bytes)):
            value = json.loads(value)
        else:
            return value
    if isinstance(value, (str, bytes)):
        raise XMError("Excessively nested JSON encoding")
    return value


def catalog_frame(payload) -> pd.DataFrame:
    payload = decode_json(payload)
    if "Items" in payload:
        rows = [
            entry["Values"] for item in payload["Items"] for entry in item.get("ListEntities", [])
        ]
    else:
        types = {
            "Horaria": "HourlyEntities",
            "Diaria": "DailyEntities",
            "Mensual": "MonthlyEntities",
            "Anual": "AnnualEntities",
            "Lista": "ListsEntities",
            "Listas": "ListsEntities",
        }
        rows = []
        for metric, definitions in payload.items():
            for _, name, entity, frequency in definitions:
                rows.append(
                    {
                        "MetricId": metric,
                        "MetricName": name,
                        "Entity": entity,
                        "Type": types.get(frequency, frequency),
                        "MetricUnits": None,
                    }
                )
    frame = pd.DataFrame(rows)
    require_columns(frame, ["MetricId", "Entity", "Type"], "XM catalog")
    if frame.duplicated(["MetricId", "Entity"]).any():
        raise XMError("Duplicate (metric, entity) in XM catalog")
    return frame


def date_chunks(start: str | date, end: str | date, days: int = 30):
    start, end = pd.Timestamp(start).date(), pd.Timestamp(end).date()
    if start > end or not 1 <= days <= 30:
        raise ValueError("XM requires increasing dates and chunk_days in [1, 30].")
    while start <= end:
        stop = min(start + timedelta(days=days - 1), end)
        yield start.isoformat(), stop.isoformat()
        start = stop + timedelta(days=1)


def _number(value) -> float:
    if value is None or (isinstance(value, str) and value.strip().lower() in {"", "null", "nan"}):
        return np.nan
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise XMError(f"Non-numeric API value {value!r}; no implicit locale guessing") from exc


def normalize(payload, spec: dict) -> pd.DataFrame:
    payload = decode_json(payload)
    if not isinstance(payload, dict) or "Items" not in payload:
        raise XMError("XM response does not contain Items")
    metric, entity, kind = spec["MetricId"], spec["Entity"], spec["Type"]
    rows = []
    for day in payload["Items"]:
        record_key = "ListEntities" if kind in {"ListsEntities", "ListEntities"} else kind
        if record_key not in day:
            raise XMError(f"{metric}/{entity}: expected {record_key}, got {list(day)}")
        for entry in day[record_key]:
            # Hourly/list records nest Values; daily observations put Code/Value
            # directly on the entity record. Both are used by the live API.
            values = entry.get("Values", entry)
            if not isinstance(values, dict):
                raise XMError("XM Values must be a mapping")
            code = str(
                next(
                    (values[k] for k in ("code", "Code", "Name", "name") if k in values),
                    entry.get("Id", ""),
                )
            )
            if not code:
                raise XMError("Missing entity code")
            common = {
                "metric": metric,
                "entity": entity,
                "entity_code": code,
                "unit": spec.get("MetricUnits", ""),
                "timezone": "America/Bogota",
            }
            if kind == "HourlyEntities":
                stamp = pd.Timestamp(day["Date"])
                if stamp.tzinfo is not None or stamp != stamp.normalize():
                    raise XMError("Hourly XM Date must be a naive local calendar date")
                expected_hours = {f"Hour{h:02d}" for h in range(1, 25)}
                extras = {key for key in values if key.startswith("Hour")} - expected_hours
                if extras:
                    raise XMError(f"Unexpected hour fields: {sorted(extras)}")
                for hour in range(1, 25):
                    key = f"Hour{hour:02d}"
                    if key not in values:
                        raise XMError(f"{metric}/{code}/{day['Date']}: missing {key}")
                    rows.append(
                        {
                            **common,
                            "timestamp": pd.Timestamp(day["Date"]) + pd.Timedelta(hours=hour - 1),
                            "value": _number(values[key]),
                        }
                    )
            elif kind in {"ListsEntities", "ListEntities"}:
                rows.append({**common, "as_of": day["Date"], **values})
            else:
                key = next((k for k in ("Value", "value") if k in values), None)
                if key is None:
                    raise XMError(f"{metric}: missing daily/monthly Value: {list(values)}")
                rows.append(
                    {
                        **common,
                        "timestamp": pd.Timestamp(day["Date"]),
                        "value": _number(values[key]),
                    }
                )
    if not rows:
        raise XMError(f"{metric}/{entity}: empty response; will NOT replace missing data with zero")
    frame = pd.DataFrame(rows)
    keys = ["timestamp", "entity_code"] if "timestamp" in frame else ["as_of", "entity_code"]
    # The live resource LIST contains exact duplicate metadata rows. Preserve
    # them in raw JSON; deduplicate only byte-equivalent normalized list rows.
    # Conflicting list entries and all duplicate time-series observations fail.
    if "as_of" in frame:
        removed = int(frame.duplicated().sum())
        frame = frame.drop_duplicates()
        frame.attrs["exact_list_duplicates_removed"] = removed
    if frame.duplicated(keys).any():
        raise XMError(f"{metric}/{entity}: duplicate observations")
    return frame.sort_values(keys).reset_index(drop=True)


class XMClient:
    def __init__(
        self,
        raw_dir: Path | str,
        timeout: int = 60,
        offline: bool = False,
        session: requests.Session | None = None,
    ):
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.offline = offline
        self.session = session or requests.Session()
        if session is None:
            retry = Retry(
                total=3,
                backoff_factor=0.8,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods={"GET", "POST"},
                respect_retry_after_header=True,
            )
            self.session.mount("https://", HTTPAdapter(max_retries=retry))
            self.session.headers["User-Agent"] = "PyPSA-col/0.1 research data client"
        self.requests_used: list[dict] = []

    def request(self, endpoint: str, body: dict, refresh: bool = False):
        if endpoint not in {"Lists", *ENDPOINTS.values()}:
            raise ValueError("Unrecognized XM endpoint")
        key = hashlib.sha256(
            json.dumps({"endpoint": endpoint, "body": body}, sort_keys=True).encode()
        ).hexdigest()[:20]
        target = self.raw_dir / body["MetricId"] / f"{key}.json"
        metadata = target.with_suffix(".metadata.json")
        if target.exists() and metadata.exists() and not refresh:
            info = json.loads(metadata.read_text())
            if sha256(target) != info["sha256"]:
                raise XMError(f"Cache integrity failure: {target}")
            self.requests_used.append(info)
            return decode_json(target.read_bytes())
        if self.offline:
            raise XMError(f"Offline cache miss: {endpoint} {body}")
        response = self.session.post(
            f"{BASE_URL}/{endpoint}", json=body, timeout=(10, self.timeout)
        )
        response.raise_for_status()
        try:
            payload = decode_json(response.content)
        except (ValueError, TypeError) as exc:
            raise XMError("XM returned non-JSON data") from exc
        if not isinstance(payload, dict) or "Items" not in payload:
            raise XMError(f"XM error response: {str(payload)[:400]}")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(response.content)
        tmp.replace(target)
        info = {
            "url": response.url,
            "request": body,
            "retrieved_at_utc": utc_now(),
            "http_status": response.status_code,
            "sha256": sha256(target),
            "raw_path": str(target.relative_to(self.raw_dir)),
            "bytes": target.stat().st_size,
        }
        write_json(metadata, info)
        self.requests_used.append(info)
        return payload

    def catalog(self, refresh: bool = False) -> pd.DataFrame:
        # Official client uses /Lists for discovery, /lists for actual list data.
        return catalog_frame(self.request("Lists", {"MetricId": "ListadoMetricas"}, refresh))

    def download(
        self,
        metric: str,
        entity: str,
        start: str,
        end: str,
        catalog: pd.DataFrame,
        filters: list | None = None,
        chunk_days: int = 30,
        refresh: bool = False,
    ) -> pd.DataFrame:
        selected = catalog[(catalog.MetricId == metric) & (catalog.Entity == entity)]
        if len(selected) != 1:
            raise XMError(f"Catalog has no unique definition for {metric}/{entity}.")
        spec = selected.iloc[0].to_dict()
        if spec["Type"] not in ENDPOINTS:
            raise XMError(f"Unknown XM frequency {spec['Type']}")
        endpoint = ENDPOINTS[spec["Type"]]
        if endpoint == "lists":
            return normalize(
                self.request(endpoint, {"MetricId": metric, "Entity": entity}, refresh), spec
            )
        if pd.isna(spec.get("MetricUnits")) or not str(spec.get("MetricUnits", "")).strip():
            raise XMError(f"{metric}: catalog has no units. Use the live or cached live catalog.")
        chunks = []
        for first, last in date_chunks(start, end, chunk_days):
            body = {
                "MetricId": metric,
                "Entity": entity,
                "StartDate": first,
                "EndDate": last,
                "Filter": filters or [],
            }
            chunks.append(normalize(self.request(endpoint, body, refresh), spec))
            if not self.offline:
                time.sleep(0.05)
        result = pd.concat(chunks, ignore_index=True)
        if result.duplicated(["timestamp", "entity_code"]).any():
            raise XMError(f"Duplicate records across requests: {metric}/{entity}")
        dates = pd.to_datetime(result.timestamp).dt.normalize()
        if not dates.between(pd.Timestamp(start), pd.Timestamp(end)).all():
            raise XMError("XM returned dates outside the requested window")
        return result


def convert_units(frame: pd.DataFrame, quantity: str) -> pd.DataFrame:
    """Convert without confusing power, hourly energy, stored energy or prices."""
    maps = {
        "energy_mwh": {"kWh": 0.001, "MWh": 1.0, "GWh": 1000.0},
        "power_mw": {"kW": 0.001, "MW": 1.0},
        "hourly_mw": {"kWh": 0.001, "MWh": 1.0},  # ONE hour intervals only
        "price_cop_mwh": {"COP/kWh": 1000.0, "COP/MWh": 1.0},
        "fraction": {"%": 0.01, "p.u.": 1.0},
    }
    if quantity == "fraction" and "metric" in frame and frame.metric.eq("PorcVoluUtilDiar").any():
        raise XMError(
            "PorcVoluUtilDiar is labelled percent but the observed API payload uses fractions. "
            "Derive filling fraction from VoluUtilDiarEner / CapaUtilDiarEner and inspect audit.json; "
            "do not guess a scaling factor from the catalog label."
        )
    factors = maps[quantity]
    units = frame.unit.astype(str).str.strip()
    unknown = set(units) - set(factors)
    if unknown:
        raise XMError(f"Cannot convert units {unknown} to {quantity}")
    out = frame.copy()
    out["value"] = pd.to_numeric(out.value, errors="raise") * units.map(factors)
    out["unit"] = {
        "energy_mwh": "MWh",
        "power_mw": "MW",
        "hourly_mw": "MW",
        "price_cop_mwh": "COP/MWh",
        "fraction": "p.u.",
    }[quantity]
    return out


def load_metric(folder: Path, metric: str, entity: str, quantity: str | None = None):
    path = folder / f"{metric}__{entity}.csv"
    if not path.exists():
        raise XMError(f"Missing {path}; run `pypsa-col download-xm --config ...` first.")
    frame = pd.read_csv(path, dtype={"entity_code": str}, keep_default_na=False, na_values=[""])
    if "timestamp" in frame:
        frame["timestamp"] = pd.to_datetime(frame.timestamp)
    return convert_units(frame, quantity) if quantity else frame


def download_bundle(root: Path, config: dict, refresh: bool = False) -> dict:
    spec = config["xm"]
    client = XMClient(root / spec["raw_dir"], spec["timeout_seconds"], spec["offline"])
    output = root / spec["processed_dir"]
    output.mkdir(parents=True, exist_ok=True)
    catalog = client.catalog(refresh)
    catalog.to_csv(output / "catalog.csv", index=False)
    stats = []
    for metric, entity in spec["metrics"]:
        frame = client.download(
            metric,
            entity,
            spec["start"],
            spec["end"],
            catalog,
            chunk_days=spec["chunk_days"],
            refresh=refresh,
        )
        path = output / f"{metric}__{entity}.csv"
        frame.to_csv(path, index=False)
        stats.append(
            {
                "metric": metric,
                "entity": entity,
                "rows": len(frame),
                "missing_values": int(frame.value.isna().sum()) if "value" in frame else 0,
                "exact_list_duplicates_removed": frame.attrs.get(
                    "exact_list_duplicates_removed", 0
                ),
                "sha256": sha256(path),
                "units": sorted(frame.unit.dropna().unique()),
            }
        )
        print(f"XM {metric}/{entity}: {len(frame):,} rows")
    manifest = {
        "retrieved_or_replayed_at_utc": utc_now(),
        "window": [spec["start"], spec["end"]],
        "timezone": "America/Bogota",
        "hour_convention": "Hour01 = [00:00,01:00)",
        "list_warning": "Lists are current snapshots, NOT historical plant registries.",
        "datasets": stats,
        "requests": client.requests_used,
    }
    manifest["quality"] = audit_download(output, stats)
    write_json(output / "audit.json", manifest["quality"])
    write_json(output / "manifest.json", manifest)
    return manifest


def audit_download(folder: Path, datasets: list[dict]) -> dict:
    """Compare reservoir unit conventions and expose missing resource observations."""
    available = {(d["metric"], d["entity"]) for d in datasets}
    audit = {
        "missing_observations": [d for d in datasets if d["missing_values"]],
        "exact_list_duplicates_removed": {
            d["metric"]: d["exact_list_duplicates_removed"]
            for d in datasets
            if d["exact_list_duplicates_removed"]
        },
        "notes": [
            "No missing resource observations were replaced by zero.",
            "Do not sum national totals together with their disaggregated entities.",
        ],
    }
    wanted = {(m, "Embalse") for m in ["VoluUtilDiarEner", "CapaUtilDiarEner", "PorcVoluUtilDiar"]}
    if wanted <= available:
        frames = []
        for metric in ["VoluUtilDiarEner", "CapaUtilDiarEner", "PorcVoluUtilDiar"]:
            frame = load_metric(folder, metric, "Embalse")
            frames.append(frame.set_index(["timestamp", "entity_code"])["value"].rename(metric))
        joined = pd.concat(frames, axis=1).dropna()
        joined = joined[joined.CapaUtilDiarEner > 0]
        ratio = joined.VoluUtilDiarEner / joined.CapaUtilDiarEner
        fraction_error = float((ratio - joined.PorcVoluUtilDiar).abs().max())
        percent_error = float((ratio - joined.PorcVoluUtilDiar / 100).abs().max())
        audit["reservoir_percentage_check"] = {
            "rows_compared": len(joined),
            "catalog_unit": "%",
            "max_error_if_wire_is_fraction": fraction_error,
            "max_error_if_wire_is_percent": percent_error,
            "interpretation": "sample behaves as fractional values despite % label"
            if fraction_error < 0.001
            else "unresolved; review upstream convention",
            "model_policy": "compute fraction from stored/useful energy, never this ambiguous field",
        }
    return audit


DASHBOARD_LIVE_METRICS = [
    ("ListadoRecursos", "Sistema"),
    ("CapEfecNeta", "Recurso"),
    ("Gene", "Recurso"),
    ("DemaReal", "Sistema"),
    ("Gene", "Sistema"),
    ("PrecBolsNaci", "Sistema"),
]


def last_closed_window(days: int = 30) -> tuple[str, str]:
    """Same convention as dashboard-sin-nodal: last `days` ending D-1 (not 'today')."""
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=int(days) - 1)
    return start.isoformat(), end.isoformat()


def download_dashboard_window(
    root: Path,
    *,
    days: int = 30,
    dest_rel: str = "data/streamlit/xm_last_month",
    refresh: bool = False,
) -> dict:
    """Pull XM metrics for Generación / Demanda / Explorador (último mes cerrado)."""
    start, end = last_closed_window(days)
    dest = Path(root) / dest_rel
    dest.mkdir(parents=True, exist_ok=True)
    raw = Path(root) / "data/raw/xm_live"
    client = XMClient(raw, timeout=90, offline=False)
    catalog = client.catalog(refresh)
    # Some list metrics have empty MetricUnits; fill a harmless placeholder so download() proceeds.
    catalog = catalog.copy()
    catalog["MetricUnits"] = catalog["MetricUnits"].fillna("").astype(str)
    catalog.loc[catalog["MetricUnits"].str.strip().eq(""), "MetricUnits"] = "kWh"
    catalog.to_csv(dest / "catalog.csv", index=False)
    notes: list[str] = []
    saved = []
    for metric, entity in DASHBOARD_LIVE_METRICS:
        try:
            frame = client.download(
                metric,
                entity,
                start,
                end,
                catalog,
                chunk_days=31,
                refresh=refresh,
            )
            frame.to_csv(dest / f"{metric}__{entity}.csv", index=False)
            saved.append({"metric": metric, "entity": entity, "rows": int(len(frame))})
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{metric}/{entity}: {exc}")
    meta = {
        "start": start,
        "end": end,
        "timezone": "America/Bogota",
        "days": days,
        "source": "XM SINERGOX live",
        "convention": "último mes cerrado, D-1 (dashboard-sin-nodal)",
        "datasets": saved,
        "notes": notes,
    }
    write_json(dest / "window.json", meta)
    return meta


def verify_processed(folder: Path, required=()) -> dict:
    """Reject partially refreshed/mixed normalized tables before a model uses them."""
    path = folder / "manifest.json"
    if not path.exists():
        raise XMError(f"Missing processed XM manifest {path}; complete download-xm first.")
    manifest = json.loads(path.read_text())
    pairs = {(entry["metric"], entry["entity"]) for entry in manifest["datasets"]}
    if not set(required).issubset(pairs):
        raise XMError(f"Required datasets absent from current XM manifest: {set(required) - pairs}")
    for entry in manifest["datasets"]:
        table = folder / f"{entry['metric']}__{entry['entity']}.csv"
        if not table.exists() or sha256(table) != entry["sha256"]:
            raise XMError(
                f"Processed XM integrity failure: {table}. Complete a consistent download "
                "instead of mixing revised tables with an old manifest."
            )
    return manifest
