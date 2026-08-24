"""
Heart of GeoPackage Converter: convert vector items to a GeoPackage.

Design notes
------------
* QGIS imports are lazy (inside `_write_layer`) so this module can be
  imported in unit tests without a running QGIS (Rule 4).
* The conversion engine prefers `QgsVectorFileWriter.writeAsVectorFormatV3`
  (QGIS 3.20+) and falls back to V2 if missing — keeps us compatible
  with QGIS 3.34 LTS through 4.x.
* `dry_run=True` walks the same code path *without* writing: it still
  validates inputs, accumulates would-be operations into the result,
  and exercises the progress callback.
* `convert()` never raises on a per-item failure: errors are collected
  in `ConversionResult.errors` so a batch of 200 files does not abort
  on one bad shapefile. Only programmer errors (bad arguments) raise.
"""

from __future__ import annotations

import contextlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ._paths import long_path
from .exceptions import ConversionError, InvalidSourceError

ProgressCallback = Callable[[int, str], None]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ConversionResult:
    """Aggregated outcome of a `Converter.convert()` call."""

    success_count: int = 0
    error_count: int = 0
    errors: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    output_files: List[Path] = field(default_factory=list)
    # Pairs (gpkg_path, layer_name) listing every layer actually written.
    # Lets callers (UI, report) distinguish freshly-written content from
    # pre-existing layers in a GeoPackage that we appended to.
    output_layers: List = field(default_factory=list)
    duration_seconds: float = 0.0
    dry_run: bool = False
    # Per-type counters for the report breakdown.
    vector_success_count: int = 0
    raster_success_count: int = 0

    def add_success(self, output_path: Path, layer_name: str = "", *, is_raster: bool = False) -> None:
        self.success_count += 1
        if is_raster:
            self.raster_success_count += 1
        else:
            self.vector_success_count += 1
        if output_path not in self.output_files:
            self.output_files.append(output_path)
        if layer_name:
            self.output_layers.append((output_path, layer_name))

    def add_error(self, source: str, message: str) -> None:
        self.error_count += 1
        self.errors.append({"source": source, "message": message})

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------


class Converter:
    """
    Convert vector items into one or more GeoPackages.

    Args:
        target_crs: optional auth id (e.g. ``"EPSG:32632"``) for output
            reprojection. ``None`` keeps each layer's source CRS.
        save_styles: when True, persist each layer's QML style inside
            the GPKG via `QgsVectorLayer.saveStyleToDatabase`.
        validate_geometries: when True, run the `native:fixgeometries`
            equivalent on each layer before writing.
        dry_run: when True, perform every check and emit progress
            callbacks but do not write to disk.
    """

    def __init__(
        self,
        target_crs: Optional[str] = None,
        save_styles: bool = True,
        validate_geometries: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.target_crs = target_crs
        self.save_styles = save_styles
        self.validate_geometries = validate_geometries
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
        Convert `items` into the GeoPackage at `output_path`.

        `items` is a list of dicts with at least `path` and `name`
        (the schema produced by `folder_scanner.scan_folder` and
        post-processed by `grouping_strategies.*`).
        """
        if items is None:
            raise InvalidSourceError("items is required")
        output_path = Path(output_path)
        result = ConversionResult(dry_run=self.dry_run)
        start = time.monotonic()

        if not items:
            result.add_warning("No items to convert")
            result.duration_seconds = time.monotonic() - start
            return result

        if not self.dry_run:
            # Wipe any pre-existing GeoPackage at the same path so each
            # convert() call starts with a clean file. Without this, the
            # OGR driver may refuse to overwrite (especially on Windows)
            # and reports "file system object already exists".
            try:
                long_out = long_path(output_path)
                if os.path.isfile(long_out):
                    os.remove(long_out)
                # Drop sidecars (-shm, -wal SQLite, plus .gpkg-journal).
                for suffix in ("-shm", "-wal", "-journal"):
                    sidecar = long_path(Path(str(output_path) + suffix))
                    if os.path.isfile(sidecar):
                        try:
                            os.remove(sidecar)
                        except OSError:
                            pass
            except OSError as exc:
                result.add_error(
                    str(output_path),
                    f"Cannot remove existing GeoPackage: {exc}. "
                    "It may be open in QGIS — close it and retry.",
                )
                result.duration_seconds = time.monotonic() - start
                return result

            try:
                os.makedirs(long_path(output_path.parent), exist_ok=True)
            except OSError as exc:
                result.add_error(str(output_path), f"Cannot create output directory: {exc}")
                result.duration_seconds = time.monotonic() - start
                return result

        total = len(items)
        remote_converted = 0
        for index, item in enumerate(items, start=1):
            name = str(item.get("name") or "layer")
            source = item.get("path")
            live_layer = item.get("layer_ref")
            # Errors are labeled with `source_label` (provider-aware, set
            # for live/remote items) when present, else the source path.
            label = str(item.get("source_label") or source or name)
            self._emit_progress(progress_callback, int(100 * (index - 1) / total), f"Converting {name}")

            if not source and live_layer is None:
                result.add_error(name, "Item missing 'path'")
                continue
            # Items the scanner already marked as unreadable (e.g. OneDrive
            # online-only placeholders): forward the warning verbatim and skip.
            if item.get("is_unreadable"):
                msg = (item.get("warnings") or ["File non leggibile"])[0]
                result.add_error(label, msg)
                continue
            if live_layer is None:
                source_path = Path(source)
                # Virtual sources (zip/rar via /vsizip/, /vsirar/, etc.)
                # bypass the on-disk existence check — OGR resolves them.
                is_virtual = bool(item.get("is_virtual")) or str(source_path).startswith(
                    ("/vsizip/", "/vsirar/")
                )
                if not is_virtual and not source_path.exists():
                    result.add_error(label, "Source file does not exist")
                    continue

            try:
                self._process_item(item, output_path, result)
                if item.get("is_remote"):
                    remote_converted += 1
            except ConversionError as exc:
                result.add_error(label, str(exc))
            except Exception as exc:  # noqa: BLE001 - batch must not abort on one item
                result.add_error(label, f"Unexpected: {exc}")

        if remote_converted:
            result.add_warning(
                f"{remote_converted} remote layer(s) downloaded and converted "
                "(WFS/ArcGIS/WCS...)"
            )
        self._emit_progress(progress_callback, 100, "Done")
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
        # Prefer the explicit OGR URI when present (zip entries), else the
        # path; live items (layer_ref) may have neither — label with name.
        source_str = str(item.get("uri") or item.get("path") or item.get("source_label") or name)
        encoding = str(item.get("encoding") or "UTF-8")

        try:
            if self.dry_run:
                result.add_success(output_path, layer_name=name)
                result.add_warning(f"[dry-run] Would write '{name}' to {output_path.name}")
                return

            error_msg = self._write_layer(
                source_path=source_str,
                layer_name=name,
                output_path=output_path,
                encoding=encoding,
                style_xml=item.get("style_xml"),
                layer=item.get("layer_ref"),
            )
            if error_msg:
                raise ConversionError(error_msg)
            result.add_success(output_path, layer_name=name)
        finally:
            # Release the live layer clone as soon as the item is done:
            # WFS/memory clones can hold a lot of cached features.
            item.pop("layer_ref", None)

    # ------------------------------------------------------------------
    # QGIS-dependent write step (lazy import; tests monkeypatch)
    # ------------------------------------------------------------------

    def _write_layer(
        self,
        source_path,
        layer_name: str,
        output_path: Path,
        encoding: str,
        style_xml: Optional[str] = None,
        layer=None,
    ) -> Optional[str]:
        """
        Write one layer into the GPKG. Returns None on success or an
        error message on failure. Never raises.

        ``layer`` — an already-valid QgsVectorLayer (a main-thread clone
        of a project layer). When given, the source is NOT re-opened by
        path: this is how WFS/ArcGIS REST/memory/CSV/PostGIS layers are
        written, since "ogr" cannot open their URIs.
        """
        try:
            from qgis.core import (
                QgsCoordinateReferenceSystem,
                QgsCoordinateTransformContext,
                QgsVectorFileWriter,
                QgsVectorLayer,
            )
        except ImportError as exc:  # pragma: no cover - production always has QGIS
            return f"QGIS core unavailable: {exc}"

        if layer is None:
            layer = QgsVectorLayer(str(source_path), layer_name, "ogr")
        if not layer.isValid():
            return f"Invalid source layer: {source_path}"

        if self.validate_geometries:
            fixed, fix_err = self._fix_geometries(layer)
            if fix_err:
                return fix_err
            layer = fixed

        # Long-path-aware spellings: avoids "unable to open database file"
        # on Windows when the output path exceeds 260 chars (mirror mode).
        long_out = long_path(output_path)
        output_exists = os.path.isfile(long_out)
        options = self._build_writer_options(
            layer_name=layer_name,
            encoding=encoding,
            output_exists=output_exists,
        )
        if self.target_crs:
            crs = QgsCoordinateReferenceSystem(self.target_crs)
            if not crs.isValid():
                return f"Invalid target CRS: {self.target_crs}"
            options.ct = self._make_transform(layer.crs(), crs)
            options.destCRS = crs
        elif layer.crs().isValid():
            options.ct = self._make_transform(layer.crs(), layer.crs())
            options.destCRS = layer.crs()

        write_fn = getattr(QgsVectorFileWriter, "writeAsVectorFormatV3", None)
        try:
            if write_fn is not None:
                ctx = QgsCoordinateTransformContext()
                error_code, error_message, *_ = write_fn(layer, long_out, ctx, options)
            else:
                error_code, error_message = QgsVectorFileWriter.writeAsVectorFormatV2(  # type: ignore[attr-defined]
                    layer, long_out, QgsCoordinateTransformContext(), options
                )
        except Exception as exc:  # noqa: BLE001
            return f"Writer raised: {exc}"

        if error_code != QgsVectorFileWriter.NoError:
            return error_message or f"Writer returned error code {error_code}"

        if self.save_styles:
            # Style persistence is best-effort: a failure here must NOT
            # mark a successful data conversion as failed.
            try:
                self._save_style(
                    Path(long_out), layer_name, layer, style_xml=style_xml
                )
            except Exception as exc:  # noqa: BLE001
                from qgis.core import QgsMessageLog
                QgsMessageLog.logMessage(
                    f"Style save skipped for {layer_name}: {exc}",
                    "GeoPackage Converter",
                )

        return None

    # ------------------------------------------------------------------
    # Helpers wrapping QGIS APIs (lazy imports happen inside)
    # ------------------------------------------------------------------

    def _build_writer_options(
        self, layer_name: str, encoding: str, output_exists: bool
    ):
        from qgis.core import QgsVectorFileWriter

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer_name
        options.fileEncoding = encoding
        if output_exists:
            options.actionOnExistingFile = (
                QgsVectorFileWriter.CreateOrOverwriteLayer
            )
        return options

    def _make_transform(self, source_crs, dest_crs):
        from qgis.core import QgsCoordinateTransform, QgsProject

        return QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())

    def _fix_geometries(self, layer) -> Tuple[object, Optional[str]]:
        """Run native:fixgeometries; on failure return (layer, error)."""
        try:
            from qgis import processing  # type: ignore[import-not-found]
        except ImportError:
            return layer, "Processing framework not available for geometry validation"
        try:
            params = {"INPUT": layer, "OUTPUT": "memory:"}
            output = processing.run("native:fixgeometries", params)
            return output["OUTPUT"], None
        except Exception as exc:  # noqa: BLE001
            return layer, f"Geometry fix failed: {exc}"

    def _save_style(
        self,
        output_path: Path,
        layer_name: str,
        source_layer,
        style_xml: Optional[str] = None,
    ) -> None:
        """
        Persist a QML style into the GeoPackage so QGIS re-applies it on reopen.

        Style source priority:
          1. ``style_xml`` argument — the *live* QGIS style of the project
             layer (preferred when available, e.g. mode "from project").
          2. ``source_layer.exportNamedStyle()`` — the style of the freshly
             opened layer (a default categorisation when the source has no
             sidecar QML).

        The style is imported into a writer-side QgsVectorLayer pointing
        at the just-written GPKG layer, then committed to the
        ``layer_styles`` table via ``saveStyleToDatabase``.
        Caller wraps this in try/except — any failure is logged and ignored.
        """
        from qgis.core import QgsVectorLayer
        from qgis.PyQt.QtXml import QDomDocument

        uri = f"{output_path}|layername={layer_name}"
        written = QgsVectorLayer(uri, layer_name, "ogr")
        if not written.isValid():
            return

        doc = QDomDocument()
        if style_xml:
            doc.setContent(style_xml)
        else:
            source_layer.exportNamedStyle(doc)

        ok, _msg = written.importNamedStyle(doc)
        if not ok:
            return

        # Persist into the layer_styles table inside the GPKG.
        # Signature varies slightly between QGIS versions; use kwargs
        # only if available, fall back to positional otherwise.
        try:
            written.saveStyleToDatabase(
                layer_name, "GeoPackage Converter", True, ""
            )
        except TypeError:
            written.saveStyleToDatabase(layer_name, "", True, "")

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


__all__ = ["Converter", "ConversionResult", "ProgressCallback"]
