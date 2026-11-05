---
title: 'FireScore: a reusable, offline-capable wildfire vulnerability index for any US county'
tags:
  - Python
  - wildfire
  - wildland-urban interface
  - GIS
  - vulnerability index
  - egress
authors:
  - name: Katy Daniels
    affiliation: 1
  - name: Nicholas J. Sokol
    orcid: 0000-0002-4798-0056
    affiliation: 1
affiliations:
  - name: Department of Geography & Sustainability, University of Tennessee, Knoxville, TN, USA
    index: 1
date: 5 November 2026
bibliography: paper.bib
# NOTE for the submitting author: JOSS also requires (verified 2026-11-05
# against joss.readthedocs.io/en/latest/submitting.html):
#  - an archive DOI minted at acceptance in a DOI-issuing repository.
#    Zenodo was ruled out by the authors; figshare is the verified route
#    (JOSS author guidance names figshare explicitly; figshare mints
#    DataCite DOIs, prefix 10.6084, and has a GitHub integration).
#  - a repository public for MORE THAN SIX MONTHS with iterative public
#    development before submission (pre-review screening gate).
#  - an explicit AI-usage disclosure statement (see below).
---

# Summary

County fire departments allocate finite mitigation budgets — defensible-space
inspections, hydrant installation, secondary-egress requirements — across
thousands of structures, usually by proximity to the most recent burn or by
staff judgement. `FireScore` is a Python package that computes a
parcel/structure-level wildfire vulnerability index for **any US county**
from free national data, with one command
(`firescore run --county "Sevier, TN"`), and hands the fire marshal a
scored layer the same day. Its five components — egress counted as outward
road exits on the real OpenStreetMap graph (motivated by Fong et al.'s
finding of a fatality-risk threshold near six community exits), water
access, LANDFIRE fuel models, wind-aligned terrain exposure from USGS
3DEP, and structure-to-structure spacing — are combined under a versioned
YAML configuration, and every score is reported as a range across
weight-sensitivity configurations rather than a point value.

# Statement of need

Existing parcel-level tools are either national fire-behaviour products
that cannot be retuned locally (the First Street Foundation model), or
single-jurisdiction indices with no reusable software. FireScore is built
for the operational cadence of a county department: one online fetch
populates a GeoParquet/GeoTIFF cache, and every later run — scoring,
validation, what-if mitigation analysis, PDF report cards, the inspection
queue, and the offline FireView field map — works with no network, which
matters in mountain counties with spotty coverage. Validation against real
burn perimeters is built in, including a permutation null, spatial block
cross-validation, calibration, and a head-to-head against the USFS
Wildfire Risk to Communities burn-probability layer, so a department can
see whether the index earns its rankings before spending by them.

# AI usage disclosure

Generative AI (Claude, Anthropic) assisted with code generation and
documentation drafting for this software. The human authors framed the
problem, made the design decisions (component definitions, data sources,
validation protocol), and reviewed and validated all AI-assisted outputs,
including live end-to-end runs on Sevier County, Tennessee and a second,
unmodified county run.

# Acknowledgements

FireScore builds on OpenStreetMap (© OpenStreetMap contributors), USGS
3DEP, LANDFIRE, FEMA USA Structures, HIFLD, and the USFS Wildfire Risk to
Communities programme. The Sevier County pilot is led by Katy Daniels in
her role with Sevier County Fire & Rescue, declared as a competing
interest in the companion manuscript.

# References
