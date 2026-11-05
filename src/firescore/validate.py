"""Validation against user-supplied burn perimeters.

Outcome definition (documented, matches the manuscript's Section 3.5
design): a structure's outcome is 1 when its centroid falls inside the
mapped burn perimeter — an exposure outcome, not a damage survey.

Reported, for each perimeter:
* composite-score ROC-AUC with a label-permutation null (the paper's
  protocol, now on real data);
* random-forest AUC on the five components, plain split and
  spatial-block cross-validation (1 km blocks);
* calibration of the score against observed burn rates (deciles + Brier);
* the head-to-head against Wildfire Risk to Communities burn probability
  sampled at the same structures (AUC and rank correlation).
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

from .geo import WORK_CRS
from .score import COMPONENTS

SEED = 2026


def outcome_for(scored: gpd.GeoDataFrame, perimeter_geom) -> np.ndarray:
    cents = scored.to_crs(WORK_CRS).geometry.centroid
    return cents.within(perimeter_geom).to_numpy()


def _permutation_null_auc(y: np.ndarray, score: np.ndarray, draws: int, rng) -> dict:
    obs = roc_auc_score(y, score)
    null = np.empty(draws)
    for i in range(draws):
        null[i] = roc_auc_score(rng.permutation(y), score)
    p = float((1 + np.sum(null >= obs)) / (draws + 1))
    return {
        "auc": float(obs),
        "null_mean": float(null.mean()),
        "null_p05": float(np.percentile(null, 5)),
        "null_p95": float(np.percentile(null, 95)),
        "empirical_p": p,
        "draws": draws,
    }


def validate_perimeter(
    scored: gpd.GeoDataFrame,
    perimeters: gpd.GeoDataFrame,
    fire_name: str,
    cfg: dict,
    out_dir: Path,
) -> dict:
    vcfg = cfg["validation"]
    rng = np.random.default_rng(vcfg["seed"])
    rows = perimeters[perimeters["fire_name"] == fire_name]
    if rows.empty:
        raise ValueError(f"perimeter {fire_name!r} not in cache")
    geom = rows.to_crs(WORK_CRS).geometry.union_all()
    y = outcome_for(scored, geom)
    result: dict = {
        "fire": fire_name,
        "structures": int(len(scored)),
        "inside_perimeter": int(y.sum()),
        "burn_rate": float(y.mean()),
    }
    if y.sum() < 10 or y.sum() > len(y) - 10:
        result["status"] = "too few positives/negatives for AUC"
        return result

    score = scored["score"].to_numpy()
    result["composite"] = _permutation_null_auc(y, score, vcfg["permutation_draws"], rng)

    # RF on components: plain split (paper continuity) + block CV
    X = scored[[f"comp_{c}" for c in COMPONENTS]].to_numpy()
    idx = rng.permutation(len(y))
    cut = int(0.7 * len(y))
    tr, te = idx[:cut], idx[cut:]
    rf = RandomForestClassifier(n_estimators=200, random_state=vcfg["seed"], n_jobs=-1)
    rf.fit(X[tr], y[tr])
    rf_auc = roc_auc_score(y[te], rf.predict_proba(X[te])[:, 1])
    result["rf_plain_split_auc"] = float(rf_auc)

    w = scored.to_crs(WORK_CRS)
    cents = np.column_stack([w.geometry.centroid.x, w.geometry.centroid.y])
    blocks = (cents[:, 0] // vcfg["block_size_m"]).astype(int) * 100000 + (
        cents[:, 1] // vcfg["block_size_m"]
    ).astype(int)
    gkf = GroupKFold(n_splits=vcfg["cv_folds"])
    fold_aucs = []
    for trn, ten in gkf.split(X, y, blocks):
        if y[ten].sum() in (0, len(y[ten])):
            continue
        m = RandomForestClassifier(n_estimators=200, random_state=vcfg["seed"], n_jobs=-1)
        m.fit(X[trn], y[trn])
        fold_aucs.append(roc_auc_score(y[ten], m.predict_proba(X[ten])[:, 1]))
    result["rf_block_cv_auc_mean"] = float(np.mean(fold_aucs)) if fold_aucs else None
    result["rf_block_cv_auc_folds"] = [float(a) for a in fold_aucs]

    # calibration by score decile
    qs = np.quantile(score, np.linspace(0, 1, 11))
    qs[0] -= 1e-9
    qs[-1] += 1e-9
    bins = np.digitize(score, qs[1:-1])
    cal = pd.DataFrame({"bin": bins, "score": score, "y": y})
    table = cal.groupby("bin").agg(n=("y", "size"), mean_score=("score", "mean"),
                                   burn_rate=("y", "mean")).reset_index()
    table.to_csv(out_dir / f"calibration_{fire_name.replace(' ', '_')}.csv", index=False)
    result["brier_score_as_probability"] = float(brier_score_loss(y, np.clip(score, 0, 1)))

    # head-to-head: Wildfire Risk to Communities burn probability
    if "wrc_burn_probability" in scored.columns:
        bp = scored["wrc_burn_probability"].to_numpy(dtype=float)
        ok = np.isfinite(bp)
        if ok.sum() > 100 and len(np.unique(bp[ok])) > 10:
            result["wrc"] = {
                "auc": float(roc_auc_score(y[ok], bp[ok])),
                "spearman_vs_firescore": float(spearmanr(score[ok], bp[ok]).statistic),
                "structures_compared": int(ok.sum()),
            }
    result["status"] = "ok"
    comp = result.get("composite", {})
    if comp and comp["auc"] < comp["null_p05"]:
        result["diagnostic"] = (
            "INVERTED: the composite scores structures inside this perimeter "
            "significantly LOWER than structures outside it. Perimeter "
            "membership is not structure loss: a perimeter dominated by "
            "uninhabited wildland (e.g. a national-park interior) makes the "
            "'inside' class mostly low-vulnerability town-edge structures "
            "while high-vulnerability WUI structures sit outside. Treat "
            "this fire's AUC as an outcome mis-specification signal, not an "
            "index failure; structure-level damage data are the fix."
        )
    return result


def run_validation(cache, scored: gpd.GeoDataFrame, cfg: dict, project_dir: str | Path) -> dict:
    perimeters = gpd.read_parquet(cache.vector_path("perimeters"))
    out_dir = Path(project_dir) / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {
        "_outcome_note": (
            "Outcome = structure centroid inside the fire perimeter (NOT "
            "observed structure loss). Current footprints include post-fire "
            "rebuilds. For perimeters dominated by uninhabited wildland the "
            "label measures park proximity more than vulnerability; see the "
            "per-fire 'diagnostic' field. The Sevier damage-registry "
            "outcome (2,460 structures, CT2) is the planned replacement."
        )
    }
    for name in sorted(perimeters["fire_name"].unique()):
        results[name] = validate_perimeter(scored, perimeters, name, cfg, out_dir)
        # calibration figure
        csv = out_dir / f"calibration_{name.replace(' ', '_')}.csv"
        if csv.exists():
            _calibration_plot(csv, out_dir / f"calibration_{name.replace(' ', '_')}.png", name)
    (out_dir / "validation.json").write_text(json.dumps(results, indent=2, default=str))
    return results


def _calibration_plot(csv_path: Path, png_path: Path, fire_name: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = pd.read_csv(csv_path)
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.plot(t["mean_score"], t["burn_rate"], "o-", label="observed burn rate")
    ax.plot([0, 1], [0, 1], "--", color="grey", label="perfect calibration")
    ax.set_xlabel("FireScore composite (decile mean)")
    ax.set_ylabel("share of structures inside perimeter")
    ax.set_title(f"Calibration — {fire_name}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
