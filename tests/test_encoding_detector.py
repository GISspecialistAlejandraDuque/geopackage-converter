"""Tests for `core.encoding_detector`."""

from __future__ import annotations

from pathlib import Path

import pytest

from geopackage_converter.core.encoding_detector import (
    DEFAULT_ENCODING,
    detect_encoding,
)
from geopackage_converter.core.exceptions import EncodingDetectionError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_shapefile_stub(tmp_path: Path, name: str = "layer") -> Path:
    """
    Create an empty .shp + .dbf pair so the detector has something
    to look at. Content does not matter; the detector only sniffs bytes.
    """
    shp = tmp_path / f"{name}.shp"
    dbf = tmp_path / f"{name}.dbf"
    shp.write_bytes(b"\x00" * 100)
    # DBF with Windows-1252-specific bytes (smart quotes, euro sign,
    # bullet) plus accented Latin text. These are *invalid* as UTF-8,
    # which forces chardet away from the default UTF-8 guess.
    payload = "Citt\xe0 perch\xe9 € “Test” • \xe8\xec\xf2\xf9"
    dbf.write_bytes(payload.encode("cp1252") * 500)
    return shp


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", None])
def test_empty_input_raises(bad):
    with pytest.raises(EncodingDetectionError):
        detect_encoding(bad)


def test_missing_file_falls_back_to_utf8(tmp_path):
    assert detect_encoding(tmp_path / "does_not_exist.shp") == DEFAULT_ENCODING


# ---------------------------------------------------------------------------
# CPG sidecar
# ---------------------------------------------------------------------------


def test_cpg_with_named_encoding(tmp_path):
    shp = _make_shapefile_stub(tmp_path)
    (tmp_path / "layer.cpg").write_text("UTF-8", encoding="ascii")
    assert detect_encoding(shp) == "UTF-8"


def test_cpg_with_numeric_codepage(tmp_path):
    shp = _make_shapefile_stub(tmp_path)
    (tmp_path / "layer.cpg").write_text("1252", encoding="ascii")
    assert detect_encoding(shp) == "Windows-1252"


def test_cpg_with_latin1_alias(tmp_path):
    shp = _make_shapefile_stub(tmp_path)
    (tmp_path / "layer.cpg").write_text("latin1", encoding="ascii")
    assert detect_encoding(shp) == "ISO-8859-1"


def test_cpg_uppercase_extension(tmp_path):
    shp = _make_shapefile_stub(tmp_path)
    (tmp_path / "layer.CPG").write_text("UTF-8", encoding="ascii")
    assert detect_encoding(shp) == "UTF-8"


def test_cpg_empty_file_falls_through(tmp_path):
    shp = _make_shapefile_stub(tmp_path)
    (tmp_path / "layer.cpg").write_text("", encoding="ascii")
    # Empty CPG -> fall through to chardet/fallback. Either way must
    # return a non-empty canonical label.
    result = detect_encoding(shp)
    assert isinstance(result, str) and result


def test_cpg_takes_precedence_over_chardet(tmp_path):
    """A .cpg saying UTF-8 must win even if the DBF bytes look like CP1252."""
    shp = _make_shapefile_stub(tmp_path)  # DBF written as cp1252
    (tmp_path / "layer.cpg").write_text("UTF-8", encoding="ascii")
    assert detect_encoding(shp) == "UTF-8"


# ---------------------------------------------------------------------------
# chardet path (skipped automatically when chardet isn't installed)
# ---------------------------------------------------------------------------


def _has_chardet() -> bool:
    try:
        import chardet  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(not _has_chardet(), reason="chardet not installed")
def test_chardet_path_normalises_high_confidence_guess(tmp_path, monkeypatch):
    """When chardet returns a confident guess, the detector normalises and uses it."""
    import chardet

    shp = _make_shapefile_stub(tmp_path)
    monkeypatch.setattr(
        chardet, "detect", lambda _b: {"encoding": "cp1252", "confidence": 0.95}
    )
    assert detect_encoding(shp) == "Windows-1252"


@pytest.mark.skipif(not _has_chardet(), reason="chardet not installed")
def test_chardet_low_confidence_falls_back(tmp_path, monkeypatch):
    """Below the confidence floor, the detector ignores chardet and uses UTF-8."""
    import chardet

    shp = _make_shapefile_stub(tmp_path)
    monkeypatch.setattr(
        chardet, "detect", lambda _b: {"encoding": "GB2312", "confidence": 0.10}
    )
    assert detect_encoding(shp) == DEFAULT_ENCODING


@pytest.mark.skipif(not _has_chardet(), reason="chardet not installed")
def test_chardet_probes_dbf_not_shp(tmp_path, monkeypatch):
    """For a .shp source the detector must read the sibling .dbf, not the .shp."""
    import chardet

    shp = _make_shapefile_stub(tmp_path)
    seen = {}

    def fake_detect(buf):
        seen["len"] = len(buf)
        return {"encoding": "latin1", "confidence": 0.99}

    monkeypatch.setattr(chardet, "detect", fake_detect)
    result = detect_encoding(shp)
    assert result == "ISO-8859-1"
    # The .shp stub is 100 bytes of zeros; the .dbf is much larger.
    assert seen["len"] > 100


# ---------------------------------------------------------------------------
# Non-shapefile sources
# ---------------------------------------------------------------------------


def test_geojson_utf8_source(tmp_path):
    src = tmp_path / "data.geojson"
    src.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    # No CPG sidecar; chardet on ASCII content will likely return ascii.
    result = detect_encoding(src)
    assert result in {"UTF-8", "ASCII"}
