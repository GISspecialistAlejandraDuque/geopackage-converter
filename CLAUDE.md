# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QGIS plugin (v0.2.1) that batch-converts vector and raster files to GeoPackage. Supports QGIS 3.34+ (Qt5) through 4.x (Qt6). UI language is Italian (source), with English and Spanish translations. License: GPL-3.0-or-later.

## Build & Development Commands

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_converter.py

# Run with coverage
pytest --cov=core --cov-report=term-missing

# Lint
ruff check .

# Format
black .

# Build translation .qm files (Windows)
i18n\build_translations.bat
```

**Dependencies**: `pip install -r requirements-dev.txt` (pytest, pytest-qt, pytest-cov, ruff, black)

## Two-Directory Sync

QGIS loads the plugin from its profile directory, NOT this repo:
- **DEV** (this repo): `Desarrollo/PluginIA/geopackage_converter/`
- **INSTALLED** (what QGIS loads): `%APPDATA%/QGIS/QGIS4/profiles/default/python/plugins/geopackage_converter/`

After editing code here, changes must be synced to the INSTALLED path (or the plugin repackaged as ZIP). Clear `__pycache__` and `sys.modules` entries before reloading in QGIS.

## Architecture

```
__init__.py          → classFactory() entry point
plugin.py            → GeoPackageConverterPlugin (toolbar, menu, action)
compat.py            → Qt5/Qt6 shim (QAction import, enum aliases, exec_dialog)

core/
  converter.py       → Converter: vector → GPKG via QgsVectorFileWriter
  raster_converter.py→ RasterConverter: raster → GPKG tiles via gdal.Translate
  folder_scanner.py  → Recursive FS scan (vector + raster formats, ZIP via /vsizip/)
  grouping_strategies.py → Bundling: all-in-one, per-subfolder, per-legend-group
  report_generator.py→ HTML report from ConversionResult
  encoding_detector.py, crs_presets.py, exceptions.py, _paths.py

gui/
  main_dialog.py     → GeoPackageConverterDialog (QDialog)
                        _ConversionTask (QgsTask for background execution)
                        Layer tree snapshot/restore for project mode

processing/
  provider.py        → QgsProcessingProvider registration
  _common.py         → Shared grouping constants and apply_grouping()
  alg_from_folder.py → Processing algorithm: folder mode
  alg_from_project.py→ Processing algorithm: project mode
```

## Key Design Patterns

- **Qt5/Qt6 compatibility**: All differences are in `compat.py`. Import from there, never branch on Qt version elsewhere.
- **Error accumulation**: `Converter.convert()` never raises on per-item failures. Errors are collected in `ConversionResult.errors`. Check `result.error_count`.
- **Lazy QGIS imports in core/**: Core modules isolate QGIS imports inside functions (not at module top) so `pytest` can run without a QGIS runtime. Tests in `tests/` monkeypatch QGIS-dependent calls.
- **Raster style limitation**: GeoPackage cannot store raster styles (GDAL limitation). In project mode, the plugin clones the full style from the original layer via `exportNamedStyle`/`importNamedStyle` after loading the converted raster.
- **Tree snapshot**: In project mode, `_snapshot_layer_tree()` captures layer order/groups/visibility before conversion. `_add_layers_from_snapshot()` replays it when loading converted layers. The snapshot must be cleared when switching to folder mode.
- **ConversionResult.output_layers**: List of `(gpkg_path, layer_name)` tuples. Only populated when `layer_name` is non-empty in `add_success()`.

## Packaging for QGIS Plugin Repository

ZIP must have a top-level `geopackage_converter/` folder, use forward slashes (not backslashes), and exclude: `tests/`, `__pycache__/`, `.git/`, `requirements-dev.txt`, `build_translations.bat`, marketing files. Use Python's `zipfile` module (PowerShell's `Compress-Archive` produces backslash paths that QGIS rejects).

## QGIS Official Plugin Requirements

All code changes must comply with the official QGIS plugin repository rules (https://plugins.qgis.org/docs/publish). Key requirements:

### Mandatory
- **License**: GPL-2.0-compatible (this plugin uses GPL-3.0-or-later).
- **metadata.txt**: Must contain valid `homepage`, `repository`, `tracker`, `author`, `email`, `description`, `about`, `version`, `tags`. All links must be publicly accessible.
- **README** and **LICENSE** files must be present in the repository.
- **No binaries** in the plugin package (`.exe`, `.dll`, `.so`, `.bat` etc. are flagged as security issues).
- **Package size** must not exceed 25 MB.
- **Cross-platform**: Must work on Windows, Linux, and macOS.
- **Code comments in English**.
- **PEP 8** and Python/QGIS coding guidelines compliance.
- **Short English description** required even if the UI is in another language.

### Security Checks (QEP 409, 2026)
- All uploaded versions are scanned automatically. Executable or binary files (`.bat`, `.exe`, `.dll`) trigger a **"Potential security issue"** warning badge visible on the public plugin page. Avoid including any such files in the ZIP.
- No generated files (`ui_*.py`, `resources_rc.py`), no hidden directories (`.git`, `__pycache__`, `__MACOSX`).

### Naming Rules
- Plugin folder name: only ASCII letters, digits, underscore `_`, and hyphen `-`. Cannot start with a digit.
- Do not include the word "plugin" in the folder name or title.
- Do not rename the plugin title between version upgrades.

### Metadata Best Practices
- Declare external dependencies clearly in the `about` field.
- Use `QgsNetworkAccessManager` for network operations (not `urllib` or `requests`).
- Use QGIS native widgets (`QgsMapLayerComboBox`, `QgsProjectionSelectionWidget`, etc.) for UI consistency.
- `experimental=True/False` must reflect the actual stability status.
