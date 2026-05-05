"""
Processing algorithm: pack the QGIS project's vector layers into
one or more GeoPackages.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterMultipleLayers,
    QgsProject,
)

from ..core.converter import Converter
from ._common import (
    GROUPING_OPTIONS,
    apply_grouping,
    make_feedback_progress,
)

_VSI_PREFIXES = ("/vsizip/", "/vsigzip/", "/vsitar/", "/vsicurl/", "/vsis3/")


def _layer_to_item(layer) -> dict:
    """Map a QgsVectorLayer to the dict schema used by core modules.

    Recognises GDAL virtual filesystem URIs (e.g. /vsizip/) so the
    converter doesn't try to `.exists()` check them on disk.
    """
    legend_group = ""
    project = QgsProject.instance()
    root = project.layerTreeRoot() if project else None
    if root is not None:
        node = root.findLayer(layer.id())
        if node is not None and node.parent() is not None:
            parent = node.parent()
            if hasattr(parent, "name") and parent != root:
                legend_group = parent.name() or ""

    raw_source = layer.source().split("|", 1)[0]
    normalised = raw_source.replace("\\", "/")
    is_virtual = any(
        normalised.lstrip("/").startswith(p.lstrip("/")) for p in _VSI_PREFIXES
    )
    if is_virtual and not normalised.startswith("/"):
        normalised = "/" + normalised

    item = {
        "path": Path(normalised) if is_virtual else Path(raw_source),
        "name": layer.name(),
        "crs": layer.crs().authid() if layer.crs().isValid() else "Unknown",
        "encoding": layer.dataProvider().encoding() if layer.dataProvider() else "UTF-8",
        "legend_group": legend_group,
    }
    if is_virtual:
        item["is_virtual"] = True
        item["uri"] = normalised

    # Snapshot the live style XML for the converter.
    try:
        from qgis.PyQt.QtXml import QDomDocument

        doc = QDomDocument()
        layer.exportNamedStyle(doc)
        xml = doc.toString()
        if xml:
            item["style_xml"] = xml
    except Exception:
        pass
    return item


class ConvertProjectLayersToGeoPackageAlgorithm(QgsProcessingAlgorithm):
    """Convert selected project vector layers to GeoPackage(s)."""

    INPUT_LAYERS = "INPUT_LAYERS"
    OUTPUT = "OUTPUT"
    TARGET_CRS = "TARGET_CRS"
    GROUPING = "GROUPING"
    SAVE_STYLES = "SAVE_STYLES"
    VALIDATE_GEOMETRIES = "VALIDATE_GEOMETRIES"
    DRY_RUN = "DRY_RUN"

    def name(self) -> str:
        return "convert_project_layers_to_geopackage"

    def displayName(self) -> str:  # noqa: N802
        return "Converti layer del progetto in GeoPackage"

    def group(self) -> str:
        return "Conversione"

    def groupId(self) -> str:  # noqa: N802
        return "conversion"

    def createInstance(self):  # noqa: N802
        return ConvertProjectLayersToGeoPackageAlgorithm()

    def shortHelpString(self) -> str:  # noqa: N802
        return (
            "Esporta in GeoPackage i layer vettoriali selezionati dal "
            "progetto QGIS attivo. Supporta riproiezione, raggruppamento "
            "per CRS o per gruppo della legenda, e salvataggio degli stili."
        )

    def initAlgorithm(self, config=None):  # noqa: N802
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT_LAYERS,
                "Layer da convertire",
                layerType=QgsProcessing.TypeVectorAnyGeometry,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.GROUPING,
                "Strategia di raggruppamento",
                options=GROUPING_OPTIONS,
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.TARGET_CRS,
                "CRS di destinazione (lasciare vuoto per non riproiettare)",
                defaultValue=QgsCoordinateReferenceSystem(),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(self.SAVE_STYLES, "Salva stili nel GeoPackage", True)
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.VALIDATE_GEOMETRIES, "Valida geometrie (fix)", False
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(self.DRY_RUN, "Anteprima (dry-run)", False)
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT,
                "GeoPackage di output (o cartella per strategie multi-file)",
                fileFilter="GeoPackage (*.gpkg)",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        layers = self.parameterAsLayerList(parameters, self.INPUT_LAYERS, context)
        output = Path(self.parameterAsFileOutput(parameters, self.OUTPUT, context))
        grouping = self.parameterAsEnum(parameters, self.GROUPING, context)
        crs = self.parameterAsCrs(parameters, self.TARGET_CRS, context)
        target_crs = crs.authid() if crs.isValid() else None
        save_styles = self.parameterAsBoolean(parameters, self.SAVE_STYLES, context)
        validate = self.parameterAsBoolean(parameters, self.VALIDATE_GEOMETRIES, context)
        dry_run = self.parameterAsBoolean(parameters, self.DRY_RUN, context)

        if not layers:
            feedback.pushWarning("Nessun layer selezionato")
            return {self.OUTPUT: str(output)}

        items = [_layer_to_item(layer) for layer in layers]
        feedback.pushInfo(f"Preparing {len(items)} layer(s)…")

        bundles = apply_grouping(grouping, items, output)
        feedback.pushInfo(f"Grouping produced {len(bundles)} GeoPackage(s)")

        converter = Converter(
            target_crs=target_crs,
            save_styles=save_styles,
            validate_geometries=validate,
            dry_run=dry_run,
        )
        progress = make_feedback_progress(feedback)
        outputs = []
        for bundle in bundles:
            if feedback.isCanceled():
                break
            result = converter.convert(bundle["items"], bundle["output_path"], progress)
            outputs.extend(str(p) for p in result.output_files)
            for err in result.errors:
                feedback.reportError(f"{err['source']}: {err['message']}")
            for w in result.warnings:
                feedback.pushWarning(w)

        return {self.OUTPUT: outputs[0] if outputs else str(output)}
