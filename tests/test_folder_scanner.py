"""Tests for `core.folder_scanner`."""

from __future__ import annotations

from pathlib import Path

import pytest

from geopackage_converter.core import folder_scanner
from geopackage_converter.core.folder_scanner import SUPPORTED_EXTENSIONS, scan_folder

# ---------------------------------------------------------------------------
# Fake QGIS inspection: keeps tests independent from a running QGIS instance.
# ---------------------------------------------------------------------------


def _fake_inspector(geometry: str = "Polygon", crs: str = "EPSG:4326", n: int = 3):
    """Return a stub for `_inspect_with_qgis` with predictable output."""

    def inspect(path: Path):
        return {
            "geometry_type": geometry,
            "crs": crs,
            "feature_count": n,
            "warnings": [],
        }

    return inspect


@pytest.fixture(autouse=True)
def _stub_qgis_inspector(monkeypatch):
    """By default, every test gets a no-warnings stub. Override per test as needed."""
    monkeypatch.setattr(folder_scanner, "_inspect_with_qgis", _fake_inspector())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _touch(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ---------------------------------------------------------------------------
# Path / directory handling
# ---------------------------------------------------------------------------


def test_missing_path_returns_empty(tmp_path):
    assert scan_folder(tmp_path / "nope") == []


def test_path_is_file_raises(tmp_path):
    f = _touch(tmp_path / "a.txt")
    with pytest.raises(NotADirectoryError):
        scan_folder(f)


def test_empty_folder_returns_empty(tmp_path):
    assert scan_folder(tmp_path) == []


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


def test_recognises_all_supported_extensions(tmp_path):
    expected = []
    for ext, fmt in SUPPORTED_EXTENSIONS.items():
        _touch(tmp_path / f"file{ext}")
        expected.append(fmt)
    results = scan_folder(tmp_path, recursive=False)
    assert sorted(r["format"] for r in results) == sorted(expected)


def test_ignores_unknown_extensions(tmp_path):
    _touch(tmp_path / "doc.txt")
    _touch(tmp_path / "img.png")
    _touch(tmp_path / "data.geojson")
    results = scan_folder(tmp_path, recursive=False)
    assert len(results) == 1
    assert results[0]["format"] == "geojson"


def test_extension_case_insensitive(tmp_path):
    _touch(tmp_path / "A.SHP")
    _touch(tmp_path / "B.GeoJSON")
    results = scan_folder(tmp_path, recursive=False)
    assert {r["format"] for r in results} == {"shp", "geojson"}


# ---------------------------------------------------------------------------
# Recursion
# ---------------------------------------------------------------------------


def test_recursive_descends_subfolders(tmp_path):
    _touch(tmp_path / "top.shp")
    _touch(tmp_path / "sub" / "nested.geojson")
    _touch(tmp_path / "sub" / "deep" / "more.kml")
    results = scan_folder(tmp_path, recursive=True)
    assert {r["name"] for r in results} == {"top", "nested", "more"}


def test_non_recursive_stays_at_top_level(tmp_path):
    _touch(tmp_path / "top.shp")
    _touch(tmp_path / "sub" / "nested.geojson")
    results = scan_folder(tmp_path, recursive=False)
    assert {r["name"] for r in results} == {"top"}


# ---------------------------------------------------------------------------
# Result shape and content
# ---------------------------------------------------------------------------


def test_result_has_all_required_keys(tmp_path):
    _touch(tmp_path / "a.shp")
    _touch(tmp_path / "a.dbf", b"\x00" * 32)
    [item] = scan_folder(tmp_path, recursive=False)
    assert {"path", "format", "name", "geometry_type", "crs", "feature_count",
            "encoding", "warnings", "subfolder"} <= set(item.keys())
    assert isinstance(item["path"], Path)
    assert item["name"] == "a"
    assert item["format"] == "shp"


def test_results_sorted_deterministically(tmp_path):
    for n in ["zeta", "alpha", "mike"]:
        _touch(tmp_path / f"{n}.geojson")
    names = [r["name"] for r in scan_folder(tmp_path, recursive=False)]
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# Encoding handling
# ---------------------------------------------------------------------------


def test_geojson_encoding_shortcircuits_to_utf8(tmp_path, monkeypatch):
    """JSON/XML formats must not even invoke the chardet path."""
    called = {"n": 0}

    def boom(_):
        called["n"] += 1
        raise RuntimeError("should not be called")

    monkeypatch.setattr(folder_scanner, "detect_encoding", boom)
    _touch(tmp_path / "x.geojson", b'{"type":"FeatureCollection"}')
    [item] = scan_folder(tmp_path, recursive=False)
    assert item["encoding"] == "UTF-8"
    assert called["n"] == 0


def test_shapefile_uses_encoding_detector(tmp_path, monkeypatch):
    monkeypatch.setattr(folder_scanner, "detect_encoding", lambda p: "Windows-1252")
    _touch(tmp_path / "x.shp")
    [item] = scan_folder(tmp_path, recursive=False)
    assert item["encoding"] == "Windows-1252"


def test_encoding_failure_falls_back_with_warning(tmp_path, monkeypatch):
    def explode(_):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(folder_scanner, "detect_encoding", explode)
    _touch(tmp_path / "x.shp")
    [item] = scan_folder(tmp_path, recursive=False)
    assert item["encoding"] == "UTF-8"
    assert any("Encoding detection failed" in w for w in item["warnings"])


# ---------------------------------------------------------------------------
# Warnings propagation from inspector
# ---------------------------------------------------------------------------


def _make_zip(zip_path, entries):
    """Create a ZIP at `zip_path` containing the given (name, bytes) pairs."""
    import zipfile
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return zip_path


def test_zip_expanded_into_virtual_items(tmp_path):
    _make_zip(tmp_path / "data.zip", [
        ("roads/main.shp", b"\x00" * 16),
        ("roads/main.dbf", b"\x00" * 16),
        ("buildings.geojson", b'{"type":"FeatureCollection"}'),
        ("readme.txt", b"ignore me"),
    ])
    results = scan_folder(tmp_path, recursive=False)
    # Layer names are prefixed with the zip stem so siblings in the
    # same target gpkg never collide.
    names = sorted(r["name"] for r in results)
    assert names == ["data__buildings", "data__main"]
    for r in results:
        assert r.get("is_virtual") is True
        assert r["uri"].startswith("/vsizip/")
        assert r["uri"].endswith((".shp", ".geojson"))
        # Subfolder = parent dir of the zip (so multiple zips in the
        # same folder go into a single output GeoPackage).
        assert r.get("subfolder") == tmp_path.name


def test_flatten_hierarchy_full_relative_path(tmp_path):
    """flatten_hierarchy=True must encode the deep path in the subfolder field."""
    _touch(tmp_path / "A" / "B" / "C" / "deep.shp")
    _touch(tmp_path / "A" / "shallow.shp")

    flat_off = scan_folder(tmp_path, flatten_hierarchy=False)
    by_name_off = {r["name"]: r["subfolder"] for r in flat_off}
    assert by_name_off["deep"] == "C"
    assert by_name_off["shallow"] == "A"

    flat_on = scan_folder(tmp_path, flatten_hierarchy=True)
    by_name_on = {r["name"]: r["subfolder"] for r in flat_on}
    assert by_name_on["deep"] == "A__B__C"
    assert by_name_on["shallow"] == "A"


def test_mirror_hierarchy_uses_forward_slashes(tmp_path):
    """mirror_hierarchy=True encodes the relative path with `/` separators."""
    _touch(tmp_path / "A" / "B" / "deep.shp")
    _touch(tmp_path / "A" / "shallow.shp")

    results = scan_folder(tmp_path, mirror_hierarchy=True)
    by_name = {r["name"]: r["subfolder"] for r in results}
    assert by_name["deep"] == "A/B"
    assert by_name["shallow"] == "A"


def test_recursive_with_special_chars_in_path(tmp_path):
    """Regression: pathlib.rglob fails on '°', os.walk does not."""
    nested = tmp_path / "Tutele (n° 422004)" / "deep"
    nested.mkdir(parents=True)
    _touch(nested / "x.shp")
    _touch(tmp_path / "y.shp")
    results = scan_folder(tmp_path, recursive=True)
    assert {r["name"] for r in results} == {"x", "y"}


def test_zip_corrupt_yields_warning(tmp_path):
    bad = tmp_path / "broken.zip"
    bad.write_bytes(b"this is not a zip")
    results = scan_folder(tmp_path, recursive=False)
    assert len(results) == 1
    assert results[0]["format"] == "zip"
    assert any("Cannot open ZIP" in w for w in results[0]["warnings"])


def test_zip_and_regular_files_coexist(tmp_path):
    _make_zip(tmp_path / "archive.zip", [("inner.shp", b"x")])
    _touch(tmp_path / "loose.geojson")
    results = scan_folder(tmp_path, recursive=False)
    names = sorted(r["name"] for r in results)
    assert names == ["archive__inner", "loose"]
    virt = [r for r in results if r["name"] == "archive__inner"][0]
    real = [r for r in results if r["name"] == "loose"][0]
    assert virt["is_virtual"] is True
    assert real.get("is_virtual") is None or real.get("is_virtual") is False


def test_inspector_warnings_appear_in_result(tmp_path, monkeypatch):
    def inspector(_):
        return {
            "geometry_type": "Unknown",
            "crs": "Unknown",
            "feature_count": 0,
            "warnings": ["CRS not recognised"],
        }

    monkeypatch.setattr(folder_scanner, "_inspect_with_qgis", inspector)
    _touch(tmp_path / "x.geojson")
    [item] = scan_folder(tmp_path, recursive=False)
    assert "CRS not recognised" in item["warnings"]


# ---------------------------------------------------------------------------
# RAR archives (/vsirar/). zipfile can't make .rar, so we mock the two
# isolated seams: rar_supported() and _list_rar_members().
# ---------------------------------------------------------------------------


def _enable_rar(monkeypatch, members):
    monkeypatch.setattr(folder_scanner, "rar_supported", lambda: True)
    monkeypatch.setattr(folder_scanner, "_list_rar_members", lambda p: list(members))


def test_rar_expanded_into_virtual_items(tmp_path, monkeypatch):
    _touch(tmp_path / "data.rar")
    _enable_rar(monkeypatch, ["roads/main.shp", "roads/main.dbf", "readme.txt"])
    results = scan_folder(tmp_path, recursive=False)
    assert [r["name"] for r in results] == ["data__main"]
    r = results[0]
    assert r["is_virtual"] is True
    assert r["archive_kind"] == "rar"
    assert r["uri"].startswith("/vsirar/")
    assert r["uri"].endswith(".shp")
    assert r["subfolder"] == tmp_path.name


def test_rar_unsupported_yields_capability_warning(tmp_path, monkeypatch):
    _touch(tmp_path / "data.rar")
    monkeypatch.setattr(folder_scanner, "rar_supported", lambda: False)
    results = scan_folder(tmp_path, recursive=False)
    assert len(results) == 1
    assert results[0]["is_unreadable"] is True
    assert results[0]["format"] == "rar"
    assert any("RAR" in w for w in results[0]["warnings"])


def test_rar_open_failure_yields_warning(tmp_path, monkeypatch):
    _touch(tmp_path / "data.rar")
    monkeypatch.setattr(folder_scanner, "rar_supported", lambda: True)

    def boom(_):
        raise RuntimeError("libarchive error")

    monkeypatch.setattr(folder_scanner, "_list_rar_members", boom)
    results = scan_folder(tmp_path, recursive=False)
    assert len(results) == 1
    assert any("Cannot open RAR" in w for w in results[0]["warnings"])


def test_rar_name_prefixing_matches_stem(tmp_path, monkeypatch):
    # When the inner file stem matches the archive stem, no "__" prefix.
    _touch(tmp_path / "comuni.rar")
    _enable_rar(monkeypatch, ["comuni.shp"])
    [r] = scan_folder(tmp_path, recursive=False)
    assert r["name"] == "comuni"


def test_rar_and_zip_and_loose_coexist(tmp_path, monkeypatch):
    _make_zip(tmp_path / "z.zip", [("inner.shp", b"x")])
    _touch(tmp_path / "r.rar")
    _touch(tmp_path / "loose.geojson")
    _enable_rar(monkeypatch, ["layer.shp"])
    results = scan_folder(tmp_path, recursive=False)
    by_name = {r["name"]: r for r in results}
    assert set(by_name) == {"z__inner", "r__layer", "loose"}
    assert by_name["z__inner"]["archive_kind"] == "zip"
    assert by_name["r__layer"]["archive_kind"] == "rar"


def test_rar_mirror_hierarchy_subfolder(tmp_path, monkeypatch):
    _touch(tmp_path / "A" / "B" / "data.rar")
    _enable_rar(monkeypatch, ["x.shp"])
    results = scan_folder(tmp_path, mirror_hierarchy=True)
    assert results[0]["subfolder"] == "A/B"


def test_rar_supported_cached(monkeypatch):
    folder_scanner._reset_rar_support_cache()
    calls = []

    def fake_prefixes():
        calls.append(1)
        return {"/vsirar/", "/vsizip/"}

    monkeypatch.setattr(folder_scanner, "_gdal_vsi_prefixes", fake_prefixes)
    assert folder_scanner.rar_supported() is True
    assert folder_scanner.rar_supported() is True
    assert len(calls) == 1  # probed once, then cached
    folder_scanner._reset_rar_support_cache()
