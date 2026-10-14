# Detailed Grid2Poster integration

## Actual reuse, not a redraw labeled Grid2Poster

The renderer is loaded directly from the pinned user repository:

```text
external/colombiacongestionV2/tools/grid2poster_col.py
external/colombiacongestionV2/tools/gis_data.py
external/colombiacongestionV2/tools/paratec_join.py
external/colombiacongestionV2/tools/themes/*.json
```

The original upstream project was also cloned and inspected at
[open-energy-transition/grid2poster, 69673e58b65472ba90a580c77b8ea7b902001dd0](https://github.com/open-energy-transition/grid2poster/tree/69673e58b65472ba90a580c77b8ea7b902001dd0)
to verify the theme/voltage-tier/rendering conventions. For reproducibility,
PyPSA-col executes **your offline Colombian adaptation**, not a separate online
OSM download or an unrelated plotting library pretending to be Grid2Poster.
The upstream gallery/poster cache is not copied into this repository.

## Rendering pipeline

1. `source.verify_source()` validates the pinned source SHA-256 manifest.
2. `gis_data` loads the three actual OSM snapshots.
3. `grid2poster_col.osm_snapshot_dataset()` supplies line segments, plants and
   substation metadata in the source renderer's **lat/lon** coordinate convention.
4. `render_poster()` preserves the Colombian thresholds **34.5 / 110 / 220 / 500 kV**,
   theme widths/alphas, voltage-specific halos, boundary, typography and island insets.
5. PyPSA-col adds model-utilization overlays **after** the background renderer.
6. The same figure is exported as PNG, vector PDF and SVG with a JSON statistics
   and route-provenance companion. No network requests occur during rendering.

All 18 source themes remain available. Examples:

```yaml
poster:
  theme: electric_midnight    # paper_grid, blueprint, monochrome_paper, etc.
  paper: a3                  # source renderer supports A5–A0 and other presets
  dpi: 300                   # higher print resolution, larger files
  include_zni_inset: true
  congestion_overlay: true
```

The delivered figures use 130 dpi to keep artifacts compact; use 300 dpi for print.
Unknown theme names are rejected rather than silently falling back. The title
explicitly says **OSM geometry / illustrative model**.

## Route construction and QA

`paratec_join.construir_grafo()` builds the source cartographic graph from
polylines, quantizing vertices around 110 m and stitching loose ends within 250 m.
`resolver_anclas()` combines name similarity, proximity and voltage coherence to
match the seven legacy hubs to station candidates. `unir_congestion()` uses
length-weighted Dijkstra with a penalty for lower-voltage segments.

The pinned source produced seven routed corridors, with median detour ratio
about 1.67 and six of seven anchors meeting the source name-similarity threshold.
That is **geographic heuristic coverage**, not proof of electrical connectivity,
asset identity, operational status or the true route of a commissioned corridor.
Anchor distances and voltage-consistency warnings are preserved in
`resources/source/anchors.csv` and `routing_quality.csv`.

If Dijkstra has no route, the source supplies a straight-line fallback. PyPSA-col
renders that path **dashed**, retaining `estado_ruta`; it is never reported as a
verified OSM connection. The canonical GeoJSON route output converts the source's
lat/lon back to standard **longitude, latitude** order.

### Why the poster graph is not the electrical graph

The source quantizer/stitcher can join nearby geometry across voltage levels,
and can route through lower-voltage paths. Reusing it as an electrical network
would invent switches/transformers. `network.py` therefore reconstructs its own
conservative **same-voltage endpoint** candidates. The two graphs intentionally
serve different purposes.

## Meaning of overlay colors

For each legacy corridor, matching PyPSA transport Links (including active
expansion vintages) are grouped by endpoint pair. The overlay shows the maximum
sampled absolute net corridor flow / active transfer capacity. The upstream
utilization palette/thresholds are retained, and the legend says **MODEL**.

This is not a measured loading of each physical OSM segment. Different model
routes can overlap or be mapped onto the same feature. Do not sum their lengths,
count them as distinct circuits, interpret colors as measured outages, or
claim national congestion costs from the map. Physical/clustered runs lacking
the seven legacy endpoint names get a background geographic map, not a misleading
invented seven-hub overlay.

Plant markers are disabled in the delivered model-overlay map to avoid presenting
OSM capacity tags as the optimized/validated generation fleet. The original
renderer and its plant/source-color support remain intact for inventory posters.
Map credits preserve OpenStreetMap contributors (ODbL), Grid2Poster (MIT), the
Colombian adaptation and the new workflow. Boundary/data licensing remains separate.
