# Atlite / Copernicus ERA5

## What is implemented and what has not been downloaded

The adapter prepares an Atlite ERA5 cutout, converts wind/PV profiles, and aligns
them to Colombian local snapshots. Atlite conversion is integration-tested
against an explicitly **synthetic weather fixture**. No CDS credential was
available during delivery, so **no genuine ERA5 request/cutout was completed**.
That is different from the XM downloads, which were completed against the live API.

## Credentials and access

Create a Copernicus Climate Data Store account, accept the ERA5 single-level
terms in the CDS portal, and configure the API with your personal access token.
Typical user-home file (not inside the repository):

```yaml
# ~/.cdsapirc
url: https://cds.climate.copernicus.eu/api
key: YOUR_PERSONAL_ACCESS_TOKEN
```

Alternatively use `CDSAPI_URL` and `CDSAPI_KEY` in your environment. Do not put real
tokens in YAML studies, commands you commit, notebooks, CI logs or source control.
A `.cdsapirc` path is ignored, but ignoring a file is not permission to publish it.
The client never writes these credential values into run provenance.

```bash
pip install -e '.[climate]'
pypsa-col build-cutout --config config/era5.yaml
pypsa-col build-profiles --config config/era5.yaml
pypsa-col run --config config/era5.yaml
```

CDS queues/downloads can take a long time. Keep the first cutout small and run
large climate jobs in a managed batch process. The demo does not access CDS.
If an existing cutout has a different time range, use a new filename. Missing
variables or incomplete spatial/time coverage raise errors; there is no hidden
synthetic fallback or interpolation across missing hours.

## Spatial and technology assumptions

`data/reference/renewable_sites.geojson` contains **illustrative resource boxes**:

- La Guajira → `wind_guajira`.
- Cesar → `solar_cesar`.
- Santander → `solar_santander`.

These are not official department boundaries, licensed sites, indigenous-land
consents, protected-area exclusions or developable-capacity estimates. Replace
with vetted polygons before research. Do not infer capacity potential from a
weather profile or political boundary.

The example uses the configurable Atlite turbine `Vestas_V112_3MW`, panel `CSi`,
PV tilt 10° and azimuth 180°. These are modeling assumptions, not a statement
about a specific Colombian project. Turbine roughness/hub-height assumptions,
wake/availability losses, PV tracking and local calibration should be reviewed
against the actual technology and siting dataset.

The cutout uses 0.25° spacing by default and prepares `wind`, `influx`,
`temperature` and `height`. The bounding box covers the selected shapes plus a
0.25° margin. Cells are weighted by shape overlap and cell area in an equal-area
projection (EPSG:6933); per-unit conversion removes the common capacity-density
factor. **No land exclusion mask** is implemented in this initial version.
Technical potentials are separate explicit scenario inputs, never claimed as
land-eligible potentials.

## Time alignment and shape contract

The model uses naive timestamps representing **America/Bogota**, not UTC and not
the user's/browser's timezone. A local interval starting 2024-01-01 00:00 requires
ERA5 at 2024-01-01 05:00 UTC. The last local hour on January 2 requires January 3
04:00 UTC. The requested UTC cutout is padded by conversion of exact endpoints,
not by a fixed manipulation of a timezone-aware index.

Profiles are converted UTC → America/Bogota → naive, then reindexed to every
required snapshot. Duplicate/non-finite/missing values or capacity factors outside
[0,1] fail. Tiny numerical tolerances may be clipped at 0/1; physical missing data
are not filled with zeros.

Output:

```text
resources/<run>/renewable_profiles.csv
resources/<run>/climate_provenance.json
cutouts/<name>.nc
cutouts/<name>.manifest.json
```

Provenance records the cutout hash, module/version, sites hash, UTC window,
resolution, turbine/panel choices and averaging convention. ERA5 is a reanalysis,
not directly an observed generation profile. Cite the appropriate ECMWF/Copernicus
dataset, version/access date and Atlite release in any paper.

## Toward a research-quality resource assessment

Add licensed-region boundaries, protected areas, slope/land cover, setbacks,
indigenous/community constraints and a justified capacity density. Evaluate
multi-year weather and drought covariation, calibrate regional biases, and
propagate uncertainty. Offshore wind, solar tracking, wake losses and detailed
hydrological runoff conversion are not silently included by this adapter.
