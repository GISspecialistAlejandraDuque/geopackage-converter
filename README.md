# GeoPackage Converter

QGIS plugin to batch-convert **vector and raster** files (Shapefile, TAB, KML/KMZ, GML, GeoJSON, DXF, GPX, MIF, ZIP, GeoTIFF, ASC, IMG, ECW, JP2) to **GeoPackage**, with two modes: **From project** and **From folder**.

## Features

- Two conversion modes: from the active QGIS project (preserving symbology, layer order and raster styles) or from a folder (recursive scan with ZIP support via GDAL `/vsizip/`).
- **Vector and raster** conversion in a single workflow.
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
- UI available in Italian, English and Spanish.

## Installation

Download the latest `.zip` from [Releases](https://github.com/GISspecialistAlejandraDuque/geopackage-converter/releases) and install via **Plugins > Manage and Install Plugins > Install from ZIP**.

## Author

**GIS Specialist di Alejandra Duque Ropero**
- Web: [gisspecialist.it](https://gisspecialist.it)
- Email: alejandra.duque@gisspecialist.it

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
