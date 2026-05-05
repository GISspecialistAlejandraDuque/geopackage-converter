@echo off
REM ----------------------------------------------------------------
REM  Build translations for GeoPackage Converter.
REM
REM  Run from the OSGeo4W shell (so pylupdate6 is on PATH).
REM  For .qm compilation you need either:
REM    - lrelease.exe from Qt SDK, OR
REM    - "pip install pyside6-tools" then pyside6-lrelease.
REM
REM  Usage from plugin root:
REM      cd geopackage_converter\i18n
REM      build_translations.bat
REM ----------------------------------------------------------------
setlocal enabledelayedexpansion
pushd %~dp0..

set SOURCES=plugin.py compat.py
for /r gui %%f in (*.py *.ui) do set SOURCES=!SOURCES! %%f
for /r core %%f in (*.py)      do set SOURCES=!SOURCES! %%f
for /r processing %%f in (*.py) do set SOURCES=!SOURCES! %%f

echo === Updating .ts files (pylupdate6) ===
for %%L in (it en es) do (
  pylupdate6 !SOURCES! -ts i18n\geopackage_converter_%%L.ts
  if errorlevel 1 goto :err
)

echo.
echo === Compiling .qm files ===
where lrelease >nul 2>&1
if !errorlevel! equ 0 (
  for %%L in (it en es) do lrelease i18n\geopackage_converter_%%L.ts
  goto :done
)
where pyside6-lrelease >nul 2>&1
if !errorlevel! equ 0 (
  for %%L in (it en es) do pyside6-lrelease i18n\geopackage_converter_%%L.ts
  goto :done
)
echo WARNING: neither 'lrelease' nor 'pyside6-lrelease' was found on PATH.
echo          Open each .ts in Qt Linguist (linguist.exe) and use File ^> Release.
echo          Or run: pip install pyside6-tools

:done
echo Done.
popd
exit /b 0

:err
echo BUILD FAILED.
popd
exit /b 1
