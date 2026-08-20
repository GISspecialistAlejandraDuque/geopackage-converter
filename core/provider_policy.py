"""
Routing policy: which conversion flow handles a layer, by data provider.

Design notes
------------
* Pure Python, no QGIS imports — fully unit-testable without a runtime.
* The provider name is what `QgsMapLayer.providerType()` returns
  (identical to `dataProvider().name()`, but never None when the
  provider failed to load).
* Policy: only file-backed providers keep the historical re-open-by-path
  flow. Everything else is handled through the *live* layer object taken
  from the project (vector) or a raster-pipe snapshot (raster), which
  makes WFS/ArcGIS REST/WCS — and, for free, memory, delimited-text,
  PostGIS, SpatiaLite… — convertible.
"""

from __future__ import annotations

# Providers whose source is a local file/dataset path that OGR/GDAL can
# re-open from the source string. Everything else goes live.
FILE_VECTOR_PROVIDERS = frozenset({"ogr"})
FILE_RASTER_PROVIDERS = frozenset({"gdal"})

# Providers considered "remote" (network services) for report labeling
# and for the remote-raster extent/resolution UI.
REMOTE_PROVIDERS = frozenset(
    {
        "wfs",  # also OGC API - Features (oapif goes through the wfs provider)
        "oapif",
        "arcgisfeatureserver",
        "arcgismapserver",
        "wcs",
        "wms",
        "xyz",
    }
)

# Human-friendly names for the most common providers, used in the layer
# list markers and in report labels. Unknown providers fall back to the
# raw provider name.
PROVIDER_DISPLAY_NAMES = {
    "wfs": "WFS",
    "oapif": "OGC API Features",
    "arcgisfeatureserver": "ArcGIS FS",
    "arcgismapserver": "ArcGIS MS",
    "wcs": "WCS",
    "wms": "WMS",
    "xyz": "XYZ",
    "memory": "Memoria",
    "delimitedtext": "CSV",
    "postgres": "PostGIS",
    "spatialite": "SpatiaLite",
    "mssql": "MS SQL",
    "oracle": "Oracle",
    "hana": "SAP HANA",
    "virtual": "Virtuale",
}

# GDAL virtual-filesystem prefixes recognised as "not a plain disk file".
# Single source of truth for the dialog and the Processing algorithms.
VSI_PREFIXES = (
    "/vsizip/",
    "/vsigzip/",
    "/vsitar/",
    "/vsirar/",
    "/vsi7z/",
    "/vsicurl/",
    "/vsis3/",
)

# Conversion routes.
ROUTE_FILE = "file"  # historical path-based flow (ogr/gdal)
ROUTE_LIVE_VECTOR = "live_vector"  # pass the live QgsVectorLayer to the writer
ROUTE_REMOTE_RASTER = "remote_raster"  # raster-pipe snapshot flow


def route_for_provider(provider_name: str, is_raster: bool) -> str:
    """Return the conversion route for a layer given its provider name."""
    provider = (provider_name or "").lower()
    if is_raster:
        return ROUTE_FILE if provider in FILE_RASTER_PROVIDERS else ROUTE_REMOTE_RASTER
    return ROUTE_FILE if provider in FILE_VECTOR_PROVIDERS else ROUTE_LIVE_VECTOR


def is_remote_provider(provider_name: str) -> bool:
    """True when the provider is a network service (WFS, WCS, ArcGIS…)."""
    return (provider_name or "").lower() in REMOTE_PROVIDERS


def provider_display_name(provider_name: str) -> str:
    """Short human-friendly name for UI markers ("WFS", "PostGIS", …)."""
    provider = (provider_name or "").lower()
    return PROVIDER_DISPLAY_NAMES.get(provider, provider_name or "?")


def source_label(provider_name: str, layer_name: str, source: str) -> str:
    """
    Readable label used in errors/report for non-file sources, instead
    of a meaningless pseudo-path. E.g. ``"wfs: Comuni (https://host/…)"``.
    """
    provider = (provider_name or "?").lower()
    src = (source or "").strip()
    if len(src) > 120:
        src = src[:117] + "..."
    if src:
        return f"{provider}: {layer_name} ({src})"
    return f"{provider}: {layer_name}"
