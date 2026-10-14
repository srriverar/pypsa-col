# Fixture provenance

The four `xm_*.json` files are small excerpts of actual XM API responses downloaded
for this delivery, not fabricated observations. Metric and endpoint contracts
follow the pinned EquipoAnaliticaXM/API_XM revision. The corresponding full raw
responses and request/SHA-256 sidecars are bundled under `data/raw/xm/`.

- Demand: 2024-01-01, national hourly kWh.
- Capacity and stored reservoir energy: first two entities on 2023-12-31.
- Catalog: selected definitions from the current 2026-10-12 API inventory.

Other test inputs, including weather, duplicate list entries and resource
crosswalks, are deliberately synthetic unit-test fixtures and are not system data.
XM API software is MIT; API data reuse terms are separate (see notices).
