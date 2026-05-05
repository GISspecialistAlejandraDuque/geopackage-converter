"""Tests for the custom exception hierarchy."""

from __future__ import annotations

import pytest

from geopackage_converter.core.exceptions import (
    ConversionError,
    CRSError,
    EncodingDetectionError,
    GeoPackageConverterError,
    InvalidSourceError,
)


@pytest.mark.parametrize(
    "exc_cls",
    [InvalidSourceError, ConversionError, EncodingDetectionError, CRSError],
)
def test_subclasses_inherit_from_base(exc_cls):
    assert issubclass(exc_cls, GeoPackageConverterError)


def test_base_is_exception():
    assert issubclass(GeoPackageConverterError, Exception)


def test_exception_carries_message():
    err = ConversionError("write failed")
    assert str(err) == "write failed"


def test_caught_via_base_class():
    with pytest.raises(GeoPackageConverterError):
        raise InvalidSourceError("nope")
