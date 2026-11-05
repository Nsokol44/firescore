from .firescore_qgis import FireScorePlugin


def classFactory(iface):  # noqa: N802
    return FireScorePlugin(iface)
