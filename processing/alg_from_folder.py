"""
Processing algorithm: scan a folder and convert every supported
vector file into one or more GeoPackages.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
)

from ..core.converter import Converter
from ..core.folder_scanner import scan_folder
from ._common import (
    GROUPING_OPTIONS,
    apply_grouping,
    make_feedback_progress,
)


class ConvertFolderToGeoPackageAlgorithm(QgsProcessingAlgorithm):
    """Convert all supported vectors in a folder to GeoPackage(s)."""

    INPUT_FOLDER = "INPUT_FOLDER"
    RECURSIVE = "RECURSIVE"
    OUTPUT = "OUTPUT"
    TARGET_CRS = "TARGET_CRS"
    GROUPING = "GROUPING"
    SAVE_STYLES = "SAVE_STYLES"
    VALIDATE_GEOMETRIES = "VALIDATE_GEOMETRIES"
    DRY_RUN = "DRY_RUN"

    def name(self) -> str:
        return "convert_folder_to_geopackage"

    def displayName(self) -> str:  # noqa: N802
        return "Converti cartella in GeoPackage"

    def group(self) -> str:
        return "Conversione"

    def groupId(self) -> str:  # noqa: N802
        return "conversion"

    def createInstance(self):  # noqa: N802
        return ConvertFolderToGeoPackageAlgorithm()

    def shortHelpString(self) -> str:  # noqa: N802
        return (
            "Esegue la scansione della cartella di input e converte tutti "
            "i file vettoriali supportati (SHP, TAB, KML, KMZ, GML, "
            "GeoJSON, DXF, GPX, MIF) in uno o più GeoPackage."
        )

    def initAlgorithm(self, config=None):  # noqa: N802
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_FOLDER,
                "Cartella di input",
                behavior=QgsProcessingParameterFile.Folder,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(self.RECURSIVE, "Scansione ricorsiva", True)
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
        folder = Path(self.parameterAsFile(parameters, self.INPUT_FOLDER, context))
        recursive = self.parameterAsBoolean(parameters, self.RECURSIVE, context)
        output = Path(self.parameterAsFileOutput(parameters, self.OUTPUT, context))
        grouping = self.parameterAsEnum(parameters, self.GROUPING, context)
        crs = self.parameterAsCrs(parameters, self.TARGET_CRS, context)
        target_crs = crs.authid() if crs.isValid() else None
        save_styles = self.parameterAsBoolean(parameters, self.SAVE_STYLES, context)
        validate = self.parameterAsBoolean(parameters, self.VALIDATE_GEOMETRIES, context)
        dry_run = self.parameterAsBoolean(parameters, self.DRY_RUN, context)

        feedback.pushInfo(f"Scanning {folder} (recursive={recursive})…")
        items = scan_folder(folder, recursive=recursive)
        feedback.pushInfo(f"Found {len(items)} supported file(s)")
        if not items:
            return {self.OUTPUT: str(output)}

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

        # Mirror QGIS contract: return the primary output path.
        return {self.OUTPUT: outputs[0] if outputs else str(output)}
