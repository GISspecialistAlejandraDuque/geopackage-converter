"""Tests for the Italian CRS presets module."""

from __future__ import annotations

import pytest

from geopackage_converter.core.crs_presets import (
    ITALIAN_CRS_PRESETS,
    CRSPreset,
    get_all_presets,
    get_preset_by_epsg,
)
from geopackage_converter.core.exceptions import CRSError

EXPECTED_EPSG_CODES = {25832, 25833, 32632, 32633, 3003, 3004, 6875, 6876, 4326}


def test_all_required_codes_present():
    codes = {p.epsg for p in ITALIAN_CRS_PRESETS}
    assert codes == EXPECTED_EPSG_CODES


def test_no_duplicate_codes():
    codes = [p.epsg for p in ITALIAN_CRS_PRESETS]
    assert len(codes) == len(set(codes))


def test_presets_are_immutable():
    preset = ITALIAN_CRS_PRESETS[0]
    with pytest.raises(Exception):  # FrozenInstanceError (subclass of AttributeError in 3.9+)
        preset.epsg = 9999  # type: ignore[misc]


def test_auth_id_format():
    preset = CRSPreset(epsg=32632, name="x", description="y")
    assert preset.auth_id == "EPSG:32632"


def test_get_all_presets_returns_copy():
    a = get_all_presets()
    b = get_all_presets()
    assert a == b
    a.clear()
    assert len(get_all_presets()) == len(ITALIAN_CRS_PRESETS)


def test_get_preset_by_epsg_found():
    p = get_preset_by_epsg(32632)
    assert p is not None
    assert p.epsg == 32632
    assert "UTM zone 32N" in p.name


def test_get_preset_by_epsg_not_found():
    assert get_preset_by_epsg(99999) is None


@pytest.mark.parametrize("bad", [0, -1, "32632", None, 3.14])
def test_get_preset_by_epsg_invalid_input(bad):
    with pytest.raises(CRSError):
        get_preset_by_epsg(bad)  # type: ignore[arg-type]


def test_every_preset_has_nonempty_fields():
    for p in ITALIAN_CRS_PRESETS:
        assert p.epsg > 0
        assert p.name.strip()
        assert p.description.strip()
