"""
Processing algorithm: pack the QGIS project's vector and raster layers
into one or more GeoPackages.
"""

from __future__ import annotations

import os
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsMapLayer,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProject,
)

from ..core._paths import long_path
from ..core.converter import Converter
from ..core.provider_policy import (
    ROUTE_LIVE_VECTOR,
    ROUTE_REMOTE_RASTER,
    VSI_PREFIXES,
    is_remote_provider,
    route_for_provider,
    source_label,
)
from ..core.raster_converter import RasterConverter, TILE_FORMATS
from ._common import (
    GROUPING_OPTIONS,
    apply_grouping,
    make_feedback_progress,
)

_VSI_PREFIXES = VSI_PREFIXES


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
        "item_type": "vector",
        "crs": layer.crs().authid() if layer.crs().isValid() else "Unknown",
        "encoding": layer.dataProvider().encoding() if layer.dataProvider() else "UTF-8",
        "legend_group": legend_group,
    }
    if is_virtual:
        item["is_virtual"] = True
        item["uri"] = normalised

    # Non-file providers (WFS, ArcGIS REST, memory, CSV, PostGIS…): hand
    # the writer a main-thread clone of the live layer, since "ogr"
    # cannot re-open their URI. Mirrors the dialog's _build_project_item.
    provider = layer.providerType()
    if route_for_provider(provider, is_raster=False) == ROUTE_LIVE_VECTOR:
        item["layer_ref"] = layer.clone()
        item["provider"] = provider
        item["source_label"] = source_label(provider, layer.name(), layer.source())
        if is_remote_provider(provider):
            item["is_remote"] = True
        item.pop("uri", None)
        item["path"] = None

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


def _raster_layer_to_item(layer, extent=None, pixel_size=0.0) -> dict:
    """Map a QgsRasterLayer to a converter-friendly item dict.

    Handles GDAL virtual filesystem URIs (/vsizip/, /vsicurl/, etc.)
    the same way the vector ``_layer_to_item`` does. Remote rasters
    (WCS, ArcGIS MapServer, WMS) instead carry a live layer clone plus
    the snapshot extent (``extent`` in the layer CRS, or the full layer
    extent) and resolution (``pixel_size`` in CRS units, 0 = native/auto).
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
        "item_type": "raster",
        "crs": layer.crs().authid() if layer.crs().isValid() else "Unknown",
        "encoding": "N/A",
        "legend_group": legend_group,
        "geometry_type": "Raster",
        "band_count": layer.bandCount(),
    }
    if is_virtual:
        item["is_virtual"] = True
        item["uri"] = normalised

    provider = layer.providerType()
    if route_for_provider(provider, is_raster=True) == ROUTE_REMOTE_RASTER:
        from ..core.raster_converter import default_remote_resolution

        ext = extent if (extent is not None and not extent.isEmpty()) else layer.extent()
        extent_tuple = (ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum())
        if pixel_size and pixel_size > 0:
            xres = yres = float(pixel_size)
        else:
            prov = layer.dataProvider()
            xres, yres = default_remote_resolution(
                ext.width(),
                ext.height(),
                prov.xSize() if prov else 0,
                prov.ySize() if prov else 0,
            )
        item["layer_ref"] = layer.clone()
        item["provider"] = provider
        item["source_label"] = source_label(provider, layer.name(), layer.source())
        item["is_remote"] = True
        item["raster_extent"] = extent_tuple
        item["raster_xres"] = xres
        item["raster_yres"] = yres
        item.pop("uri", None)
        item["path"] = None
    return item


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


class ConvertProjectLayersToGeoPackageAlgorithm(QgsProcessingAlgorithm):
    """Convert selected project layers (vector and raster) to GeoPackage(s)."""

    INPUT_LAYERS = "INPUT_LAYERS"
    OUTPUT = "OUTPUT"
    TARGET_CRS = "TARGET_CRS"
    GROUPING = "GROUPING"
    SAVE_STYLES = "SAVE_STYLES"
    VALIDATE_GEOMETRIES = "VALIDATE_GEOMETRIES"
    DRY_RUN = "DRY_RUN"
    TILE_FORMAT = "TILE_FORMAT"
    TILE_SIZE = "TILE_SIZE"
    JPEG_QUALITY = "JPEG_QUALITY"
    REMOTE_EXTENT = "REMOTE_EXTENT"
    REMOTE_PIXEL_SIZE = "REMOTE_PIXEL_SIZE"

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
            "Esporta in GeoPackage i layer vettoriali e raster selezionati dal "
            "progetto QGIS attivo. Supporta riproiezione, raggruppamento "
            "per CRS o per gruppo della legenda, e salvataggio degli stili. "
            "I layer vettoriali remoti o non-file (WFS/OGC API Features, "
            "ArcGIS REST FeatureServer, memoria, testo delimitato, PostGIS, "
            "SpatiaLite) vengono scaricati e salvati nel GeoPackage; i raster "
            "remoti (WCS, ArcGIS MapServer, WMS) vengono campionati "
            "all'estensione e risoluzione indicate dai parametri dedicati."
        )

    def initAlgorithm(self, config=None):  # noqa: N802
        # TypeMapLayer accepts both vector and raster layers.
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT_LAYERS,
                "Layer da convertire",
                layerType=QgsProcessing.TypeMapLayer,
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
            QgsProcessingParameterExtent(
                self.REMOTE_EXTENT,
                "Estensione per i raster remoti (vuoto = estensione intera del layer)",
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.REMOTE_PIXEL_SIZE,
                "Risoluzione raster remoti (unità CRS, 0 = nativa/auto)",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.0,
                minValue=0.0,
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
        layers = self.parameterAsLayerList(parameters, self.INPUT_LAYERS, context)
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
        remote_pixel_size = self.parameterAsDouble(parameters, self.REMOTE_PIXEL_SIZE, context)

        if not layers:
            feedback.pushWarning("Nessun layer selezionato")
            return {self.OUTPUT: str(output)}

        # Build items — distinguish vector from raster.
        items = []
        for layer in layers:
            if layer.type() == QgsMapLayer.RasterLayer:
                # The REMOTE_EXTENT is resolved per layer in the layer's CRS
                # so the Processing framework handles the transform for us.
                remote_extent = None
                if self.REMOTE_EXTENT in parameters and parameters[self.REMOTE_EXTENT]:
                    remote_extent = self.parameterAsExtent(
                        parameters, self.REMOTE_EXTENT, context, layer.crs()
                    )
                items.append(
                    _raster_layer_to_item(
                        layer, extent=remote_extent, pixel_size=remote_pixel_size
                    )
                )
            else:
                items.append(_layer_to_item(layer))
        feedback.pushInfo(f"Preparing {len(items)} layer(s)…")

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
                _clean_stale_gpkg(bundle["output_path"])

            if raster_items:
                result = raster_conv.convert(raster_items, bundle["output_path"], progress)
                outputs.extend(str(p) for p in result.output_files if str(p) not in outputs)
                for err in result.errors:
                    feedback.reportError(f"{err['source']}: {err['message']}")
                for w in result.warnings:
                    feedback.pushWarning(w)

        return {self.OUTPUT: outputs[0] if outputs else str(output)}
