"""Fetchers for the national (non-OSM) layers.

Every fetcher writes into the :class:`~firescore.cache.CountyCache` and
records provenance in the cache manifest. All sources are free national
products; nothing here needs a paid account or a county data agreement.
"""

from __future__ import annotations

import io
import math

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.io import MemoryFile

from ..cache import CountyCache
from ..geo import WGS84, county_boundary
from . import arcgis

FEMA_STRUCTURES_URL = (
    "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/"
    "USA_Structures_View/FeatureServer/0"
)
HIFLD_STATIONS_URL = (  # legacy HIFLD endpoint: DEAD as of 2026-11-05 (see fetch/osm.py)
    "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/"
    "Fire_Stations/FeatureServer/0"
)
DEM_SERVICE = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"
GEOPLATFORM = "https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation"
CT2_SERVICE = (
    "https://services1.arcgis.com/HLC8bAygObK4fhPW/ArcGIS/rest/services/"
    "ChimneyTops2/FeatureServer/0"
)
WFIGS_PERIMETERS = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Interagency_Perimeters/FeatureServer/0"
)


def _bbox(gdf: gpd.GeoDataFrame, pad_deg: float = 0.02) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = gdf.total_bounds
    return (minx - pad_deg, miny - pad_deg, maxx + pad_deg, maxy + pad_deg)


def _grid_for_bbox(bbox, target_m: float) -> tuple[int, int]:
    minx, miny, maxx, maxy = bbox
    mid_lat = math.radians((miny + maxy) / 2)
    w_m = (maxx - minx) * 111_320 * math.cos(mid_lat)
    h_m = (maxy - miny) * 110_540
    return max(16, int(w_m / target_m)), max(16, int(h_m / target_m))


def _write_tiff(cache: CountyCache, layer: str, tiff_bytes: bytes, source: str, detail: str):
    path = cache.raster_path(layer)
    with MemoryFile(tiff_bytes) as mem, mem.open() as src:
        profile = src.profile
        data = src.read()
    profile.update(driver="GTiff", compress="deflate", tiled=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)
    cache.record(layer, source, detail)


def fetch_boundary(cache: CountyCache, fips: str) -> gpd.GeoDataFrame:
    bnd = county_boundary(fips)
    bnd.to_parquet(cache.vector_path("boundary"))
    cache.record("boundary", "US Census Bureau TIGER/Line 2024 counties",
                 f"county FIPS {fips}", rows=len(bnd))
    return bnd


def fetch_footprints(cache: CountyCache, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Building footprints used as the structure (parcel-proxy) layer.

    Primary: FEMA USA Structures (ORNL/FEMA). Labelled ``footprint_proxy``
    in every output: these are structures, not legal parcels, until a
    county supplies its own parcel layer as an override.
    """
    bbox = _bbox(boundary)
    fields = arcgis.layer_fields(FEMA_STRUCTURES_URL)
    keep = [f for f in ("BUILD_ID", "FIPS", "OCC_CLS", "PRIM_OCC", "PROP_ADDR",
                        "PROP_CITY", "PROP_ST", "PROP_ZIP", "SQFEET", "HEIGHT",
                        "NUM_STORY", "YEAR_BUILT") if f in fields]
    fips = str(boundary.iloc[0]["GEOID"])
    if "FIPS" in fields:
        # County-exact pull (75,227 structures for Sevier) beats envelope+clip.
        gdf = arcgis.query_features(FEMA_STRUCTURES_URL, where=f"FIPS='{fips}'",
                                    out_fields=",".join(keep) or "*")
    else:
        gdf = arcgis.query_features(FEMA_STRUCTURES_URL, bbox=bbox,
                                    out_fields=",".join(keep) or "*")
    if gdf.empty:
        raise RuntimeError("FEMA USA Structures returned no features for this county")
    gdf = gpd.clip(gdf, boundary)
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].reset_index(drop=True)
    gdf["structure_id"] = [f"FS-{i:06d}" for i in range(len(gdf))]
    gdf["layer_role"] = "footprint_proxy"
    gdf.to_parquet(cache.vector_path("footprints"))
    cache.record("footprints", "FEMA USA Structures (ORNL/FEMA hosted view)",
                 f"{FEMA_STRUCTURES_URL}; structures, not legal parcels", rows=len(gdf))
    return gdf


def fetch_dem(cache: CountyCache, boundary: gpd.GeoDataFrame, resolution_m: float = 30.0):
    """USGS 3DEP elevation via the National Map ImageServer."""
    bbox = _bbox(boundary, pad_deg=0.01)
    width, height = _grid_for_bbox(bbox, resolution_m)
    tiff = arcgis.export_image_tiff(DEM_SERVICE, bbox, width, height)
    _write_tiff(cache, "dem", tiff, "USGS 3DEP (National Map 3DEPElevation ImageServer)",
                f"exportImage at ~{resolution_m:.0f} m grid")


def fetch_wrc(cache: CountyCache, boundary: gpd.GeoDataFrame, service_name: str):
    """Wildfire Risk to Communities burn probability (USFS geoplatform)."""
    url = f"{GEOPLATFORM}/{service_name}/ImageServer"
    bbox = _bbox(boundary, pad_deg=0.01)
    width, height = _grid_for_bbox(bbox, 30.0)
    tiff = arcgis.export_image_tiff(url, bbox, width, height)
    _write_tiff(cache, "wrc_bp", tiff,
                "USFS Wildfire Risk to Communities — Burn Probability (geoplatform ImageServer)",
                url)


def fetch_perimeters(cache: CountyCache, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Known Sevier validation perimeters + a generic WFIGS pull.

    Chimney Tops 2 (2016) comes from the NPS/GRSM FeatureServer the research
    program already cites. Any WFIGS perimeter intersecting the county is
    added (Hatcher Mountain, Mar-Apr 2022, is found this way). Perimeter
    layers for other counties come from WFIGS the same way; users can also
    drop their own file in with `firescore import-perimeter`.
    """
    frames: list[gpd.GeoDataFrame] = []
    fips = str(boundary.iloc[0]["GEOID"])
    if fips == "47155":
        try:
            ct2 = arcgis.query_features(CT2_SERVICE)
            if not ct2.empty:
                ct2 = ct2[["geometry"]].copy()
                ct2["fire_name"] = "Chimney Tops 2"
                ct2["fire_year"] = 2016
                frames.append(ct2)
        except Exception:
            pass
    bbox = _bbox(boundary)
    try:
        wfigs = arcgis.query_features(WFIGS_PERIMETERS, bbox=bbox, page_size=500)
        if not wfigs.empty:
            cols = {c.lower(): c for c in wfigs.columns}
            name_c = cols.get("poly_incidentname") or cols.get("irwin_incidentname")
            year_c = cols.get("attr_firediscoverydatetime") or cols.get("poly_firediscoverydatetime") or cols.get("irwin_firediscoverydatetime")
            acres_c = cols.get("poly_gisacres") or cols.get("irwin_calculatedacres")
            keep = wfigs[[name_c, acres_c, "geometry"]].copy() if name_c and acres_c else wfigs[["geometry"]].copy()
            keep.columns = ["fire_name", "gis_acres", "geometry"] if name_c and acres_c else ["geometry"]
            if "fire_name" not in keep.columns:
                keep["fire_name"] = "WFIGS perimeter"
            if year_c is not None:
                yrs = pd.to_datetime(wfigs[year_c], unit="ms", utc=True, errors="coerce")
                keep["fire_year"] = yrs.dt.year.fillna(0).astype(int).to_numpy()
            else:
                keep["fire_year"] = 0
            # WFIGS holds recent perimeters; keep only substantial incidents
            if "gis_acres" in keep.columns:
                keep = keep[keep["gis_acres"].fillna(0) >= 100]
            frames.append(keep[[c for c in ("fire_name", "fire_year", "geometry") if c in keep.columns]])
    except Exception:
        pass
    if frames:
        out = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=WGS84)
    else:
        out = gpd.GeoDataFrame({"fire_name": [], "fire_year": [], "geometry": []}, crs=WGS84)
    out.to_parquet(cache.vector_path("perimeters"))
    cache.record("perimeters", "NPS/GRSM ChimneyTops2 FeatureServer + NIFC WFIGS Interagency Perimeters",
                 "validation outcomes", rows=len(out))
    return out
