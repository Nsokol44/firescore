"""Multi-event validation outcomes from the supplied incident files.

Paper 2's validation set is the incident record Katy Daniels supplied
(NASF / FPA-FOD points 2013-2022 + Tennessee Division of Forestry
fiResponse 2020-2026), NOT the code's earlier assumptions: where the
notebook or manuscript text conflicts with these files, the files govern.

STRUCTURES-FIELD DEFINITION (confirmed by Katy Daniels, Sevier County
Fire & Rescue, 2026-11-05, relayed via Nick Sokol):

- "Threatened" is a SOFT, broad category: anything from minor heat
  damage (her example: warping on the siding) where the structure faced
  damage but is SALVAGEABLE, through structures simply IN THE FIRE PATH
  (exposed), whether or not they were damaged.
- "Destroyed" is the hard category: the structure was lost.

Consequences enforced by this module:

1. DESTROYED is the only damage outcome. In both files the FPA-FOD pair
   order is (threatened, destroyed): Residences/OtherStruc = threatened,
   Residenc_1/OtherStr_1 = destroyed. Verified against the Chimney
   Tops 2 record (destroyed 1,373 residences + 894 other = the official
   after-action counts) and the 2022 Indigo Lane record, on which both
   files agree (destroyed residences = 125).
2. THREATENED is reported only as an EXPOSURE indicator. This module
   never emits a pooled threatened+destroyed "impacted" figure; if a
   caller constructs one elsewhere it must be reported alongside the
   destroyed-only result.
3. ANOMALY GUARD: a destroyed count that is physically implausible
   (>= 10,000 structures on one incident) is a coding error, not data -
   the fiResponse export carries exactly one (20,000 residences on a
   5-acre fire). Such records are excluded from outcome totals and
   returned in the flags list; they are never silently reinterpreted
   as threatened either.

PRIVACY: only whitelisted, de-identified fields are read (incident id,
date, cause class, acres, the four structures fields, injuries,
fatalities, point location). The fiResponse/NASF incident-name fields
embed street addresses for many small incidents; names are used only
for internal perimeter matching and are NEVER written to outputs -
events are identified in outputs by a sequential id, source, date and
year. The Sevier EMA CAD log is not ingested by FireScore at all (see
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

# Whitelisted source fields (DBF-truncated FPA-FOD names).
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
IMPLAUSIBLE_DESTROYED = 10_000
_NAME_NOISE = {"SEVIER", "COUNTY", "TENNESSEE", "TN", "THE", "FIRE", "WF"}


def _read_source(path: str, source: str) -> gpd.GeoDataFrame:
    g = gpd.read_file(path)
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
    out["structures_threatened"] = out["residences_threatened"] + out["other_threatened"]
    out["structures_destroyed"] = out["residences_destroyed"] + out["other_destroyed"]
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
                       "NOT reinterpreted as threatened"),
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

    Columns named ``*_destroyed`` are the OUTCOME. Columns named
    ``*_threatened`` are EXPOSURE context only. No pooled column exists.
    The events' private ``_match_name`` is used solely for perimeter
    matching and is never copied to output.
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
            "structures_destroyed_outcome": float(ev["structures_destroyed"]),
            "residences_destroyed_outcome": float(ev["residences_destroyed"]),
            "injuries": float(ev["injuries"]),
            "fatalities": float(ev["fatalities"]),
        })
    return pd.DataFrame(rows)


def destroyed_only_summary(table: pd.DataFrame) -> dict:
    """Aggregate validation summary. DESTROYED ONLY - by construction
    this function has no pooled threatened+destroyed figure to give."""
    dmg = table[table["structures_destroyed_outcome"] > 0]
    return {
        "events": int(len(table)),
        "events_with_destroyed": int(len(dmg)),
        "structures_destroyed_total": float(table["structures_destroyed_outcome"].sum()),
        "structures_threatened_exposure_total": float(table["structures_threatened_exposure"].sum()),
        "exposure_note": ("threatened totals are EXPOSURE context (soft category: "
                          "minor damage through in-path exposure), never an outcome"),
        "mean_score_exposed_destroyed_events": (
            float(dmg["mean_score_exposed"].mean()) if len(dmg) else None),
        "mean_score_exposed_no_destroyed_events": (
            float(table.loc[table["structures_destroyed_outcome"] == 0, "mean_score_exposed"].mean())
            if (table["structures_destroyed_outcome"] == 0).any() else None),
    }
