"""Tests for `core.converter`. Mocks `_write_layer` so QGIS is not required."""

from __future__ import annotations

from pathlib import Path

import pytest

from geopackage_converter.core.converter import ConversionResult, Converter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _real_file(tmp_path: Path, name: str = "src.shp") -> Path:
    """Create a non-empty file so `Path.exists()` succeeds in the converter."""
    p = tmp_path / name
    p.write_bytes(b"\x00" * 32)
    return p


def _item(path: Path, name: str = "layer", **extra) -> dict:
    base = {"path": path, "name": name, "encoding": "UTF-8"}
    base.update(extra)
    return base


@pytest.fixture
def fake_writer(monkeypatch):
    """Replace `_write_layer` with a recorder that always succeeds."""
    calls = []

    def fake(self, source_path, layer_name, output_path, encoding, style_xml=None):
        calls.append(
            {
                "source_path": source_path,
                "layer_name": layer_name,
                "output_path": output_path,
                "encoding": encoding,
                "style_xml": style_xml,
                "target_crs": self.target_crs,
                "save_styles": self.save_styles,
                "validate_geometries": self.validate_geometries,
            }
        )
        return None

    monkeypatch.setattr(Converter, "_write_layer", fake)
    return calls


# ---------------------------------------------------------------------------
# ConversionResult
# ---------------------------------------------------------------------------


def test_result_default_values():
    r = ConversionResult()
    assert r.success_count == 0
    assert r.error_count == 0
    assert r.errors == []
    assert r.warnings == []
    assert r.output_files == []
    assert r.duration_seconds == 0.0
    assert r.dry_run is False


def test_result_add_success_dedupes_output_files(tmp_path):
    r = ConversionResult()
    r.add_success(tmp_path / "a.gpkg")
    r.add_success(tmp_path / "a.gpkg")
    assert r.success_count == 2
    assert r.output_files == [tmp_path / "a.gpkg"]


def test_result_add_error_records_source_and_message():
    r = ConversionResult()
    r.add_error("foo.shp", "boom")
    assert r.error_count == 1
    assert r.errors == [{"source": "foo.shp", "message": "boom"}]


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def test_convert_none_items_raises(tmp_path):
    with pytest.raises(Exception):
        Converter().convert(None, tmp_path / "out.gpkg")  # type: ignore[arg-type]


def test_convert_empty_items_returns_warning(tmp_path):
    r = Converter().convert([], tmp_path / "out.gpkg")
    assert r.success_count == 0
    assert r.error_count == 0
    assert any("No items" in w for w in r.warnings)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_convert_writes_each_item(tmp_path, fake_writer):
    src1 = _real_file(tmp_path, "a.shp")
    src2 = _real_file(tmp_path, "b.shp")
    out = tmp_path / "out" / "bundle.gpkg"
    r = Converter().convert([_item(src1, "a"), _item(src2, "b")], out)

    assert r.success_count == 2
    assert r.error_count == 0
    assert r.output_files == [out]
    assert out.parent.exists()  # converter created the directory
    assert [c["layer_name"] for c in fake_writer] == ["a", "b"]
    assert all(c["output_path"] == out for c in fake_writer)


def test_convert_passes_options_through(tmp_path, fake_writer):
    src = _real_file(tmp_path)
    Converter(
        target_crs="EPSG:32632",
        save_styles=False,
        validate_geometries=True,
    ).convert([_item(src)], tmp_path / "out.gpkg")
    assert fake_writer[0]["target_crs"] == "EPSG:32632"
    assert fake_writer[0]["save_styles"] is False
    assert fake_writer[0]["validate_geometries"] is True


def test_convert_uses_item_encoding(tmp_path, fake_writer):
    src = _real_file(tmp_path)
    Converter().convert([_item(src, encoding="Windows-1252")], tmp_path / "out.gpkg")
    assert fake_writer[0]["encoding"] == "Windows-1252"


def test_convert_default_encoding_when_missing(tmp_path, fake_writer):
    src = _real_file(tmp_path)
    item = {"path": src, "name": "x"}  # no encoding key
    Converter().convert([item], tmp_path / "out.gpkg")
    assert fake_writer[0]["encoding"] == "UTF-8"


# ---------------------------------------------------------------------------
# Error handling — must never abort the batch
# ---------------------------------------------------------------------------


def test_missing_source_records_error(tmp_path, fake_writer):
    good = _real_file(tmp_path, "good.shp")
    missing = tmp_path / "missing.shp"
    r = Converter().convert(
        [_item(missing, "missing"), _item(good, "good")],
        tmp_path / "out.gpkg",
    )
    assert r.success_count == 1
    assert r.error_count == 1
    assert "does not exist" in r.errors[0]["message"]


def test_writer_error_message_recorded(tmp_path, monkeypatch):
    src = _real_file(tmp_path)
    monkeypatch.setattr(
        Converter, "_write_layer", lambda *a, **kw: "GDAL exploded"
    )
    r = Converter().convert([_item(src)], tmp_path / "out.gpkg")
    assert r.success_count == 0
    assert r.error_count == 1
    assert "GDAL exploded" in r.errors[0]["message"]


def test_writer_unexpected_exception_caught(tmp_path, monkeypatch):
    src = _real_file(tmp_path)

    def boom(*a, **kw):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(Converter, "_write_layer", boom)
    r = Converter().convert([_item(src)], tmp_path / "out.gpkg")
    assert r.error_count == 1
    assert "disk on fire" in r.errors[0]["message"]


def test_one_failure_does_not_stop_batch(tmp_path, monkeypatch):
    src1 = _real_file(tmp_path, "a.shp")
    src2 = _real_file(tmp_path, "b.shp")
    src3 = _real_file(tmp_path, "c.shp")

    def selective(self, source_path, layer_name, output_path, encoding, style_xml=None):
        return "nope" if layer_name == "b" else None

    monkeypatch.setattr(Converter, "_write_layer", selective)
    r = Converter().convert(
        [_item(src1, "a"), _item(src2, "b"), _item(src3, "c")],
        tmp_path / "out.gpkg",
    )
    assert r.success_count == 2
    assert r.error_count == 1


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_dry_run_does_not_invoke_writer(tmp_path, monkeypatch):
    src = _real_file(tmp_path)

    def must_not_run(*a, **kw):
        raise AssertionError("writer must not be called in dry-run")

    monkeypatch.setattr(Converter, "_write_layer", must_not_run)
    r = Converter(dry_run=True).convert([_item(src)], tmp_path / "out.gpkg")
    assert r.dry_run is True
    assert r.success_count == 1
    assert any("dry-run" in w for w in r.warnings)


def test_dry_run_does_not_create_output_dir(tmp_path):
    src = _real_file(tmp_path)
    out_dir = tmp_path / "should_not_exist"
    Converter(dry_run=True).convert([_item(src)], out_dir / "out.gpkg")
    assert not out_dir.exists()


# ---------------------------------------------------------------------------
# Progress callback
# ---------------------------------------------------------------------------


def test_progress_callback_called_per_item_and_at_end(tmp_path, fake_writer):
    calls = []

    def cb(pct, msg):
        calls.append((pct, msg))

    src1 = _real_file(tmp_path, "a.shp")
    src2 = _real_file(tmp_path, "b.shp")
    Converter().convert(
        [_item(src1, "a"), _item(src2, "b")],
        tmp_path / "out.gpkg",
        progress_callback=cb,
    )
    assert calls[0] == (0, "Converting a")
    assert calls[1] == (50, "Converting b")
    assert calls[-1] == (100, "Done")


def test_progress_callback_exception_is_swallowed(tmp_path, fake_writer):
    src = _real_file(tmp_path)

    def bad_cb(pct, msg):
        raise RuntimeError("UI thread died")

    r = Converter().convert([_item(src)], tmp_path / "out.gpkg", progress_callback=bad_cb)
    assert r.success_count == 1


# ---------------------------------------------------------------------------
# Duration is populated
# ---------------------------------------------------------------------------


def test_virtual_source_skips_exists_check(tmp_path, fake_writer):
    """Items with is_virtual or /vsizip/ paths must NOT trigger 'does not exist'."""
    item = {
        "path": Path("/vsizip/whatever.zip/inner.shp"),
        "uri": "/vsizip/whatever.zip/inner.shp",
        "name": "inner",
        "is_virtual": True,
    }
    r = Converter().convert([item], tmp_path / "out.gpkg")
    assert r.success_count == 1
    assert r.error_count == 0
    assert fake_writer[0]["source_path"] == "/vsizip/whatever.zip/inner.shp"


def test_duration_recorded(tmp_path, fake_writer):
    src = _real_file(tmp_path)
    r = Converter().convert([_item(src)], tmp_path / "out.gpkg")
    assert r.duration_seconds >= 0.0
