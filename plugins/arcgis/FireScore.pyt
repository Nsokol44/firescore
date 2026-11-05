"""FireScore ArcGIS Pro toolbox (.pyt).

Wraps the `firescore` CLI so an Esri-shop GIS analyst can fetch, score,
validate and export a county without leaving ArcGIS Pro. The tools run the
installed FireScore package in a subprocess (the ArcGIS Python environment
only needs `arcpy` for parameter handling and messages).

Honest status: this file is syntax-checked (py_compile) but has NOT been
executed inside ArcGIS Pro — there is no ArcGIS installation in the build
environment (it is Windows/licensed software). The tool logic is a thin
subprocess wrapper over the tested CLI; the untested surface is limited to
ArcGIS parameter plumbing.
"""

import subprocess
import sys

import arcpy


def _run(args, label):
    arcpy.AddMessage(f"FireScore {label}: {' '.join(args)}")
    proc = subprocess.run(
        [sys.executable, "-m", "firescore.cli", *args],
        capture_output=True, text=True,
    )
    arcpy.AddMessage(proc.stdout[-3000:] if proc.stdout else "")
    if proc.returncode != 0:
        raise arcpy.ExecuteError(f"firescore failed: {proc.stderr[-2000:]}")
    return proc.stdout


class Toolbox:
    def __init__(self):
        self.label = "FireScore"
        self.alias = "firescore"
        self.tools = [FetchScoreCounty, RunWhatIf, ExportCounty]


class _CountyParams:
    @staticmethod
    def county():
        p = arcpy.Parameter(displayName='County (e.g. "Sevier, TN")', name="county",
                            datatype="GPString", parameterType="Required", direction="Input")
        return p

    @staticmethod
    def project():
        p = arcpy.Parameter(displayName="FireScore project folder", name="project",
                            datatype="DEFolder", parameterType="Required", direction="Input")
        return p

    @staticmethod
    def config():
        p = arcpy.Parameter(displayName="County YAML config (optional)", name="config",
                            datatype="DEFile", parameterType="Optional", direction="Input")
        p.filter.list = ["yaml", "yml"]
        return p


class FetchScoreCounty:
    def __init__(self):
        self.label = "Fetch + score a county"
        self.description = ("One online fetch of every national input layer, then scoring. "
                            "Check 'offline' to score from an existing cache only.")

    def getParameterInfo(self):
        return [_CountyParams.county(), _CountyParams.project(), _CountyParams.config(),
                arcpy.Parameter(displayName="Offline (cache only)", name="offline",
                                datatype="GPBoolean", parameterType="Optional", direction="Input")]

    def execute(self, parameters, messages):
        args = ["run", "--county", parameters[0].valueAsText,
                "--project", parameters[1].valueAsText]
        if parameters[2].valueAsText:
            args += ["--config", parameters[2].valueAsText]
        if parameters[3].value:
            args += ["--offline"]
        _run(args, "run")


class RunWhatIf:
    def __init__(self):
        self.label = "What-if for one structure"
        self.description = "Rank clear-veg / add-hydrant / add-road actions for one structure id."

    def getParameterInfo(self):
        sid = arcpy.Parameter(displayName="Structure id (e.g. FS-001234)", name="sid",
                              datatype="GPString", parameterType="Required", direction="Input")
        return [_CountyParams.project(), sid]

    def execute(self, parameters, messages):
        _run(["whatif", "--project", parameters[0].valueAsText,
              "--id", parameters[1].valueAsText], "whatif")


class ExportCounty:
    def __init__(self):
        self.label = "Export (GPKG / shapefile / GeoJSON / FireView)"
        self.description = "Write all export formats and the offline FireView package."

    def getParameterInfo(self):
        return [_CountyParams.project(),
                arcpy.Parameter(displayName='County label (e.g. "Sevier, TN")', name="county",
                                datatype="GPString", parameterType="Optional", direction="Input")]

    def execute(self, parameters, messages):
        args = ["export", "--project", parameters[0].valueAsText]
        if parameters[1].valueAsText:
            args += ["--county", parameters[1].valueAsText]
        _run(args, "export")
