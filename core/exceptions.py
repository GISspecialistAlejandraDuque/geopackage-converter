"""
Custom exception hierarchy for GeoPackage Converter.

All errors raised by `core/` derive from `GeoPackageConverterError`, so callers
(GUI, Processing algorithms) can catch a single base class to surface
plugin-specific failures without swallowing unrelated exceptions.
"""

from __future__ import annotations


class GeoPackageConverterError(Exception):
    """Base class for every error raised by the plugin core."""


class InvalidSourceError(GeoPackageConverterError):
    """Raised when an input file/layer cannot be opened or is unsupported."""


class ConversionError(GeoPackageConverterError):
    """Raised when writing to the GeoPackage fails for a specific layer."""


class EncodingDetectionError(GeoPackageConverterError):
    """Raised when encoding detection fails irrecoverably (rare; usually we fall back to UTF-8)."""


class CRSError(GeoPackageConverterError):
    """Raised for invalid, unknown, or unresolvable CRS references."""


class RasterConversionError(GeoPackageConverterError):
    """Raised when writing a raster layer to the GeoPackage fails."""


__all__ = [
    "GeoPackageConverterError",
    "InvalidSourceError",
    "ConversionError",
    "RasterConversionError",
    "EncodingDetectionError",
    "CRSError",
]
