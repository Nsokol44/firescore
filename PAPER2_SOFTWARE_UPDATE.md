# Paper 2 — Software Update for the Wave-2 Manuscript Pass

**Purpose.** The FireScore software behind Paper 2 ("A Reusable,
Open-Source Parcel-Level Wildfire Vulnerability Index", Daniels & Sokol)
has been rebuilt. This note states, section by section, what the software
now verifiably does, so the wave-2 rewrite claims only verified
capabilities. All numbers below are from real runs on 2026-11-05
(checkpoints: `~/workspace/firescore/BUILD_LOG.md`; provenance is stamped
into every output).

**Do not edit the Paper 2 merged Doc from this note** — this is the input
to the wave-2 pass, which proceeds once the parallel round-2 edits land.

---

## 1. What changed, in one paragraph

The legacy implementation scored a **synthetic fixture**: slope and aspect
were relabelled as both "vegetation" and "terrain", water distances were
Euclidean to synthetic hydrant points, station distance was Euclidean,
and validation was a random-forest AUC against the Chimney Tops 2
perimeter (0.530, p = 0.232). The rebuilt software ingests **real national
data for any US county** in one command, scores five mechanistically
distinct components on those data, works **fully offline** after one
fetch, and reports every score as a **range** across weight
configurations. Sevier County (75,227 structures) scores offline in
~90 seconds; a second county (Blount, TN — 79,056 structures) ran on the
same code and shipped default config, unmodified: cold fetch 18m34s,
offline scoring mean 0.427, 12.3% of structures High or Extreme, water
again resolving to the labelled draft-site proxy (0 OSM hydrants).

## 2. Verified capability → manuscript section map

### Data & code availability (manuscript §: Availability)

- **New text basis:** "FireScore is open source (MIT) at
  github.com/Nsokol44/firescore [repo creation pending parent-agent
  browser step at time of writing; code is committed locally]. The
  release archive DOI route is verified as **figshare** (JOSS names
  figshare explicitly as a qualifying archive; it mints DataCite DOIs of
  the form 10.6084/m9.figshare.*): **DOI route verified as figshare,
  archive to be minted at release.** Zenodo is not used. UT TRACE was
  checked and is not verified as DOI-minting for software deposits."
- Replace any wording implying the code is "available on request" or
  archived as a notebook. The notebook-era code survives only as
  provenance (see §7).

### Study area & data (§: Data)

- Inputs are now: FEMA USA Structures footprints (labelled in all outputs
  as **parcel proxies**, `layer_role = footprint_proxy`); OpenStreetMap
  roads (drive graph), hydrants, stations, and water features via osmnx;
  USGS 3DEP DEM (30 m); LANDFIRE **LF2023 FBFM40** via the LFPS v2 API;
  USFS Wildfire Risk to Communities burn probability (validation only);
  Census TIGER county boundary; NPS/WFIGS fire perimeters (validation).
- County parcels, hydrants, and stations are **optional overrides** with
  defined precedence (county layer > national layer > labelled proxy).
- Delete the synthetic-fixture data description entirely. The four Sevier
  point shapefiles from the research program are inputs to Papers 1/3,
  not to this software.
- **Offline contract (new methods paragraph):** one `firescore fetch`
  populates a per-county cache (GeoParquet vectors, GeoTIFF rasters, and
  a provenance manifest with per-layer source, URL, row counts, and
  checksums). `firescore run --offline` refuses any layer not in cache
  rather than touching the network. The Sevier scoring run reported here
  was executed with `--offline`.

### Index construction (§: Methods) — component by component

| Component (new) | Construction | What it replaces |
|---|---|---|
| Egress | DBSCAN structure clusters (subdivision proxy); **outward-exit count on the real OSM road graph** (edges crossing the cluster's node set), dead-end status of the nearest node, **drive distance to the nearest station over the graph** (multi-source Dijkstra, OSM speeds), distance to road. Subweights + the Fong et al. 6-exit reference are config values. | Dead-end fraction + Euclidean clips. |
| Water | Nearest of (county hydrants > OSM hydrants ≥ 25 > **OSM draft sites, labelled PROXY** > station-drive fallback). The normaliser follows the source's construct (400 m hydrant / 1,500 m drafting / 5,000 m station drive), all in config. | Euclidean distance to synthetic hydrants at a single 400 m clip. |
| Vegetation | **LANDFIRE FBFM40 modal fuel model within 45 m**, mapped through a documented ordinal hazard table (config), mixed with **distance to wildland**, where wildland = a contiguous burnable patch ≥ 1 ha. | Slope+aspect relabelled (the artifact). Slope/aspect no longer enter vegetation at all. |
| Terrain | Slope from the 3DEP DEM + **wind-aligned exposure**: aspect agreement with a configurable downslope-wind direction (default SSE 157.5°, the 2016 CT2 impinging flow; overridable per run, importable from Paper 1's catalog). | Raw slope+aspect composite. |
| Spacing (NEW) | Nearest-neighbour footprint distance + count within 30 m (cKDTree), full risk ≤ 9 m, zero ≥ 60 m (config). | — (structure-to-structure spread was unmodelled) |

- **All constants live in a versioned YAML config** (`config_version` 2,
  stamped into outputs): the legacy 300 m / 400 m / 5,000 m clips, class
  thresholds (0.35/0.55/0.75), weights, subweights, what-if costs.
  Counties tune the file, not the code.
- **Scores are ranges.** Five weight configurations (default,
  egress-/water-/fuel-dominant, equal) are computed for every structure;
  the manuscript must report score, score_low, score_high and stop
  reporting point values. Class labels derive from the default
  configuration, with the worst-case class also carried.

### Validation (§: Validation) — rewritten, and read the caveats

The module computes, per cached fire perimeter: composite AUC with a
**500-draw label-permutation null**; a random forest on the components
under **spatial block cross-validation** (1 km blocks) alongside the
plain split (the gap between them is reported as the spatial-leakage
diagnostic); Brier score; decile calibration tables + plots; and a
**head-to-head against WRC burn probability** at the same structures
(AUC + Spearman).

Verified Sevier results (2026-11-05; full detail in the project's
`outputs/validation.json`):

- **Chimney Tops 2 (2,873 structures inside): composite AUC 0.229 —
  INVERTED**, permutation p = 1.0 on the high side; calibration decreases
  monotonically with score. WRC burn probability is also inverted on
  this outcome (AUC 0.379); RF block-CV AUC is 0.925. Interpretation
  (also emitted by the software as a diagnostic in validation.json):
  perimeter membership is **not** structure loss — the CT2 perimeter is
  dominated by uninhabited park interior, its in-perimeter structures
  are concentrated in low-scoring Gatlinburg, and current footprints
  include post-fire rebuilds. The RF's 0.925 measures how identifiable
  park proximity is from the features, not loss prediction. **The
  manuscript must not cite any CT2 perimeter AUC — legacy 0.530 or new
  0.229 — as validation of the index.** The honest validation outcome
  for CT2 awaits the structure-level damage registry (2,460 damaged
  structures; acquisition is step 1 of the Paper 2 novelty program).
- **Indigo Lane / Hatcher Mountain 2022 (36 structures inside):**
  composite AUC 0.474 (within the permutation null band; underpowered),
  WRC AUC 0.921 (WRC identifies that neighbourhood's landscape hazard),
  RF block-CV 0.49. FireScore–WRC Spearman ρ = 0.226 county-wide —
  weak-to-moderate, as expected: WRC is landscape hazard only, FireScore
  adds egress, water, and spacing structure terms.
- Runtime note: full validation over 14 Sevier perimeters took ~10 min.

### Multi-event validation (NASF + fiResponse) — the governing design

Per Nick's ruling (2026-11-05), **the four supplied data files govern**
wherever the notebook or manuscript text conflicts with them, and
**NASF (148 records, 2013–2022) + fiResponse (111 records, 2020–2026)
are Paper 2's multi-event validation set** — superseding any
single-event framing in the draft. The rebuilt software implements this
in `firescore/events.py` (`firescore validate --nasf … --firesponse …`):

- **Structures-field definition (confirmed by Katy Daniels, Sevier
  County Fire & Rescue reporting practice, 2026-11-05):** "threatened"
  is a SOFT, broad category — minor heat damage (e.g. warped siding) on
  a salvageable structure, through structures simply in the fire path
  (exposed), damaged or not. "Destroyed" is the hard category: the
  structure was lost. **The wave-2 manuscript must state this
  definition.** A reviewer pooling the two fields would be using a
  materially softer endpoint.
- **Design rules the software enforces:** DESTROYED is the only damage
  outcome; THREATENED is reported only as an exposure indicator; no
  pooled threatened+destroyed figure is ever emitted (a pooled figure
  from any other tool must be reported alongside the destroyed-only
  result). Field order in both files is (threatened, destroyed) per
  FPA-FOD pair — verified against the CT2 record (destroyed 1,373
  residences + 894 other structures, matching the official after-action
  counts) and the 2022 Indigo Lane record, on which both files agree
  (125 residences destroyed).
- **Anomaly guard:** one fiResponse record reports 20,000 destroyed
  residences on a 5-acre fire — a coding anomaly. It is excluded from
  outcome totals and flagged in the output, never silently used and
  never reinterpreted as threatened.
- **Harmonised Sevier results (2026-11-05):** 259 raw records → **208
  events** after cross-source deduplication (NASF precedence) and the
  anomaly exclusion. **20 events with destroyed structures; 2,686
  structures destroyed in total** (CT2 alone: 2,267); threatened
  (exposure) total 1,129. 8 events matched cached perimeters; the rest
  use an area-derived exposure circle, flagged as such. Event-level
  diagnostic, stated plainly: the mean FireScore of exposed structures
  does **not** separate destroyed from non-destroyed events (0.421 vs
  0.459 — CT2's large low-scoring exposed set dominates), so the
  multi-event set's value is that it makes the index testable across
  208 events; it does not rescue a structure-loss claim the perimeter
  analysis already failed. Exposure denominators use current
  footprints, so structures destroyed and never rebuilt are invisible
  — a stated limitation.
- Acreage precedence note: CT2 is 17,010 ac in NASF vs 17,140 ac in
  IRWIN; NASF governs within this validation set.

### Privacy rule for all published material (Nick, 2026-11-05)

The EMA CAD log carries caller names, phone numbers, and street
addresses. **FireScore does not ingest it.** If a county ever supplies
CAD data, only de-identified fields (date, community/jurisdiction,
disposition, cause class) may be used, and that choice must be
documented. Published examples (this note, the example notebook, the
pilot pack) use aggregate geography or synthetic parcels — never real
addresses; note that even the NASF/fiResponse incident-name fields
embed street addresses for small incidents and are generalised in all
outputs. Report cards and the inspection queue are **local practitioner
features**, generated on the county's own machine from its own data;
the constraint is on what this project publishes, archives, or shares,
and the manuscript's availability/ethics text should say exactly that.

### New practitioner sections (Discussion / Software features)

- **What-if editor:** three actions per structure — clear vegetation
  (30 m), add hydrant, add a second road exit (shortest off-cluster
  link, graph re-scored) — each returning the target's delta, the count
  of structures improved, the planning-level cost from config, and the
  score drop per $1,000. Verified on FS-051786 (a single-family
  structure in Seymour, Sevier County; score 0.843 [0.773–0.915],
  Extreme): clear_veg −0.071
  ($3,000; best per $), add_hydrant −0.140 ($6,500; 14 structures
  improved), add_road (259 m link) −0.035 ($141,610; 32 structures).
  Hydrant semantics: a hydrant can only improve a structure's water
  term (min of baseline vs hydrant term) — a guard written after the
  first implementation silently swapped the baseline's water source
  and raised county scores.
- **Report cards:** one-page PDF per structure (component breakdown,
  plain-language "why" lines, recommended actions, proxy labels printed,
  range-not-point wording, screening-not-prediction disclaimer).
  25 generated for Sevier's top of queue.
- **Inspection queue:** all 75,227 structures ranked worst-first by
  score-range upper bound, with persisted inspected/not-inspected state
  (`firescore queue --mark-inspected`). STR flagging activates when a
  county STR layer is supplied (`--str-layer`); **no STR flags were
  inferred** in the Sevier run (is_str = 0 throughout).
- **Exports:** GeoPackage (layer `firescore`), shapefile, GeoJSON +
  attributes CSV + field spec (hosted-feature-layer ready), and the
  **FireView** offline field package (self-contained HTML + vendored
  Leaflet + local data; verified zero external references; opens from
  file://).

### Reproducibility (§: Methods or Availability)

- pip-installable (`pyproject.toml`, pinned `requirements.txt`,
  `environment.yml`), deterministic: repeat offline runs reproduce every
  numeric column exactly (max |Δ| = 0.0). Tests: 7 offline tests incl.
  CRS-consistency and what-if no-raise guards; GitHub Actions CI config
  ships. Sevier end-to-end example notebook:
  `examples/sevier_end_to_end.ipynb` (executed against the real project;
  all outputs recorded).
- JOSS submission readiness: the paper draft (`paper.md`) exists, but
  JOSS's current pre-review requires a **public repository older than
  six months with iterative development** plus demonstrated research
  impact, and a mandatory AI-usage disclosure (included). Plan the JOSS
  submission timeline accordingly; the software is usable and citable
  (CITATION.cff) before that gate opens.

## 3. Claims the wave-2 pass must REMOVE or REWRITE

1. Any validation claim resting on the legacy RF/perimeter AUC (0.530).
2. Any description of vegetation as slope/aspect-derived.
3. Any Euclidean station/hydrant distance.
4. Any point-valued score reporting.
5. Any implication that parcels (not footprint proxies) are the unit in
   the national pipeline, or that hydrant data exist for Sevier in OSM
   (the count is 0; water is the labelled draft-site proxy).
6. "Archived code" language pointing at the research notebook.

## 4. Standing caveats to carry into the manuscript's limitations

- Road graph truncates at the county boundary: border clusters (e.g.
  Seymour) can show fewer exits than reality. Documented in the pilot
  pack; a buffered-graph option is future work.
- OSM station coverage is partial (11 mapped in Sevier); station drive
  distances are upper bounds where volunteer stations are unmapped.
- FEMA footprints include non-residential structures; the queue/report
  layer carries occupancy fields so residential subsets are one filter
  away.
- FBFM40 hazard values are ordinal design weights (documented in
  config), not measured fire behaviour.

## 5. Provenance

- Legacy code: notebook cell 7 of Katy's research notebook (extract in
  the build workspace inventory; **not** part of the software repo).
- Build record: `BUILD_LOG.md` in the repo — includes the five fetch/
  scoring defects found and fixed during the build (ArcGIS pagination
  cap, osmnx edge schema, HIFLD service retirement, LFPS v2 migration,
  what-if source-swap, validation CRS) with their evidence.
