"""
Build the QGIS-plugin release ZIP for GeoPackage Converter.

Produces ``geopackage_converter_v<version>.zip`` with a single top-level
``geopackage_converter/`` folder and forward-slash paths (QGIS rejects the
backslash paths that PowerShell's Compress-Archive produces).

Development-only and non-distributable files are excluded so the public
package stays clean and passes the QGIS repository security scan (no
``.bat``/binaries, no ``CLAUDE.md``, no tests, no marketing assets).

Usage (from anywhere):
    python scripts/build_release_zip.py [output_dir]

``output_dir`` defaults to the plugin's parent directory.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent  # .../geopackage_converter
PLUGIN_NAME = PLUGIN_DIR.name  # "geopackage_converter"

# Directories skipped anywhere in the tree.
EXCLUDE_DIRS = {"tests", "__pycache__", ".git", "scripts", ".pytest_cache", ".ruff_cache"}
# Exact filenames skipped.
EXCLUDE_FILES = {
    "CLAUDE.md",
    ".gitignore",
    "requirements-dev.txt",
    "blog_article.docx",
    "blog_article.html",
    "reel_script.txt",
    "plugin_infographic.svg",
    "plugin_infographic.webp",
}
# File suffixes skipped (.bat trips the QGIS repo security scan;
# .ts are translation *sources*, only compiled .qm are shipped).
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".bat", ".ts"}


def _read_version() -> str:
    meta = PLUGIN_DIR / "metadata.txt"
    for line in meta.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("Could not find version= in metadata.txt")


def _should_include(path: Path) -> bool:
    rel_parts = path.relative_to(PLUGIN_DIR).parts
    if any(part in EXCLUDE_DIRS for part in rel_parts[:-1]):
        return False
    if path.name in EXCLUDE_FILES:
        return False
    return path.suffix.lower() not in EXCLUDE_SUFFIXES


def build(output_dir: Path) -> Path:
    version = _read_version()
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{PLUGIN_NAME}_v{version}.zip"

    files = [
        p
        for p in sorted(PLUGIN_DIR.rglob("*"))
        if p.is_file() and _should_include(p)
    ]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            rel = f.relative_to(PLUGIN_DIR).as_posix()  # forward slashes
            arcname = f"{PLUGIN_NAME}/{rel}"
            zf.write(f, arcname)

    _verify(zip_path)
    print(f"Built {zip_path} ({len(files)} files, version {version})")
    return zip_path


def _verify(zip_path: Path) -> None:
    """Sanity-check the produced archive against the packaging rules."""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    problems = []
    if any("\\" in n for n in names):
        problems.append("backslash paths present (QGIS rejects these)")
    if not all(n.startswith(f"{PLUGIN_NAME}/") for n in names):
        problems.append(f"not every entry is under {PLUGIN_NAME}/")
    for banned in ("CLAUDE.md", "/tests/", ".bat", "requirements-dev.txt"):
        if any(banned in n for n in names):
            problems.append(f"contains a file matching '{banned}'")
    if problems:
        raise SystemExit("Release ZIP verification failed:\n  - " + "\n  - ".join(problems))


if __name__ == "__main__":
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else PLUGIN_DIR.parent
    build(out)
