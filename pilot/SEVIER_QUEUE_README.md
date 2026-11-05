# Sevier County inspection queue — deliverable notes

**File:** `projects/sevier_47155/outputs/inspection_queue.csv` (75,227 rows,
worst-first), generated 2026-11-05 from the first full FireScore run of
Sevier County (all national sources; see the run's provenance.json).

## How to use it

- Work the queue top-down. `queue_rank` is by the upper bound of the score
  range, so structures that are worst under *any* defensible weighting
  come first.
- Mark completions with
  `firescore queue --county "Sevier, TN" --mark-inspected FS-000001,FS-000002`
  — the state persists in the project and survives re-runs.
- When the county assessor STR layer is available, re-run with
  `--str-layer <file>`: STR-permit structures are flagged `is_str` and can
  be worked as their own worst-first list. In this first run no STR layer
  was supplied, so `is_str` is 0 throughout — nothing was inferred.

## Top of the queue (2026-11-05 run) — aggregate profile

Published examples use aggregate geography only; the address-level queue
itself is generated locally by the queue command and stays on the
practitioner's machine (see the privacy note in docs/data_sources.md).

- All 25 top-ranked structures are class **Extreme** (of 155 Extreme
  county-wide, out of 75,227).
- By community: Sevierville 10, Seymour 9, Strawberry Plains 3, Kodak 2.
- 72% of the top 25 sit in road clusters with **0 counted outward exits**
  — read with caveat 4 below: border clusters (Seymour, Strawberry
  Plains) are exactly where county-line graph truncation bites, so
  verify exit counts against the real road network before acting.
- The county class distribution: Low 15,694 / Moderate 49,394 /
  High 9,984 / Extreme 155.

## Caveats the pilot must carry (from the run's provenance)

1. **Structures are building footprints** (FEMA USA Structures), labelled
   `footprint_proxy` — not assessor parcels. Address fields are the
   structures layer's own; verify against the parcel fabric in week 1.
2. **Water is a labelled proxy** (`osm_draft_sites_PROXY`): OpenStreetMap
   has zero hydrants mapped in Sevier County. The queue's water term is
   drafting distance to open water. The county hydrant layer is the
   single highest-value data contribution the pilot can make.
3. **Stations are the 11 OSM-mapped stations.** Unmapped volunteer
   stations make some drive distances too long. A verified station list
   (even a spreadsheet of addresses) overrides via the station layer.
4. **Exit counts truncate at the county line.** The road graph is clipped
   to Sevier County, so clusters near the border (e.g. Seymour) may show
   fewer exits than they truly have where roads continue into Knox or
   Blount County. Verify the top Seymour clusters against the real road
   network before acting on exit counts alone.
5. Scores are **screening values**, not loss predictions; the validation
   diagnostics (perimeter AUCs, incl. an inverted CT2 result explained in
   validation.json) ship with the project outputs.
