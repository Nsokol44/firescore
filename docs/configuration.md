# Configuration

Every scoring constant lives in one versioned YAML file
(`firescore/config/default.yaml`, `config_version: 2`). A county copies it,
edits it, and passes it with `--config`; **no constant is edited in code**.
Your copy is deep-merged over the defaults, so you only write what changes.

What is configurable:

- `distances` — the clip distances inherited from the legacy index
  (road 300 m, station 5,000 m, hydrant 400 m), the wildland-proximity decay
  (500 m), the structure-cluster radius (150 m), and the structure-spacing
  risk band (9–60 m).
- `egress.exits_reference` — 6, the exit count at which the exit deficit
  reaches zero (Fong et al. 2026).
- `egress.subweights` — how the four egress sub-scores combine.
- `weights` — the default component weights.
- `sensitivity` — the alternative weight configurations. Every structure's
  reported score is the **range** across these configurations.
- `classes` — the class thresholds (0.35 / 0.55 / 0.75) and labels.
- `terrain.slope_full_deg` — slope at which slope risk saturates (40°).
- `wind.downslope_from_deg` — the fire-weather wind's FROM direction
  (default 157.5°, the SSE flow of the 2016 Chimney Tops 2 event). Override
  on the command line with `--wind-from-deg`, or import from the companion
  climatology catalog when available.
- `fuels.hazard_by_code` — the LANDFIRE FBFM40 hazard lookup (ordinal,
  documented as a design table, tunable per county).
- `whatif.costs_usd` — planning costs used for the per-dollar what-if
  ranking (clearing per structure, hydrant installed, second road per metre
  plus a fixed egress cost).
- `validation` — block size, CV folds, permutation draws, seed.
- `fetch` — LANDFIRE product, DEM resolution, WRC service name, timeouts.

The config version is stamped into every output's provenance, so a score
can always be traced to the exact constants that produced it.
