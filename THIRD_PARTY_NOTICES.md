# Third-party code, data and attribution

This is a mixed-provenance research repository. The new-code MIT license does
**not** supersede any upstream code or data terms.

## ColombiaCongestionV2 — user-supplied system source

- Source: https://github.com/srriverar/colombiacongestionV2
- Locked commit: `a6fcf7622249f555d81e293a11f05b8a6aee7c39`.
- Author acknowledged in its README: **Prof. Sergio Rivera, Universidad Nacional de Colombia**.
- The pinned repository contains an educational/research purpose statement, but
  **no root LICENSE file granting a general open-source code license**.
- Its owner requested reuse in this delivery. The working source snapshot is
  included for that requested work and integrity-checked, not relicensed.
- **Before public redistribution of the combined repository, the owner should
  explicitly grant/select a license for this source and verify included assets.**
  Alternatively distribute the new wrapper with its pinned-fetch bootstrap.

The source is unchanged. All copied/checked source paths and hashes are recorded
in `config/sources.lock.json`. Source generated files/caches are not relicensed.

## Grid2Poster

Original project: https://github.com/open-energy-transition/grid2poster

Inspected upstream commit: `69673e58b65472ba90a580c77b8ea7b902001dd0`.
Original MIT copyright notice: **Copyright (c) 2026 Tobias Augspurger**.
The user repository ships a Colombian offline adaptation and 18 upstream themes.
Its original MIT notice is preserved verbatim at:

```text
external/colombiacongestionV2/tools/themes/LICENSE_grid2poster.txt
```

Credit Open Energy Transition/Grid2Poster and the Colombian adaptation when
publishing maps. The theme MIT license is not automatically a blanket license
for all other user-repository code.

## OpenStreetMap geometry

Network geometries and OSM-derived routes: **© OpenStreetMap contributors**,
Open Database License (ODbL). See https://www.openstreetmap.org/copyright and
https://opendatacommons.org/licenses/odbl/1-0/ .

Maintain attribution. Assess ODbL database/derived-database/share-alike obligations
for redistributed cleaned/clustered geodatabases, not only produced map images.
The source snapshot includes simplification and centroid extraction; geographic
coverage is not an official engineering asset register.

## XM and API_XM

API software contract inspected at:
https://github.com/EquipoAnaliticaXM/API_XM/tree/ee9d7cf10c5e4f0210d955055d2a078f426fc439

Official client software license: MIT, **Copyright (c) 2020 XM S.A. E.S.P.**
That notice is preserved in `data/reference/LICENSE_API_XM` beside the legacy
catalog excerpt/copy. The new downloader is a separate synchronous implementation
of the public request contract, not a claim that XM endorses this model.

**API observations are a separate data product.** Public accessibility and an MIT
client license do not establish blanket MIT/CC terms for all XM/PARATEC/SIMEM data.
The delivery preserves source/requests/access dates/hashes. Review XM's applicable
terms before republishing a data archive or making commercial/operational claims.
Do not apply the new-code MIT license to raw electricity observations.

## Boundaries and other reference assets

The source README attributes its mainland reference boundary to geoBoundaries and
its island geometry to OSM. Preserve original provenance and verify the license
of each specific boundary dataset/version; no new blanket boundary-data license
is asserted here. Other catalog links (UPME, GEM, Google, operator exports) are
not a license to redistribute the linked material. Google imagery is not bundled.

## Copernicus ERA5, Atlite and PyPSA

No real ERA5 cutout was downloaded for this delivery. Future cutouts are subject
to the applicable Copernicus/ECMWF dataset terms; follow the CDS citation/license
instructions and never redistribute credentials.

PyPSA, Linopy, Atlite, HiGHS and their dependencies retain their respective
licenses. They are installed dependencies, not copied into the distributable
archive. Cite the software/data versions used in a study. The repository's
`CITATION.cff` is release metadata, not an invented peer-reviewed paper or DOI.

## dashboard-sin-nodal (Streamlit SIN tablero)

- Source: https://github.com/srriverar/dashboard-sin-nodal
- Locked commit: `514cc091932502056692d264fc0ade27cd62c786`.
- Live app: https://dashboard-sin-nodal.streamlit.app/
- Authors acknowledged in its README: Manuel Fernando Fajardo Rodríguez (v1–v2) and Prof. Sergio Rivera (v3–v4); nodal module credited to Libardo Acero García.
- PyPSA-col copies **declared** mapping rules (7 subregions, demand shares, toponymic keywords, plant-dimension columns) and does **not** import or relicense the Streamlit app, its dual-ascent OPF, or NOAA seeds.
- Same caution as the app itself: subregions are board assumptions, not official XM/UPME geography.
