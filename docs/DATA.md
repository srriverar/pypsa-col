# Data contracts and XM ingestion

## Source hierarchy

1. Raw observations and explicit engineering exports retain their source, retrieval
   date, revision and units.
2. Reviewed researcher crosswalks connect those observations to model buses/assets.
3. Any missing electrical parameter or spatial allocation remains an **assumption**,
   a QA item or a hard failure — not an unlabeled observation.
4. Synthetic profiles are allowed only in explicit demo/hybrid configurations.

The pinned official client contract was inspected at
[EquipoAnaliticaXM/API_XM, ee9d7cf10c5e4f0210d955055d2a078f426fc439](https://github.com/EquipoAnaliticaXM/API_XM/tree/ee9d7cf10c5e4f0210d955055d2a078f426fc439).
The new downloader uses `requests` directly rather than importing that client's
async event-loop/global warning changes.

## Endpoints and request contract

```text
POST https://servapibi.xm.com.co/Lists    {"MetricId": "ListadoMetricas"}
POST https://servapibi.xm.com.co/hourly
POST https://servapibi.xm.com.co/daily
POST https://servapibi.xm.com.co/lists
```

Example body:

```json
{"MetricId":"Gene","Entity":"Recurso","StartDate":"2024-01-01","EndDate":"2024-01-02","Filter":["GVIO"]}
```

The **live catalog** is authoritative for metric/entity combinations and units.
The client's static `metricasAPI.json` is a JSON-encoded **string containing JSON**,
not directly a dictionary. `decode_json()` handles this explicitly. The legacy
catalog has no reliable unit metadata and cannot silently replace the live catalog
for normalized numeric downloads. An offline run replays a previously cached **live**
catalog and its exact request cache.

The live catalog reported `MaxDays=31` for the sampled hourly/daily metrics. The
upstream public README says maximum 30 days. We use the conservative limit of
**30 inclusive dates**, advancing the next request to the preceding end + one day.
There are no overlapping month-boundary requests. Leap days are tested.

Requests have `(10s connect, configurable 60s read)` timeouts. Read-only POSTs
may be retried three times for connection/429/5xx failures with backoff. Failed,
empty or schema-incompatible observations are never silently converted to zero.
Use `--refresh` for revisions, or `xm.offline: true` to forbid HTTP requests.

## Downloaded example inventory

The delivery contains the API responses and normalized tables below. Historical
observations cover **2023-12-31–2024-01-02**; lists describe their own API as-of date,
**2026-10-12**. The model examples use January 1–2; December 31 provides a prior
reservoir state.

| Metric | Entity | Frequency | Catalog unit | Model/analysis use |
|---|---|---|---|---|
| `DemaReal` | Sistema | hourly | kWh | National real demand, converted to mean MW over each one-hour interval |
| `DemaOR` | Agente | hourly | kWh | Regional-allocation evidence; not silently equated to national demand |
| `Gene` | Sistema, Recurso | hourly | kWh | Observed dispatch/reference, **not** renewable availability or river inflow |
| `CapEfecNeta` | Recurso | daily | kW | Historical generator power bounds |
| `DispoReal` | Recurso | hourly | kW | Observed availability evidence; missing values require review |
| `VoluUtilDiarEner` | Sistema, Embalse | daily | kWh | Electrical-equivalent stored useful reservoir energy |
| `CapaUtilDiarEner` | Sistema, Embalse | daily | kWh | Useful reservoir energy capacity |
| `PorcVoluUtilDiar` | Embalse | daily | `%` | QA only: ambiguous wire scaling in observed response |
| `AporEner` | Sistema, Rio | daily | kWh | Daily energy inflows; reviewed river allocation needed |
| `PrecBolsNaci` | Sistema | hourly | COP/kWh | National market reference, kept separate from modeled USD LMPs |
| `ListadoRecursos` | Sistema | current list | none | Resource IDs, type, fuel, agent, start date and status |
| `ListadoEmbalses` | Sistema | current list | none | Reservoir code/name and hydrological region |
| `ListadoRios` | Sistema | current list | none | River code/name and hydrological region |

These are **17 metric/entity datasets and 44,906 normalized records**. In this
sample `Gene/Recurso` contains **3,534 missing hourly values** and `DispoReal/Recurso`
contains **16,409**. The current resource list had two exact duplicate rows; the
reservoir list had six. Exact duplicate **list metadata** are deduplicated and
counted; conflicting list records and all duplicate time-series observations fail.
All original records remain in the raw JSON. Changes on a later fresh download
are possible; the manifest records the actual response.

### Unit-label anomaly: reservoir percentages

The sample `PorcVoluUtilDiar` values include `0.63587` for AGREGADO BOGOTA while
its catalog says `%`. The corresponding energy ratio is approximately `0.63587`,
not `0.0063587`. `audit.json` compares both interpretations against
`VoluUtilDiarEner / CapaUtilDiarEner` over matched records.

- The processed raw-value table preserves the catalog label and response value.
- The model computes fractions from the two compatible energy series.
- `convert_units(..., 'fraction')` refuses this ambiguous metric rather than
  performing the incorrect divide-by-100 conversion.
- Do not infer a general rule for unrelated percentage metrics from this sample.

## Schema and time semantics

Normalized observations have:

```text
metric,entity,entity_code,unit,timezone,timestamp,value
```

`timestamp` is **timezone-naive Colombian wall time**, with an explicit
`timezone=America/Bogota` field. `Hour01` denotes the interval `[00:00,01:00)` and
is stored at 00:00; `Hour24` at 23:00 on the same reported day. ERA5 is UTC and
must be shifted by its timezone conversion, not by the computer's local timezone.

Hourly records have nested `Values.code` and `Values.Hour01…Hour24`. Daily records
may instead have flat `Code/Value` or `Name/Value`; `Name` identifies reservoirs
and rivers. Treating generic `Id="Embalse"` as a unique reservoir would merge all
reservoirs and is prohibited. Current list records use `as_of`, never a fabricated
historical timestamp.

Conversions are dimension-specific:

- `hourly_mw`: kWh in a one-hour interval / 1,000.
- `power_mw`: kW / 1,000. Do not divide power by 24.
- `energy_mwh`: kWh / 1,000; GWh × 1,000.
- `AporEner`: daily MWh / 24 to a flat hourly MW inflow. This conserves daily energy
  but does not claim measured hourly inflows.
- `price_cop_mwh`: COP/kWh × 1,000. **No** implicit foreign-exchange conversion.
- Cubic metres or m³/s are not electrical MWh; a head/efficiency/cascade model is
  required. The client intentionally does not guess those conversions.

## Cache and provenance

```text
data/raw/xm/<MetricId>/<request_hash>.json
                                 .metadata.json
data/processed/xm/<MetricId>__<Entity>.csv
                  catalog.csv
                  manifest.json
                  audit.json
```

Raw sidecars retain the URL, POST body, retrieval UTC timestamp, HTTP status, size
and SHA-256. Cache reads verify content hashes. Model preparation records hashes
of normalized files and crosswalks in `input_provenance.json`. A refresh replaces
the response for that request; archive an old raw directory if revision history
must be retained. There is no implicit immutable multi-version database.

## Three clearly different input modes

### `demo`

Uses source dashboard fleet/corridor assumptions, inherited demand weights and
deterministic synthetic time series. No XM/Copernicus access. Annualized cost and
capacity assumptions are demonstrations, not estimates of current Colombian prices.

### `xm_hybrid`

Observed **national** demand is allocated with inherited seven-hub weights.
Observed prior-day system filling fraction initializes assumed reservoirs. Hourly
inflows preserve the national inflow/useful-storage ratio, scaled to assumed model
reservoir sizes. Fleet coverage is not nationally calibrated. This intentionally
exposes, rather than masks, a large supply/demand coverage mismatch. It is useful
for testing ingestion and dimensional consistency, not adequacy claims.

### `xm_mapped`

Requires reviewed crosswalks in `data/user`. Every positive historical-capacity
resource must be accounted for. Daily net capacity creates power bounds; wind/PV
also need actual weather profiles, and run-of-river needs a supplied explicit
profile. Historical `Gene` is never forced as potential. `DispoReal` is downloaded
but not auto-imputed where absent; incorporate reviewed availability decisions
before claiming an operational reconstruction. Costs/efficiencies are reviewed
inputs, not inferred from resource names or national market prices.

Reservoir maps allow multiple turbines at one electrical bus to share one energy
store. A resource cannot be mapped twice. River shares for every selected river
must sum to one; a reservoir needs a river allocation. Multi-reservoir cascades or
one reservoir feeding distinct buses need an explicit Store/Link formulation and
are rejected by this simplified adapter. Daily observed useful capacity must be
constant over the window; otherwise a variable-bound implementation is required.

Fixed load weights are a conservative total-demand allocation, **not** measured
nodal loads. `DemaOR` excludes some STN-connected demand and has distinct loss/
measurement definitions; the code does not renormalize it into an official nodal
load data set without a separately reviewed method.
