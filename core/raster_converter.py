"""
Raster-to-GeoPackage converter.

Parallel to `converter.py` (vector), this module converts raster files
(GeoTIFF, JP2, ECW, IMG, ASC, VRT) into GeoPackage raster tiles using
GDAL via QGIS Processing algorithms.

Design notes
------------
* QGIS imports are lazy (inside methods) so this module can be imported
  in unit tests without a running QGIS.
* Uses `processing.run("gdal:translate", ...)` for format conversion.
  When CRS reprojection is needed, uses `processing.run("gdal:warpreproject")`.
* Supports appending multiple rasters to the same GPKG via
  `APPEND_SUBDATASET=YES` with unique `RASTER_TABLE` names.
* Returns the same `ConversionResult` type as the vector converter for
  unified reporting.
* `convert()` never raises on a per-item failure: errors are collected
  in `ConversionResult.errors`.
"""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from ._paths import long_path
from .converter import ConversionResult, ProgressCallback
from .exceptions import RasterConversionError

# Tile format choices understood by the GDAL GeoPackage raster driver.
TILE_FORMATS = ("AUTO", "PNG", "JPEG", "WEBP")
TILE_SIZES = (256, 512)

# Remote-raster defaults: when the service does not report a native
# size, the snapshot's long edge is capped at this many pixels.
DEFAULT_REMOTE_MAX_PX = 4096
# Above this many pixels (width*height*bands) the UI warns the user
# that the snapshot will be very heavy.
HUGE_OUTPUT_THRESHOLD_PX = 200_000_000


# ---------------------------------------------------------------------------
# Pure helpers for remote-raster sizing (no QGIS — unit-testable)
# ---------------------------------------------------------------------------


def default_remote_resolution(
    extent_w: float,
    extent_h: float,
    provider_xsize: int = 0,
    provider_ysize: int = 0,
    max_default_px: int = DEFAULT_REMOTE_MAX_PX,
) -> tuple:
    """
    Propose (xres, yres) in CRS units for a remote raster snapshot.

    Native resolution when the provider reports its size (WCS usually
    does); otherwise size the long edge to ``max_default_px``.
    """
    if extent_w <= 0 or extent_h <= 0:
        return (1.0, 1.0)
    if provider_xsize > 0 and provider_ysize > 0:
        return (extent_w / provider_xsize, extent_h / provider_ysize)
    res = max(extent_w, extent_h) / max(1, max_default_px)
    return (res, res)


def estimate_remote_pixels(
    extent_w: float, extent_h: float, xres: float, yres: float
) -> int:
    """Width*height in pixels for a snapshot at the given resolution."""
    if extent_w <= 0 or extent_h <= 0 or xres <= 0 or yres <= 0:
        return 0
    return max(1, round(extent_w / xres)) * max(1, round(extent_h / yres))


def is_output_huge(
    pixels: int, band_count: int = 1, threshold_px: int = HUGE_OUTPUT_THRESHOLD_PX
) -> bool:
    """True when the estimated snapshot is heavy enough to warn about."""
    return pixels * max(1, band_count) > threshold_px


class RasterConverter:
    """
    Convert raster items into one or more GeoPackages.

    Args:
        target_crs: optional auth id (e.g. ``"EPSG:32632"``) for output
            reprojection. ``None`` keeps each raster's source CRS.
        tile_format: tile encoding inside the GPKG. One of AUTO, PNG,
            JPEG, WEBP. Default AUTO lets GDAL decide.
        tile_size: tile width/height in pixels. 256 (default) or 512.
        jpeg_quality: JPEG/WebP compression quality (1-100). Default 75.
        dry_run: when True, perform every check but do not write.
    """

    def __init__(
        self,
        target_crs: Optional[str] = None,
        tile_format: str = "AUTO",
        tile_size: int = 256,
        jpeg_quality: int = 75,
        dry_run: bool = False,
    ) -> None:
        self.target_crs = target_crs
        self.tile_format = tile_format if tile_format in TILE_FORMATS else "AUTO"
        self.tile_size = tile_size if tile_size in TILE_SIZES else 256
        self.jpeg_quality = max(1, min(100, jpeg_quality))
        self.dry_run = dry_run

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def convert(
        self,
        items: List[Dict],
        output_path: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ConversionResult:
        """
        Convert raster `items` into the GeoPackage at `output_path`.

        Items may be appended to an already-existing GPKG (e.g. one
        that already contains vector layers from the vector converter).
        """
        output_path = Path(output_path)
        result = ConversionResult(dry_run=self.dry_run)
        start = time.monotonic()

        if not items:
            result.add_warning("No raster items to convert")
            result.duration_seconds = time.monotonic() - start
            return result

        if not self.dry_run:
            try:
                os.makedirs(long_path(output_path.parent), exist_ok=True)
            except OSError as exc:
                result.add_error(str(output_path), f"Cannot create output directory: {exc}")
                result.duration_seconds = time.monotonic() - start
                return result

        total = len(items)
        remote_converted = 0
        for index, item in enumerate(items, start=1):
            name = str(item.get("name") or "raster")
            source = item.get("path")
            live_layer = item.get("layer_ref")
            label = str(item.get("source_label") or source or name)
            self._emit_progress(
                progress_callback,
                int(100 * (index - 1) / total),
                f"Converting raster {name}",
            )

            if not source and live_layer is None:
                result.add_error(name, "Item missing 'path'")
                continue
            if item.get("is_unreadable"):
                msg = (item.get("warnings") or ["File non leggibile"])[0]
                result.add_error(label, msg)
                continue
            if live_layer is None:
                source_path = Path(source)
                if not item.get("is_virtual") and not source_path.exists():
                    result.add_error(label, "Source file does not exist")
                    continue

            try:
                self._process_item(item, output_path, result)
                if item.get("is_remote"):
                    remote_converted += 1
            except RasterConversionError as exc:
                result.add_error(label, str(exc))
            except Exception as exc:  # noqa: BLE001
                result.add_error(label, f"Unexpected raster error: {exc}")

        if remote_converted:
            result.add_warning(
                f"{remote_converted} remote raster(s) sampled and converted "
                "(WCS/ArcGIS/WMS...)"
            )
        self._emit_progress(progress_callback, 100, "Raster conversion done")
        result.duration_seconds = time.monotonic() - start
        return result

    # ------------------------------------------------------------------
    # Per-item flow
    # ------------------------------------------------------------------

    def _process_item(
        self,
        item: Dict,
        output_path: Path,
        result: ConversionResult,
    ) -> None:
        name = str(item["name"])
        source_str = str(item.get("uri") or item.get("path") or item.get("source_label") or name)

        try:
            if self.dry_run:
                result.add_success(output_path, layer_name=name, is_raster=True)
                result.add_warning(f"[dry-run] Would write raster '{name}' to {output_path.name}")
                return

            if item.get("layer_ref") is not None:
                error_msg = self._write_remote_raster(
                    item, raster_table=name, output_path=output_path
                )
            else:
                error_msg = self._write_raster(
                    source_path=source_str,
                    raster_table=name,
                    output_path=output_path,
                )
            if error_msg:
                raise RasterConversionError(error_msg)
            result.add_success(output_path, layer_name=name, is_raster=True)
        finally:
            # Release the live layer clone as soon as the item is done.
            item.pop("layer_ref", None)

    # ------------------------------------------------------------------
    # Remote raster (WCS/ArcGIS MapServer/WMS): pipe snapshot → temp
    # GeoTIFF → the standard _write_raster GPKG-tiling path.
    # ------------------------------------------------------------------

    def _write_remote_raster(
        self,
        item: Dict,
        raster_table: str,
        output_path: Path,
    ) -> Optional[str]:
        """
        Materialise a remote raster provider into a temporary GeoTIFF via
        the QGIS raster pipe, then convert it to GPKG tiles through the
        existing `_write_raster()` (reusing tile format/size/quality and
        the reprojection branch). Returns None on success or an error
        message on failure.

        The snapshot is written in the layer's own CRS at the extent and
        resolution carried by the item (`raster_extent`,
        `raster_xres`/`raster_yres`); a target CRS, if any, is applied by
        `_write_raster` on the temp file.
        """
        import shutil
        import tempfile

        try:
            from qgis.core import (
                QgsCoordinateTransformContext,
                QgsRasterFileWriter,
                QgsRasterPipe,
                QgsRectangle,
            )
        except ImportError as exc:  # pragma: no cover - production always has QGIS
            return f"QGIS core unavailable: {exc}"

        layer = item.get("layer_ref")
        if layer is None or not layer.isValid():
            return "Remote raster layer is not valid"

        extent_tuple = item.get("raster_extent")
        if not extent_tuple:
            ext = layer.extent()
            extent_tuple = (ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum())
        extent = QgsRectangle(*extent_tuple)
        if extent.isEmpty():
            return "Remote raster extent is empty"

        xres = float(item.get("raster_xres") or 0)
        yres = float(item.get("raster_yres") or 0)
        if xres <= 0 or yres <= 0:
            provider0 = layer.dataProvider()
            xres, yres = default_remote_resolution(
                extent.width(),
                extent.height(),
                provider0.xSize() if provider0 else 0,
                provider0.ySize() if provider0 else 0,
            )
        width = max(1, round(extent.width() / xres))
        height = max(1, round(extent.height() / yres))

        # Worker-owned provider copy: the pipe takes ownership of it.
        provider = layer.dataProvider().clone()
        pipe = QgsRasterPipe()
        if not pipe.set(provider):
            return "Cannot build raster pipe for remote layer"

        tmp_dir = tempfile.mkdtemp(prefix="gpkgconv_")
        tmp_tif = os.path.join(tmp_dir, "remote_snapshot.tif")
        try:
            writer = QgsRasterFileWriter(tmp_tif)
            writer.setOutputFormat("GTiff")
            err = writer.writeRaster(
                pipe, width, height, extent, layer.crs(), QgsCoordinateTransformContext()
            )
            # Scoped enum form works on both Qt5 and Qt6 builds.
            if err != QgsRasterFileWriter.WriterError.NoError:
                return f"Remote raster snapshot failed (code {err})"
            if not os.path.isfile(tmp_tif):
                return "Remote raster snapshot produced no file"

            return self._write_raster(
                source_path=tmp_tif,
                raster_table=raster_table,
                output_path=output_path,
            )
        except Exception as exc:  # noqa: BLE001
            return f"Remote raster snapshot failed: {exc}"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # GDAL-dependent write step (lazy import)
    # ------------------------------------------------------------------

    def _write_raster(
        self,
        source_path: str,
        raster_table: str,
        output_path: Path,
    ) -> Optional[str]:
        """
        Write one raster into the GPKG. Returns None on success or an
        error message on failure.
        """
        try:
            from qgis import processing  # type: ignore[import-not-found]
        except ImportError:
            return "QGIS Processing framework not available"

        long_out = long_path(output_path)
        output_exists = os.path.isfile(long_out)

        # Build GDAL creation options string.
        co_parts = [
            f"TILE_FORMAT={self.tile_format}",
            f"BLOCKXSIZE={self.tile_size}",
            f"BLOCKYSIZE={self.tile_size}",
            f"RASTER_TABLE={raster_table}",
            f"RASTER_IDENTIFIER={raster_table}",
        ]
        if self.tile_format in ("JPEG", "WEBP") or (
            self.tile_format == "AUTO" and self.jpeg_quality != 75
        ):
            co_parts.append(f"QUALITY={self.jpeg_quality}")
        if output_exists:
            co_parts.append("APPEND_SUBDATASET=YES")

        options_str = "|".join(co_parts)

        # Choose algorithm: warpreproject if CRS change, translate otherwise.
        try:
            if self.target_crs:
                from qgis.core import QgsCoordinateReferenceSystem, QgsRasterLayer

                src_layer = QgsRasterLayer(source_path, "temp_check")
                src_crs = src_layer.crs().authid() if src_layer.isValid() else ""

                if src_crs and src_crs != self.target_crs:
                    # Reproject + convert via gdalwarp.
                    processing.run(
                        "gdal:warpreproject",
                        {
                            "INPUT": source_path,
                            "SOURCE_CRS": None,
                            "TARGET_CRS": QgsCoordinateReferenceSystem(self.target_crs),
                            "RESAMPLING": 0,  # Nearest neighbour
                            "NODATA": None,
                            "TARGET_RESOLUTION": None,
                            "OPTIONS": options_str,
                            "DATA_TYPE": 0,  # Use input type
                            "EXTRA": "",
                            "OUTPUT": str(long_out),
                        },
                    )
                else:
                    # Same CRS — just translate.
                    processing.run(
                        "gdal:translate",
                        {
                            "INPUT": source_path,
                            "TARGET_CRS": None,
                            "NODATA": None,
                            "COPY_SUBDATASETS": False,
                            "OPTIONS": options_str,
                            "EXTRA": "",
                            "DATA_TYPE": 0,
                            "OUTPUT": str(long_out),
                        },
                    )
            else:
                processing.run(
                    "gdal:translate",
                    {
                        "INPUT": source_path,
                        "TARGET_CRS": None,
                        "NODATA": None,
                        "COPY_SUBDATASETS": False,
                        "OPTIONS": options_str,
                        "EXTRA": "",
                        "DATA_TYPE": 0,
                        "OUTPUT": str(long_out),
                    },
                )
        except Exception as exc:  # noqa: BLE001
            return f"GDAL raster conversion failed: {exc}"

        # Verify output was created / updated.
        if not os.path.isfile(long_out):
            return "Output GeoPackage was not created by GDAL"

        return None

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    @staticmethod
    def _emit_progress(
        cb: Optional[ProgressCallback], percent: int, message: str
    ) -> None:
        if cb is None:
            return
        # Never let UI callback errors break the conversion.
        with contextlib.suppress(Exception):
            cb(percent, message)


__all__ = [
    "RasterConverter",
    "TILE_FORMATS",
    "TILE_SIZES",
    "default_remote_resolution",
    "estimate_remote_pixels",
    "is_output_huge",
]
