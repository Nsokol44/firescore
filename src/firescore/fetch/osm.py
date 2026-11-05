"""OpenStreetMap layers via osmnx: the drive graph, hydrants, draft sites.

The road graph is the analytical core of the egress component: exit counts
are counted on it and station distance is a drive distance over it, so it
is cached as node/edge GeoParquet (with per-edge length and travel time)
and rebuilt into a networkx graph offline.
"""

from __future__ import annotations

import geopandas as gpd
import osmnx as ox
import pandas as pd

from ..cache import CountyCache
from ..geo import WGS84

ox.settings.use_cache = True
ox.settings.log_console = False


def fetch_roads(cache: CountyCache, boundary: gpd.GeoDataFrame, timeout_s: int = 300) -> None:
    ox.settings.timeout = timeout_s
    polygon = boundary.geometry.union_all()
    graph = ox.graph_from_polygon(polygon, network_type="drive", simplify=True)
    graph = ox.truncate.truncate_graph_polygon(graph, polygon, truncate_by_edge=True)
    graph = ox.add_edge_speeds(graph)
    graph = ox.add_edge_travel_times(graph)
    nodes, edges = ox.convert.graph_to_gdfs(graph)
    nodes = nodes.reset_index()[["osmid", "x", "y", "geometry"]]
    edge_cols = ["u", "v", "key", "osmid", "highway", "name", "length",
                 "speed_kph", "travel_time", "geometry"]
    edges = edges.reset_index()
    edges = edges[[c for c in edge_cols if c in edges.columns]]
    assert {"u", "v"} <= set(edges.columns), "osmnx edges lost their u/v endpoint columns"
    def _first(v):
        return v[0] if isinstance(v, list) and v else v

    if len(edges):
        for col in ("highway", "name", "osmid"):
            if col in edges.columns and any(isinstance(v, list) for v in edges[col]):
                edges[col] = edges[col].apply(_first)
        edges["osmid"] = edges["osmid"].astype("int64")
    nodes.to_parquet(cache.vector_path("roads_nodes"))
    edges.to_parquet(cache.vector_path("roads_edges"))
    cache.record("roads_nodes", "OpenStreetMap via osmnx (drive network)",
                 f"nodes={len(nodes)}", rows=len(nodes))
    cache.record("roads_edges", "OpenStreetMap via osmnx (drive network)",
                 f"edges={len(edges)}; per-edge length + travel_time (OSM speeds, osmnx defaults)",
                 rows=len(edges))


def fetch_stations(cache: CountyCache, boundary: gpd.GeoDataFrame, timeout_s: int = 300) -> gpd.GeoDataFrame:
    """Fire stations from OpenStreetMap (amenity=fire_station).

    HIFLD's fire-station layer is no longer published as an open national
    service (checked the HIFLD GeoPlatform hub and ArcGIS Online on
    2026-11-05: every same-named service is a local layer, and the legacy
    HIFLD service URL is dead). OSM is the open national source; coverage
    in Sevier County includes the municipal departments and the county
    volunteer departments. A county station layer overrides this cleanly.
    Polygon stations are represented by their centroid.
    """
    ox.settings.timeout = timeout_s
    polygon = boundary.geometry.union_all()
    try:
        feats = ox.features.features_from_polygon(polygon, tags={"amenity": "fire_station"})
    except Exception:
        feats = gpd.GeoDataFrame(geometry=[], crs=WGS84)
    if feats.empty:
        out = gpd.GeoDataFrame({"station_name": [], "station_source": [], "geometry": []}, crs=WGS84)
    else:
        feats = feats[feats.geometry.notna()].copy()
        feats["geometry"] = feats.geometry.representative_point()
        name = feats["name"] if "name" in feats.columns else None
        out = gpd.GeoDataFrame(
            {
                "station_name": [str(n) if n == n and str(n) != "nan" else "Fire Station"
                                 for n in (name if name is not None else [None] * len(feats))],
                "station_source": "OpenStreetMap",
                "geometry": feats.geometry.to_numpy(),
            },
            crs=WGS84,
        ).reset_index(drop=True)
    out.to_parquet(cache.vector_path("stations"))
    cache.record("stations", "OpenStreetMap (amenity=fire_station)",
                 "HIFLD open service unavailable (verified 2026-11-05); county layer overrides",
                 rows=len(out))
    return out


def fetch_hydrants(cache: CountyCache, boundary: gpd.GeoDataFrame, timeout_s: int = 300) -> gpd.GeoDataFrame:
    """OSM fire hydrants. Coverage is volunteer-mapped and often sparse in
    rural counties; the water component falls back to draft sites when the
    hydrant count is too low to be meaningful, and says so in provenance."""
    ox.settings.timeout = timeout_s
    polygon = boundary.geometry.union_all()
    try:
        hyd = ox.features.features_from_polygon(polygon, tags={"emergency": "fire_hydrant"})
    except Exception:
        hyd = gpd.GeoDataFrame(geometry=[], crs=WGS84)
    if not hyd.empty:
        hyd = hyd[hyd.geometry.geom_type == "Point"][["geometry"]].copy()
        hyd["hydrant_source"] = "OpenStreetMap"
        hyd = hyd.reset_index(drop=True)
    hyd.to_parquet(cache.vector_path("hydrants"))
    cache.record("hydrants", "OpenStreetMap (emergency=fire_hydrant)",
                 "volunteer-mapped; sparse in rural counties", rows=len(hyd))
    return hyd


def fetch_draft_sites(cache: CountyCache, boundary: gpd.GeoDataFrame, timeout_s: int = 300) -> gpd.GeoDataFrame:
    """Rural water-supply proxy: points on OSM water features (rivers,
    streams, lakes, ponds) a tanker can draft from. Used only when hydrant
    coverage is inadequate, and always labelled PROXY in outputs."""
    ox.settings.timeout = timeout_s
    polygon = boundary.geometry.union_all()
    frames = []
    for tags in ({"waterway": ["river", "stream"]}, {"natural": "water"}):
        try:
            feats = ox.features.features_from_polygon(polygon, tags=tags)
        except Exception:
            continue
        if feats.empty:
            continue
        feats = feats[feats.geometry.notna()]
        lines = feats[feats.geometry.geom_type.isin(["LineString", "MultiLineString"])]
        polys = feats[feats.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
        pts = []
        for geom in lines.geometry:
            for frac in (0.25, 0.5, 0.75):
                pts.append(geom.interpolate(frac, normalized=True))
        for geom in polys.geometry:
            pts.append(geom.representative_point())
        if pts:
            frames.append(gpd.GeoDataFrame(geometry=pts, crs=WGS84))
    if frames:
        out = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=WGS84)
        out["draft_source"] = "OpenStreetMap water features (PROXY)"
        out = out.reset_index(drop=True)
    else:
        out = gpd.GeoDataFrame({"draft_source": [], "geometry": []}, crs=WGS84)
    out.to_parquet(cache.vector_path("draft_sites"))
    cache.record("draft_sites", "OpenStreetMap water features (PROXY)",
                 "tanker draft-site proxy used only when hydrants are sparse", rows=len(out))
    return out
