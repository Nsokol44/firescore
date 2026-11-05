"""Fetch orchestration: one online pass populates the county cache."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd

from ..cache import CountyCache, OfflineCacheMiss
from ..geo import WGS84, county_fips
from . import landfire, national, osm

REQUIRED_FOR_SCORING = [
    "boundary", "footprints", "roads_nodes", "roads_edges", "stations", "dem", "fbfm40",
]
WATER_LAYERS = ["hydrants", "draft_sites"]


def apply_override(cache: CountyCache, layer: str, path: str | Path) -> int:
    """A county-supplied local layer replaces the national default."""
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        raise ValueError(f"override layer {path} has no CRS")
    gdf = gdf.to_crs(WGS84)
    gdf.to_parquet(cache.vector_path(layer))
    cache.record(layer, "LOCAL OVERRIDE (county-supplied)", str(path), rows=len(gdf))
    return len(gdf)


def check_offline_ready(cache: CountyCache) -> None:
    missing = [lyr for lyr in REQUIRED_FOR_SCORING if not cache.has(lyr)]
    if not any(cache.has(lyr) for lyr in WATER_LAYERS):
        missing.append("hydrants|draft_sites")
    if missing:
        raise OfflineCacheMiss(
            "cache is incomplete; missing: " + ", ".join(missing)
            + f" (cache: {cache.root}). Run `firescore fetch` online first."
        )


def fetch_all(
    cache: CountyCache,
    county_spec: str,
    cfg: dict,
    overrides: dict[str, str] | None = None,
) -> dict:
    """Populate every layer. Optional layers record failures in the
    manifest instead of aborting the run; required layers raise."""
    fips = county_fips(county_spec)
    summary: dict = {"fips": fips, "layers": {}}

    boundary = national.fetch_boundary(cache, fips)
    summary["layers"]["boundary"] = len(boundary)

    steps = [
        ("footprints", ["footprints"], lambda: national.fetch_footprints(cache, boundary), True),
        ("roads", ["roads_nodes", "roads_edges"],
         lambda: osm.fetch_roads(cache, boundary, cfg["fetch"]["overpass_timeout_s"]), True),
        ("stations", ["stations"],
         lambda: osm.fetch_stations(cache, boundary, cfg["fetch"]["overpass_timeout_s"]), True),
        ("dem", ["dem"], lambda: national.fetch_dem(cache, boundary, cfg["fetch"]["dem_resolution_m"]), True),
        ("fbfm40", ["fbfm40"], lambda: landfire.fetch_fbfm40(
            cache, boundary, cfg["fetch"]["landfire_product"], cfg["fetch"]["landfire_email"]), True),
        ("hydrants", ["hydrants"], lambda: osm.fetch_hydrants(cache, boundary, cfg["fetch"]["overpass_timeout_s"]), False),
        ("draft_sites", ["draft_sites"], lambda: osm.fetch_draft_sites(cache, boundary, cfg["fetch"]["overpass_timeout_s"]), False),
        ("wrc_bp", ["wrc_bp"], lambda: national.fetch_wrc(cache, boundary, cfg["fetch"]["wrc_service"]), False),
        ("perimeters", ["perimeters"], lambda: national.fetch_perimeters(cache, boundary), False),
    ]
    warnings: list[str] = []
    for name, layers, fn, required in steps:
        if all(cache.has(lyr) for lyr in layers):
            summary["layers"][name] = "cached (skipped)"
            continue
        try:
            result = fn()
            summary["layers"][name] = len(result) if result is not None else "ok"
        except Exception as exc:  # noqa: BLE001 - recorded, then policy decides
            if required:
                raise
            warnings.append(f"{name}: {type(exc).__name__}: {exc}")
            cache.manifest["layers"][name] = {"fetch_status": f"FAILED: {exc}"}
            cache.manifest_path.write_text(json.dumps(cache.manifest, indent=2))
    summary["warnings"] = warnings

    for layer, path in (overrides or {}).items():
        summary["layers"][f"override:{layer}"] = apply_override(cache, layer, path)
    return summary
