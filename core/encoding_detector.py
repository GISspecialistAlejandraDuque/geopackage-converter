"""
Encoding detection for vector source files.

Strategy (in order):
    1. Sidecar `.cpg` file next to the source (Esri convention for shapefiles).
    2. `chardet` probe on the `.dbf` (or the file itself for non-shapefile sources).
    3. UTF-8 fallback (the GeoPackage native encoding).

Detected names are normalised to canonical Python codec labels
(e.g. `cp1252` -> `Windows-1252`, `latin1` -> `ISO-8859-1`) so callers
can pass them straight to `QgsVectorLayer` / `open()` without surprises.

Pure-Python: no QGIS or Qt imports here — keeps the module unit-testable
without a running QGIS instance (Rule 4).
"""

from __future__ import annotations

import codecs
from pathlib import Path
from typing import Optional

from .exceptions import EncodingDetectionError

# How many bytes to sniff with chardet. 64 KiB is plenty for legacy DBFs
# and avoids loading huge files into memory.
_CHARDET_SAMPLE_BYTES = 64 * 1024

# Confidence floor below which we discard chardet's guess and fall back
# to UTF-8 rather than risk a wrong label.
_CHARDET_MIN_CONFIDENCE = 0.60

# Map of common aliases -> canonical Python codec name.
# Keys are stored lowercase, stripped of '-' and '_' for robust matching.
_ALIAS_MAP = {
    "utf8": "UTF-8",
    "utf8sig": "UTF-8-SIG",
    "utf8bom": "UTF-8-SIG",
    "utf16": "UTF-16",
    "utf16le": "UTF-16-LE",
    "utf16be": "UTF-16-BE",
    "ascii": "ASCII",
    "latin1": "ISO-8859-1",
    "latin9": "ISO-8859-15",
    "iso88591": "ISO-8859-1",
    "iso885915": "ISO-8859-15",
    "cp1252": "Windows-1252",
    "windows1252": "Windows-1252",
    "ansi": "Windows-1252",
    "cp850": "CP850",
    "cp437": "CP437",
    "macroman": "MacRoman",
}

DEFAULT_ENCODING = "UTF-8"


def _normalize_label(raw: str) -> str:
    """
    Return a canonical encoding label for a raw string.

    Falls back to the codec module's canonical lookup when no manual
    alias matches; if even that fails, returns the raw label as-is so
    downstream code can still attempt to use it.
    """
    if not raw:
        return DEFAULT_ENCODING
    key = raw.strip().lower().replace("-", "").replace("_", "")
    if key in _ALIAS_MAP:
        return _ALIAS_MAP[key]
    try:
        return codecs.lookup(raw).name.upper().replace("_", "-")
    except LookupError:
        return raw.strip()


def _read_cpg_sidecar(source: Path) -> Optional[str]:
    """
    Look for a sidecar `.cpg` file (case-insensitive on the extension)
    next to `source` and return its contents stripped, or None.

    Esri's convention: the `.cpg` holds a single line with the codepage
    name (e.g. "UTF-8", "1252", "ISO-8859-1").
    """
    stem_path = source.with_suffix("")
    for ext in (".cpg", ".CPG", ".cpG", ".Cpg"):
        candidate = stem_path.with_suffix(ext)
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="ascii", errors="replace").strip()
            except OSError:
                return None
            if not text:
                return None
            # Some CPG files contain just a codepage number (e.g. "1252").
            if text.isdigit():
                return f"cp{text}"
            return text
    return None


def _probe_with_chardet(target: Path) -> Optional[str]:
    """
    Run chardet on the first chunk of `target`. Returns the detected
    encoding string when confidence >= threshold, else None.
    Returns None if chardet is not installed (it is an optional dependency).
    """
    try:
        import chardet  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        with target.open("rb") as handle:
            sample = handle.read(_CHARDET_SAMPLE_BYTES)
    except OSError:
        return None
    if not sample:
        return None
    result = chardet.detect(sample)
    encoding = result.get("encoding")
    confidence = float(result.get("confidence") or 0.0)
    if not encoding or confidence < _CHARDET_MIN_CONFIDENCE:
        return None
    return encoding


def detect_encoding(file_path) -> str:
    """
    Detect the text encoding of a vector source file.

    Args:
        file_path: path to the vector file (str or Path). For shapefiles,
            pass the `.shp` path; the function will still pick up the
            sibling `.cpg` and probe the `.dbf`.

    Returns:
        Canonical encoding label (e.g. "UTF-8", "Windows-1252", "ISO-8859-1").
        Always returns a string — falls back to UTF-8 rather than failing.

    Raises:
        EncodingDetectionError: only if `file_path` is empty/invalid.
            Missing files do *not* raise — they fall back to UTF-8.
    """
    if not file_path:
        raise EncodingDetectionError("file_path is required")
    source = Path(file_path)

    # 1. Sidecar .cpg (works for any source, but is mainly a shapefile thing).
    cpg_value = _read_cpg_sidecar(source)
    if cpg_value:
        return _normalize_label(cpg_value)

    # 2. chardet on the most informative companion file.
    #    For shapefiles the textual data lives in the .dbf, not the .shp.
    probe_target = source
    if source.suffix.lower() == ".shp":
        dbf = source.with_suffix(".dbf")
        if dbf.is_file():
            probe_target = dbf

    if probe_target.is_file():
        guess = _probe_with_chardet(probe_target)
        if guess:
            return _normalize_label(guess)

    # 3. Fallback.
    return DEFAULT_ENCODING


__all__ = ["detect_encoding", "DEFAULT_ENCODING"]
