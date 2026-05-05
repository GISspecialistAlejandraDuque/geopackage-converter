"""
Tests for the QGIS-independent helpers in `processing._common`.

The two algorithm classes themselves require QGIS at import time, so
they are exercised manually in the Processing Toolbox (per Phase 9
acceptance criteria) and via the integration test in Phase 13.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from geopackage_converter.processing._common import (
    GROUPING_ALL_IN_ONE,
    GROUPING_BY_LEGEND_GROUP,
    GROUPING_BY_SUBFOLDER,
    GROUPING_OPTIONS,
    apply_grouping,
    make_feedback_progress,
)


def test_grouping_options_count():
    assert len(GROUPING_OPTIONS) == 3


def _items():
    return [
        {"name": "a", "path": Path("/d/zone1/a.shp"), "crs": "EPSG:4326"},
        {"name": "b", "path": Path("/d/zone2/b.shp"), "crs": "EPSG:32632",
         "legend_group": "Infra"},
    ]


def test_apply_grouping_all_in_one(tmp_path):
    bundles = apply_grouping(GROUPING_ALL_IN_ONE, _items(), tmp_path / "out.gpkg")
    assert len(bundles) == 1
    assert bundles[0]["output_path"] == tmp_path / "out.gpkg"


def test_apply_grouping_by_subfolder(tmp_path):
    bundles = apply_grouping(GROUPING_BY_SUBFOLDER, _items(), tmp_path / "out.gpkg")
    assert {b["output_path"].name for b in bundles} == {"zone1.gpkg", "zone2.gpkg"}


def test_apply_grouping_by_legend_group(tmp_path):
    bundles = apply_grouping(GROUPING_BY_LEGEND_GROUP, _items(), tmp_path / "out.gpkg")
    names = {b["output_path"].name for b in bundles}
    assert "Infra.gpkg" in names
    assert "ungrouped.gpkg" in names


def test_apply_grouping_unknown_index_raises(tmp_path):
    with pytest.raises(ValueError):
        apply_grouping(99, _items(), tmp_path / "out.gpkg")


def test_make_feedback_progress_forwards_to_qgs_feedback():
    class FakeFeedback:
        def __init__(self):
            self.progress = None
            self.messages = []

        def setProgress(self, p):  # noqa: N802
            self.progress = p

        def pushInfo(self, msg):  # noqa: N802
            self.messages.append(msg)

    fb = FakeFeedback()
    cb = make_feedback_progress(fb)
    cb(42, "halfway")
    assert fb.progress == 42
    assert fb.messages == ["halfway"]
    cb(100, "")
    assert fb.progress == 100
    assert fb.messages == ["halfway"]  # empty message is not pushed
