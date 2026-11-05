"""FireScore QGIS plugin (skeleton, honest scope).

What works today: the plugin registers a "FireScore" menu with three
actions that shell out to the installed `firescore` CLI —
  * "Fetch county (online, once)"  -> firescore fetch
  * "Score county from cache"      -> firescore run --offline
  * "Open scored layer"            -> loads outputs/scores.parquet as a layer
  * "What-if for selected feature" -> firescore whatif for the selected id

What is NOT done (stated plainly, per project policy): the what-if results
are shown in the QGIS log/message bar, not yet in a docked panel; there is
no in-plugin config editor (edit the YAML); the plugin has been syntax-
checked but NOT run inside QGIS on this machine (no QGIS in the build
environment). County GIS staff run QGIS 3.34+; the plugin targets that.
"""

from __future__ import annotations

import subprocess

from qgis.PyQt.QtWidgets import QAction, QFileDialog, QInputDialog, QMessageBox
from qgis.core import QgsProject, QgsVectorLayer


class FireScorePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.actions: list[QAction] = []
        self.project_dir: str | None = None

    def initGui(self):  # noqa: N802 (QGIS API name)
        for label, slot in (
            ("FireScore: choose project folder", self._choose_project),
            ("FireScore: fetch county (online, once)", self._fetch),
            ("FireScore: score county from cache (offline)", self._score),
            ("FireScore: open scored layer", self._open_layer),
            ("FireScore: what-if for selected structure", self._whatif),
        ):
            action = QAction(label, self.iface.mainWindow())
            action.triggered.connect(slot)
            self.iface.addPluginToMenu("FireScore", action)
            self.actions.append(action)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu("FireScore", action)

    # ---------------------------------------------------------------
    def _choose_project(self):
        path = QFileDialog.getExistingDirectory(
            self.iface.mainWindow(), "FireScore project folder")
        if path:
            self.project_dir = path
            self.iface.messageBar().pushMessage("FireScore", f"Project: {path}")

    def _run_cli(self, args: list[str]) -> str:
        proc = subprocess.run(["firescore", *args], capture_output=True, text=True)
        out = (proc.stdout or "") + (proc.stderr or "")
        self.iface.messageBar().pushMessage("FireScore", out[-400:])
        return out

    def _fetch(self):
        county, ok = QInputDialog.getText(
            self.iface.mainWindow(), "FireScore fetch", 'County, e.g. "Sevier, TN"')
        if ok and county:
            self._run_cli(["fetch", "--county", county,
                           *(["--project", self.project_dir] if self.project_dir else [])])

    def _score(self):
        county, ok = QInputDialog.getText(
            self.iface.mainWindow(), "FireScore (offline)", 'County, e.g. "Sevier, TN"')
        if ok and county:
            self._run_cli(["run", "--county", county, "--offline",
                           *(["--project", self.project_dir] if self.project_dir else [])])

    def _open_layer(self):
        if not self.project_dir:
            self._choose_project()
        if not self.project_dir:
            return
        layer = QgsVectorLayer(f"{self.project_dir}/outputs/scores.parquet",
                               "FireScore scores", "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
        else:
            QMessageBox.warning(None, "FireScore", "scores.parquet not found or invalid")

    def _whatif(self):
        layer = self.iface.activeLayer()
        if layer is None or not layer.selectedFeatureCount():
            QMessageBox.information(None, "FireScore", "Select a scored structure first.")
            return
        feat = layer.selectedFeatures()[0]
        sid = feat["structure_id"]
        self._run_cli(["whatif", "--project", self.project_dir or "", "--id", str(sid)])


def classFactory(iface):  # noqa: N802 (QGIS entry point)
    return FireScorePlugin(iface)
