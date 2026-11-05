# FireScore

A reusable, open-source **parcel/structure-level wildfire vulnerability index**
that runs on **any US county** from free national data — and, once fetched,
runs **fully offline**.

```bash
pip install firescore            # or: pip install -e .  from this repo
firescore run --county "Sevier, TN"
firescore run --county "Sevier, TN" --offline   # same result, no network
```

The first command pulls every input for the county, scores every structure,
and writes a scored layer a fire marshal can use the same day. The second
command proves the offline contract: it reads only the local cache and
fails loudly if anything is missing.

## What it does differently from the notebook prototype

The index began as a research notebook that ran on a **synthetic fixture**:
900 invented parcels, a grid road network, synthetic hydrant distances, and
a "vegetation" component built from slope and aspect. FireScore v2 replaces
every synthetic input with the real national product and fixes the science:

| Component | Legacy (synthetic) | FireScore v2 (real) |
|---|---|---|
| Structures | invented boxes | FEMA USA Structures footprints (parcel proxy, labelled) — or real county parcels as an override |
| Egress | nearest-node degree on a grid | outward **exit counts per structure cluster on the real OSM road graph** (Fong et al. 2026 six-exit threshold), dead-end indicator, **drive-time** station distance (Dijkstra) |
| Water | synthetic distances | OSM hydrants where mapped; otherwise OSM water-feature draft sites, labelled PROXY |
| Vegetation | slope + aspect (artifact) | **LANDFIRE FBFM40 fuel models** (hazard lookup) + distance-to-wildland |
| Terrain | slope + S/W aspect | 3DEP slope + **wind-aligned exposure** (aspect vs. a configurable downslope wind) |
| Spacing | — | **structure-to-structure nearest-neighbour distance** (house-to-house spread) |
| Constants | hard-coded 300/400/5000 | **versioned YAML config** — counties tune weights, thresholds, costs |
| Validation | RF AUC vs. permutation null, synthetic | same protocol on **real perimeters** (Chimney Tops 2, Hatcher Mountain), + spatial block CV, calibration, and a **head-to-head against Wildfire Risk to Communities** |
| Score | a point value | a **range** across five weight-sensitivity configurations |

## The offline contract

`firescore fetch` populates a per-county cache: vectors as **GeoParquet**,
rasters as GeoTIFF, provenance in a manifest. After that, `run`,
`validate`, `whatif`, `report`, `queue`, and `export` never need the
network; `--offline` makes the guarantee explicit and fails loudly when a
layer is missing rather than silently reaching out.

## Practitioner outputs

- **What-if editor** — clear vegetation, add a hydrant, add a second road
  exit; see the score change instantly, ranked by score drop per $1,000.
- **Report cards** — one-page PDF per structure with the component
  breakdown, a plain-language "why", and recommended actions.
- **Inspection queue** — structures ranked worst-first, STR parcels first
  when a local STR layer is supplied, with inspected tracking persisted.
- **FireView** — an offline field package (GeoPackage + a self-contained
  HTML map) that works on a phone in airplane mode.

## Data sources (all free, all national)

OpenStreetMap (roads, hydrants, water features) · USGS 3DEP (terrain) ·
LANDFIRE FBFM40 (fuels) · FEMA USA Structures (buildings) · USFS
stations) · USFS Wildfire Risk to Communities (burn-probability comparison
layer) · Census TIGER/Line (county boundaries) · NIFC WFIGS + NPS (burn
perimeters for validation).

## Repository layout

`src/firescore/` the package · `tests/` offline test suite ·
`examples/` Sevier County end-to-end notebook · `docs/` manual ·
`plugins/` QGIS plugin + ArcGIS Pro toolbox · `pilot/` Sevier County
Fire & Rescue pilot pack · `paper.md` the JOSS manuscript draft.

## License

MIT (see `LICENSE`). Data products keep their own terms; the cache manifest
records the source of every layer.
