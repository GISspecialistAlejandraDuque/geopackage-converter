# GeoPackage Converter

QGIS plugin to batch-convert vector files (Shapefile, TAB, KML/KMZ, GML, GeoJSON, DXF, GPX, MIF, ZIP) to **GeoPackage**, with two modes: **From project** and **From folder**.

## Features

- Two conversion modes: from the active QGIS project (preserving symbology) or from a folder (recursive scan with ZIP support via GDAL `/vsizip/`).
- Multi-format input, GeoPackage output.
- Grouping strategies: all-in-one, per subfolder, per legend group, mirror folder structure.
- Optional CRS reprojection with native QGIS selector.
- Automatic encoding detection for shapefiles (CPG, chardet, UTF-8 fallback).
- Style preservation inside GeoPackage (`layer_styles` table).
- Geometry validation (`native:fixgeometries`).
- Background execution with progress bar and HTML report.
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
