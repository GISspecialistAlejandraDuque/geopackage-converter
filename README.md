# GeoPackage Converter

QGIS plugin to batch-convert **vector and raster** files (Shapefile, TAB, KML/KMZ, GML, GeoJSON, DXF, GPX, MIF, ZIP, RAR, GeoTIFF, ASC, IMG, ECW, JP2) and **remote layers** (WFS, WCS, ArcGIS REST) to **GeoPackage**, with two modes: **From project** and **From folder**.

## Features

- Two conversion modes: from the active QGIS project (preserving symbology, layer order and raster styles) or from a folder (recursive scan with ZIP and RAR support via GDAL `/vsizip/` and `/vsirar/`).
- **Vector and raster** conversion in a single workflow.
- **Remote and non-file layers** (project mode): WFS/OGC API Features, ArcGIS REST FeatureServer, memory, delimited-text/CSV, PostGIS and SpatiaLite (vector); WCS, ArcGIS MapServer and WMS (raster, with editable extent and resolution).
- Raster tiling with configurable format (AUTO/PNG/JPEG/WEBP), tile size and quality.
- Full raster style cloning (renderer, opacity, resampling, brightness/contrast) from the original project layer.
- Project layer tree preservation: converted layers load with the same order, groups and visibility as the original.
- Grouping strategies: all-in-one, per subfolder, per legend group (ungrouped layers get individual files).
- Optional CRS reprojection with native QGIS selector.
- Automatic encoding detection for shapefiles (CPG, chardet, UTF-8 fallback).
- Style preservation inside GeoPackage (`layer_styles` table).
- Geometry validation (`native:fixgeometries`).
- Background execution with progress bar and HTML report (with vector/raster breakdown).
- Processing algorithms for automation and scripting.
- Compatible with QGIS 3.34+ (Qt5) and QGIS 4.0+ (Qt6).
- UI available in Italian, English and Spanish (falls back to English for other locales).

> **Note:** RAR archive support requires a QGIS build whose GDAL (>= 3.7) includes libarchive — available in QGIS 3.44+. On older builds a `.rar` is reported with a clear warning and the rest of the folder is still converted.

## Installation

Download the latest `.zip` from [Releases](https://github.com/GISspecialistAlejandraDuque/geopackage-converter/releases) and install via **Plugins > Manage and Install Plugins > Install from ZIP**.

## Author

**GIS Specialist di Alejandra Duque Ropero**
- Web: [gisspecialist.it](https://gisspecialist.it)
- Email: alejandra.duque@gisspecialist.it

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
