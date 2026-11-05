"""FireScore command line.

    firescore run --county "Sevier, TN"        # fetch once, then score
    firescore run --county "Sevier, TN" --offline   # score from cache only
    firescore validate --project projects/sevier_47155
    firescore whatif --project projects/sevier_47155 --id FS-001234
    firescore report --project projects/sevier_47155 --top 25
    firescore queue --project projects/sevier_47155 [--str-layer str.geojson]
    firescore export --project projects/sevier_47155
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd

from . import __version__
from .cache import CountyCache
from .config import load_config
from .geo import county_fips, slugify_county


def _project(args) -> Path:
    if args.project:
        return Path(args.project)
    fips = county_fips(args.county)
    name = args.county.split(",")[0].strip().replace(" County", "")
    return Path("projects") / slugify_county(fips, name)


def _load_scored(args, cfg, cache) -> gpd.GeoDataFrame:
    path = _project(args) / "outputs" / "scores.parquet"
    if path.exists():
        return gpd.read_parquet(path)
    from .score import compute_scores, write_scores

    scored = compute_scores(cache, cfg, wind_from_deg=args.wind_from_deg)
    write_scores(cache, scored, _project(args))
    return scored


def cmd_fetch(args) -> int:
    from .fetch import fetch_all

    cfg = load_config(args.config)
    project = _project(args)
    cache = CountyCache(project)
    overrides = {}
    if args.parcels:
        overrides["parcels"] = args.parcels
    if args.hydrants:
        overrides["hydrants"] = args.hydrants
    if args.stations:
        overrides["stations"] = args.stations
    summary = fetch_all(cache, args.county, cfg, overrides or None)
    summary["project"] = str(project)
    print(json.dumps(summary, indent=2, default=str))
    return 0


def cmd_run(args) -> int:
    from .fetch import check_offline_ready, fetch_all
    from .score import compute_scores, write_scores

    cfg = load_config(args.config)
    project = _project(args)
    cache = CountyCache(project)
    if args.offline:
        check_offline_ready(cache)
        fetched = "offline: cache only, no network used"
    else:
        try:
            check_offline_ready(cache)
            fetched = "cache already complete; no fetch needed"
        except Exception:
            overrides = {}
            if args.parcels:
                overrides["parcels"] = args.parcels
            fetch_all(cache, args.county, cfg, overrides or None)
            fetched = "fetched national layers into cache"
    scored = compute_scores(cache, cfg, wind_from_deg=args.wind_from_deg)
    summary = write_scores(cache, scored, project)
    summary["fetch"] = fetched
    summary["project"] = str(project)
    prov = {
        "county": args.county,
        "fips": county_fips(args.county) if not args.offline else summary.get("fips"),
        "config_version": cfg["meta"]["config_version"],
        "firescore_version": __version__,
        "layers": cache.manifest.get("layers", {}),
    }
    (project / "outputs" / "provenance.json").write_text(json.dumps(prov, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    return 0


def cmd_validate(args) -> int:
    from .validate import run_validation

    cfg = load_config(args.config)
    cache = CountyCache(_project(args))
    scored = _load_scored(args, cfg, cache)
    results = run_validation(cache, scored, cfg, _project(args))
    if getattr(args, "nasf", None) or getattr(args, "firesponse", None):
        from .events import destroyed_only_summary, event_table, load_events

        events, flags = load_events(args.nasf, args.firesponse)
        perimeters = None
        if cache.has("perimeters"):
            perimeters = gpd.read_parquet(cache.vector_path("perimeters"))
        table = event_table(scored, events, perimeters)
        out_dir = _project(args) / "outputs"
        table.to_csv(out_dir / "event_table.csv", index=False)
        ev_summary = {"summary": destroyed_only_summary(table), "flags": flags,
                      "events_file": "event_table.csv"}
        (out_dir / "event_validation.json").write_text(json.dumps(ev_summary, indent=2, default=str))
        results["_event_validation"] = ev_summary
    print(json.dumps(results, indent=2, default=str))
    return 0


def cmd_whatif(args) -> int:
    from .whatif import WhatIfSession

    cfg = load_config(args.config)
    cache = CountyCache(_project(args))
    scored = _load_scored(args, cfg, cache)
    session = WhatIfSession(cache, cfg, scored)
    ranked = session.rank_actions(args.id)
    print(json.dumps(ranked, indent=2, default=str))
    return 0


def cmd_report(args) -> int:
    from .report import report_card

    cfg = load_config(args.config)
    cache = CountyCache(_project(args))
    scored = _load_scored(args, cfg, cache)
    out_dir = _project(args) / "outputs" / "report_cards"
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.id:
        rows = scored[scored["structure_id"] == args.id]
    else:
        rows = scored.sort_values("score_high", ascending=False).head(args.top)
    made = []
    for _, row in rows.iterrows():
        made.append(str(report_card(row, out_dir / f"card_{row['structure_id']}.pdf",
                                    args.county or "County")))
    print(json.dumps({"cards": made}, indent=2))
    return 0


def cmd_queue(args) -> int:
    from .report import build_queue, mark_inspected

    project = _project(args)
    if args.mark_inspected:
        n = mark_inspected(project, [s.strip() for s in args.mark_inspected.split(",") if s.strip()])
        print(json.dumps({"inspected_total": n}))
        return 0
    cfg = load_config(args.config)
    cache = CountyCache(project)
    scored = _load_scored(args, cfg, cache)
    queue = build_queue(scored, project, str_layer=args.str_layer)
    print(json.dumps({
        "queue_rows": int(len(queue)),
        "str_flagged": int(queue["is_str"].sum()) if "is_str" in queue else 0,
        "top5": queue.head(5).to_dict(orient="records"),
    }, indent=2, default=str))
    return 0


def cmd_export(args) -> int:
    from .export import export_all, export_fireview

    cfg = load_config(args.config)
    project = _project(args)
    cache = CountyCache(project)
    scored = _load_scored(args, cfg, cache)
    paths = export_all(scored, project)
    boundary = None
    if cache.has("boundary"):
        boundary = gpd.read_parquet(cache.vector_path("boundary"))
    fv = export_fireview(scored, project, args.county or "County", boundary)
    paths["fireview"] = str(fv)
    print(json.dumps(paths, indent=2, default=str))
    return 0


def cmd_import_perimeter(args) -> int:
    cache = CountyCache(_project(args))
    gdf = gpd.read_file(args.file).to_crs("EPSG:4326")
    gdf = gdf[["geometry"]].copy()
    gdf["fire_name"] = args.name
    gdf["fire_year"] = args.year
    if cache.has("perimeters"):
        old = gpd.read_parquet(cache.vector_path("perimeters"))
        gdf = gpd.GeoDataFrame(
            __import__("pandas").concat([old, gdf], ignore_index=True), crs="EPSG:4326")
    gdf.to_parquet(cache.vector_path("perimeters"))
    cache.record("perimeters", "user-supplied perimeter file", args.file, rows=len(gdf))
    print(json.dumps({"perimeters_total": int(len(gdf))}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="firescore", description=__doc__)
    parser.add_argument("--version", action="version", version=f"firescore {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, county_required=True):
        p.add_argument("--county", required=county_required, help='e.g. "Sevier, TN"')
        p.add_argument("--project", help="project directory (default projects/<county>_<fips>)")
        p.add_argument("--config", help="county YAML config (merged over the shipped defaults)")

    p = sub.add_parser("fetch"); common(p)
    p.add_argument("--parcels"); p.add_argument("--hydrants"); p.add_argument("--stations")
    p.set_defaults(fn=cmd_fetch)

    p = sub.add_parser("run"); common(p)
    p.add_argument("--offline", action="store_true",
                   help="fail loudly if a needed layer is not cached; never touch the network")
    p.add_argument("--parcels", help="local parcel layer override")
    p.add_argument("--wind-from-deg", type=float, help="override downslope wind FROM direction")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("validate"); common(p, county_required=False)
    p.add_argument("--wind-from-deg", type=float, default=None)
    p.add_argument("--nasf", default=None,
                   help="NASF/FPA-FOD incident file (multi-event validation set)")
    p.add_argument("--firesponse", default=None,
                   help="TN Division of Forestry fiResponse incident file")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("whatif"); common(p, county_required=False)
    p.add_argument("--id", required=True)
    p.add_argument("--wind-from-deg", type=float, default=None)
    p.set_defaults(fn=cmd_whatif)

    p = sub.add_parser("report"); common(p, county_required=False)
    p.add_argument("--id"); p.add_argument("--top", type=int, default=10)
    p.add_argument("--wind-from-deg", type=float, default=None)
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("queue"); common(p, county_required=False)
    p.add_argument("--str-layer", help="local short-term-rental layer (GeoJSON/shapefile)")
    p.add_argument("--mark-inspected", help="comma-separated structure ids to mark inspected")
    p.add_argument("--wind-from-deg", type=float, default=None)
    p.set_defaults(fn=cmd_queue)

    p = sub.add_parser("export"); common(p, county_required=False)
    p.add_argument("--wind-from-deg", type=float, default=None)
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("import-perimeter")
    p.add_argument("--project", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--year", type=int, required=True)
    p.set_defaults(fn=cmd_import_perimeter)

    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except Exception as exc:  # noqa: BLE001 - CLI surfaces errors plainly
        print(f"firescore: error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
