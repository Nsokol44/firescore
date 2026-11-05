"""Per-county local cache.

The offline contract: one online ``firescore fetch`` populates this cache;
every later command runs from it. Vector layers are stored as GeoParquet,
rasters as GeoTIFF, and the road graph as node/edge GeoParquet. With
``--offline``, any layer not present raises :class:`OfflineCacheMiss`
instead of touching the network.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

VECTOR_LAYERS = [
    "boundary", "footprints", "parcels", "roads_nodes", "roads_edges",
    "stations", "hydrants", "draft_sites", "perimeters",
]
RASTER_LAYERS = ["dem", "fbfm40", "wrc_bp"]


class OfflineCacheMiss(RuntimeError):
    """Raised in offline mode when a required layer is not cached."""


class CountyCache:
    def __init__(self, project_dir: str | Path):
        self.root = Path(project_dir) / "cache"
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        if self.manifest_path.exists():
            self.manifest = json.loads(self.manifest_path.read_text())
        else:
            self.manifest = {"layers": {}}

    # -- paths -------------------------------------------------------------
    def vector_path(self, layer: str) -> Path:
        return self.root / f"{layer}.parquet"

    def raster_path(self, layer: str) -> Path:
        return self.root / f"{layer}.tif"

    def path_for(self, layer: str) -> Path:
        if layer in RASTER_LAYERS:
            return self.raster_path(layer)
        return self.vector_path(layer)

    def has(self, layer: str) -> bool:
        return self.path_for(layer).exists()

    # -- manifest ----------------------------------------------------------
    def record(self, layer: str, source: str, detail: str, rows: int | None = None) -> None:
        self.manifest["layers"][layer] = {
            "source": source,
            "detail": detail,
            "rows": rows,
            "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "file": self.path_for(layer).name,
        }
        self.manifest_path.write_text(json.dumps(self.manifest, indent=2))

    def describe(self, layer: str) -> dict | None:
        return self.manifest["layers"].get(layer)

    # -- guarded access ------------------------------------------------------
    def require(self, layer: str, offline: bool) -> Path:
        path = self.path_for(layer)
        if path.exists():
            return path
        if offline:
            raise OfflineCacheMiss(
                f"--offline: layer {layer!r} is not in the cache at {self.root}. "
                f"Run `firescore fetch` once with network access first."
            )
        raise FileNotFoundError(f"layer {layer!r} not cached at {path}")
