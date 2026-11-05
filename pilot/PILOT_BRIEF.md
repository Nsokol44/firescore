# FireScore Pilot — Sevier County Fire & Rescue

**One-page brief for the pilot lead (Katy Daniels, Wildfire Hazard Mitigation Specialist)**

## What FireScore is

A free, open-source tool that scores **every structure in Sevier County**
for wildfire vulnerability and ranks them for action. It runs on national
data (no county data purchase), and after one download it runs **entirely
offline** — built for mountain coverage.

Each structure gets five component scores (0–1) and a class
(Low / Moderate / High / Extreme), reported as a **range** across five
defensible weight configurations, never a single over-precise number:

- **Egress** — outward road exits counted on the real road network
  (national research puts the fatality-risk threshold near six exits),
  dead ends, and drive time to the nearest station.
- **Water access** — distance to hydrants / drafting sites.
- **Vegetation/fuel** — LANDFIRE fuel models around the structure.
- **Terrain** — slope and exposure to downslope wind.
- **Structure spacing** — how close the next structure is (the
  house-to-house spread that drove Gatlinburg's 2016 losses).

## What the department gets

1. The scored layer (GeoPackage/shapefile/GeoJSON) for county GIS.
2. An **inspection queue**: structures ranked worst-first, STR-permit
   parcels first when the permit list is loaded, with inspected tracking.
3. **Report cards**: a one-page PDF per structure an inspector can hand to
   an owner — the score, why, and what to do about it.
4. A **what-if tool**: clear vegetation, add a hydrant, add a second road —
   see the score change and the cost-effectiveness ranking before spending.
5. **FireView**: the map on a phone, offline, for field use.

## What the pilot asks of the department

- Katy leads; one GIS contact for questions about local layers.
- Optional local layers improve it (parcels, hydrants, stations, STR
  permits) — none are required to start.
- Log every decision the tool changes in the decisions log (template in
  this pack). That log is the evidence base for the research paper and for
  any future county adoption decision.

## What FireScore is not

It is a screening and prioritisation tool. It does not predict whether a
specific structure will burn, and its rankings should be checked against
local knowledge — the pilot's job is exactly to find where it disagrees.

## Validation status (filled in from the Sevier run)

See `outputs/validation.json` in the Sevier project: the score has been
tested against the real Chimney Tops 2 (2016) and Hatcher Mountain (2022)
perimeters with a permutation null, spatial block cross-validation, and a
head-to-head against the US Forest Service's national burn-probability
layer. The numbers in that file — good or bad — are the ones to quote.
