"""LANDFIRE fuel-model extraction via the LFPS v2 API.

The legacy ArcGIS GPServer endpoint (LandfireProductService) was retired
when the LANDFIRE Product Service moved to its v2 REST API (documented in
the LFPS User Guide, https://lfps.usgs.gov/LFProductsServiceUserGuide.pdf):

    GET https://lfps.usgs.gov/api/job/submit?Layer_List=LF2023_FBFM40
        &Area_of_Interest="xmin ymin xmax ymax"&Output_Projection=4326
        &Email=<email>            (required; used for usage statistics)
    GET https://lfps.usgs.gov/api/job/status?JobId=<id>
        -> on completion the payload carries a download URL for a zip
           holding the GeoTIFF + metadata.

Jobs are asynchronous (typically minutes). The zip's GeoTIFF is stored
into the county cache as fbfm40.tif.
"""

from __future__ import annotations

import io
import time
import zipfile

import geopandas as gpd
import requests

from ..cache import CountyCache
from ..geo import WGS84

LFPS_API = "https://lfps.usgs.gov/api/job"
_POLL_S = 20
_MAX_POLLS = 75  # 25 minutes
_DONE = ("completed", "complete", "succeeded", "success")
_FAILED = ("failed", "error", "cancelled", "canceled")


def _find_url(obj) -> str | None:
    """Recursively find the first http(s) URL ending in .zip in a payload."""
    if isinstance(obj, str):
        return obj if obj.startswith("http") and ".zip" in obj else None
    if isinstance(obj, dict):
        for v in obj.values():
            hit = _find_url(v)
            if hit:
                return hit
    if isinstance(obj, (list, tuple)):
        for v in obj:
            hit = _find_url(v)
            if hit:
                return hit
    return None


def fetch_fbfm40(cache: CountyCache, boundary: gpd.GeoDataFrame,
                 product: str, email: str) -> str:
    if not email:
        raise ValueError(
            "LFPS requires an email for usage statistics: set fetch.landfire_email "
            "in firescore.yaml (any valid address; it is sent only to USGS LFPS)."
        )
    b = boundary.to_crs(WGS84).geometry.union_all().bounds
    aoi = f"{b[0]:.4f} {b[1]:.4f} {b[2]:.4f} {b[3]:.4f}"
    session = requests.Session()
    session.headers["User-Agent"] = "firescore/0.1"
    resp = session.get(
        f"{LFPS_API}/submit",
        params={"Layer_List": product, "Area_of_Interest": aoi,
                "Output_Projection": "4326", "Email": email},
        timeout=120,
    )
    resp.raise_for_status()
    payload = resp.json()
    job_id = payload.get("jobId") or payload.get("JobId")
    if not job_id:
        raise RuntimeError(f"LFPS submit returned no job id: {str(payload)[:300]}")

    download_url: str | None = None
    status = ""
    for _ in range(_MAX_POLLS):
        time.sleep(_POLL_S)
        r = session.get(f"{LFPS_API}/status", params={"JobId": job_id}, timeout=60)
        r.raise_for_status()
        d = r.json()
        status = str(d.get("status", ""))
        if status.lower() in _FAILED:
            raise RuntimeError(f"LFPS job {job_id} ended '{status}': {str(d)[:300]}")
        url = _find_url(d)
        if url and status.lower() in _DONE:
            download_url = url
            break
        if url and status.lower() not in ("pending", "executing", "submitted", "queued", ""):
            download_url = url
            break
    if not download_url:
        raise TimeoutError(f"LFPS job {job_id} produced no download URL (last status: {status})")

    z = session.get(download_url, timeout=900)
    z.raise_for_status()
    out_path = cache.raster_path("fbfm40")
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        tifs = [n for n in zf.namelist() if n.lower().endswith((".tif", ".tiff"))]
        if not tifs:
            raise RuntimeError(f"LFPS output zip contains no GeoTIFF: {zf.namelist()}")
        with zf.open(tifs[0]) as src, open(out_path, "wb") as dst:
            dst.write(src.read())
    cache.record("fbfm40", f"LANDFIRE {product} via LFPS v2 API",
                 f"{LFPS_API}/submit job {job_id}", rows=None)
    return str(out_path)
