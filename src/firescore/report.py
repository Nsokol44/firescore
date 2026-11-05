"""Practitioner outputs: one-page parcel report cards (PDF) and the
STR-first inspection queue with persisted inspected tracking."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd

COMPONENT_LABELS = {
    "egress": ("Egress", "How many ways out, and how far the fire station is by road."),
    "water": ("Water access", "Distance to the nearest hydrant or drafting site."),
    "vegetation": ("Vegetation / fuel", "LANDFIRE fuel model around the structure and distance to wildland."),
    "terrain": ("Terrain", "Slope steepness and exposure to the prevailing downslope wind."),
    "spacing": ("Structure spacing", "How close the nearest neighbouring structure is (house-to-house spread)."),
}

WHY_TEMPLATES = {
    "egress": "This property's road cluster has {exits} outward exit(s) and the nearest station is {mins:.0f} minutes away by road.",
    "water": "The nearest water source is {dist:.0f} m away ({source}).",
    "vegetation": "The surrounding fuel model scores {hazard:.2f} and wildland is {dist:.0f} m away.",
    "terrain": "The slope is {slope:.0f} degrees with wind exposure {expo:.2f} for a wind from {wind:.0f} degrees.",
    "spacing": "The nearest neighbouring structure is {nn:.0f} m away.",
}


def _why_lines(row: pd.Series) -> tuple[list[str], list[str]]:
    comp = {c: float(row[f"comp_{c}"]) for c in COMPONENT_LABELS}
    ranked = sorted(comp.items(), key=lambda kv: kv[1], reverse=True)
    why, actions = [], []
    facts = {
        "exits": int(row.get("cluster_exits", 0)),
        "mins": float(row.get("station_drive_s", 0)) / 60.0,
        "dist": float(row.get("dist_water_m", 0)),
        "source": str(row.get("water_source", "")),
        "hazard": float(row.get("fuel_hazard", 0)),
        "slope": float(row.get("slope_deg", 0)),
        "expo": float(row.get("wind_exposure", 0)),
        "wind": float(row.get("wind_from_deg", 0)),
        "nn": float(row.get("nn_structure_m", 0)),
    }
    for name, value in ranked[:3]:
        label, _ = COMPONENT_LABELS[name]
        tmpl = WHY_TEMPLATES[name]
        if name == "vegetation":
            why.append(f"{label} ({value:.2f}): " + tmpl.format(
                hazard=facts["hazard"], dist=float(row.get("dist_wildland_m", 0))))
        else:
            try:
                why.append(f"{label} ({value:.2f}): " + tmpl.format(**facts))
            except (KeyError, ValueError):
                why.append(f"{label} ({value:.2f})")
    for name, _ in ranked:
        if name == "vegetation":
            actions.append("Clear defensible space: remove flammable vegetation within 30 ft (9 m) of the structure.")
        elif name == "egress" and facts["exits"] < 6:
            actions.append("Support a second road exit for this cluster; it currently has "
                           f"{facts['exits']} outward exit(s).")
        elif name == "water":
            actions.append("Nearest water is far: flag for the hydrant / draft-site plan.")
        elif name == "spacing":
            actions.append("Create non-combustible separation from the neighbouring structure "
                           "(fencing, outbuilding fuels, wood piles).")
        elif name == "terrain":
            actions.append("Slope/wind exposure is fixed: prioritise roof, vent and deck hardening.")
        if len(actions) >= 3:
            break
    return why, actions


def report_card(row: pd.Series, out_path: str | Path, county_label: str) -> Path:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    out_path = Path(out_path)
    c = canvas.Canvas(str(out_path), pagesize=LETTER)
    w, h = LETTER
    y = h - 0.8 * inch
    c.setFont("Times-Bold", 16)
    c.drawString(0.8 * inch, y, "FireScore — Parcel Report Card")
    y -= 0.3 * inch
    c.setFont("Times-Roman", 11)
    addr = row.get("PROP_ADDR") or row.get("prop_addr") or ""
    city = row.get("PROP_CITY") or row.get("prop_city") or ""
    c.drawString(0.8 * inch, y, f"{county_label}  •  Structure {row['structure_id']}"
                 + (f"  •  {addr} {city}".rstrip() if str(addr).strip() else ""))
    y -= 0.35 * inch
    c.setFont("Times-Bold", 13)
    c.drawString(0.8 * inch, y,
                 f"Vulnerability class: {row['vuln_class']}   "
                 f"Score {float(row['score']):.2f}  (range {float(row['score_low']):.2f}–{float(row['score_high']):.2f})")
    y -= 0.15 * inch
    c.setFont("Times-Italic", 9)
    c.drawString(0.8 * inch, y, "The score is a range across five defensible weight configurations, not a single number.")
    y -= 0.4 * inch
    c.setFont("Times-Bold", 12)
    c.drawString(0.8 * inch, y, "Component breakdown (0 = lowest risk, 1 = highest)")
    y -= 0.22 * inch
    c.setFont("Times-Roman", 10)
    for name, (label, blurb) in COMPONENT_LABELS.items():
        v = float(row[f"comp_{name}"])
        c.drawString(0.8 * inch, y, f"{label}: {v:.2f}")
        c.setStrokeColorRGB(0.6, 0.6, 0.6)
        c.rect(2.6 * inch, y - 1, 2.6 * inch, 8, stroke=1, fill=0)
        c.setFillColorRGB(0.75, 0.15, 0.1)
        c.rect(2.6 * inch, y - 1, 2.6 * inch * v, 8, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)
        y -= 0.19 * inch
    y -= 0.15 * inch
    why, actions = _why_lines(row)
    c.setFont("Times-Bold", 12)
    c.drawString(0.8 * inch, y, "Why this score")
    y -= 0.22 * inch
    c.setFont("Times-Roman", 10)
    for line in why:
        first = True
        for chunk in _wrap(line, 95):
            c.drawString(0.9 * inch, y, ("• " if first else "  ") + chunk)
            first = False
            y -= 0.17 * inch
    y -= 0.1 * inch
    c.setFont("Times-Bold", 12)
    c.drawString(0.8 * inch, y, "Recommended actions")
    y -= 0.22 * inch
    c.setFont("Times-Roman", 10)
    for line in actions:
        first = True
        for chunk in _wrap(line, 95):
            c.drawString(0.9 * inch, y, ("• " if first else "  ") + chunk)
            first = False
            y -= 0.17 * inch
    y = 1.1 * inch
    c.setFont("Times-Roman", 8)
    c.setFillColorRGB(0.25, 0.25, 0.25)
    role = str(row.get("layer_role", ""))
    c.drawString(0.8 * inch, y,
                 f"Data: OpenStreetMap roads; USGS 3DEP terrain; LANDFIRE fuels; FEMA USA Structures"
                 + (" (footprint proxy for parcels)" if role == "footprint_proxy" else "")
                 + f". Config v{row.get('config_version', '')}. Generated {date.today().isoformat()}.")
    c.drawString(0.8 * inch, y - 0.15 * inch,
                 "FireScore is a screening and prioritisation tool. It does not predict whether a specific structure will burn.")
    c.showPage()
    c.save()
    return out_path


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width=width) or [""]


# ------------------------------------------------------------ inspection queue
def build_queue(
    scored: gpd.GeoDataFrame,
    project_dir: str | Path,
    str_layer: str | Path | None = None,
) -> pd.DataFrame:
    df = scored.copy()
    if str_layer is not None:
        str_gdf = gpd.read_file(str_layer).to_crs(df.crs)
        joined = gpd.sjoin(df, str_gdf, how="left", predicate="intersects")
        df["is_str"] = joined.groupby(level=0).size().reindex(df.index).notna().astype(int).to_numpy()
    elif "is_str" not in df.columns:
        df["is_str"] = 0
    df = df.sort_values(["is_str", "score_high"], ascending=[False, False]).reset_index(drop=True)
    df.insert(0, "queue_rank", range(1, len(df) + 1))
    log = _load_log(project_dir)
    df["inspected"] = df["structure_id"].isin(log).astype(int) if log else 0
    cols = ["queue_rank", "structure_id", "is_str", "score", "score_low", "score_high",
            "vuln_class", "class_high", "cluster_exits", "station_drive_s", "inspected"]
    cols = [c for c in cols if c in df.columns]
    for extra in ("PROP_ADDR", "PROP_CITY"):
        if extra in df.columns:
            cols.append(extra)
    queue = df[cols]
    out_csv = Path(project_dir) / "outputs" / "inspection_queue.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    queue.to_csv(out_csv, index=False)
    return queue


def _load_log(project_dir: str | Path) -> set[str]:
    path = Path(project_dir) / "inspection_log.json"
    if path.exists():
        return set(json.loads(path.read_text()).get("inspected", []))
    return set()


def mark_inspected(project_dir: str | Path, structure_ids: list[str]) -> int:
    log = _load_log(project_dir)
    log.update(structure_ids)
    path = Path(project_dir) / "inspection_log.json"
    path.write_text(json.dumps(
        {"inspected": sorted(log), "updated": date.today().isoformat()}, indent=2))
    return len(log)
