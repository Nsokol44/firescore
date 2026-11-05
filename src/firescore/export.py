"""Exports: GeoPackage, shapefile, hosted-layer-ready GeoJSON/CSV, and the
offline FireView field package.

FireView is a directory a firefighter can copy to a phone: ``index.html``
plus a vendored Leaflet build and the data as a local ``data.js`` file.
It references NOTHING on the network, so it opens from ``file://`` with
airplane mode on. (No basemap tiles offline by design; the scored points
and the county boundary carry the geography, and an OSM tile layer is
added only when the device happens to be online.)
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

ASSETS = Path(__file__).parent / "assets" / "fireview"

FIELD_SPEC = {
    "structure_id": "unique structure identifier (FS-###### footprint proxy, or county parcel id)",
    "score": "FireScore composite under the default weights, 0-1 (higher = more vulnerable)",
    "score_low": "minimum score across the sensitivity weight configurations",
    "score_high": "maximum score across the sensitivity weight configurations",
    "vuln_class": "class of the default score: Low / Moderate / High / Extreme",
    "comp_egress": "egress component 0-1 (exits, dead ends, road + station drive distance)",
    "comp_water": "water-access component 0-1 (hydrant or draft-site distance)",
    "comp_vegetation": "vegetation/fuel component 0-1 (LANDFIRE FBFM40 + wildland proximity)",
    "comp_terrain": "terrain component 0-1 (slope + wind-aligned exposure)",
    "comp_spacing": "structure-spacing component 0-1 (nearest-neighbour structure)",
    "cluster_exits": "outward road exits of the structure's cluster, counted on the OSM graph",
    "station_drive_s": "drive time to nearest fire station over the road graph, seconds",
    "water_source": "which water layer scored this county (osm_hydrants / osm_draft_sites_PROXY / station_drive_PROXY)",
    "layer_role": "footprint_proxy (FEMA USA Structures) or county_parcels (local override)",
}


def export_all(scored: gpd.GeoDataFrame, project_dir: str | Path) -> dict:
    out = Path(project_dir) / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    gpkg = out / "scores.gpkg"
    scored.to_file(gpkg, layer="firescore", driver="GPKG")
    paths["geopackage"] = str(gpkg)
    shp_dir = out / "scores_shapefile"
    shp_dir.mkdir(exist_ok=True)
    scored.to_file(shp_dir / "scores.shp")
    paths["shapefile"] = str(shp_dir / "scores.shp")
    gj = out / "scores.geojson"
    scored.to_file(gj, driver="GeoJSON")
    paths["geojson"] = str(gj)
    csv = out / "scores_attributes.csv"
    pd.DataFrame(scored.drop(columns="geometry")).to_csv(csv, index=False)
    paths["attributes_csv"] = str(csv)
    spec = out / "field_spec.json"
    spec.write_text(json.dumps(FIELD_SPEC, indent=2))
    paths["field_spec"] = str(spec)
    return paths


_VIEWER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FireView — {county} (offline)</title>
<link rel="stylesheet" href="leaflet.css">
<style>
  html, body, #map {{ height: 100%; margin: 0; }}
  body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }}
  #panel {{ position: absolute; z-index: 1000; top: 8px; left: 8px; background: rgba(255,255,255,.94);
           padding: 8px 10px; border-radius: 8px; font-size: 13px; max-width: 240px;
           box-shadow: 0 1px 5px rgba(0,0,0,.4); }}
  .sw {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; }}
  #panel h3 {{ margin: 2px 0 6px; font-size: 14px; }}
</style>
</head>
<body>
<div id="panel">
  <h3>FireView — {county}</h3>
  <div><span class="sw" style="background:#1a9850"></span>Low</div>
  <div><span class="sw" style="background:#fee08b"></span>Moderate</div>
  <div><span class="sw" style="background:#f46d43"></span>High</div>
  <div><span class="sw" style="background:#a50026"></span>Extreme</div>
  <div style="margin-top:6px;color:#555">Offline package. Tap a point for its score range, exits and station drive time.</div>
</div>
<div id="map"></div>
<script src="leaflet.js"></script>
<script src="data.js"></script>
<script>
  var map = L.map('map');
  L.rectangle([[90,-180],[-90,180]], {{color:'#ddd', weight:0, fillColor:'#f2efe9', fillOpacity:1}}).addTo(map);
  var COLORS = {{'Low':'#1a9850','Moderate':'#e6c619','High':'#f46d43','Extreme':'#a50026'}};
  var layer = L.geoJSON(FIRESCORE_DATA, {{
    pointToLayer: function (f, latlng) {{
      return L.circleMarker(latlng, {{radius: 4, weight: 0.5, color: '#333',
        fillColor: COLORS[f.properties.vuln_class] || '#888', fillOpacity: 0.85}});
    }},
    onEachFeature: function (f, lyr) {{
      var p = f.properties;
      lyr.bindPopup('<b>' + p.structure_id + '</b> — ' + p.vuln_class + '<br>' +
        'Score ' + p.score + ' (range ' + p.score_low + '–' + p.score_high + ')<br>' +
        'Exits: ' + p.cluster_exits + ' · Station drive: ' + Math.round(p.station_drive_s/60) + ' min<br>' +
        'Egress ' + p.comp_egress + ' · Water ' + p.comp_water + ' · Fuel ' + p.comp_vegetation +
        ' · Terrain ' + p.comp_terrain + ' · Spacing ' + p.comp_spacing);
    }}
  }}).addTo(map);
  if (typeof FIRESCORE_BOUNDARY !== 'undefined') {{
    L.geoJSON(FIRESCORE_BOUNDARY, {{style: {{color:'#444', weight:1.5, fillOpacity:0}}}}).addTo(map);
  }}
  try {{ map.fitBounds(layer.getBounds()); }} catch (e) {{ map.setView([35.9,-83.55], 10); }}
  // If the device IS online, offer OSM tiles as an optional overlay.
  if (navigator.onLine) {{
    L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
      {{attribution: '© OpenStreetMap contributors'}}).addTo(map).bringToBack();
  }}
</script>
</body>
</html>
"""


def export_fireview(scored: gpd.GeoDataFrame, project_dir: str | Path, county_label: str,
                    boundary: gpd.GeoDataFrame | None = None) -> Path:
    fv = Path(project_dir) / "fireview"
    fv.mkdir(parents=True, exist_ok=True)
    (fv / "leaflet.js").write_bytes((ASSETS / "leaflet.js").read_bytes())
    (fv / "leaflet.css").write_bytes((ASSETS / "leaflet.css").read_bytes())
    pts = scored.copy()
    pts["geometry"] = pts.geometry.centroid
    keep = ["structure_id", "score", "score_low", "score_high", "vuln_class",
            "comp_egress", "comp_water", "comp_vegetation", "comp_terrain", "comp_spacing",
            "cluster_exits", "station_drive_s"]
    keep = [k for k in keep if k in pts.columns]
    for col in keep:
        if col not in ("structure_id", "vuln_class"):
            pts[col] = pts[col].astype(float).round(3)
    gj = json.loads(pts[keep + ["geometry"]].to_json())
    data_js = "var FIRESCORE_DATA = " + json.dumps(gj) + ";\n"
    if boundary is not None:
        data_js += "var FIRESCORE_BOUNDARY = " + boundary.to_json() + ";\n"
    (fv / "data.js").write_text(data_js)
    (fv / "index.html").write_text(_VIEWER_HTML.replace("{county}", county_label))
    (fv / "README.txt").write_text(
        "FireView offline field package. Copy this whole folder to the phone or tablet, "
        "open index.html in the browser. No network is needed: the map library and the "
        "data are local files. If the device is online, street tiles load as a bonus layer.\n"
    )
    return fv
