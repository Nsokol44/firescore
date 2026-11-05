# The index (v2)

Five components, each in [0, 1] with 1 = most vulnerable, combined by the
configured weights. The composite is reported as a **range** across the
sensitivity weight configurations, never as a bare point value.

## Egress

Computed on the real OpenStreetMap drive graph:

- **Exit deficit** — structures are grouped into clusters (DBSCAN, 150 m);
  a cluster's exits are the distinct road-graph connections from its node
  set to the rest of the network. Deficit = `clip(1 − exits/6, 0, 1)`.
- **Dead-end indicator** — of the structure's nearest road node (the legacy
  term, kept): 1.0 for degree ≤ 1, 0.5 for degree 2, else 0.
- **Station drive distance** — multi-source Dijkstra over the graph from
  every mapped fire-station node, clipped at 5,000 m. (The legacy index used
  a Euclidean distance to two invented station points.)
- **Road distance** — distance to the nearest road edge, clipped at 300 m.

## Water access

Distance to the nearest water source, clipped at 400 m. Source priority:
county hydrants (override) → OpenStreetMap hydrants → OpenStreetMap water
features as tanker **draft sites (labelled PROXY)** → station drive distance
(labelled PROXY). The layer actually used is recorded per county and per
structure (`water_source`).

## Vegetation / fuel

LANDFIRE FBFM40 fuel model at the structure (modal within 45 m), mapped to
a hazard value by the config lookup table, blended 70/30 with a
distance-to-wildland decay (500 m) computed from the same raster. This
replaces the legacy component, which was slope and aspect relabelled — the
reason it correlated with terrain by construction.

## Terrain

USGS 3DEP slope (60% weight, saturating at 40°) plus **wind-aligned
exposure** (40%): how directly the slope faces into the configured
downslope wind, `0.5 + 0.5·cos(aspect − wind_from)`, neutral 0.5 on flat
ground.

## Structure spacing

Nearest-neighbour structure distance from the footprint layer: full risk
at ≤ 9 m, zero at ≥ 60 m. This is the house-to-house spread pathway that
drove losses in Gatlinburg in 2016.

## Provenance labels

Where no parcel layer exists, FEMA USA Structures footprints are the
structure layer and every output carries `layer_role = footprint_proxy`.
A county parcel layer supplied with `--parcels` replaces them and the
label changes to `county_parcels`. Proxies are always labelled, never
silent.
