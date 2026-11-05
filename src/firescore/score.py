"""Composite scoring: five real components, YAML-configured weights,
score reported as a range across the sensitivity configurations."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio.enums import Resampling
from scipy.spatial import cKDTree

from .cache import CountyCache
from .egress import egress_features
from .features import (
    distance_to_mask,
    modal_neighbourhood,
    raster_to_work_crs,
    sample_points,
    slope_aspect,
    structure_spacing,
)
from .geo import WORK_CRS, WGS84

COMPONENTS = ["egress", "water", "vegetation", "terrain", "spacing"]


def _classify(values: np.ndarray, cfg: dict) -> np.ndarray:
    th = cfg["classes"]["thresholds"]
    labels = cfg["classes"]["labels"]
    idx = np.digitize(values, th)
    return np.array([labels[i] for i in idx], dtype=object)


def _points_in_work_crs(gdf: gpd.GeoDataFrame) -> np.ndarray:
    w = gdf.to_crs(WORK_CRS)
    return np.column_stack([w.geometry.x, w.geometry.y])


def compute_scores(cache: CountyCache, cfg: dict, wind_from_deg: float | None = None) -> gpd.GeoDataFrame:
    d = cfg["distances"]
    wind_from = float(wind_from_deg if wind_from_deg is not None else cfg["wind"]["downslope_from_deg"])

    if cache.has("parcels"):
        structs = gpd.read_parquet(cache.vector_path("parcels"))
        id_col = next((c for c in ("parcel_id", "PARCEL_ID", "APN") if c in structs.columns), None)
        if id_col is None:
            structs["structure_id"] = [f"PC-{i:06d}" for i in range(len(structs))]
        else:
            structs = structs.rename(columns={id_col: "structure_id"})
        layer_role = "county_parcels"
        if "geometry" in structs and (structs.geometry.geom_type == "Point").all():
            structs = structs.copy()
            structs["geometry"] = structs.geometry.buffer(6)  # point parcels -> nominal footprint
    else:
        structs = gpd.read_parquet(cache.vector_path("footprints"))
        layer_role = "footprint_proxy"
    structs = structs.to_crs(WGS84).reset_index(drop=True)
    structs_w = structs.to_crs(WORK_CRS)
    cents = np.column_stack([structs_w.geometry.centroid.x, structs_w.geometry.centroid.y])

    # ---- terrain + wind-aligned exposure (USGS 3DEP DEM) -------------------
    dem, dem_tr, dem_nd = raster_to_work_crs(cache.raster_path("dem"), 30.0, Resampling.bilinear)
    dem = np.where(dem == dem_nd, np.nan, dem)
    filled = np.where(np.isnan(dem), np.nanmean(dem), dem)
    slope, facing = slope_aspect(filled, abs(dem_tr.a))
    slope_s = sample_points(slope, dem_tr, cents[:, 0], cents[:, 1])
    facing_s = sample_points(facing, dem_tr, cents[:, 0], cents[:, 1])
    flat = slope_s < 2.0
    wind_alignment = 0.5 + 0.5 * np.cos(np.radians(facing_s - wind_from))
    wind_exposure = np.where(flat, 0.5, np.clip(wind_alignment, 0, 1))
    terrain = np.clip(
        0.6 * np.clip(slope_s / cfg["terrain"]["slope_full_deg"], 0, 1) + 0.4 * wind_exposure, 0, 1
    )

    # ---- vegetation / fuel (LANDFIRE FBFM40) -------------------------------
    fuel, fuel_tr, fuel_nd = raster_to_work_crs(cache.raster_path("fbfm40"), 30.0, Resampling.nearest)
    fuel = np.where(fuel == fuel_nd, 0, fuel).astype(int)
    hazard_table = {int(k): float(v) for k, v in cfg["fuels"]["hazard_by_code"].items()}
    default_h = float(cfg["fuels"]["default_hazard"])
    hazard = np.vectorize(lambda c: hazard_table.get(int(c), default_h))(fuel)
    modal_code = modal_neighbourhood(fuel, fuel_tr, cents[:, 0], cents[:, 1],
                                     cfg["fuels"]["fuel_sample_radius_m"])
    fuel_hazard = np.array([hazard_table.get(int(c), default_h) for c in modal_code])
    # "Wildland" = a CONTIGUOUS burnable patch of at least
    # fuels.wildland_min_patch_ha hectares. Without the patch filter, at
    # 30 m grain nearly every structure sits within metres of some stray
    # burnable pixel and the proximity term stops discriminating.
    from scipy import ndimage

    burnable = hazard > 0.10
    labels, _ = ndimage.label(burnable)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    cell_ha = abs(fuel_tr.a * fuel_tr.e) / 10_000.0
    min_cells = max(1, int(round(float(cfg["fuels"]["wildland_min_patch_ha"]) / cell_ha)))
    wildland = sizes[labels] >= min_cells
    dist_wild = sample_points(distance_to_mask(wildland, abs(fuel_tr.a)), fuel_tr,
                              cents[:, 0], cents[:, 1])
    prox = np.clip(1.0 - dist_wild / d["wildland_clip_m"], 0, 1)
    mix = cfg["fuels"]["vegetation_mix"]
    vegetation = np.clip(mix["fuel_hazard"] * fuel_hazard + mix["wildland_proximity"] * prox, 0, 1)

    # ---- egress (real OSM graph) -------------------------------------------
    nodes = gpd.read_parquet(cache.vector_path("roads_nodes"))
    edges = gpd.read_parquet(cache.vector_path("roads_edges"))
    stations = gpd.read_parquet(cache.vector_path("stations"))
    eg = egress_features(structs, nodes, edges, stations, cfg)
    sub = cfg["egress"]["subweights"]
    exits_deficit = np.clip(1.0 - eg["cluster_exits"].to_numpy() / cfg["egress"]["exits_reference"], 0, 1)
    egress = np.clip(
        sub["exits"] * exits_deficit
        + sub["dead_end"] * eg["dead_end_score"].to_numpy()
        + sub["station"] * np.clip(eg["station_drive_m"].to_numpy() / d["station_clip_m"], 0, 1)
        + sub["road_dist"] * np.clip(eg["dist_road_m"].to_numpy() / d["road_clip_m"], 0, 1),
        0, 1,
    )

    # ---- water access --------------------------------------------------------
    water_source = "none"
    dist_water = np.full(len(structs), np.nan)
    if cache.has("hydrants"):
        hyd = gpd.read_parquet(cache.vector_path("hydrants"))
        if len(hyd) >= 25:
            tree = cKDTree(_points_in_work_crs(hyd))
            dist_water, _ = tree.query(cents)
            water_source = "osm_hydrants"
    if water_source == "none" and cache.has("draft_sites"):
        ds = gpd.read_parquet(cache.vector_path("draft_sites"))
        if len(ds) >= 10:
            tree = cKDTree(_points_in_work_crs(ds))
            dist_water, _ = tree.query(cents)
            water_source = "osm_draft_sites_PROXY"
    if water_source == "none":
        dist_water = eg["station_drive_m"].to_numpy()
        water_source = "station_drive_PROXY"
    # The normaliser follows the CONSTRUCT each source measures: hydrant
    # spacing (400 m), drafting distance to open water (wider), or station
    # drive distance (5 km). Using the hydrant clip against stream
    # distances would saturate the component nearly everywhere.
    if water_source == "osm_draft_sites_PROXY":
        water_clip = float(d["draft_site_clip_m"])
    elif water_source == "station_drive_PROXY":
        water_clip = float(d["station_clip_m"])
    else:
        water_clip = float(d["hydrant_clip_m"])
    water = np.clip(dist_water / water_clip, 0, 1)

    # ---- structure-to-structure spacing --------------------------------------
    nn_dist, nn_count = structure_spacing(cents)
    lo, hi = d["spacing_full_risk_m"], d["spacing_zero_risk_m"]
    spacing = np.clip((hi - nn_dist) / (hi - lo), 0, 1)

    # ---- composite + sensitivity range ---------------------------------------
    comp = pd.DataFrame(
        {
            "egress": egress, "water": water, "vegetation": vegetation,
            "terrain": terrain, "spacing": spacing,
        }
    )
    scores = {}
    for name, wts in cfg["sensitivity"].items():
        scores[name] = sum(wts[c] * comp[c] for c in COMPONENTS)
    score_default = scores["default"]
    score_low = np.min(np.column_stack(list(scores.values())), axis=1)
    score_high = np.max(np.column_stack(list(scores.values())), axis=1)

    out = structs.copy()
    out["layer_role"] = layer_role
    for c in COMPONENTS:
        out[f"comp_{c}"] = comp[c].to_numpy()
    for name, vals in scores.items():
        out[f"score_{name}"] = vals
    out["score"] = score_default
    out["score_low"] = score_low
    out["score_high"] = score_high
    out["vuln_class"] = _classify(score_default, cfg)
    out["class_high"] = _classify(score_high, cfg)
    # diagnostics / audit columns
    out["slope_deg"] = slope_s
    out["aspect_facing_deg"] = facing_s
    out["wind_exposure"] = wind_exposure
    out["fuel_code"] = modal_code
    out["fuel_hazard"] = fuel_hazard
    out["dist_wildland_m"] = dist_wild
    out["dist_water_m"] = dist_water
    out["water_source"] = water_source
    out["nn_structure_m"] = nn_dist
    out["structures_within_30m"] = nn_count
    out = pd.concat([out, eg.reset_index(drop=True)], axis=1)

    # WRC burn probability sampled for comparison/validation (not a component)
    if cache.has("wrc_bp"):
        try:
            bp, bp_tr, bp_nd = raster_to_work_crs(cache.raster_path("wrc_bp"), 30.0, Resampling.bilinear)
            vals = sample_points(bp, bp_tr, cents[:, 0], cents[:, 1], nodata=bp_nd)
            out["wrc_burn_probability"] = vals
        except Exception:
            out["wrc_burn_probability"] = np.nan
    out["wind_from_deg"] = wind_from
    out["config_version"] = cfg["meta"]["config_version"]
    return gpd.GeoDataFrame(out, geometry="geometry", crs=WGS84)


def write_scores(cache: CountyCache, scored: gpd.GeoDataFrame, project_dir: str | Path) -> dict:
    out_dir = Path(project_dir) / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "scores.parquet"
    scored.to_parquet(path)
    summary = {
        "structures": int(len(scored)),
        "layer_role": str(scored["layer_role"].iloc[0]) if len(scored) else None,
        "water_source": str(scored["water_source"].iloc[0]) if len(scored) else None,
        "mean_score": float(scored["score"].mean()) if len(scored) else None,
        "class_counts": scored["vuln_class"].value_counts().to_dict() if len(scored) else {},
        "high_or_extreme_share": float(
            scored["vuln_class"].isin(["High", "Extreme"]).mean()
        ) if len(scored) else None,
        "scores_file": str(path),
    }
    (out_dir / "score_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary
