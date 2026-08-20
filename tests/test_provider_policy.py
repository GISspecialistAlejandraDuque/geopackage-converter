"""Tests for the provider routing policy (pure Python, no QGIS)."""

from __future__ import annotations

import pytest

from geopackage_converter.core.provider_policy import (
    ROUTE_FILE,
    ROUTE_LIVE_VECTOR,
    ROUTE_REMOTE_RASTER,
    VSI_PREFIXES,
    is_remote_provider,
    provider_display_name,
    route_for_provider,
    source_label,
)


@pytest.mark.parametrize(
    ("provider", "is_raster", "expected"),
    [
        # Vector: only ogr keeps the path-based flow.
        ("ogr", False, ROUTE_FILE),
        ("OGR", False, ROUTE_FILE),  # case-insensitive
        ("wfs", False, ROUTE_LIVE_VECTOR),
        ("oapif", False, ROUTE_LIVE_VECTOR),
        ("arcgisfeatureserver", False, ROUTE_LIVE_VECTOR),
        ("memory", False, ROUTE_LIVE_VECTOR),
        ("delimitedtext", False, ROUTE_LIVE_VECTOR),
        ("postgres", False, ROUTE_LIVE_VECTOR),
        ("spatialite", False, ROUTE_LIVE_VECTOR),
        # Raster: only gdal keeps the path-based flow.
        ("gdal", True, ROUTE_FILE),
        ("wcs", True, ROUTE_REMOTE_RASTER),
        ("arcgismapserver", True, ROUTE_REMOTE_RASTER),
        ("wms", True, ROUTE_REMOTE_RASTER),
        ("xyz", True, ROUTE_REMOTE_RASTER),
    ],
)
def test_route_for_provider(provider, is_raster, expected):
    assert route_for_provider(provider, is_raster) == expected


@pytest.mark.parametrize("provider", ["", None])
def test_route_for_provider_tolerates_missing_name(provider):
    # An unknown/empty provider must not crash; it routes to the live
    # flow (vector) / remote flow (raster), never to a bogus file path.
    assert route_for_provider(provider, False) == ROUTE_LIVE_VECTOR
    assert route_for_provider(provider, True) == ROUTE_REMOTE_RASTER


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("wfs", True),
        ("WFS", True),
        ("arcgisfeatureserver", True),
        ("arcgismapserver", True),
        ("wcs", True),
        ("wms", True),
        ("ogr", False),
        ("gdal", False),
        ("memory", False),
        ("postgres", False),
        ("", False),
        (None, False),
    ],
)
def test_is_remote_provider(provider, expected):
    assert is_remote_provider(provider) is expected


def test_provider_display_name_known_and_unknown():
    assert provider_display_name("wfs") == "WFS"
    assert provider_display_name("memory") == "Memoria"
    assert provider_display_name("somethingelse") == "somethingelse"
    assert provider_display_name("") == "?"


def test_source_label_contains_provider_name_and_source():
    label = source_label("wfs", "Comuni", "https://example.org/wfs?typename=x")
    assert label == "wfs: Comuni (https://example.org/wfs?typename=x)"


def test_source_label_truncates_long_uris():
    label = source_label("wfs", "Comuni", "u" * 300)
    assert len(label) < 160
    assert label.endswith("...)")


def test_source_label_without_source():
    assert source_label("memory", "Appunti", "") == "memory: Appunti"


def test_vsi_prefixes_include_archives():
    for prefix in ("/vsizip/", "/vsirar/", "/vsi7z/", "/vsitar/", "/vsicurl/"):
        assert prefix in VSI_PREFIXES
