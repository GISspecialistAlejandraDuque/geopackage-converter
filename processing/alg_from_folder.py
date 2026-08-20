"""
Processing algorithm: scan a folder and convert every supported
vector and raster file into one or more GeoPackages.
"""

from __future__ import annotations

import os
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
)

from ..core._paths import long_path
from ..core.converter import Converter
from ..core.folder_scanner import scan_folder
from ..core.raster_converter import RasterConverter, TILE_FORMATS
from ._common import (
    GROUPING_OPTIONS,
    apply_grouping,
    make_feedback_progress,
)


def _clean_stale_gpkg(output_path: Path) -> None:
    """Remove a pre-existing GPKG and its SQLite sidecars."""
    try:
        lp = long_path(output_path)
        if os.path.isfile(lp):
            os.remove(lp)
        for suffix in ("-shm", "-wal", "-journal"):
            sidecar = long_path(Path(str(output_path) + suffix))
            if os.path.isfile(sidecar):
                try:
                    os.remove(sidecar)
                except OSError:
                    pass
    except OSError:
        pass


class ConvertFolderToGeoPackageAlgorithm(QgsProcessingAlgorithm):
    """Convert all supported vectors and rasters in a folder to GeoPackage(s)."""

    INPUT_FOLDER = "INPUT_FOLDER"
    RECURSIVE = "RECURSIVE"
    OUTPUT = "OUTPUT"
    TARGET_CRS = "TARGET_CRS"
    GROUPING = "GROUPING"
    SAVE_STYLES = "SAVE_STYLES"
    VALIDATE_GEOMETRIES = "VALIDATE_GEOMETRIES"
    DRY_RUN = "DRY_RUN"
    TILE_FORMAT = "TILE_FORMAT"
    TILE_SIZE = "TILE_SIZE"
    JPEG_QUALITY = "JPEG_QUALITY"

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
            "i file supportati in uno o più GeoPackage.\n\n"
            "Vettoriali: SHP, TAB, KML, KMZ, GML, GeoJSON, DXF, GPX, MIF\n"
            "Raster: GeoTIFF, JP2, ECW, IMG, ASC, VRT\n"
            "Archivi: ZIP, RAR (letti tramite GDAL /vsizip/ e /vsirar/, "
            "niente estrazione; RAR richiede GDAL ≥ 3.7/libarchive)"
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
            QgsProcessingParameterEnum(
                self.TILE_FORMAT,
                "Formato tile raster",
                options=list(TILE_FORMATS),
                defaultValue=0,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.TILE_SIZE,
                "Dimensione tile raster",
                options=["256", "512"],
                defaultValue=0,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.JPEG_QUALITY,
                "Qualità JPEG/WebP (1–100)",
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=75,
                minValue=1,
                maxValue=100,
                optional=True,
            )
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
        tile_fmt_idx = self.parameterAsEnum(parameters, self.TILE_FORMAT, context)
        tile_format = TILE_FORMATS[tile_fmt_idx] if tile_fmt_idx < len(TILE_FORMATS) else "AUTO"
        tile_sz_idx = self.parameterAsEnum(parameters, self.TILE_SIZE, context)
        tile_size = 512 if tile_sz_idx == 1 else 256
        jpeg_quality = self.parameterAsInt(parameters, self.JPEG_QUALITY, context)

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
        raster_conv = RasterConverter(
            target_crs=target_crs,
            tile_format=tile_format,
            tile_size=tile_size,
            jpeg_quality=jpeg_quality,
            dry_run=dry_run,
        )
        progress = make_feedback_progress(feedback)
        outputs = []
        for bundle in bundles:
            if feedback.isCanceled():
                break
            all_items = bundle["items"]
            vector_items = [it for it in all_items if it.get("item_type", "vector") != "raster"]
            raster_items = [it for it in all_items if it.get("item_type") == "raster"]

            if vector_items:
                result = converter.convert(vector_items, bundle["output_path"], progress)
                outputs.extend(str(p) for p in result.output_files)
                for err in result.errors:
                    feedback.reportError(f"{err['source']}: {err['message']}")
                for w in result.warnings:
                    feedback.pushWarning(w)
            elif raster_items and not dry_run:
                # Raster-only: wipe stale GPKG (vector converter does
                # this internally, but it's not called here).
                _clean_stale_gpkg(bundle["output_path"])

            if raster_items:
                result = raster_conv.convert(raster_items, bundle["output_path"], progress)
                outputs.extend(str(p) for p in result.output_files if str(p) not in outputs)
                for err in result.errors:
                    feedback.reportError(f"{err['source']}: {err['message']}")
                for w in result.warnings:
                    feedback.pushWarning(w)

        # Mirror QGIS contract: return the primary output path.
        return {self.OUTPUT: outputs[0] if outputs else str(output)}
