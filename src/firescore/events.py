"""Multi-event validation outcomes from the supplied incident files.

Paper 2's validation set is the incident record Katy Daniels supplied
(NASF / FPA-FOD points 2013-2022 + Tennessee Division of Forestry
fiResponse 2020-2026), NOT the code's earlier assumptions: where the
notebook or manuscript text conflicts with these files, the files govern.

STRUCTURES FIELDS - THREE CATEGORIES (threatened / damaged / destroyed)

The FPA-FOD standard carries three structures outcomes per class
(residences, other structures): THREATENED, DAMAGED, DESTROYED.

- "Threatened" (definition confirmed by Katy Daniels, Sevier County
  Fire & Rescue, 2026-11-05, relayed via Nick Sokol) is a SOFT, broad
  category: anything from minor heat damage (her example: warping on
  the siding) where the structure faced damage but is SALVAGEABLE,
  through structures simply IN THE FIRE PATH (exposed), whether or not
  they were damaged.
- "Destroyed" (same confirmation) is the hard category: the structure
  was lost.
- "Damaged" - WORKING DEFINITION, INFERRED, NOT CONFIRMED: structures
  that sustained actual fire damage but were not destroyed - damaged
  yet standing / repairable, short of the total-loss (rebuild)
  threshold that defines destroyed. This wording is inferred from the
  FPA-FOD / NWCG quantity standards; it is NOT derived from values in
  the delivered extracts (which carry no damaged values - see the
  inventory below) and it awaits Katy Daniels' confirmation. Do not
  present it as settled.

COLUMN INVENTORY OF THE DELIVERED EXTRACTS (re-derived 2026-11-05)

Both delivered extracts carry exactly TWO populated structures columns
per class, in the pair order (threatened, destroyed):

- NASF (148 records): Residences / OtherStruc = threatened;
  Residenc_1 / OtherStr_1 = destroyed. The DBF has no third structures
  column at all.
- fiResponse (111 records): the same two populated columns per class
  (OtherStr_1 is zero throughout). Its apparent extra structures
  columns (Residenc_2, Residenc_3, OtherStr_2, OtherStr_3) belong to a
  second, empty attribute block (a join artifact): every numeric field
  in that block is 0 and every text field is null. They carry NO data.

The DAMAGED columns of the FPA-FOD triple are therefore ABSENT from
these extracts - not zero-filled measurements, simply not carried.
This module represents damaged explicitly (0 with
``damaged_carried_in_source = False`` for both delivered files) so a
future export that does carry it slots into the schema without
redefining endpoints, and so damaged is never silently merged into
threatened or destroyed.

ANCHORS (the mapping is pinned by events with independent final
assessments, not by column-name guessing):

- Indigo Lane / Hatcher Mountain, 2022-03-30: BOTH files give
  Residenc_1 = 125 with every other structures field 0. Sevier
  County's final damage assessment for that fire (April 2022) reports
  exactly 125 structures destroyed (64 residential + 61 overnight
  rental), 62 damaged (4 major + 58 minor), 26 affected, 213 total.
  125 == 125 identifies Residenc_1 as DESTROYED (as DAMAGED it would
  read ~62). Incident reporting counts overnight-rental cabins as
  residences, which is why the 125 sits in the residences column and
  the other-structures columns are 0.
- Chimney Tops 2, 2016-11-28 (NASF): Residenc_1 = 1,373 residences +
  OtherStr_1 = 894 other = 2,267 destroyed. The official final
  assessment reports 2,179 destroyed (2,121 residences + 58 other
  structures) and 2,460 damaged-or-destroyed (hence 281 damaged). The
  incident-report total is the same endpoint as the official destroyed
  total on an earlier, looser basis (+4.0%), BUT the residence/other
  split differs sharply (incident 1,373 / 894 vs final 2,121 / 58), so
  TOTAL structures destroyed is the robust endpoint and the split is
  indicative only. Corroboration that the NASF row is an early
  incident snapshot: its injuries field (134) is the 5 Dec 2016
  running estimate, against the final official 191.
- Timber Ridge Road, 2021-12-11 (5 acres): both files give
  Residences = 8, Residenc_1 = 1 - identical, confirming the two
  systems' columns are aligned.
- Behavioural check: the threatened column is populated on 60/148
  NASF and 61/111 fiResponse records, typically small counts on small
  fires (exposure reporting); the destroyed column is populated on
  only 12 NASF and 4 fiResponse records (one of them the anomaly
  below).

LAYOUT GUARD: DBF name truncation makes the full three-column FPA-FOD
layout ambiguous - in a complete export the order is (threatened,
damaged, destroyed), so Residenc_1 there would mean DAMAGED, not
destroyed. If a source file ever arrives with a POPULATED third
structures column, this loader raises instead of guessing: the layout
must be confirmed with the provider before outcomes are computed.

DESIGN RULES enforced by this module:

1. DESTROYED is the primary damage outcome.
2. DAMAGED is a real-damage endpoint: the loss-affected total
   (damaged + destroyed) is reported ALONGSIDE the destroyed-only
   result. Pooling damaged with destroyed is legitimate because both
   denote actual damage - unlike threatened. On the delivered Sevier
   extracts damaged is not carried, so the loss-affected endpoint
   equals the destroyed-only endpoint by ABSENCE of the field, and
   the summary says so explicitly.
3. THREATENED is reported only as an EXPOSURE indicator and is never
   pooled with damaged or destroyed.
4. ANOMALY GUARD: a destroyed count that is physically implausible
   (>= 10,000 structures on one incident) is a coding error, not data
   - the fiResponse export carries exactly one (20,000 residences on
   a 5-acre fire). Such records are excluded from outcome totals and
   returned in the flags list; they are never silently reinterpreted
   as threatened or damaged either.

PRIVACY: only whitelisted, de-identified fields are read (incident id,
date, cause class, acres, the structures fields, injuries, fatalities,
point location). The fiResponse/NASF incident-name fields embed street
addresses for many small incidents; names are used only for internal
perimeter matching and are NEVER written to outputs - events are
identified in outputs by a sequential id, source, date and year. The
Sevier EMA CAD log is not ingested by FireScore at all (see
docs/data_sources.md for the de-identification rule if a county ever
supplies CAD data).
"""

from __future__ import annotations

import re
import unicodedata

import geopandas as gpd
import numpy as np
import pandas as pd

from .geo import WORK_CRS

# Whitelisted source fields (DBF-truncated FPA-FOD names), as verified
# in the delivered extracts (see module docstring): pair order is
# (threatened, destroyed). The FPA-FOD DAMAGED columns are not carried
# in either delivered extract.
_FIELDS = {
    "LocalIncid": "incident_id",
    "FireDiscov": "discovery",
    "Statistica": "cause_code",
    "Residences": "residences_threatened",
    "Residenc_1": "residences_destroyed",
    "OtherStruc": "other_threatened",
    "OtherStr_1": "other_destroyed",
    "NumberInju": "injuries",
    "NumberFata": "fatalities",
    "FinalFireA": "acres",
}
# Columns that would indicate a third structures category if populated.
# In the delivered fiResponse export these exist but are an all-zero
# join artifact; a POPULATED one means a different (full-triple) layout
# whose DBF names are ambiguous - refuse to guess (module docstring).
_THIRD_STRUCTURE_COLUMNS = ("Residenc_2", "OtherStr_2", "Residenc_3", "OtherStr_3")
IMPLAUSIBLE_DESTROYED = 10_000
_NAME_NOISE = {"SEVIER", "COUNTY", "TENNESSEE", "TN", "THE", "FIRE", "WF"}


def _read_source(path: str, source: str) -> gpd.GeoDataFrame:
    g = gpd.read_file(path)
    for c in _THIRD_STRUCTURE_COLUMNS:
        if c in g.columns and pd.to_numeric(g[c], errors="coerce").fillna(0).abs().sum() > 0:
            raise ValueError(
                f"{source}: column {c} is populated, indicating a "
                "three-column structures layout. Under DBF truncation "
                "that layout is ambiguous (in the full FPA-FOD triple, "
                "Residenc_1 = DAMAGED, not destroyed), so the layout "
                "must be confirmed with the data provider before "
                "outcomes are computed. See firescore.events docstring."
            )
    keep = {src: dst for src, dst in _FIELDS.items() if src in g.columns}
    cols = list(keep) + (["IncidentNa"] if "IncidentNa" in g.columns else []) + ["geometry"]
    out = g[cols].rename(columns=keep).copy()
    if "IncidentNa" in out.columns:
        # Internal perimeter-matching ONLY. Incident-name fields in these
        # exports embed street addresses; the column is underscore-marked
        # private and event_table never writes it anywhere.
        out = out.rename(columns={"IncidentNa": "_match_name"})
    else:
        out["_match_name"] = ""
    out["source"] = source
    out["discovery"] = pd.to_datetime(out["discovery"], errors="coerce")
    for c in ("residences_threatened", "residences_destroyed", "other_threatened",
              "other_destroyed", "injuries", "fatalities", "acres"):
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    # DAMAGED: a distinct FPA-FOD category that neither delivered
    # extract carries (2026-11-05 inventory). Represented explicitly as
    # 0 / not-carried so the three-category schema is stable and the
    # absence is visible in every output, never merged away.
    out["residences_damaged"] = 0.0
    out["other_damaged"] = 0.0
    out["damaged_carried_in_source"] = False
    out["structures_threatened"] = out["residences_threatened"] + out["other_threatened"]
    out["structures_damaged"] = out["residences_damaged"] + out["other_damaged"]
    out["structures_destroyed"] = out["residences_destroyed"] + out["other_destroyed"]
    out["structures_loss_affected"] = out["structures_damaged"] + out["structures_destroyed"]
    return out


def load_events(nasf_path: str | None = None, firesponse_path: str | None = None,
                ) -> tuple[gpd.GeoDataFrame, list[dict]]:
    """Load + harmonise the supplied incident files.

    Returns (events, flags). Events are deduplicated across sources by
    discovery date + rounded location (the 2020-2022 overlap appears in
    both files; NASF, the federal FPA-FOD record, takes precedence).
    Records failing the plausibility guard are excluded from the events
    frame and described in flags.
    """
    frames = []
    if nasf_path:
        frames.append(_read_source(nasf_path, "NASF"))
    if firesponse_path:
        frames.append(_read_source(firesponse_path, "fiResponse"))
    if not frames:
        raise ValueError("at least one incident file is required")
    ev = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)

    flags: list[dict] = []
    bad = ev["structures_destroyed"] >= IMPLAUSIBLE_DESTROYED
    for _, r in ev[bad].iterrows():
        flags.append({
            "incident_id": str(r["incident_id"]),
            "source": r["source"],
            "year": int(r["discovery"].year) if pd.notna(r["discovery"]) else None,
            "structures_destroyed_reported": float(r["structures_destroyed"]),
            "reason": ("implausible destroyed count (coding anomaly); excluded "
                       "from outcome totals pending provider confirmation; "
                       "NOT reinterpreted as threatened or damaged"),
        })
    ev = ev[~bad].copy()

    ev = ev.to_crs(WORK_CRS)
    ev["_key"] = list(zip(ev["discovery"].dt.date,
                          (ev.geometry.x / 100).round(), (ev.geometry.y / 100).round()))
    ev["_precedence"] = np.where(ev["source"] == "NASF", 0, 1)  # federal record wins
    ev = ev.sort_values(["_precedence"]).drop_duplicates("_key", keep="first")
    ev = ev.drop(columns=["_key", "_precedence"]).reset_index(drop=True)
    ev["event_seq"] = np.arange(1, len(ev) + 1)
    return ev, flags


def _norm_tokens(name: str) -> set[str]:
    s = unicodedata.normalize("NFKD", str(name)).upper()
    toks = {t for t in re.split(r"[^A-Z0-9]+", s) if t and t not in _NAME_NOISE}
    return toks


def _match_perimeter(event_name: str, year: int, perimeters: gpd.GeoDataFrame):
    """Match an incident to a cached perimeter by distinctive name tokens
    + year. Internal only - names never leave this module."""
    etoks = _norm_tokens(event_name)
    best, best_overlap = None, 0
    for _, row in perimeters.iterrows():
        if int(row.get("fire_year", 0)) not in (0, year):
            continue
        ptoks = _norm_tokens(str(row.get("fire_name", "")))
        overlap = len(etoks & ptoks)
        if overlap > best_overlap and overlap >= min(2, len(ptoks)):
            best, best_overlap = row, overlap
    return best


def event_table(scored: gpd.GeoDataFrame, events: gpd.GeoDataFrame,
                perimeters: gpd.GeoDataFrame | None = None) -> pd.DataFrame:
    """Per-event exposure/outcome table.

    Exposure geometry: the matched cached perimeter when one exists,
    else a circle at the incident point with the reported final area
    (flagged ``circle_approx``; radius floored at 50 m, capped at 5 km).

    Three structures categories are kept distinct end to end:
    ``*_destroyed`` and ``*_damaged`` are damage OUTCOMES (their sum is
    the ``*_loss_affected_outcome``); ``*_threatened`` is EXPOSURE
    context only and is never added to either. The events' private
    ``_match_name`` is used solely for perimeter matching and is never
    copied to output.
    """
    work = scored.to_crs(WORK_CRS)
    cents = work.geometry.centroid
    per_w = perimeters.to_crs(WORK_CRS) if perimeters is not None else None
    rows = []
    for _, ev in events.iterrows():
        year = int(ev["discovery"].year) if pd.notna(ev["discovery"]) else 0
        geom, how = None, "circle_approx"
        if per_w is not None:
            hit = _match_perimeter(str(ev.get("_match_name", "")), year, per_w)
            if hit is not None:
                geom, how = hit.geometry, "perimeter"
        if geom is None:
            radius = float(np.clip(np.sqrt(max(float(ev["acres"]), 0.01) * 4046.86 / np.pi), 50, 5000))
            geom = ev.geometry.buffer(radius)
        inside = cents.within(geom)
        rows.append({
            "event_seq": int(ev["event_seq"]),
            "source": ev["source"],
            "year": year,
            "acres": float(ev["acres"]),
            "exposure_geometry": how,
            "structures_exposed": int(inside.sum()),
            "mean_score_exposed": float(work.loc[inside, "score"].mean()) if inside.any() else None,
            "structures_threatened_exposure": float(ev["structures_threatened"]),
            "structures_damaged": float(ev["structures_damaged"]),
            "structures_destroyed_outcome": float(ev["structures_destroyed"]),
            "structures_loss_affected_outcome": float(ev["structures_loss_affected"]),
            "residences_damaged": float(ev["residences_damaged"]),
            "residences_destroyed_outcome": float(ev["residences_destroyed"]),
            "damaged_carried_in_source": bool(ev["damaged_carried_in_source"]),
            "injuries": float(ev["injuries"]),
            "fatalities": float(ev["fatalities"]),
        })
    return pd.DataFrame(rows)


def event_outcome_summary(table: pd.DataFrame) -> dict:
    """Aggregate validation summary under the three-category design.

    DESTROYED is the primary outcome. DAMAGED is a real-damage endpoint
    reported in its own right, and the loss-affected total
    (damaged + destroyed) is reported alongside the destroyed-only
    result. THREATENED appears only as an exposure total. No key mixes
    threatened with either damage category.
    """
    dmg = table[table["structures_destroyed_outcome"] > 0]
    loss = table[table["structures_loss_affected_outcome"] > 0]
    carried = bool(table["damaged_carried_in_source"].any()) if len(table) else False
    return {
        "events": int(len(table)),
        "events_with_destroyed": int(len(dmg)),
        "structures_destroyed_total": float(table["structures_destroyed_outcome"].sum()),
        "events_with_damaged": int((table["structures_damaged"] > 0).sum()),
        "structures_damaged_total": float(table["structures_damaged"].sum()),
        "damaged_carried_in_source": carried,
        "damaged_note": (
            "DAMAGED is a distinct FPA-FOD category (real damage short of "
            "destruction; working definition inferred from the FPA-FOD/NWCG "
            "standard, pending Katy Daniels' confirmation). It is NOT "
            "carried in the delivered Sevier extracts (2026-11-05 column "
            "inventory: no populated damaged column in either file), so "
            "damaged totals are 0 here and the loss-affected endpoint "
            "equals the destroyed-only endpoint by absence of the field, "
            "not by merging."
            if not carried else
            "DAMAGED totals come from the source files' damaged columns."
        ),
        "events_with_loss_affected": int(len(loss)),
        "structures_loss_affected_total": float(table["structures_loss_affected_outcome"].sum()),
        "structures_threatened_exposure_total": float(table["structures_threatened_exposure"].sum()),
        "exposure_note": ("threatened totals are EXPOSURE context (soft category: "
                          "minor damage through in-path exposure), never an outcome "
                          "and never added to damaged or destroyed"),
        "mean_score_exposed_destroyed_events": (
            float(dmg["mean_score_exposed"].mean()) if len(dmg) else None),
        "mean_score_exposed_no_destroyed_events": (
            float(table.loc[table["structures_destroyed_outcome"] == 0, "mean_score_exposed"].mean())
            if (table["structures_destroyed_outcome"] == 0).any() else None),
        "mean_score_exposed_loss_affected_events": (
            float(loss["mean_score_exposed"].mean()) if len(loss) else None),
        "mean_score_exposed_no_loss_affected_events": (
            float(table.loc[table["structures_loss_affected_outcome"] == 0, "mean_score_exposed"].mean())
            if (table["structures_loss_affected_outcome"] == 0).any() else None),
    }


# Backwards-compatible alias: the summary now covers all three
# categories, with destroyed still the primary outcome.
destroyed_only_summary = event_outcome_summary
