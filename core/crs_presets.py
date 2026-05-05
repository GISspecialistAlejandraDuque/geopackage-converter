"""
Italian CRS presets for GeoPackage Converter.

This module is intentionally pure-Python: no QGIS imports, no Qt.
That keeps `core/` testable in isolation (Rule 4) and lets the GUI/Processing
layers consume the presets without dragging the QGIS runtime into unit tests.

Each preset is a `CRSPreset` dataclass with:
* `epsg`   — EPSG numeric code
* `name`   — human-readable name (matches the official EPSG label)
* `description` — short Italian description for UI tooltips/labels

The list `ITALIAN_CRS_PRESETS` is the canonical source of truth.
Helpers `get_preset_by_epsg()` and `get_all_presets()` are the public API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .exceptions import CRSError


@dataclass(frozen=True)
class CRSPreset:
    """An Italian CRS preset entry. Immutable so it can be safely shared."""

    epsg: int
    name: str
    description: str

    @property
    def auth_id(self) -> str:
        """Return the QGIS-style authority id, e.g. 'EPSG:32632'."""
        return f"EPSG:{self.epsg}"


# Canonical list. Order matters: it drives the default order in the UI combo box.
# ETRS89 / UTM (25832, 25833) are listed first because they are the official
# European reference frame adopted by Italian public administration (INSPIRE).
ITALIAN_CRS_PRESETS: List[CRSPreset] = [
    CRSPreset(
        epsg=25832,
        name="ETRS89 / UTM zone 32N",
        description="Standard europeo INSPIRE - Italia centro-occidentale",
    ),
    CRSPreset(
        epsg=25833,
        name="ETRS89 / UTM zone 33N",
        description="Standard europeo INSPIRE - Italia centro-orientale",
    ),
    CRSPreset(
        epsg=32632,
        name="WGS 84 / UTM zone 32N",
        description="Italia centro-occidentale",
    ),
    CRSPreset(
        epsg=32633,
        name="WGS 84 / UTM zone 33N",
        description="Italia centro-orientale",
    ),
    CRSPreset(
        epsg=3003,
        name="Monte Mario / Italy zone 1",
        description="Gauss-Boaga Ovest",
    ),
    CRSPreset(
        epsg=3004,
        name="Monte Mario / Italy zone 2",
        description="Gauss-Boaga Est",
    ),
    CRSPreset(
        epsg=6875,
        name="RDN2008 / Italy zone (E-N)",
        description="Sistema nazionale unificato",
    ),
    CRSPreset(
        epsg=6876,
        name="RDN2008 / Zone 12 (E-N)",
        description="Sistema nazionale unificato",
    ),
    CRSPreset(
        epsg=4326,
        name="WGS 84",
        description="Coordinate geografiche globali",
    ),
]


def get_all_presets() -> List[CRSPreset]:
    """Return a copy of the preset list (defensive against external mutation)."""
    return list(ITALIAN_CRS_PRESETS)


def get_preset_by_epsg(code: int) -> Optional[CRSPreset]:
    """
    Return the preset matching `code`, or None if not found.

    Raises:
        CRSError: if `code` is not a positive integer.
    """
    if not isinstance(code, int) or code <= 0:
        raise CRSError(f"Invalid EPSG code: {code!r}")
    for preset in ITALIAN_CRS_PRESETS:
        if preset.epsg == code:
            return preset
    return None


__all__ = [
    "CRSPreset",
    "ITALIAN_CRS_PRESETS",
    "get_all_presets",
    "get_preset_by_epsg",
]
