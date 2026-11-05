# Validation

FireScore has two validation designs. The **multi-event design is the
governing one** for the Sevier research program (Nick's ruling,
2026-11-05: the supplied data files govern over earlier code and text);
the perimeter design below it is retained as a diagnostic.

## Multi-event validation (NASF + fiResponse)

`firescore validate --nasf <file> --firesponse <file>` builds the
event table from the incident files Katy Daniels supplied (NASF /
FPA-FOD 2013–2022, 148 records; TN Division of Forestry fiResponse
2020–2026, 111 records), deduplicated across sources (NASF precedence;
208 harmonised Sevier events).

**Structures-field definitions** — the FPA-FOD standard carries
THREE structures outcomes per class (residences, other structures):
threatened, damaged, destroyed. Two of the three definitions were
confirmed by Katy Daniels (Sevier County Fire & Rescue reporting
practice, 2026-11-05):

> *Threatened* is a soft, broad category: anything from minor heat
> damage (e.g. warping on the siding) where the structure faced damage
> but is salvageable, through structures simply in the fire path
> (exposed), whether or not they were damaged. *Destroyed* is the hard
> category: the structure was lost.

> *Damaged* — WORKING DEFINITION, INFERRED, NOT CONFIRMED: structures
> that sustained actual fire damage but were not destroyed — damaged
> yet standing / repairable, short of the total-loss (rebuild)
> threshold that defines destroyed. This wording is inferred from the
> FPA-FOD / NWCG quantity standards and awaits Katy Daniels'
> confirmation; it is not derived from values in the delivered files.

**Column inventory (re-derived 2026-11-05):** both delivered extracts
carry exactly two populated structures columns per class, in the pair
order (threatened, destroyed). The DAMAGED columns are absent — the
NASF DBF has no third structures column, and fiResponse's apparent
extra structures columns belong to an empty join-artifact attribute
block (all zeros / nulls). The module therefore represents damaged
explicitly (0, flagged `damaged_carried_in_source = false`) so the
absence is visible in every output and damaged is never silently
merged into another category. A source file arriving with a
*populated* third structures column raises an error instead of being
guessed at: under DBF truncation the full-triple layout is ambiguous
(in a complete export Residenc_1 would be DAMAGED, not destroyed), so
the layout must be confirmed with the provider first.

**Mapping anchors:** the pair order is pinned by events with
independent final assessments, not by column names. Indigo Lane /
Hatcher Mountain (2022-03-30): both files give 125 in the second
column and 0 elsewhere; Sevier County's final damage assessment for
that fire reports exactly **125 structures destroyed** (64 residential
+ 61 overnight rental), 62 damaged, 26 affected — 125 == 125 pins the
second column as DESTROYED (as damaged it would read ~62; incident
reporting counts rental cabins as residences, which is why the other
columns are 0). Chimney Tops 2 (2016-11-28, NASF): 1,373 + 894 =
2,267 in the second columns vs the official final 2,179 destroyed —
the same endpoint on an earlier, looser incident-report basis
(+4.0%), but the residence/other split differs sharply from the final
assessment (1,373 / 894 vs 2,121 / 58), so **total structures
destroyed is the robust endpoint and the split is indicative only**.

Enforced rules:

- **Destroyed is the primary damage outcome.**
- **Damaged is a real-damage endpoint.** The loss-affected total
  (damaged + destroyed) is reported alongside the destroyed-only
  result; pooling the two is legitimate because both denote actual
  damage. On the delivered extracts damaged is not carried, so the
  loss-affected endpoint equals the destroyed-only endpoint by
  absence of the field, and the summary says so.
- **Threatened is an exposure indicator only** and is never pooled
  with either damage category. The module never emits a pooled
  threatened-inclusive "impacted" figure; any pooled figure produced
  elsewhere must be reported alongside the destroyed-only result.
- **Anomaly guard:** an implausible destroyed count (≥ 10,000 on one
  incident — the fiResponse export contains exactly one: 20,000
  residences on a 5-acre fire) is excluded from outcome totals and
  flagged, never silently used or reinterpreted.
- Exposure geometry is the matched real perimeter when one is cached,
  else an area-derived circle at the incident point (flagged
  `circle_approx`). Exposure denominators use *current* footprints;
  structures destroyed and never rebuilt are invisible — a stated
  limitation.
- Outputs (`event_table.csv`, `event_validation.json`) identify events
  by sequence, source and year only: the incident-name fields in these
  exports embed street addresses and are never written out.

Sevier reference results (2026-11-05, three-category mapping): 20
events with destroyed structures, 2,686 structures destroyed in
total; damaged 0 (category not carried in the delivered extracts —
see the inventory above), so the loss-affected endpoint is likewise
20 events / 2,686 structures, equal to destroyed-only by absence;
threatened (exposure) total 1,129. The mean FireScore of exposed
structures does not separate destroyed from non-destroyed events
(0.42 vs 0.46), and the loss-affected separation check is identical
on this data for the same reason — the multi-event set makes the
index testable across 208 events; it does not manufacture a
structure-loss claim.

## Perimeter validation (diagnostic)

`firescore validate` also tests the score against real burn perimeters
in the cache (drop in your own with `firescore import-perimeter`). The
outcome is an exposure outcome — the structure's centroid inside the
mapped perimeter. Perimeter membership is **not** structure loss (see
the inverted Chimney Tops 2 diagnostic the module emits); treat these
numbers as diagnostics, not validation of loss prediction.

For each perimeter it reports:

- **Composite AUC + permutation null** — the manuscript's protocol
  (500 label permutations, empirical p), now on real data.
- **Random-forest AUC** on the five components, plain 70/30 split
  (continuity with the manuscript) **and spatial block cross-validation**
  (1 km blocks, 5 folds) — the honest number for clustered parcel data.
- **Calibration** — observed burn rate by score decile (CSV + plot) and a
  Brier score.
- **Head-to-head** — Wildfire Risk to Communities burn probability sampled
  at the same structures: its AUC against the same outcome, and its rank
  correlation with FireScore.

A score that cannot beat its permutation null, or that loses its block-CV
advantage, is reported as exactly that. The tool's credibility with a fire
department depends on the nulls being real.
