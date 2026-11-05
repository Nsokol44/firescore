"""Egress on the real road graph.

Three of the four egress sub-scores are read straight off the cached OSM
drive graph:

* exit count per structure cluster — the number of distinct outward graph
  connections of the cluster's node set (Fong et al. 2026 put the
  fatality-risk threshold near six exits);
* the legacy dead-end indicator of the structure's nearest road node;
* station distance as a DRIVE distance / drive time over the graph
  (multi-source Dijkstra from every station node) — replacing the legacy
  Euclidean distance to two synthetic station points.

Clusters are structure clusters (DBSCAN on structure centroids), documented
as a subdivision proxy: the county has not published a subdivision layer,
and no such national layer exists.
"""

from __future__ import annotations

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.cluster import DBSCAN

from .geo import WORK_CRS


def build_graph(nodes: gpd.GeoDataFrame, edges: gpd.GeoDataFrame) -> nx.Graph:
    """Undirected graph with per-edge length (m) and travel_time (s).

    Parallel/directed duplicates collapse to the minimum travel time, so a
    two-way street is one edge and a one-way pair keeps its faster leg —
    documented simplification for evacuation drive distance.
    """
    best: dict[tuple[int, int], tuple[float, float]] = {}
    for u, v, length, tt in zip(edges["u"], edges["v"], edges["length"], edges["travel_time"]):
        key = (int(u), int(v)) if u <= v else (int(v), int(u))
        cand = (float(length), float(tt) if tt == tt else float(length) / 8.0)
        if key not in best or cand[1] < best[key][1]:
            best[key] = cand
    graph = nx.Graph()
    xy = {int(o): (float(x), float(y)) for o, x, y in zip(nodes["osmid"], nodes["x"], nodes["y"])}
    graph.add_nodes_from(xy)
    for node, (x, y) in xy.items():
        graph.nodes[node]["x"] = x
        graph.nodes[node]["y"] = y
    for (u, v), (length, tt) in best.items():
        graph.add_edge(u, v, length=length, travel_time=tt)
    return graph


def egress_features(
    structures: gpd.GeoDataFrame,
    nodes: gpd.GeoDataFrame,
    edges: gpd.GeoDataFrame,
    stations: gpd.GeoDataFrame,
    cfg: dict,
) -> pd.DataFrame:
    """Per-structure egress sub-metrics (all in metres / seconds / counts)."""
    d = cfg["distances"]
    structs = structures.to_crs(WORK_CRS)
    cents = np.column_stack([structs.geometry.centroid.x, structs.geometry.centroid.y])

    graph = build_graph(nodes, edges)
    node_ids = np.array(list(graph.nodes()))
    # node coordinates into the working CRS for metric snapping
    nodes_w = nodes.to_crs(WORK_CRS)
    lut = {int(o): (float(p.x), float(p.y)) for o, p in zip(nodes_w["osmid"], nodes_w.geometry)}
    node_xy = np.array([lut[int(n)] for n in node_ids])
    tree = cKDTree(node_xy)
    snap_dist, snap_idx = tree.query(cents)
    snap_node = node_ids[snap_idx]

    degrees = dict(graph.degree())
    dead_end = np.array(
        [1.0 if degrees[int(n)] <= 1 else (0.5 if degrees[int(n)] == 2 else 0.0) for n in snap_node]
    )

    # distance to nearest road EDGE (not just node)
    edges_w = edges.to_crs(WORK_CRS)
    nearest = gpd.sjoin_nearest(
        gpd.GeoDataFrame(geometry=structs.geometry.centroid, crs=WORK_CRS),
        edges_w[["geometry"]],
        how="left",
        distance_col="dist_road_m",
    )
    nearest = nearest[~nearest.index.duplicated(keep="first")].sort_index()
    dist_road = nearest["dist_road_m"].to_numpy() if "dist_road_m" in nearest else snap_dist

    # station drive distance/time: multi-source Dijkstra from station nodes
    stations_w = stations.to_crs(WORK_CRS)
    st_xy = np.column_stack([stations_w.geometry.x, stations_w.geometry.y])
    _, st_idx = tree.query(st_xy)
    station_nodes = [int(node_ids[i]) for i in st_idx]
    if station_nodes:
        ttime = nx.multi_source_dijkstra_path_length(graph, station_nodes, weight="travel_time")
        tdist = nx.multi_source_dijkstra_path_length(graph, station_nodes, weight="length")
        station_s = np.array([ttime.get(int(n), np.nan) for n in snap_node], dtype=float)
        station_m = np.array([tdist.get(int(n), np.nan) for n in snap_node], dtype=float)
    else:
        station_s = np.full(len(structs), np.nan)
        station_m = np.full(len(structs), np.nan)
    far = np.nanmax(station_m[np.isfinite(station_m)]) if np.isfinite(station_m).any() else d["station_clip_m"]
    station_m = np.where(np.isfinite(station_m), station_m, far * 1.5)
    station_s = np.where(np.isfinite(station_s), station_s, (far * 1.5) / 8.0)

    # structure clusters and their outward-exit counts
    labels = DBSCAN(eps=d["cluster_eps_m"], min_samples=d["cluster_min_samples"]).fit_predict(cents)
    exits = np.zeros(len(structs), dtype=int)
    cluster_of_node_radius = d["cluster_node_radius_m"]
    unique_labels = [lab for lab in np.unique(labels)]
    node_tree = tree
    for lab in unique_labels:
        members = np.where(labels == lab)[0]
        pts = cents[members]
        cand_idx: set[int] = set()
        for pt in pts:
            cand_idx.update(node_tree.query_ball_point(pt, r=cluster_of_node_radius))
        if not cand_idx:
            exits[members] = 0
            continue
        node_set = {int(node_ids[i]) for i in cand_idx}
        outside_neighbours: set[int] = set()
        for n in node_set:
            for nb in graph.neighbors(n):
                if nb not in node_set:
                    outside_neighbours.add(nb)
        exits[members] = len(outside_neighbours)

    return pd.DataFrame(
        {
            "snap_node": snap_node,
            "snap_dist_m": snap_dist,
            "dist_road_m": dist_road,
            "dead_end_score": dead_end,
            "station_drive_m": station_m,
            "station_drive_s": station_s,
            "cluster_id": labels,
            "cluster_exits": exits,
        },
        index=structures.index,
    )
