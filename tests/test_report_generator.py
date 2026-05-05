"""Tests for `core.report_generator`."""

from __future__ import annotations

from pathlib import Path

from geopackage_converter.core.converter import ConversionResult
from geopackage_converter.core.report_generator import generate_html_report


def _result(**kwargs) -> ConversionResult:
    r = ConversionResult()
    for k, v in kwargs.items():
        setattr(r, k, v)
    return r


def test_writes_file_at_given_path(tmp_path):
    out = tmp_path / "sub" / "report.html"
    written = generate_html_report(_result(), out)
    assert written == out.resolve()
    assert out.is_file()
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_summary_counts_rendered(tmp_path):
    r = _result(
        success_count=7,
        error_count=2,
        warnings=["a", "b", "c"],
    )
    out = generate_html_report(r, tmp_path / "r.html")
    text = out.read_text(encoding="utf-8")
    assert ">7<" in text  # success
    assert ">2<" in text  # errors
    assert ">3<" in text  # warnings count
    assert ">9<" in text  # total = success + error


def test_output_files_listed(tmp_path):
    r = _result(output_files=[tmp_path / "a.gpkg", tmp_path / "b.gpkg"])
    text = generate_html_report(r, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "a.gpkg" in text
    assert "b.gpkg" in text


def test_no_output_files_shows_empty_message(tmp_path):
    text = generate_html_report(_result(), tmp_path / "r.html").read_text(encoding="utf-8")
    assert "Nessun file generato" in text


def test_errors_table_rendered(tmp_path):
    r = _result(
        error_count=1,
        errors=[{"source": "/data/broken.shp", "message": "GDAL boom"}],
    )
    text = generate_html_report(r, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "/data/broken.shp" in text
    assert "GDAL boom" in text


def test_html_escaping_prevents_injection(tmp_path):
    r = _result(
        error_count=1,
        errors=[{"source": "<script>alert(1)</script>", "message": "x & y"}],
        warnings=["<b>bold</b>"],
    )
    text = generate_html_report(r, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text
    assert "x &amp; y" in text
    assert "<b>bold</b>" not in text
    assert "&lt;b&gt;bold" in text


def test_duration_formatting(tmp_path):
    cases = [
        (0.123, "123 ms"),
        (5.0, "5s"),
        (75.0, "1m 15s"),
        (3725.0, "1h 2m 5s"),
    ]
    for seconds, expected in cases:
        text = generate_html_report(
            _result(duration_seconds=seconds), tmp_path / f"r{seconds}.html"
        ).read_text(encoding="utf-8")
        assert expected in text, f"missing {expected!r} for {seconds}s"


def test_dry_run_marked_in_title(tmp_path):
    text = generate_html_report(
        _result(dry_run=True), tmp_path / "r.html"
    ).read_text(encoding="utf-8")
    assert "dry-run" in text


def test_creates_parent_directory(tmp_path):
    out = tmp_path / "deeply" / "nested" / "r.html"
    generate_html_report(_result(), out)
    assert out.is_file()


def test_no_unreplaced_tokens(tmp_path):
    """Every {{TOKEN}} in the template must be substituted."""
    r = _result(
        success_count=1,
        error_count=1,
        warnings=["w"],
        errors=[{"source": "s", "message": "m"}],
        output_files=[Path("/tmp/x.gpkg")],
        duration_seconds=2.0,
    )
    text = generate_html_report(r, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "{{" not in text
    assert "}}" not in text
