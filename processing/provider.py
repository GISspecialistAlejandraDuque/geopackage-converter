"""
QgsProcessingProvider for GeoPackage Converter.

Registers the two algorithms (folder → GPKG, project layers → GPKG)
under the ``geopackage_converter`` provider id so they appear in the
Processing Toolbox under "GeoPackage Converter".
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .alg_from_folder import ConvertFolderToGeoPackageAlgorithm
from .alg_from_project import ConvertProjectLayersToGeoPackageAlgorithm

_ICON_PATH = Path(__file__).resolve().parent.parent / "resources" / "icons" / "icon.svg"


class GeoPackageConverterProvider(QgsProcessingProvider):
    """Top-level Processing provider for the plugin."""

    def id(self) -> str:  # noqa: D401 - QGIS API
        return "geopackage_converter"

    def name(self) -> str:
        return "GeoPackage Converter"

    def icon(self):
        return QIcon(str(_ICON_PATH)) if _ICON_PATH.is_file() else super().icon()

    def longName(self) -> str:  # noqa: N802 - QGIS API
        return self.name()

    def loadAlgorithms(self) -> None:  # noqa: N802 - QGIS API
        self.addAlgorithm(ConvertFolderToGeoPackageAlgorithm())
        self.addAlgorithm(ConvertProjectLayersToGeoPackageAlgorithm())
