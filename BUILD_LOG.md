# FireScore — BUILD LOG

Checkpointed progress notes for Nick / the parent agent. Every claim here is
checked against a file or a run on this machine; anything unverified is marked so.

## 2026-11-05 ~10:52 EST — Inventory (COMPLETE)

Drive folder "Katy Daniels - Wildfire and Fire Hazard Assessments"
(1j8K7_fLaL9cATbhJCc44LkVpYuVSOP7R) inventoried. Contents:
- Paper 1, 2, 3 originals + merged 2026-11-05 Docs (Paper 2 merged Doc
  1TjH53YUX8fQ2yl6RydlVVOm7gpcUAyvfl9tqe3CKGjY — NOT edited by this project).
- `Gatlinburg_Wildfire_Research_Notebook(1).ipynb` (41 cells; downloaded to
  `inventory/Gatlinburg_Wildfire_Research_Notebook.ipynb`). Paper 2 code is
  notebook cell 7 (193 lines, extracted to
  `inventory/notebook_cell7_paper2_code.py`): synthetic-fixture generator
  (900 parcels, Gatlinburg bbox), synthetic terrain proxy (slope/aspect
  generated from longitude/latitude gradients), a 12x12 grid road graph
  (OSM path present but never exercised), per-parcel Python loops for
  nearest-node distances, synthetic hydrant distances, the four-component
  composite, RF validation vs. a synthetic burn outcome + permutation null.
- `gatlinburg_dataset_access_guide.md` (downloaded to `inventory/`) and the
  Doc "Fire Data For Studies" (a duplicate of the guide, read to
  `inventory/fire_data_for_studies.txt`).
- No standalone .py files exist anywhere in the series: the "archived code"
  named in the manuscript (`wildfire_analysis.py`, `make_figures.py`,
  `make_maps.py`) exists only as notebook cells. This project becomes that
  code, as a real package.
- Local series files: `~/workspace/daniels-wildfire/DATA_INVENTORY.md` (four
  Sevier fire-point shapefiles; NO parcel/road/hydrant layers) and
  `~/workspace/daniels-wildfire/rebuild/` (Paper 1 §4.1/§4.5 rebuild;
  deduplicated union 951 incidents; mean 0.348 EMA calls/day).

Legacy index being replaced (Paper 2 §§3.2-3.3, verified from the merged doc):
- Egress = 0.4*dead_end + 0.3*clip(dist_to_road_m/300) + 0.3*clip(dist_station_m/5000),
  station distance EUCLIDEAN to two synthetic points.
- Water = clip(dist_hydrant_m/400), hydrant distance SYNTHETIC.
- Vegetation = clip(0.3 + 0.4*slope/45 + 0.3*S-or-W-aspect) — slope+aspect,
  the terrain-correlation artifact this build kills.
- Terrain = clip(0.6*slope/40 + 0.4*aspect).
- Composite weights E .30 / W .20 / V .25 / T .25; classes at 0.35 / 0.55 / 0.75.
- Sensitivity configs: default, egress-dominant (.55/.15/.15/.15),
  water-dominant (.15/.55/.15/.15), equal (.25 each). Validation: held-out RF
  AUC vs. MTBS Chimney Tops 2 perimeter, 500-draw permutation null.

Environment (this VM): Python 3.12.3 system; 4 cores; 7 GB RAM; 48 GB free
disk. geopandas/rasterio/networkx present in system python; osmnx NOT
present (venv to be built). Internet: partially restricted — some domains
returned HTTP 403 in earlier paper work; each source endpoint is probed
individually below and fallbacks are recorded.

## 2026-11-05 — Environment (pending import probe)

- [ ] venv + pinned dependencies (see `environment.yml` / `requirements.txt`
      once written; versions recorded from installed packages, not assumed)
- [ ] endpoint reachability probe for every national source (OSM/Overpass,
      Census TIGER, USGS 3DEP, FEMA USA Structures, LANDFIRE, WRC burn
      probability, HIFLD stations, MTBS/WFIGS perimeters)

## Build order (Nick's ranking)

1. Item 1 real-data ingestion + offline cache (`firescore run --county "Sevier, TN"`)
2. Item 2 scientific fixes (real fuels, spacing, wind-aligned exposure, real
   egress, YAML config, validation module)
3. What-if editor
4. Practitioner features (report cards, inspection queue, uncertainty ranges,
   FireView offline package)
5. County workflow fit (GPKG/SHP/GeoJSON exports, QGIS plugin skeleton,
   ArcGIS Pro .pyt)
6. JOSS-grade engineering (pyproject, CI, docs, notebook, DOI-route verification)
7. Second county unmodified run + Sevier pilot pack

## Open decisions (do not guess)

- DOI archive route: Zenodo RULED OUT by Nick; verify TRACE vs figshare
  against JOSS's current requirements before any archive is created.
- GitHub repo Nsokol44/firescore: this subagent cannot operate the live
  browser; repo creation is staged locally and flagged to the parent agent.

## 2026-11-05 ~11:05 EST — Environment + scaffold (COMPLETE)

- venv `~/workspace/.venvs/firescore` (system-site-packages): geopandas 1.2.0,
  rasterio 1.5.2, networkx 3.7, pandas 3.0.6, numpy 2.5.3, scikit-learn 1.9.1,
  scipy 1.18.1 + pip-installed osmnx 2.1.1, reportlab 5.1.0.
- Endpoint probe results (all from this VM): Census TIGER 200; FEMA USA
  Structures FeatureServer (FiaPA4ga0iQKduv3/USA_Structures_View) 200; HIFLD
  Fire_Stations 200; USGS 3DEP ImageServer 200; AWS terrain tiles 200;
  LFPS GPServer 200; USFS geoplatform Fire_Aviation folder 200 incl.
  USFS_EDW_RMRS_WRC_BurnProbability ImageServer; NPS/GRSM ChimneyTops2
  FeatureServer 200; WFIGS Interagency Perimeters 200; Microsoft
  dataset-links.csv 200 (fallback only). Overpass /api/status returned 406
  on a bare GET (endpoint quirk; the interpreter POST osmnx uses is what
  matters — verdict comes from the roads fetch itself).
- Package scaffold written: config (all constants in YAML, 5 sensitivity
  configs, Fong 6-exit reference, FBFM40 hazard table), cache (GeoParquet +
  GeoTIFF, manifest, OfflineCacheMiss), fetch (TIGER/FEMA/HIFLD/3DEP/WRC/
  WFIGS/NPS via ArcGIS REST; OSM roads+hydrants+draft sites via osmnx;
  LANDFIRE via LFPS async job), egress (real graph: cluster exit counts,
  dead-end, drive-time Dijkstra), features (DEM slope/aspect, wind-aligned
  exposure, FBFM40 modal hazard, wildland distance transform, KD-tree
  spacing), score (5 components, score = range across sensitivity configs),
  validate (permutation-null AUC, RF + spatial block CV, calibration, WRC
  head-to-head), whatif (clear_veg / add_hydrant / add_road with per-$1k
  ranking), report (PDF cards, STR-first queue with persisted log),
  export (GPKG/SHP/GeoJSON/CSV + offline FireView with vendored Leaflet 1.9.4).
- Smoke tests passed: package installs editable; `firescore --help` runs;
  config validates; county FIPS resolution works (Sevier 47155, Blount
  47009, Cocke 47029) from the Census gazetteer.

NEXT: Sevier fetch (the long pole), then first real score run.

## 2026-11-05 ~11:15 EST — Two fetch defects found and fixed

1. PAGINATION BUG (serious): with `f=geojson`, ArcGIS omits
   `exceededTransferLimit` at the top level, so the feature query stopped
   after one page. Sevier "footprints" landed as 900 rows — the in-county
   slice of an OBJECTID-ordered first page — against a true count of 75,227
   (verified by a returnCountOnly query on FIPS='47155'). Fixed: continue
   while pages come back full; footprints now pull by county FIPS directly.
2. osmnx edges carry LIST-valued `osmid` after graph simplification, which
   GeoParquet refuses. Fixed in `fetch/osm.py`.

Fetch restarted in full after the fixes.

## 2026-11-05 ~11:40 EST — Fetch defects #3/#4 + test fix

3. STATIONS SOURCE REPLACED: the legacy HIFLD fire-station service URL is
   dead, and the HIFLD GeoPlatform hub + ArcGIS Online contain no open
   national fire-station service (33 same-named candidates checked; all
   local, largest 744 rows). HIFLD fire stations are no longer openly
   served. Stations now come from OpenStreetMap (Sevier: 11 mapped
   stations — municipal departments present, some volunteer departments
   unmapped; county override documented as the fix). Recorded in code,
   docs, and the report-card footer.
4. Roads cached fine after the osmid fix: 9,497 nodes / 21,614 edges.
   Footprints re-pulled by FIPS: 75,227 structures (matches the service's
   own count exactly).
- Test fix: the egress unit test's fixture made the grid block's only exit
  the spur chain (exits=1 was the CORRECT answer for that fixture). The
  test now uses a hand-computable node radius and asserts exits 4 vs 1.

## 2026-11-05 ~12:05 EST — LANDFIRE route replaced (LFPS v2); tests green

5. LFPS GPServer retired: lfps.usgs.gov now serves the v2 REST API
   (User Guide v6.1). POST to the old submitJob hangs; GET returns the
   website's HTML. New fetcher uses GET /api/job/submit (Layer_List=
   LF2023_FBFM40, Email REQUIRED - usage statistics only; default config
   carries nsokol@utk.edu, flagged for Nick, users set their own) and
   /api/job/status polling. Probe job submitted + executing within
   seconds. edcintl GeoServer WCS and landfire.cr.usgs.gov routes probed
   and dead/flaky - not used.
- Unit tests: 6/6 PASS (mini-county fixture, offline; includes the
  osm_hydrants -> draft_sites_PROXY -> station fallback chain, range
  scores, what-if monotonicity, FireView export).
- DEM cached (3DEP exportImage, 30 m). Fetch order now at LANDFIRE.

## 2026-11-05 ~12:35 EST — Sevier cache COMPLETE (all real, 0 warnings)

boundary 1 (TIGER) | footprints 75,227 (FEMA USA Structures, by FIPS) |
roads 9,497 nodes / 21,614 edges (OSM) | stations 11 (OSM) | DEM (3DEP
30 m) | FBFM40 (LANDFIRE LF2023 via LFPS v2) | hydrants 0 in OSM ->
water falls to draft_sites_PROXY: 9,739 OSM water features (honest label;
county hydrant layer is THE pilot data ask) | WRC burn probability |
perimeters 14 with real years: Chimney Tops 2 2016 (57 km2), INDIGO LANE
2022 = Hatcher Mountain, Seymour 2022, East Parkway 2025, + RX units.
Two more defects fixed en route: WFIGS year field is
attr_FireDiscoveryDateTime; a pd NameError was being swallowed by a bare
except (now imports at module level).

## 2026-11-05 ~13:15 EST — SEVIER SCORED OFFLINE; determinism value-verified

- `firescore run --county "Sevier, TN" --offline`: 75,227 structures in
  ~90 s wall (fetch skipped, cache only). Mean score 0.434; Low 15,694 /
  Moderate 49,394 / High 9,984 / Extreme 155. Water source:
  osm_draft_sites_PROXY (0 OSM hydrants in Sevier). Layer role:
  footprint_proxy (FEMA structures, labelled).
- Two construct fixes from first-run diagnostics: (a) wildland =
  contiguous burnable patch >= 1 ha (config), else 30 m raster grain made
  proximity saturate; (b) water normaliser follows the source construct
  (hydrant 400 m / draft site 1500 m / station drive 5000 m).
- Determinism: repeat offline runs give max |delta| = 0.0 on every
  numeric column (ids and row order identical). Parquet file md5 varies
  (footer serialization), data do not.

## 2026-11-05 ~14:05 EST — what-if sound; hydrant bug fixed; validation CRS bug

- What-if on FS-051786 (a single-family structure in Seymour; score 0.843
  [0.773-0.915], Extreme): clear_veg -$0.0706 ($3,000; best per $),
  add_hydrant -$0.1400 ($6,500; 14 structures), add_road 259 m link
  -$0.0350 ($141,610; 32 structures). All county-mean deltas <= 0.
- BUG (fixed): add_hydrant originally recomputed ALL water components
  from hydrants alone, silently swapping the baseline's draft-site
  construct and RAISING county scores (mean +0.065). Now a hydrant can
  only improve a structure's water term (min of baseline vs hydrant
  term). Regression test added.
- BUG (fixed): validation rerun returned 0 structures inside every
  perimeter - a half-applied CRS fix (points reprojected, perimeter not).
  Both now in EPSG:5070; CRS-consistency test added. Tests 7/7.
- Exports verified: GPKG/SHP/GeoJSON all 75,227 rows; FireView package
  has zero external references (vendored Leaflet + local data.js).
- Report cards: 25 PDFs; card text verified (proxy labels printed,
  ranges not points, screening disclaimer). Queue: 75,227 rows ranked,
  STR flags 0 (no county STR layer supplied - pilot supplies it).
- Blount fetch under way: 79,056 footprints, roads done.

## 2026-11-05 ~15:10 EST — VALIDATION FINAL; BLOUNT PROOF DONE; notebook shipped

- Validation (final code): CT2 composite AUC 0.229 vs permutation null
  [0.491, 0.509] - INVERTED, auto-flagged by the new diagnostic; WRC also
  inverted on CT2 (0.379); RF block-CV 0.925 (park-proximity signal, NOT
  loss skill). Indigo Lane 2022: composite 0.474 (inside null band),
  WRC 0.921, RF block-CV 0.49. FireScore-WRC Spearman 0.226. The honest
  read: perimeter membership is the wrong outcome for park-dominated
  perimeters; the CT2 damage registry is the fix (novelty program step 1).
- BLOUNT COUNTY (47009), UNMODIFIED code + default config: cold fetch
  18m34s (79,056 footprints; 8,064/19,222 road nodes/edges; 7 stations;
  0 hydrants -> draft proxy 10,883); offline run mean 0.427, High+
  Extreme 12.3%. Reusability proof complete.
- Example notebook examples/sevier_end_to_end.ipynb EXECUTED against the
  real Sevier project (nbclient, 0 errors, real recorded outputs).
- Tests: 7/7 on final code. Install check rerunning in a clean venv
  (first attempt died on the 512 MB /tmp tmpfs, not on the package).
- Clean-venv install VERIFIED: fresh venv + `pip install ~/workspace/
  firescore` -> `firescore -h` lists all 8 subcommands, rc=0 (759 MB
  env). GitHub repo creation under Nsokol44 remains for the parent
  agent's browser route; local repo: 3+ commits, clean tree.

## 2026-11-05 ~13:20 EST — Nick's two rulings applied (files govern; PII strip)

1. FOUR FILES GOVERN. NASF (148) + fiResponse (111) are Paper 2's
   multi-event validation set; new module firescore/events.py +
   `validate --nasf/--firesponse`. Structures definition CONFIRMED by
   Katy Daniels: threatened = SOFT (minor heat damage through in-path
   exposure, salvageable); destroyed = structure lost. Field order is
   (threatened, destroyed), anchored on NASF's Chimney Tops 2 record
   (destroyed 1,373 res + 894 other = official after-action counts) and
   both files agreeing on Indigo Lane 2022 (125 res destroyed).
   The inventory's 20,127 mystery RESOLVED: fiResponse Residenc_1 sums
   20,127 = one record reporting 20,000 destroyed residences on a
   5-acre fire (coding anomaly, excluded + flagged by an implausibility
   guard; NOT reinterpreted as threatened) + 125 + 1 + 1 legitimate.
   Harmonised: 259 raw -> 208 events (NASF precedence on the
   2020-2022 overlap); 20 events with destroyed; 2,686 destroyed total;
   threatened (exposure) 1,129. Event-mean exposed score does not
   separate destroyed events (0.42 vs 0.46) - reported plainly.
2. PII STRIP. The EMA CAD log was never ingested by this build (cache
   holds national sources only - verified). Published/shared artifacts
   scrubbed of real street addresses (they came from the public FEMA
   structures layer, not the EMA file, but Nick's rule is aggregate
   geography in examples): PAPER2 update, pilot queue readme (now an
   aggregate top-of-queue profile), this log, and the example notebook
   (re-executed; queue display is community-level; what-if target
   derived from the local queue). NASF/fiResponse incident-name fields
   embed street addresses - event outputs use sequence/source/year
   only. Report cards + the address-level queue remain LOCAL
   practitioner artifacts (county machine, county data); the rule and
   the EMA de-identified-fields-only condition are documented in
   docs/data_sources.md + docs/validation.md.
- Tests: 10/10 (3 new events tests: CT2 anchor mapping, anomaly guard
  + dedupe, no-pooling/no-name-leak).
