"""
Filesystem scanner for vector sources.

Walks a folder (optionally recursive), filters by supported extension,
and returns one metadata dict per file. The QGIS-dependent inspection
step is isolated in `_inspect_with_qgis()`, which is the only thing that
needs `qgis.core`. Tests monkeypatch that function so the rest of the
module stays unit-testable without a running QGIS (Rule 4).
"""

from __future__ import annotations

import os
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Dict, List, Optional, Union

from ._paths import long_path as _long_path_impl
from .encoding_detector import detect_encoding

# Map supported extensions -> short format key used in result dicts.
# Lowercase, leading dot included.
SUPPORTED_EXTENSIONS: Dict[str, str] = {
    ".shp": "shp",
    ".tab": "tab",
    ".kml": "kml",
    ".kmz": "kmz",
    ".gml": "gml",
    ".geojson": "geojson",
    ".json": "geojson",
    ".dxf": "dxf",
    ".gpx": "gpx",
    ".mif": "mif",
}

# Archives expanded virtually via GDAL's /vsizip/ filesystem.
# Each entry inside becomes a separate item.
_ARCHIVE_EXTENSIONS = {".zip"}

# Inner extensions worth surfacing from a ZIP. Mirrors SUPPORTED_EXTENSIONS
# but excludes .kmz (already a zipped KML — handled by OGR directly).
_ZIP_INNER_EXTENSIONS = set(SUPPORTED_EXTENSIONS) - {".kmz"}

# Extensions for which encoding detection makes sense.
# XML-/JSON-based formats are virtually always UTF-8.
_ENCODING_RELEVANT_EXTS = {".shp", ".tab", ".dxf", ".mif"}


def _long_path(path):
    """Backward-compat shim around the shared `_paths.long_path` helper."""
    return _long_path_impl(path)


def _vsizip_uri(zip_path: Path, inner: str) -> str:
    """Build a GDAL /vsizip/ URI. Forward slashes for OGR portability."""
    z = str(zip_path.resolve()).replace("\\", "/")
    return f"/vsizip/{z}/{inner.lstrip('/')}"


def _iter_zip_vector_entries(zip_path: Path) -> Iterable[Dict[str, object]]:
    """
    Yield one metadata dict per supported vector file inside `zip_path`.

    The dict has the same shape used by `scan_folder` results, plus
    `is_virtual=True` and `archive` (the zip Path) so callers can group/log.
    Failures (corrupt zip, IOError) are yielded as a single warning entry.
    """
    # Detect OneDrive / cloud "online-only" placeholders: the file
    # appears in directory listings but isn't materialised on disk.
    # On Windows the GetFileAttributesW call returns 0xFFFFFFFF (-1)
    # for these. We surface a friendly hint instead of a cryptic ENOENT.
    accessible_path = _long_path(zip_path)
    is_online_only_placeholder = False
    try:
        if not os.path.isfile(accessible_path):
            is_online_only_placeholder = True
    except OSError:
        is_online_only_placeholder = True

    try:
        if is_online_only_placeholder:
            raise FileNotFoundError("File not materialised on disk")
        with zipfile.ZipFile(accessible_path) as zf:
            names = zf.namelist()
    except (zipfile.BadZipFile, OSError) as exc:
        if is_online_only_placeholder or isinstance(exc, FileNotFoundError):
            warning = (
                "File non disponibile localmente. Probabilmente è un "
                "placeholder OneDrive/cloud non ancora scaricato: "
                "tasto destro sul file in Esplora risorse → "
                "'Mantieni sempre su questo dispositivo', poi riprova."
            )
        else:
            warning = f"Cannot open ZIP: {exc}"
        # Group by *parent directory of the zip*, not by zip stem.
        # That way multiple zips in the same folder produce one .gpkg.
        parent_label = zip_path.parent.name or "unsorted"
        yield {
            "path": zip_path,
            "format": "zip",
            "name": zip_path.stem,
            "geometry_type": "Unknown",
            "crs": "Unknown",
            "feature_count": 0,
            "encoding": "UTF-8",
            "warnings": [warning],
            "is_virtual": True,
            "archive": zip_path,
            "subfolder": parent_label,
            "is_unreadable": True,
        }
        return

    for inner in sorted(names):
        if inner.endswith("/"):
            continue
        ext = Path(inner).suffix.lower()
        if ext not in _ZIP_INNER_EXTENSIONS:
            continue
        uri = _vsizip_uri(zip_path, inner)
        # Layer name: prefix with the zip stem when the inner shapefile
        # would collide on a generic name. Always include the zip stem
        # so layers from sibling zips in the same group remain traceable.
        inner_stem = Path(inner).stem
        layer_name = inner_stem if inner_stem == zip_path.stem else f"{zip_path.stem}__{inner_stem}"
        parent_label = zip_path.parent.name or "unsorted"
        yield {
            # Use the archive path (a real file on disk) so callers'
            # `.exists()` checks succeed; the OGR-friendly URI lives
            # in `uri` and is preferred by the converter.
            "path": zip_path,
            "uri": uri,
            "format": SUPPORTED_EXTENSIONS[ext],
            "name": layer_name,
            "is_virtual": True,
            "archive": zip_path,
            "subfolder": parent_label,
            "inner_path": inner,
        }


# ---------------------------------------------------------------------------
# QGIS-dependent inspection (kept isolated for testability)
# ---------------------------------------------------------------------------


def _inspect_with_qgis(path) -> Dict[str, object]:
    """
    Open `path` with QgsVectorLayer and extract metadata.

    `path` can be a `pathlib.Path` for a file on disk OR a string-like
    URI (e.g. ``/vsizip/foo.zip/inner.shp``). Strings are passed
    verbatim to OGR, which understands the GDAL virtual filesystems.

    Returns a dict with keys: geometry_type, crs, feature_count, warnings.
    Never raises — failures are reported via the `warnings` list and
    fallback values ("Unknown" / 0).
    """
    warnings: List[str] = []
    geometry_type = "Unknown"
    crs_id = "Unknown"
    feature_count = 0

    try:
        from qgis.core import QgsVectorLayer, QgsWkbTypes
    except ImportError:
        warnings.append("QGIS core not available; metadata limited to filename")
        return {
            "geometry_type": geometry_type,
            "crs": crs_id,
            "feature_count": feature_count,
            "warnings": warnings,
        }

    source = str(path)
    name = Path(source).stem
    layer = QgsVectorLayer(source, name, "ogr")
    if not layer.isValid():
        warnings.append("Layer invalid or unreadable by OGR")
        return {
            "geometry_type": geometry_type,
            "crs": crs_id,
            "feature_count": feature_count,
            "warnings": warnings,
        }

    wkb = layer.wkbType()
    geometry_type = QgsWkbTypes.displayString(wkb) or "Unknown"

    crs = layer.crs()
    if crs.isValid():
        auth = crs.authid()
        crs_id = auth if auth else crs.description() or "Unknown"
    else:
        warnings.append("CRS not recognised")
        crs_id = "Unknown"

    feature_count = max(int(layer.featureCount()), 0)
    return {
        "geometry_type": geometry_type,
        "crs": crs_id,
        "feature_count": feature_count,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _iter_candidate_files(root: Path, recursive: bool) -> Iterable[Path]:
    """
    Yield files under `root` whose extension is supported directly OR
    is an archive we know how to peek into.

    Uses `os.walk` (not `Path.rglob`) because `pathlib`'s glob has a
    long-standing Windows bug on paths containing characters like
    `°`, `&` or non-ASCII punctuation: `rglob('*')` silently fails to
    descend past the offending segment. `os.walk` walks correctly.
    """
    accepted = set(SUPPORTED_EXTENSIONS) | _ARCHIVE_EXTENSIONS
    walk_root = _long_path(root)
    if recursive:
        for dirpath, _dirs, filenames in os.walk(walk_root):
            for fname in filenames:
                if Path(fname).suffix.lower() in accepted:
                    # Strip the long-path prefix back so downstream
                    # tools see a clean Path. We re-add it on access.
                    clean_dir = dirpath[4:] if dirpath.startswith("\\\\?\\") else dirpath
                    yield Path(clean_dir) / fname
    else:
        try:
            entries = list(os.scandir(walk_root))
        except OSError:
            return
        for entry in entries:
            if entry.is_file() and Path(entry.name).suffix.lower() in accepted:
                clean = entry.path[4:] if entry.path.startswith("\\\\?\\") else entry.path
                yield Path(clean)


def scan_folder(
    path: Union[str, Path],
    recursive: bool = True,
    flatten_hierarchy: bool = False,
    mirror_hierarchy: bool = False,
) -> List[Dict[str, object]]:
    """
    Scan `path` for supported vector files and return metadata for each.

    Args:
        path: directory to scan.
        recursive: when True (default), descend into subdirectories.
        flatten_hierarchy: when True, the `subfolder` field of each item
            encodes the *full* relative path from `root` (joined with
            ``__``) instead of just the immediate parent name. This lets
            the "by subfolder" grouping preserve a deep hierarchy in the
            output filename.
        mirror_hierarchy: when True, the `subfolder` field encodes the
            full relative path joined with the OS separator (``/``).
            Combined with the "by subfolder" grouping, the converter
            *replicates the input folder structure on disk* — each
            ``.gpkg`` lands inside nested directories that mirror the
            source layout. Wins over ``flatten_hierarchy`` when both
            are passed.

    Returns:
        A list of dicts with keys:
            path, format, name, geometry_type, crs, feature_count,
            encoding, warnings.
        Returns an empty list when `path` does not exist or contains no
        supported files.

    Raises:
        NotADirectoryError: if `path` exists but is not a directory.
    """
    root = Path(path)
    if not root.exists():
        return []
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    def _subfolder_label(file_or_zip: Path) -> str:
        """Compute the grouping label honoring the hierarchy flags."""
        try:
            rel = file_or_zip.relative_to(root)
        except ValueError:
            return file_or_zip.parent.name or "unsorted"
        parts = rel.parts[:-1]  # drop filename
        if not parts:
            return root.name or "unsorted"
        if mirror_hierarchy:
            # Forward-slash joined: grouping_strategies will turn this
            # back into nested output directories on disk.
            return "/".join(parts)
        if flatten_hierarchy:
            return "__".join(parts)
        return parts[-1]

    results: List[Dict[str, object]] = []
    for file_path in sorted(_iter_candidate_files(root, recursive)):
        ext = file_path.suffix.lower()

        # Archives: expand into one entry per inner vector file.
        if ext in _ARCHIVE_EXTENSIONS:
            for entry in _iter_zip_vector_entries(file_path):
                if "format" in entry and "geometry_type" not in entry:
                    meta = _inspect_with_qgis(entry["uri"])
                    entry["geometry_type"] = meta["geometry_type"]
                    entry["crs"] = meta["crs"]
                    entry["feature_count"] = meta["feature_count"]
                    entry["encoding"] = "UTF-8"  # vsizip + chardet rarely useful
                    entry["warnings"] = list(meta.get("warnings") or [])
                # When flatten/mirror is on, encode the full hierarchy.
                # Otherwise keep the zip-parent subfolder set inside
                # _iter_zip_vector_entries.
                if flatten_hierarchy or mirror_hierarchy:
                    entry["subfolder"] = _subfolder_label(file_path)
                results.append(entry)
            continue

        # Regular file on disk.
        fmt = SUPPORTED_EXTENSIONS[ext]
        encoding = _detect_encoding_safe(file_path, ext)
        meta = _inspect_with_qgis(file_path)

        warnings: List[str] = list(meta.get("warnings") or [])  # type: ignore[arg-type]
        if encoding is None:
            encoding = "UTF-8"
            warnings.append("Encoding detection failed; assumed UTF-8")

        results.append(
            {
                "path": file_path,
                "format": fmt,
                "name": file_path.stem,
                "geometry_type": meta["geometry_type"],
                "crs": meta["crs"],
                "feature_count": meta["feature_count"],
                "encoding": encoding,
                "warnings": warnings,
                "subfolder": _subfolder_label(file_path),
            }
        )
    return results


def _detect_encoding_safe(file_path: Path, ext: str) -> Optional[str]:
    """
    Encoding detection that never raises. Returns a label or None.
    XML-/JSON-based formats short-circuit to UTF-8 without probing.
    """
    if ext not in _ENCODING_RELEVANT_EXTS:
        return "UTF-8"
    try:
        return detect_encoding(file_path)
    except Exception:  # noqa: BLE001 - defensive: scanner must never crash on a single file
        return None


__all__ = ["scan_folder", "SUPPORTED_EXTENSIONS"]
