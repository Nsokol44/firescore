# Practitioner outputs

- **Report cards** (`firescore report --top 25` or `--id FS-…`): a one-page
  PDF per structure — class and score range, the five component bars, a
  plain-language "why" generated from its own numbers, and recommended
  actions. Written to hand to a property owner.
- **Inspection queue** (`firescore queue`): every structure ranked by its
  worst-case score, **STR parcels first** when a local STR layer is given
  (`--str-layer`). `--mark-inspected FS-001,FS-002` persists inspections in
  `inspection_log.json`, so the queue survives between shifts.
- **Exports** (`firescore export`): GeoPackage, shapefile, GeoJSON +
  attribute CSV with a field spec (ready to publish as a hosted feature
  layer), and the **FireView** offline field package.
