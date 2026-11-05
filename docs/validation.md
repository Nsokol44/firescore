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

**Structures-field definition** — confirmed by Katy Daniels (Sevier
County Fire & Rescue reporting practice, 2026-11-05):

> *Threatened* is a soft, broad category: anything from minor heat
> damage (e.g. warping on the siding) where the structure faced damage
> but is salvageable, through structures simply in the fire path
> (exposed), whether or not they were damaged. *Destroyed* is the hard
> category: the structure was lost.

Enforced rules:

- **Destroyed is the only damage outcome** (FPA-FOD pair order
  threatened→destroyed; anchored on the Chimney Tops 2 record:
  1,373 residences + 894 other structures destroyed).
- **Threatened is an exposure indicator only.** The module never emits
  a pooled threatened+destroyed "impacted" figure; any pooled figure
  produced elsewhere must be reported alongside the destroyed-only
  result.
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

Sevier reference results (2026-11-05): 20 events with destroyed
structures, 2,686 structures destroyed in total; threatened
(exposure) total 1,129. The mean FireScore of exposed structures does
not separate destroyed from non-destroyed events (0.42 vs 0.46) — the
multi-event set makes the index testable across 208 events; it does
not manufacture a structure-loss claim.

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
