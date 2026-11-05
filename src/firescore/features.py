"""Per-structure feature derivation from cached rasters (vectorised)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject
from scipy import ndimage
from scipy.spatial import cKDTree

from .geo import WORK_CRS


def raster_to_work_crs(path: Path, res_m: float, resampling: Resampling):
    """Reproject a cached raster (EPSG:4326) to the working CRS in memory."""
    with rasterio.open(path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, WORK_CRS, src.width, src.height, *src.bounds, resolution=res_m
        )
        data = np.empty((height, width), dtype=np.float32)
        reproject(
            source=rasterio.band(src, 1),
            destination=data,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=WORK_CRS,
            resampling=resampling,
        )
        nodata = src.nodata
    return data, transform, nodata


def sample_points(data: np.ndarray, transform, xs: np.ndarray, ys: np.ndarray,
                  nodata: float | None = None, fill: float = np.nan) -> np.ndarray:
    """Vectorised raster sampling at point coordinates."""
    inv = ~transform
    cols, rows = inv * (xs, ys)
    cols = np.floor(cols).astype(int)
    rows = np.floor(rows).astype(int)
    h, w = data.shape
    valid = (rows >= 0) & (rows < h) & (cols >= 0) & (cols < w)
    out = np.full(len(xs), fill, dtype=np.float64)
    vals = data[rows[valid], cols[valid]]
    if nodata is not None:
        vals = np.where(vals == nodata, fill, vals)
    out[valid] = vals
    return out


def slope_aspect(dem: np.ndarray, cell_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Slope (degrees) and downslope facing azimuth (degrees, 0=N, CW)."""
    dzdy, dzdx = np.gradient(dem.astype(np.float64), cell_m)
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    # Downhill vector = -gradient; azimuth measured clockwise from north.
    facing = (np.degrees(np.arctan2(-dzdx, -dzdy)) + 360.0) % 360.0
    return slope.astype(np.float32), facing.astype(np.float32)


def modal_neighbourhood(data: np.ndarray, transform, xs, ys, radius_m: float) -> np.ndarray:
    """Modal raster value within a square neighbourhood of each point."""
    inv = ~transform
    cols, rows = inv * (xs, ys)
    cols = np.floor(cols).astype(int)
    rows = np.floor(rows).astype(int)
    cell = abs(transform.a)
    r = max(1, int(round(radius_m / cell)))
    h, w = data.shape
    padded = np.pad(data, r, mode="edge")
    out = np.empty(len(xs), dtype=data.dtype)
    # Gather (2r+1)^2 windows vectorised, then take the mode per row.
    offsets = [(di, dj) for di in range(-r, r + 1) for dj in range(-r, r + 1)]
    windows = np.stack(
        [padded[rows + r + di, cols + r + dj] for di, dj in offsets], axis=1
    )
    for i in range(len(xs)):
        vals, counts = np.unique(windows[i], return_counts=True)
        out[i] = vals[np.argmax(counts)]
    return out


def distance_to_mask(mask: np.ndarray, cell_m: float) -> np.ndarray:
    """Distance (m) from every cell to the nearest True cell of ``mask``."""
    return ndimage.distance_transform_edt(~mask) * cell_m


def structure_spacing(centroids_xy: np.ndarray, radius_m: float = 30.0) -> tuple[np.ndarray, np.ndarray]:
    """Nearest-neighbour structure distance and neighbour count (KD-tree)."""
    tree = cKDTree(centroids_xy)
    dists, _ = tree.query(centroids_xy, k=2)
    nn_dist = dists[:, 1]
    counts = tree.query_ball_point(centroids_xy, r=radius_m, return_length=True)
    return nn_dist, np.asarray(counts) - 1  # exclude self
