"""The what-if editor: mitigation actions rescored instantly.

Actions are applied to an in-memory copy of the scored layer (and, for a
new road, to the cached graph edges) and the affected structures are
rescored with the same code path as the main run. Each action reports the
target structure's score change, the number of structures improved, an
estimated cost from the YAML config, and the score drop per $1,000 — the
mitigation return-on-effort ranking a fire marshal actually spends by.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .cache import CountyCache
from .egress import egress_features
from .geo import WORK_CRS
from .score import COMPONENTS


def _composite(comp: pd.DataFrame, weights: dict) -> np.ndarray:
    return sum(weights[c] * comp[c] for c in COMPONENTS).to_numpy()


class WhatIfSession:
    def __init__(self, cache: CountyCache, cfg: dict, scored: gpd.GeoDataFrame):
        self.cache = cache
        self.cfg = cfg
        self.base = scored.reset_index(drop=True)
        self.weights = cfg["sensitivity"]["default"]
        self.work = self.base.to_crs(WORK_CRS)
        self.cents = np.column_stack(
            [self.work.geometry.centroid.x, self.work.geometry.centroid.y]
        )

    def _row(self, structure_id: str) -> int:
        hits = np.where(self.base["structure_id"] == structure_id)[0]
        if len(hits) != 1:
            raise ValueError(f"structure_id {structure_id!r} not found / not unique")
        return int(hits[0])

    def _rescore_rows(self, comp: pd.DataFrame, rows: np.ndarray) -> pd.DataFrame:
        out = comp.copy()
        new = _composite(out, self.weights)
        out["score_new"] = new
        out["delta"] = new - self.base["score"].to_numpy()
        return out.iloc[rows] if rows is not None else out

    # ------------------------------------------------------------- actions
    def clear_veg(self, structure_id: str, radius_m: float = 30.0) -> dict:
        """Defensible-space clearing: fuel hazard around the target drops to
        the configured cleared value for every structure within the radius."""
        i = self._row(structure_id)
        tree = cKDTree(self.cents)
        affected = np.array(tree.query_ball_point(self.cents[i], r=radius_m))
        comp = self.base[[f"comp_{c}" for c in COMPONENTS]].copy()
        comp.columns = COMPONENTS
        mix = self.cfg["fuels"]["vegetation_mix"]
        cleared = float(self.cfg["whatif"]["cleared_fuel_hazard"])
        veg = comp["vegetation"].to_numpy().copy()
        prox_part = veg - mix["fuel_hazard"] * self.base["fuel_hazard"].to_numpy()
        veg[affected] = np.clip(mix["fuel_hazard"] * cleared + prox_part[affected], 0, 1)
        comp["vegetation"] = veg
        res = self._rescore_rows(comp, None)
        cost = float(self.cfg["whatif"]["costs_usd"]["clear_veg_per_structure"]) * len(affected)
        return self._report("clear_veg", structure_id, res, i, cost,
                            f"cleared fuel within {radius_m:.0f} m; {len(affected)} structures treated")

    def add_hydrant(self, structure_id: str) -> dict:
        """A new hydrant at the target structure's location.

        Semantics: the hydrant AUGMENTS the water supply the baseline was
        scored on. A structure's new water component is the BETTER of its
        baseline component and the hydrant term evaluated on the hydrant
        construct (distance to the new hydrant over the hydrant clip).
        Recomputing every structure's water from hydrants alone would
        silently swap the baseline's source (e.g. draft sites) for a
        one-hydrant world and RAISE scores county-wide - a category error
        this implementation avoids by construction (no score can rise).
        """
        i = self._row(structure_id)
        tree = cKDTree(np.array([self.cents[i]]))
        dist_new, _ = tree.query(self.cents)
        hydrant_term = np.clip(dist_new / self.cfg["distances"]["hydrant_clip_m"], 0, 1)
        comp = self.base[[f"comp_{c}" for c in COMPONENTS]].copy()
        comp.columns = COMPONENTS
        comp["water"] = np.minimum(comp["water"].to_numpy(), hydrant_term)
        res = self._rescore_rows(comp, None)
        cost = float(self.cfg["whatif"]["costs_usd"]["hydrant_installed"])
        return self._report("add_hydrant", structure_id, res, i, cost,
                            "hydrant installed at the target structure")

    def add_road(self, structure_id: str) -> dict:
        """A second exit: link the target cluster's road node set to the
        nearest road node outside the cluster, then recompute egress for the
        whole county on the modified graph (still seconds)."""
        i = self._row(structure_id)
        nodes = gpd.read_parquet(self.cache.vector_path("roads_nodes"))
        edges = gpd.read_parquet(self.cache.vector_path("roads_edges"))
        stations = gpd.read_parquet(self.cache.vector_path("stations"))
        from .egress import build_graph

        graph = build_graph(nodes, edges)
        nodes_w = nodes.to_crs(WORK_CRS)
        lut = {int(o): (float(p.x), float(p.y)) for o, p in zip(nodes_w["osmid"], nodes_w.geometry)}
        node_ids = np.array(list(graph.nodes()))
        node_xy = np.array([lut[int(n)] for n in node_ids])
        tree = cKDTree(node_xy)
        # cluster node set for the target's cluster
        lab = int(self.base["cluster_id"].iloc[i])
        members = np.where(self.base["cluster_id"].to_numpy() == lab)[0]
        cand: set[int] = set()
        for pt in self.cents[members]:
            cand.update(tree.query_ball_point(pt, r=self.cfg["distances"]["cluster_node_radius_m"]))
        in_nodes = {int(node_ids[j]) for j in cand}
        if not in_nodes:
            in_nodes = {int(self.base["snap_node"].iloc[i])}
        outside = np.array([j for j, n in enumerate(node_ids) if int(n) not in in_nodes])
        if len(outside) == 0:
            raise RuntimeError("no road node outside the cluster to link to")
        d_out, idx_out = tree.query(self.cents[i], k=len(node_ids))
        target_out = next(int(node_ids[j]) for j in np.atleast_1d(idx_out)
                          if int(node_ids[j]) not in in_nodes)
        anchor_in = int(self.base["snap_node"].iloc[i])
        a = lut[anchor_in]
        b = lut[target_out]
        length = float(np.hypot(a[0] - b[0], a[1] - b[1]))
        new_edge = pd.DataFrame(
            [{
                "u": anchor_in, "v": target_out, "key": 0, "osmid": -1,
                "highway": "residential", "name": "WHATIF second exit",
                "length": length, "speed_kph": 25.0, "travel_time": length / (25_000 / 3600),
                "geometry": None,
            }]
        )
        from shapely.geometry import LineString

        new_edge["geometry"] = [LineString([a, b])]
        new_edge = gpd.GeoDataFrame(new_edge, geometry="geometry", crs=WORK_CRS).to_crs("EPSG:4326")
        edges2 = pd.concat([edges, new_edge[edges.columns]], ignore_index=True)
        edges2 = gpd.GeoDataFrame(edges2, geometry="geometry", crs="EPSG:4326")
        new_eg = egress_features(self.base, nodes, edges2, stations, self.cfg)

        comp = self.base[[f"comp_{c}" for c in COMPONENTS]].copy()
        comp.columns = COMPONENTS
        d = self.cfg["distances"]
        sub = self.cfg["egress"]["subweights"]
        exits_deficit = np.clip(
            1.0 - new_eg["cluster_exits"].to_numpy() / self.cfg["egress"]["exits_reference"], 0, 1)
        comp["egress"] = np.clip(
            sub["exits"] * exits_deficit
            + sub["dead_end"] * new_eg["dead_end_score"].to_numpy()
            + sub["station"] * np.clip(new_eg["station_drive_m"].to_numpy() / d["station_clip_m"], 0, 1)
            + sub["road_dist"] * np.clip(new_eg["dist_road_m"].to_numpy() / d["road_clip_m"], 0, 1),
            0, 1)
        res = self._rescore_rows(comp, None)
        costs = self.cfg["whatif"]["costs_usd"]
        cost = float(costs["road_egress_fixed"]) + float(costs["second_road_per_m"]) * length
        return self._report("add_road", structure_id, res, i, cost,
                            f"new {length:.0f} m exit link from node {anchor_in} to node {target_out}")

    # ------------------------------------------------------------- report
    def _report(self, action, structure_id, res: pd.DataFrame, i: int, cost: float, detail: str) -> dict:
        delta = res["delta"].to_numpy()
        target_delta = float(delta[i])
        improved = int(np.sum(delta < -0.005))
        return {
            "action": action,
            "structure_id": structure_id,
            "detail": detail,
            "score_before": float(self.base["score"].iloc[i]),
            "score_after": float(res["score_new"].iloc[i]),
            "delta": target_delta,
            "structures_improved": improved,
            "mean_delta_all": float(delta.mean()),
            "cost_usd": cost,
            "drop_per_1000_usd": float(-target_delta / cost * 1000) if cost > 0 else None,
        }

    def rank_actions(self, structure_id: str) -> list[dict]:
        results = []
        for fn in (self.clear_veg, self.add_hydrant, self.add_road):
            try:
                results.append(fn(structure_id))
            except Exception as exc:  # noqa: BLE001 - report, don't hide
                results.append({"action": fn.__name__, "structure_id": structure_id,
                                "error": f"{type(exc).__name__}: {exc}"})
        ok = [r for r in results if "delta" in r]
        ok.sort(key=lambda r: (r["drop_per_1000_usd"] or 0), reverse=True)
        return ok + [r for r in results if "delta" not in r]
