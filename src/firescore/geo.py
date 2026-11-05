"""County resolution and shared geospatial helpers."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import geopandas as gpd
import requests

WORK_CRS = "EPSG:5070"  # NAD83 / Conus Albers, metres
WGS84 = "EPSG:4326"

GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2024_Gazetteer/2024_Gaz_counties_national.zip"
)
TIGER_COUNTY_URL = "https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/tl_2024_us_county.zip"

STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56", "PR": "72",
}


def global_cache_dir() -> Path:
    import os

    root = Path(os.environ.get("FIRESCORE_HOME", Path.home() / ".cache" / "firescore"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def parse_county(spec: str) -> tuple[str, str]:
    """Parse 'Sevier, TN' -> ('Sevier', 'TN'). Also accepts a 5-digit FIPS."""
    spec = spec.strip()
    if spec.isdigit() and len(spec) == 5:
        return spec, ""
    if "," not in spec:
        raise ValueError(f"county must look like 'Sevier, TN' (got {spec!r})")
    name, state = [p.strip() for p in spec.rsplit(",", 1)]
    return name, state.upper()


def _gazetteer() -> "pd.DataFrame":
    import pandas as pd

    path = global_cache_dir() / "2024_Gaz_counties_national.txt"
    if not path.exists():
        resp = requests.get(GAZETTEER_URL, timeout=120)
        resp.raise_for_status()
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        name = [n for n in zf.namelist() if n.endswith(".txt")][0]
        path.write_bytes(zf.read(name))
    df = pd.read_csv(path, sep="\t", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    return df


def county_fips(spec: str) -> str:
    """Resolve 'Sevier, TN' (or 'Sevier County, TN') to its 5-digit FIPS."""
    name, state = parse_county(spec)
    if state == "" and name.isdigit():
        return name
    if state not in STATE_FIPS:
        raise ValueError(f"unknown state code {state!r}")
    base = name.replace(" County", "").replace(" Parish", "").strip().lower()
    gaz = _gazetteer()
    rows = gaz[gaz["GEOID"].str.startswith(STATE_FIPS[state])]
    match = rows[rows["NAME"].str.lower() == base]
    if match.empty:
        match = rows[rows["NAME"].str.lower().str.startswith(base)]
    if len(match) != 1:
        raise ValueError(f"could not uniquely resolve county {spec!r}")
    return str(match.iloc[0]["GEOID"])


def county_boundary(fips: str) -> gpd.GeoDataFrame:
    """County boundary polygon from Census TIGER/Line (cached globally)."""
    path = global_cache_dir() / "tl_2024_us_county.zip"
    if not path.exists():
        resp = requests.get(TIGER_COUNTY_URL, timeout=300)
        resp.raise_for_status()
        path.write_bytes(resp.content)
    counties = gpd.read_file(path, layer="tl_2024_us_county")
    row = counties[counties["GEOID"] == fips]
    if row.empty:
        raise ValueError(f"FIPS {fips} not in TIGER county file")
    return row[["GEOID", "NAME", "STATEFP", "geometry"]].to_crs(WGS84).reset_index(drop=True)


def slugify_county(fips: str, name: str) -> str:
    return f"{name.lower().replace(' ', '_')}_{fips}"
