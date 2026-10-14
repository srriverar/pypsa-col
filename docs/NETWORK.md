# Network construction, clustering and the 147/18 question

## Never confuse these four objects

1. **OSM feature:** a tagged geometry that may be only part of a line or a
   substation centroid. Completeness, commissioning and circuit identity vary.
2. **Electrical bus:** a voltage-level connection node. One physical substation
   may contain 500/230/115 kV buses connected through real transformers.
3. **Model hub/region:** an aggregation of loads and generation, not necessarily
   an actual bus or an official UPME planning subarea.
4. **Cartographic route:** a suggested OSM path drawn to locate an abstract
   corridor. It can overlap other routes and is not a list of verified circuits.

The locked source has 771 substation features but **127 tags in {220,230,500} kV**.
There is no verified 147-bus electrical model or official 18-subarea membership
file in that source. PyPSA-col does not assert otherwise.

## Seven source hubs

La Guajira, Cesar, Caribe, Antioquia, Medellin, Bogota and Tolima are extracted
from `ANCLAS_MODELO` and the legacy model. Source anchors include the upstream
Colectora/Cuestecitas, La Loma, Sabanalarga, San Carlos, Ancón Sur, Bacatá and
Mirolindo descriptions. These labels themselves are not a fresh validation of
connection status or commissioning date.

The default `Link` representation has `p_min_pu=-1`, `efficiency=1`. It conserves
energy in both directions and models corridor transfer limits, but has no KVL,
reactive power, voltage magnitudes or N-1 guarantees. The source's numerical
corridor capacity assumptions are retained rather than replaced by typical MVA
ratings inferred from map geometry. The Colectora assumption is not a claim that
the corridor was fully in service on the model's 2024 sample dates.

**Important geographic compromise:** the legacy seven-hub network has no Santander
bus. Its example Santander solar profile is injected at Bogota and prominently
marked as an illustrative delivery mapping. A reviewed network must supply a
real resource-to-bus connection. No nearest city is automatically authoritative.

## Conservative physical candidate

```bash
pypsa-col audit-source --config config/demo.yaml
pypsa-col build-network --config config/physical-candidate.yaml
```

The builder:

1. Selects source line features with 220, 230 or 500 kV tags, retaining OSM IDs.
2. Projects endpoint coordinates from EPSG:4326 to **EPSG:9377** for metre distances.
3. Matches endpoints to nearby candidate substation centroids within 1,500 m.
   A higher-voltage station may host a lower-voltage candidate bus, but that
   membership is marked inferred. Separate voltage buses remain separate.
4. Groups **unmatched endpoints only**, at the **same voltage**, within 250 m.
   It does not join interior geometric crossings or infer switchgear.
5. Creates separate same-voltage `Line` branches. Self-loops after snapping and
   zero-length routes go into `rejected_lines.csv`, not hidden deletion.
6. Uses the upstream voltage-specific typical R/X/B/MVA table **only as an
   explicit engineering-default candidate**, never as official XM/PARATEC data.
7. Inserts transformers only from a supplied reviewed file. No electrical links
   are inferred between voltage layers. Disconnected components are all retained.

At the delivered default settings: **272 buses, 337 retained line segments,
20 connected components, 0 transformers**. The largest component has 146 buses;
that numerical proximity to 147 must **not** be mistaken for an official model.
The counts depend on snapping, source segmentation and incomplete geometry.
The physical path is built and tested, but no national operational result is
claimed from this unreviewed candidate.

Outputs include bus provenance, endpoint-to-bus match distances, circuit counts,
parameter status, rejected lines, degree-one buses and isolated buses.
Inspect ambiguous or long snaps, international border segments, missing sections,
station associations and source topology before doing any study.

### Units and parallel circuits

For a line of length `L` and `c` parallel circuits:

```text
r = r_per_km * L / c             [ohm]
x = x_per_km * L / c             [ohm]
b = b_microSiemens_per_km * L*c * 1e-6  [Siemens]
s_nom = typical_MVA_per_circuit * c    [MVA]
```

Circuit factors are applied exactly once; `num_parallel` is not also multiplied.
Typical values are candidates, not validated ratings or protection/stability limits.
PyPSA's linear active-power OPF is lossless here; `r` and `b` are retained but do not
make this an AC-voltage/reactive-power solve.

Transformer `r` and `x` are **per-unit on the transformer's own nominal MVA base**.
A PARATEC `r_pu` value cannot be assigned to a line's Ohmic `r` without
`Z_base = V_kV² / S_MVA`. Likewise current in amperes is not an MVA rating.

`inspect-paratec` reuses the upstream export-column/name normalizer, but its output
is deliberately unreviewed. The upstream normalizer matches `corriente` under an
MVA-like alias and can normalize per-unit field names: this is useful for finding
columns, **not permission to assume electrical units**.

## Reviewed physical inputs

`config/research.yaml` requires complete reviewed line overrides and explicit
transformers in the canonical schemas in `data/user/README.md`. The current code
checks reference IDs, uniqueness, coverage, positive reactance/capacity and review
fields. These checks do not replace engineering validation; a `reviewed=true`
flag is a researcher assertion, not external certification.

For a real historical study, also review commissioning dates: the OSM snapshot is
from 2026, while the demonstration observations are from 2024. The shipped
candidate does not reconstruct historical topology automatically.

## Exactly 18 regions, without inventing an official mapping

`config/clustered18.yaml` reads a complete `bus,region,source,reviewed` table. It
requires each candidate bus exactly once, a source citation on every row and
exactly 18 distinct nonempty region names. All voltage-level/junction buses must
be covered — matching 147 station labels alone would be insufficient.

A geographic nearest-hub or k-means solution is not an official UPME subarea
assignment; no such result is mislabeled as official here. Supply a versioned
UPME/XM membership table or a researcher-reviewed boundary overlay, with
publication date and treatment of boundary/junction ambiguities.

The reduction operates **before** adding assets/time series. It sums crossing
branch nameplates between region pairs into symmetric, lossless **transport**
Links. Within-region bottlenecks and phase-angle physics disappear. The sum of
cut-set capacities is not a firm transfer limit, N-1 capability, PTDF-equivalent
network or market-price zone. Use a validated AC reduction/PTDF process if those
properties are needed, then benchmark its error against the reviewed full network.

## San Andrés and Providencia

The upstream geographical insets are preserved on posters. These ZNI islands are
not added as SIN nodes and never receive a fictitious transmission connection.
