# Quickstart

```bash
pip install firescore
firescore run --county "Sevier, TN"
```

This creates `projects/sevier_47155/` with:

- `cache/` — every input layer (GeoParquet + GeoTIFF) and a provenance manifest
- `outputs/scores.parquet` — the scored structure layer
- `outputs/score_summary.json`, `outputs/provenance.json`

Then:

```bash
firescore run --county "Sevier, TN" --offline        # prove it runs offline
firescore validate --project projects/sevier_47155   # score vs. real burn perimeters
firescore whatif --project projects/sevier_47155 --id FS-001234
firescore report --project projects/sevier_47155 --top 25   # PDF report cards
firescore queue  --project projects/sevier_47155            # inspection queue
firescore export --project projects/sevier_47155            # GPKG/SHP/GeoJSON + FireView
```

Local overrides are optional and always win over the national defaults:

```bash
firescore fetch --county "Sevier, TN" --parcels county_parcels.geojson \
              --hydrants county_hydrants.geojson
```

A county copy of the scoring configuration is just a YAML file:
`firescore run --county "Sevier, TN" --config my_county.yaml`.
