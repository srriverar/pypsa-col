# Data layers

- `raw/xm`: unmodified API response snapshots + per-request sidecars (URL, POST body, UTC
  retrieval time, SHA-256). The delivery includes an actually downloaded example.
- `processed/xm`: normalized long tables; values retain their catalog units.
- `reference`: source locks, legacy XM catalog and illustrative weather-site boxes.
- `user`: reviewed crosswalks and electrical parameters supplied by the researcher.
- OSM geometries stay in `external/colombiacongestionV2/data` with their provenance.

Never mix synthetic and observed time series without marking the run as hybrid.
See `docs/DATA.md`, `docs/NETWORK.md`, and `THIRD_PARTY_NOTICES.md`.
