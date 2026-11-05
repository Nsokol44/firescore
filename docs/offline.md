# The offline workflow

Mountain coverage is spotty; the tool is built for that.

1. **Once, somewhere with a connection:** `firescore fetch --county "Sevier, TN"`.
   Every national layer lands in `projects/sevier_47155/cache/` — vectors as
   GeoParquet, rasters as GeoTIFF, and a `manifest.json` recording the source,
   the retrieval time, and the row count of each layer.
2. **Anywhere after that:** every other command reads only the cache.
   `firescore run --offline` enforces the contract: if a required layer is
   missing it raises `OfflineCacheMiss` naming the layer, instead of touching
   the network and failing cryptically in the field.
3. **On the phone:** `firescore export` writes a `fireview/` folder — copy it
   whole to the device and open `index.html`. The map library and the data are
   local files; nothing is fetched. If the device happens to be online, street
   tiles appear as a bonus layer, but the scored map works in airplane mode.

Parquet was chosen for the vector cache because it is compact, typed, and
readable from Python, QGIS, ArcGIS Pro, R, and DuckDB without a server.
