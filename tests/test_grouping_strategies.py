"""Tests for `core.grouping_strategies`."""

from __future__ import annotations

from pathlib import Path

import pytest

from geopackage_converter.core.grouping_strategies import (
    group_all_in_one,
    group_by_crs,
    group_by_legend_group,
    group_by_subfolder,
    resolve_name_conflicts,
)


def _item(name="layer", path="/tmp/x.shp", crs="EPSG:4326", **extra):
    base = {"name": name, "path": Path(path), "crs": crs}
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# resolve_name_conflicts
# ---------------------------------------------------------------------------


def test_no_conflicts_keeps_names():
    items = [_item(name="a"), _item(name="b"), _item(name="c")]
    resolve_name_conflicts(items)
    assert [i["name"] for i in items] == ["a", "b", "c"]
    assert [i["original_name"] for i in items] == ["a", "b", "c"]


def test_duplicates_get_numeric_suffix():
    items = [_item(name="roads"), _item(name="roads"), _item(name="roads")]
    resolve_name_conflicts(items)
    assert [i["name"] for i in items] == ["roads", "roads_1", "roads_2"]
    assert all(i["original_name"] == "roads" for i in items)


def test_collision_with_preexisting_suffix_skips():
    """If 'roads_1' already exists, the second 'roads' must become 'roads_2'."""
    items = [_item(name="roads"), _item(name="roads_1"), _item(name="roads")]
    resolve_name_conflicts(items)
    assert [i["name"] for i in items] == ["roads", "roads_1", "roads_2"]


def test_case_insensitive_collision():
    items = [_item(name="Roads"), _item(name="roads")]
    resolve_name_conflicts(items)
    assert items[0]["name"] == "Roads"
    assert items[1]["name"].lower() == "roads_1"


def test_resolve_returns_same_list():
    items = [_item()]
    out = resolve_name_conflicts(items)
    assert out is items


# ---------------------------------------------------------------------------
# group_all_in_one
# ---------------------------------------------------------------------------


def test_all_in_one_single_bundle(tmp_path):
    items = [_item(name="a"), _item(name="b")]
    result = group_all_in_one(items, tmp_path / "out.gpkg")
    assert len(result) == 1
    assert result[0]["output_path"] == tmp_path / "out.gpkg"
    assert [i["name"] for i in result[0]["items"]] == ["a", "b"]


def test_all_in_one_resolves_conflicts(tmp_path):
    items = [_item(name="dup"), _item(name="dup")]
    [bundle] = group_all_in_one(items, tmp_path / "out.gpkg")
    assert [i["name"] for i in bundle["items"]] == ["dup", "dup_1"]


def test_all_in_one_empty_input(tmp_path):
    result = group_all_in_one([], tmp_path / "out.gpkg")
    assert result == [{"output_path": tmp_path / "out.gpkg", "items": []}]


# ---------------------------------------------------------------------------
# group_by_crs
# ---------------------------------------------------------------------------


def test_by_crs_separates_distinct_crs(tmp_path):
    items = [
        _item(name="a", crs="EPSG:4326"),
        _item(name="b", crs="EPSG:32632"),
        _item(name="c", crs="EPSG:4326"),
    ]
    result = group_by_crs(items, tmp_path)
    by_path = {b["output_path"].name: [i["name"] for i in b["items"]] for b in result}
    assert by_path == {
        "by_crs_EPSG_4326.gpkg": ["a", "c"],
        "by_crs_EPSG_32632.gpkg": ["b"],
    }


def test_by_crs_unknown_grouped_together(tmp_path):
    items = [
        _item(name="a", crs="Unknown"),
        _item(name="b", crs=""),
        _item(name="c"),  # missing key handled by .get
    ]
    items[2].pop("crs")
    result = group_by_crs(items, tmp_path)
    assert len(result) == 1
    assert result[0]["output_path"].name == "by_crs_CRS_unknown.gpkg"
    assert [i["name"] for i in result[0]["items"]] == ["a", "b", "c"]


def test_by_crs_preserves_input_order(tmp_path):
    items = [
        _item(name="a", crs="EPSG:32633"),
        _item(name="b", crs="EPSG:4326"),
    ]
    result = group_by_crs(items, tmp_path)
    assert [b["output_path"].name for b in result] == [
        "by_crs_EPSG_32633.gpkg",
        "by_crs_EPSG_4326.gpkg",
    ]


# ---------------------------------------------------------------------------
# group_by_subfolder
# ---------------------------------------------------------------------------


def test_by_subfolder_uses_path_parent(tmp_path):
    items = [
        _item(name="a", path="/data/roads/main.shp"),
        _item(name="b", path="/data/roads/secondary.shp"),
        _item(name="c", path="/data/buildings/houses.shp"),
    ]
    result = group_by_subfolder(items, tmp_path)
    by_name = {b["output_path"].name: [i["name"] for i in b["items"]] for b in result}
    assert by_name == {
        "roads.gpkg": ["a", "b"],
        "buildings.gpkg": ["c"],
    }


def test_by_subfolder_explicit_subfolder_key_wins(tmp_path):
    items = [_item(name="a", path="/data/roads/x.shp", subfolder="custom_group")]
    [bundle] = group_by_subfolder(items, tmp_path)
    assert bundle["output_path"].name == "custom_group.gpkg"


def test_by_subfolder_sanitizes_invalid_chars(tmp_path):
    items = [_item(name="a", path="/data/bad:name?/x.shp")]
    [bundle] = group_by_subfolder(items, tmp_path)
    assert ":" not in bundle["output_path"].name
    assert "?" not in bundle["output_path"].name


def test_by_subfolder_mirror_creates_nested_output(tmp_path):
    """Multi-segment subfolder labels become nested output dirs."""
    items = [
        _item(name="parchi", path="/data/x.shp", subfolder="BENI/Aree"),
        _item(name="grotte", path="/data/y.shp", subfolder="BENI/Aree"),
        _item(name="solo", path="/data/z.shp", subfolder="BENI"),
    ]
    bundles = group_by_subfolder(items, tmp_path, mirror_layout=True)
    by_path = {b["output_path"].relative_to(tmp_path).as_posix(): len(b["items"]) for b in bundles}
    assert "BENI/Aree/Aree.gpkg" in by_path
    assert "BENI/BENI.gpkg" in by_path
    assert by_path["BENI/Aree/Aree.gpkg"] == 2
    assert by_path["BENI/BENI.gpkg"] == 1


def test_by_subfolder_mirror_handles_backslashes(tmp_path):
    """Windows-style \\ separators in the subfolder label are normalised."""
    items = [_item(name="x", path="/d/x.shp", subfolder=r"A\B\C")]
    [bundle] = group_by_subfolder(items, tmp_path)
    rel = bundle["output_path"].relative_to(tmp_path).as_posix()
    assert rel == "A/B/C/C.gpkg"


def test_by_subfolder_resolves_conflicts_per_bundle(tmp_path):
    """Same layer name in different subfolders must NOT collide."""
    items = [
        _item(name="roads", path="/data/zone_a/roads.shp"),
        _item(name="roads", path="/data/zone_b/roads.shp"),
    ]
    result = group_by_subfolder(items, tmp_path)
    assert len(result) == 2
    for bundle in result:
        assert [i["name"] for i in bundle["items"]] == ["roads"]


# ---------------------------------------------------------------------------
# group_by_legend_group
# ---------------------------------------------------------------------------


def test_by_legend_group_buckets_per_group(tmp_path):
    items = [
        _item(name="a", legend_group="Infrastrutture"),
        _item(name="b", legend_group="Infrastrutture"),
        _item(name="c", legend_group="Idrografia"),
    ]
    result = group_by_legend_group(items, tmp_path)
    by_name = {b["output_path"].name: [i["name"] for i in b["items"]] for b in result}
    assert by_name == {
        "Infrastrutture.gpkg": ["a", "b"],
        "Idrografia.gpkg": ["c"],
    }


def test_by_legend_group_missing_or_empty_get_individual_gpkg(tmp_path):
    # Since 0.2.0 ungrouped layers each get their own GPKG named after
    # the layer, instead of being lumped into a single ungrouped.gpkg.
    items = [
        _item(name="a"),
        _item(name="b", legend_group=""),
        _item(name="c", legend_group=None),
    ]
    result = group_by_legend_group(items, tmp_path)
    by_name = {b["output_path"].name: [i["name"] for i in b["items"]] for b in result}
    assert by_name == {
        "a.gpkg": ["a"],
        "b.gpkg": ["b"],
        "c.gpkg": ["c"],
    }


def test_by_legend_group_sanitizes_name(tmp_path):
    items = [_item(name="a", legend_group="Layer/with:bad*chars")]
    [bundle] = group_by_legend_group(items, tmp_path)
    name = bundle["output_path"].name
    for ch in '/\\:*?"<>|':
        assert ch not in name


# ---------------------------------------------------------------------------
# Cross-cutting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "strategy",
    [
        lambda items, dst: group_all_in_one(items, dst / "out.gpkg"),
        group_by_crs,
        group_by_subfolder,
        group_by_legend_group,
    ],
)
def test_every_strategy_returns_list_of_bundles(strategy, tmp_path):
    items = [_item(name="a"), _item(name="b")]
    result = strategy(items, tmp_path)
    assert isinstance(result, list)
    for bundle in result:
        assert set(bundle.keys()) == {"output_path", "items"}
        assert isinstance(bundle["output_path"], Path)
        assert isinstance(bundle["items"], list)
