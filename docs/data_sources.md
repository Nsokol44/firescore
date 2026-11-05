# Data sources

All inputs are free national products, pulled once per county and cached
with per-layer provenance (`cache/manifest.json`).

| Layer | Source | Notes |
|---|---|---|
| Boundary | Census TIGER/Line 2024 | county by FIPS |
| Structures | FEMA USA Structures (ORNL/FEMA) | footprints as parcel proxy, labelled; county parcels override |
| Roads | OpenStreetMap via osmnx | drive network, speeds + travel times |
| Hydrants | OpenStreetMap | volunteer-mapped; sparse in rural counties |
| Draft sites | OpenStreetMap water features | PROXY for tanker drafting |
| Stations | OpenStreetMap | HIFLD's open fire-station service is retired (verified 2026-11-05); county layer overrides |
| Terrain | USGS 3DEP ImageServer | ~30 m DEM export |
| Fuels | LANDFIRE FBFM40 via LFPS | async product service |
| Burn probability | USFS Wildfire Risk to Communities | comparison/validation only, never a component |
| Perimeters | NPS/GRSM (Chimney Tops 2), NIFC WFIGS | validation outcomes; user files importable |

License note: OSM data is © OpenStreetMap contributors (ODbL); LANDFIRE,
3DEP, TIGER, FEMA and USFS products are US federal works. FireScore
code is MIT.

## Supplied incident files (research-program data)

These files were supplied by Katy Daniels (Sevier County Fire &
Rescue). **Where they conflict with earlier code, notebook outputs, or
manuscript text, the files govern.**

| File | Records | Role |
|---|---|---|
| NASF / FPA-FOD points, 2013–2022 | 148 | Multi-event validation set (Paper 2) |
| TN Forestry fiResponse, 2020–2026 | 111 | Multi-event validation set (Paper 2) |
| NIFC / IRWIN points, 2016–2025 | 106 | Cross-check (CT2 acreage: 17,140 ac vs NASF's 17,010 — NASF governs the Paper 2 set) |
| Sevier County EMA CAD brush-fire calls, 2020–2025 | 763 | **Not ingested by FireScore** — see the privacy rule below |

Structures-field definitions for the validation files are documented
in [Validation](validation.md): the FPA-FOD standard carries three
categories (threatened = soft exposure category; damaged = real
damage short of destruction, working definition inferred and pending
the provider's confirmation; destroyed = structure lost). Both
delivered extracts carry only the (threatened, destroyed) pair — the
damaged columns are absent (the fiResponse file's extra structures
columns are an empty join artifact) — credited to the data provider's
practice and verified against the county's final damage assessments.

## Privacy — what never gets published

- **EMA CAD data carries caller PII** (names on 709/763 records, phone
  numbers on 643/763, street addresses). FireScore does not ingest it.
  If a county ever supplies CAD data for an analysis, ingest ONLY
  de-identified fields (date, community/jurisdiction, disposition,
  cause class), strip caller name/phone/address fields before any use,
  and document that choice. The raw EMA file and any caller-identifying
  fields must never enter this repository or any shipped cache.
- **Incident-name fields** in NASF/fiResponse embed street addresses
  for many small incidents; event outputs use sequence/source/year
  identifiers only.
- **Report cards and the inspection queue are local practitioner
  features**: they are generated on the county's own machine, from the
  county's own data, for hand-delivery. Published examples in this
  project use aggregate geography (community level) or clearly
  synthetic example parcels — never real addresses.
