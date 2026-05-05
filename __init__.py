# GeoPackage Converter - QGIS plugin
# classFactory will be implemented in Phase 11.


def classFactory(iface):  # noqa: N802 (QGIS-required name)
    """Entry point for QGIS plugin loader. Implemented in Phase 11."""
    from .plugin import GeoPackageConverterPlugin
    return GeoPackageConverterPlugin(iface)
