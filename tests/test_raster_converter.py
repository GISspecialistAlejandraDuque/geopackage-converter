"""Tests for `core.raster_converter`.

Mocks the GDAL/QGIS write steps so no QGIS runtime is required.
"""

from __future__ import annotations

import pytest

from geopackage_converter.core.raster_converter import (
    DEFAULT_REMOTE_MAX_PX,
    RasterConverter,
    default_remote_resolution,
    estimate_remote_pixels,
    is_output_huge,
)


# ---------------------------------------------------------------------------
# Pure sizing helpers
# ---------------------------------------------------------------------------


def test_default_remote_resolution_uses_native_when_provider_size_known():
    # 1000 units wide, provider reports 2000 px → 0.5 units/px.
    xres, yres = default_remote_resolution(1000.0, 500.0, 2000, 1000)
    assert xres == pytest.approx(0.5)
    assert yres == pytest.approx(0.5)


def test_default_remote_resolution_caps_long_edge_when_size_unknown():
    xres, yres = default_remote_resolution(8192.0, 4096.0, 0, 0)
    # Long edge (8192) mapped onto DEFAULT_REMOTE_MAX_PX.
    assert xres == pytest.approx(8192.0 / DEFAULT_REMOTE_MAX_PX)
    assert yres == xres


def test_default_remote_resolution_degenerate_extent():
    assert default_remote_resolution(0, 0, 0, 0) == (1.0, 1.0)


def test_estimate_remote_pixels():
    assert estimate_remote_pixels(1000, 500, 1.0, 1.0) == 500_000
    assert estimate_remote_pixels(1000, 500, 0, 1.0) == 0


def test_is_output_huge_threshold():
    assert is_output_huge(300_000_000, 1) is True
    assert is_output_huge(100_000_000, 1) is False
    # Band count multiplies the pixel budget.
    assert is_output_huge(80_000_000, 3) is True


# ---------------------------------------------------------------------------
# convert() dispatch for remote (live) raster items
# ---------------------------------------------------------------------------


class _FakeLayer:
    def isValid(self):
        return True


def test_convert_remote_item_dispatches_to_write_remote(tmp_path, monkeypatch):
    calls = []

    def fake_remote(self, item, raster_table, output_path):
        calls.append((item["name"], raster_table))
        return None

    monkeypatch.setattr(RasterConverter, "_write_remote_raster", fake_remote)

    item = {
        "name": "wcs_dtm",
        "item_type": "raster",
        "layer_ref": _FakeLayer(),
        "is_remote": True,
        "raster_extent": (0, 0, 100, 100),
        "raster_xres": 1.0,
        "raster_yres": 1.0,
    }
    r = RasterConverter().convert([item], tmp_path / "out.gpkg")
    assert r.success_count == 1
    assert r.error_count == 0
    assert calls == [("wcs_dtm", "wcs_dtm")]


def test_convert_remote_item_skips_exists_check(tmp_path, monkeypatch):
    monkeypatch.setattr(
        RasterConverter, "_write_remote_raster", lambda *a, **kw: None
    )
    # No path at all, bogus is fine — layer_ref present.
    item = {"name": "x", "layer_ref": _FakeLayer(), "raster_xres": 1, "raster_yres": 1}
    r = RasterConverter().convert([item], tmp_path / "out.gpkg")
    assert r.error_count == 0


def test_convert_remote_item_errors_use_source_label(tmp_path, monkeypatch):
    monkeypatch.setattr(
        RasterConverter, "_write_remote_raster", lambda *a, **kw: "snapshot failed"
    )
    item = {
        "name": "DTM",
        "layer_ref": _FakeLayer(),
        "source_label": "wcs: DTM (https://example.org/wcs)",
    }
    r = RasterConverter().convert([item], tmp_path / "out.gpkg")
    assert r.error_count == 1
    assert r.errors[0]["source"] == "wcs: DTM (https://example.org/wcs)"


def test_convert_remote_layer_ref_released(tmp_path, monkeypatch):
    monkeypatch.setattr(
        RasterConverter, "_write_remote_raster", lambda *a, **kw: None
    )
    item = {"name": "x", "layer_ref": _FakeLayer()}
    RasterConverter().convert([item], tmp_path / "out.gpkg")
    assert "layer_ref" not in item


def test_convert_remote_aggregate_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(
        RasterConverter, "_write_remote_raster", lambda *a, **kw: None
    )
    items = [
        {"name": "a", "layer_ref": _FakeLayer(), "is_remote": True},
        {"name": "b", "layer_ref": _FakeLayer(), "is_remote": True},
    ]
    r = RasterConverter().convert(items, tmp_path / "out.gpkg")
    assert any("2 remote raster" in w for w in r.warnings)


def test_convert_remote_dry_run_does_not_write(tmp_path, monkeypatch):
    def must_not_run(*a, **kw):
        raise AssertionError("write must not run in dry-run")

    monkeypatch.setattr(RasterConverter, "_write_remote_raster", must_not_run)
    item = {"name": "x", "layer_ref": _FakeLayer()}
    r = RasterConverter(dry_run=True).convert([item], tmp_path / "out.gpkg")
    assert r.success_count == 1
    assert any("dry-run" in w for w in r.warnings)


def test_convert_local_raster_still_uses_write_raster(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        RasterConverter,
        "_write_raster",
        lambda self, source_path, raster_table, output_path: calls.append(source_path) or None,
    )
    src = tmp_path / "dtm.tif"
    src.write_bytes(b"\x00" * 16)
    item = {"name": "dtm", "path": src, "item_type": "raster"}
    r = RasterConverter().convert([item], tmp_path / "out.gpkg")
    assert r.success_count == 1
    assert calls == [str(src)]
