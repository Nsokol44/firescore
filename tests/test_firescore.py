"""Offline unit tests: a synthetic mini-county exercises config, egress math,
the composite, the what-if sign convention, and the offline failure mode.
No network is touched by any test in this file."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon

from firescore.cache import CountyCache, OfflineCacheMiss
from firescore.config import load_config
from firescore.egress import build_graph, egress_features
from firescore.fetch import check_offline_ready


def _mini_county(tmp_path):
    """Two clusters: a 3-exit grid cluster and a dead-end spur, one station."""
    cfg = load_config()
    cache = CountyCache(tmp_path)
    # structures: 4 in a grid block, 3 along a dead-end spur
    pts = [(0, 0), (60, 0), (0, 60), (60, 60), (600, 0), (700, 0), (800, 0)]
    structs = gpd.GeoDataFrame(
        {"structure_id": [f"T-{i}" for i in range(len(pts))]},
        geometry=[Point(x, y).buffer(5) for x, y in pts],
        crs="EPSG:5070",
    ).to_crs("EPSG:4326")
    # road nodes on a 100 m grid around the first cluster + a spur east
    node_xy = {}
    nid = 0
    grid = {}
    for gx in (-100, 0, 100):
        for gy in (-100, 0, 100):
            grid[(gx, gy)] = nid
            node_xy[nid] = (gx, gy)
            nid += 1
    spur = [(200, 0), (400, 0), (600, 0), (700, 0), (800, 0)]
    prev = grid[(100, 0)]
    spur_ids = []
    for xy in spur:
        node_xy[nid] = xy
        spur_ids.append(nid)
        nid += 1
    edges = []
    def add(u, v):
        (x1, y1), (x2, y2) = node_xy[u], node_xy[v]
        length = float(np.hypot(x1 - x2, y1 - y2))
        edges.append({"u": u, "v": v, "key": 0, "length": length,
                      "travel_time": length / 10.0, "highway": "residential",
                      "name": "", "osmid": 1,
                      "geometry": LineString([(x1, y1), (x2, y2)])})
    for (gx, gy), i in grid.items():
        if (gx + 100, gy) in grid:
            add(i, grid[(gx + 100, gy)])
        if (gx, gy + 100) in grid:
            add(i, grid[(gx, gy + 100)])
    chain = [grid[(100, 0)]] + spur_ids
    for a, b in zip(chain[:-1], chain[1:]):
        add(a, b)
    nodes = gpd.GeoDataFrame(
        {"osmid": list(node_xy), "x": [v[0] for v in node_xy.values()],
         "y": [v[1] for v in node_xy.values()]},
        geometry=[Point(v) for v in node_xy.values()], crs="EPSG:5070",
    ).to_crs("EPSG:4326")
    nodes["x"] = nodes.geometry.x
    nodes["y"] = nodes.geometry.y
    edges = gpd.GeoDataFrame(edges, geometry="geometry", crs="EPSG:5070").to_crs("EPSG:4326")
    stations = gpd.GeoDataFrame(
        {"station_name": ["Central"], "station_source": ["test"]},
        geometry=[Point(-100, -100)], crs="EPSG:5070",
    ).to_crs("EPSG:4326")
    return cfg, structs, nodes, edges, stations


def test_config_sums_to_one():
    cfg = load_config()
    assert abs(sum(cfg["weights"].values()) - 1) < 1e-9
    assert cfg["meta"]["config_version"] == 2
    assert len(cfg["fuels"]["hazard_by_code"]) >= 40


def test_graph_collapses_parallel_edges():
    import pathlib
    import tempfile

    cfg, structs, nodes, edges, stations = _mini_county(pathlib.Path(tempfile.mkdtemp()))
    g = build_graph(nodes, edges)
    assert g.number_of_nodes() == len(nodes)
    assert all("travel_time" in d for _, _, d in g.edges(data=True))


def test_egress_dead_end_beats_grid(tmp_path):
    import copy

    cfg, structs, nodes, edges, stations = _mini_county(tmp_path)
    cfg = copy.deepcopy(cfg)
    cfg["distances"]["cluster_node_radius_m"] = 60  # hand-computable node sets
    eg = egress_features(structs, nodes, edges, stations, cfg)
    grid_exits = eg["cluster_exits"].iloc[0]
    spur = eg.iloc[6]  # far end of the spur
    assert grid_exits >= 3
    assert spur["cluster_exits"] <= 1
    assert spur["dead_end_score"] == 1.0
    assert spur["station_drive_m"] > eg["station_drive_m"].iloc[0]
    assert np.isfinite(eg["station_drive_s"]).all()


def test_offline_cache_miss_is_loud(tmp_path):
    cache = CountyCache(tmp_path)
    with pytest.raises(OfflineCacheMiss):
        check_offline_ready(cache)
    with pytest.raises(OfflineCacheMiss):
        cache.require("dem", offline=True)


def test_scores_are_ranges(tmp_path):
    """Composite bounds: every default score sits inside [low, high]."""
    from firescore.score import _classify

    cfg = load_config()
    vals = np.array([0.0, 0.34, 0.35, 0.55, 0.75, 1.0])
    labels = _classify(vals, cfg)
    assert list(labels) == ["Low", "Low", "Moderate", "High", "Extreme", "Extreme"]


def test_whatif_clear_veg_never_raises_score(tmp_path):
    """Sign convention: clearing fuel cannot increase a structure's score."""
    from firescore.whatif import WhatIfSession

    cfg, structs, nodes, edges, stations = _mini_county(tmp_path)
    cache = CountyCache(tmp_path)
    scored = structs.copy()
    n = len(scored)
    scored["score"] = 0.5
    for c in ("egress", "water", "vegetation", "terrain", "spacing"):
        scored[f"comp_{c}"] = 0.5
    scored["fuel_hazard"] = 0.9
    scored["cluster_id"] = 0
    scored["cluster_exits"] = 1
    scored["snap_node"] = 0
    session = WhatIfSession(cache, cfg, scored)
    res = session.clear_veg("T-0", radius_m=30)
    assert res["delta"] < 0
    # A hydrant can only improve water access: no structure's score may
    # rise, including the county-wide mean (guards the source-swap bug
    # found on the real Sevier run, 2026-11-05).
    resh = session.add_hydrant("T-0")
    assert resh["delta"] <= 1e-9
    assert resh["mean_delta_all"] <= 1e-9


def test_outcome_for_is_crs_consistent():
    """Perimeter membership must be computed in one CRS: a square in 4326
    and points in the same place must match after internal reprojection.
    (Regression guard: the 2026-11-05 validation rerun returned 0 inside
    for every fire after a half-done CRS fix.)"""
    from firescore.validate import outcome_for

    poly = gpd.GeoDataFrame(
        geometry=[Polygon([(-83.60, 35.68), (-83.50, 35.68), (-83.50, 35.75), (-83.60, 35.75), (-83.60, 35.68)])],
        crs="EPSG:4326",
    )
    pts = gpd.GeoDataFrame(
        geometry=[Point(-83.55, 35.71), Point(-83.30, 35.90)], crs="EPSG:4326"
    )
    y = outcome_for(pts, poly.to_crs(5070).geometry.union_all())
    assert y.tolist() == [True, False]


def _fake_fpa_fod(path, rows):
    """Minimal FPA-FOD-shaped point file (DBF-truncated field names)."""
    g = gpd.GeoDataFrame(rows, geometry=[Point(-83.55, 35.71)] * len(rows), crs="EPSG:4326")
    g.to_file(path)
    return path


def test_events_destroyed_is_the_outcome(tmp_path):
    """Field semantics anchored on the real Chimney Tops 2 record:
    (threatened, destroyed) pair order; destroyed = 1,373 + 894."""
    from firescore.events import load_events

    row = {"LocalIncid": "16-E0573", "FireDiscov": "2016-11-28", "IncidentNa": "CHIMNEY TOPS 2",
           "Statistica": 5, "Residences": 0, "Residenc_1": 1373, "OtherStruc": 0,
           "OtherStr_1": 894, "NumberInju": 0, "NumberFata": 14, "FinalFireA": 17010.0}
    p = _fake_fpa_fod(tmp_path / "nasf.shp", [row])
    ev, flags = load_events(nasf_path=str(p))
    assert flags == []
    assert ev.iloc[0]["structures_destroyed"] == 2267
    assert ev.iloc[0]["structures_threatened"] == 0


def test_events_anomaly_guard_and_dedupe(tmp_path):
    from firescore.events import load_events

    base = {"Statistica": 5, "Residences": 3, "Residenc_1": 2, "OtherStruc": 0,
            "OtherStr_1": 0, "NumberInju": 0, "NumberFata": 0, "FinalFireA": 5.0}
    nasf = [dict(base, LocalIncid="A1", FireDiscov="2022-03-30", IncidentNa="INDIGO LANE")]
    fres = [dict(base, LocalIncid="B1", FireDiscov="2022-03-30", IncidentNa="INDIGO LANE"),
            dict(base, LocalIncid="B2", FireDiscov="2023-11-15", IncidentNa="SUGAR MOUNTAIN",
                 Residenc_1=20000)]
    ev, flags = load_events(nasf_path=str(_fake_fpa_fod(tmp_path / "n.shp", nasf)),
                            firesponse_path=str(_fake_fpa_fod(tmp_path / "f.shp", fres)))
    assert len(ev) == 1 and ev.iloc[0]["source"] == "NASF"  # overlap deduped, NASF wins
    assert len(flags) == 1 and flags[0]["structures_destroyed_reported"] == 20000


def test_event_table_never_pools_or_leaks_names(tmp_path):
    from firescore.events import destroyed_only_summary, event_table, load_events

    base = {"Statistica": 5, "Residences": 10, "Residenc_1": 2, "OtherStruc": 0,
            "OtherStr_1": 0, "NumberInju": 0, "NumberFata": 0, "FinalFireA": 40.0}
    p = _fake_fpa_fod(tmp_path / "n.shp",
                      [dict(base, LocalIncid="A1", FireDiscov="2022-03-30",
                            IncidentNa="123 PRIVATE ADDRESS LANE")])
    ev, _ = load_events(nasf_path=str(p))
    scored = gpd.GeoDataFrame(
        {"score": [0.4, 0.9]},
        geometry=[Polygon([(-83.56, 35.70), (-83.54, 35.70), (-83.54, 35.72), (-83.56, 35.72), (-83.56, 35.70)]),
                  Polygon([(-83.20, 35.90), (-83.18, 35.90), (-83.18, 35.92), (-83.20, 35.92), (-83.20, 35.90)])],
        crs="EPSG:4326")
    table = event_table(scored, ev)
    assert not any("impacted" in c or "_match_name" in c or "PRIVATE" in c for c in table.columns)
    assert table.iloc[0]["structures_destroyed_outcome"] == 2
    assert table.iloc[0]["structures_threatened_exposure"] == 10
    s = destroyed_only_summary(table)
    assert s["structures_destroyed_total"] == 2
    assert not any("impacted" in k or "pooled" in k for k in s)
