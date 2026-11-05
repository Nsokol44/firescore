"""Minimal ArcGIS REST helpers (feature query + image export)."""

from __future__ import annotations

import io

import geopandas as gpd
import pandas as pd
import requests

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "firescore/0.1 (+https://github.com/Nsokol44/firescore)"})


def query_features(
    layer_url: str,
    where: str = "1=1",
    bbox: tuple[float, float, float, float] | None = None,
    out_fields: str = "*",
    page_size: int = 2000,
    timeout: int = 300,
) -> gpd.GeoDataFrame:
    """Paginated ArcGIS FeatureServer query -> GeoDataFrame (EPSG:4326)."""
    frames: list[gpd.GeoDataFrame] = []
    offset = 0
    while True:
        params = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "orderByFields": "OBJECTID",
        }
        if bbox is not None:
            params.update(
                {
                    "geometry": ",".join(str(v) for v in bbox),
                    "geometryType": "esriGeometryEnvelope",
                    "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                }
            )
        resp = SESSION.get(f"{layer_url}/query", params=params, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
        if "error" in payload:
            raise RuntimeError(f"ArcGIS error from {layer_url}: {payload['error']}")
        features = payload.get("features", [])
        if not features:
            break
        frames.append(gpd.GeoDataFrame.from_features(features, crs="EPSG:4326"))
        # NOTE: with f=geojson ArcGIS hides exceededTransferLimit inside
        # "properties" (or omits it); a full page is the robust continuation
        # signal. Trusting the top-level flag silently truncated a 75k-row
        # county to one partial page during the first Sevier fetch.
        flag = payload.get("exceededTransferLimit")
        if flag is None and isinstance(payload.get("properties"), dict):
            flag = payload["properties"].get("exceededTransferLimit")
        if not flag and len(features) < page_size:
            break
        offset += len(features)
    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return pd.concat(frames, ignore_index=True)


def export_image_tiff(
    image_service_url: str,
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
    timeout: int = 600,
) -> bytes:
    """ImageServer exportImage -> raw TIFF bytes (EPSG:4326 grid)."""
    params = {
        "bbox": ",".join(str(v) for v in bbox),
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": f"{width},{height}",
        "format": "tiff",
        "f": "image",
    }
    resp = SESSION.get(f"{image_service_url}/exportImage", params=params, timeout=timeout)
    resp.raise_for_status()
    if b"II" not in resp.content[:4] and b"MM" not in resp.content[:4]:
        raise RuntimeError(f"exportImage did not return a TIFF from {image_service_url}")
    return resp.content


def layer_fields(layer_url: str, timeout: int = 60) -> list[str]:
    resp = SESSION.get(layer_url, params={"f": "json"}, timeout=timeout)
    resp.raise_for_status()
    return [f["name"] for f in resp.json().get("fields", [])]


def open_raster_bytes(tiff_bytes: bytes):
    import rasterio
    from rasterio.io import MemoryFile

    mem = MemoryFile(tiff_bytes)
    return mem.open()
