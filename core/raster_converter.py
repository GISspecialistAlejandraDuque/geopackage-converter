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

import os
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ._paths import long_path
from .converter import ConversionResult, ProgressCallback
from .exceptions import RasterConversionError

# Tile format choices understood by the GDAL GeoPackage raster driver.
TILE_FORMATS = ("AUTO", "PNG", "JPEG", "WEBP")
TILE_SIZES = (256, 512)


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
        for index, item in enumerate(items, start=1):
            name = str(item.get("name") or "raster")
            source = item.get("path")
            self._emit_progress(
                progress_callback,
                int(100 * (index - 1) / total),
                f"Converting raster {name}",
            )

            if not source:
                result.add_error(name, "Item missing 'path'")
                continue
            if item.get("is_unreadable"):
                msg = (item.get("warnings") or ["File non leggibile"])[0]
                result.add_error(str(source), msg)
                continue
            source_path = Path(source)
            if not item.get("is_virtual") and not source_path.exists():
                result.add_error(str(source_path), "Source file does not exist")
                continue

            try:
                self._process_item(item, output_path, result)
            except RasterConversionError as exc:
                result.add_error(str(source_path), str(exc))
            except Exception as exc:  # noqa: BLE001
                result.add_error(str(source_path), f"Unexpected raster error: {exc}")

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
        source_str = str(item.get("uri") or item["path"])

        if self.dry_run:
            result.add_success(output_path, layer_name=name, is_raster=True)
            result.add_warning(f"[dry-run] Would write raster '{name}' to {output_path.name}")
            return

        error_msg = self._write_raster(
            source_path=source_str,
            raster_table=name,
            output_path=output_path,
        )
        if error_msg:
            raise RasterConversionError(error_msg)
        result.add_success(output_path, layer_name=name, is_raster=True)

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
                    result = processing.run(
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
                    result = processing.run(
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
                result = processing.run(
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
        try:
            cb(percent, message)
        except Exception:  # noqa: BLE001
            pass


__all__ = ["RasterConverter", "TILE_FORMATS", "TILE_SIZES"]
