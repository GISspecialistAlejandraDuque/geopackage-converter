"""
Grouping strategies and layer-name conflict resolution.

An *item* is a dict (typically produced by `folder_scanner.scan_folder`
or assembled from project layers) with at least these keys:

    path           : pathlib.Path     # source file
    name           : str              # base layer name
    crs            : str              # auth id like "EPSG:32632" or "Unknown"
    subfolder      : Optional[Path]   # used by `group_by_subfolder` (Mode B)
    legend_group   : Optional[str]    # used by `group_by_legend_group` (Mode A)

Each strategy returns a list of *bundles*:

    {"output_path": Path, "items": [item, ...]}

`resolve_name_conflicts(items)` mutates a list in place: when two items
share the same layer name, suffixes `_1`, `_2`, ... are appended to all
duplicates after the first. The original `name` is preserved in
`item["original_name"]` so the report and UI can show the rename.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Sanitisation helpers
# ---------------------------------------------------------------------------

# Characters not safe inside a filename on Windows / macOS / Linux.
_INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_for_filename(value: str, fallback: str = "unnamed") -> str:
    """Return `value` reduced to a safe filename fragment."""
    cleaned = _INVALID_FS_CHARS.sub("_", value).strip(" .")
    return cleaned or fallback


def _crs_filename_token(crs: Optional[str]) -> str:
    """Turn a CRS authid like 'EPSG:32632' into 'EPSG_32632'; unknowns become 'CRS_unknown'."""
    if not crs or crs.strip().lower() in {"unknown", ""}:
        return "CRS_unknown"
    return _sanitize_for_filename(crs).replace(":", "_")


# ---------------------------------------------------------------------------
# Name-conflict resolver
# ---------------------------------------------------------------------------


def resolve_name_conflicts(items: List[Dict]) -> List[Dict]:
    """
    Append `_1`, `_2`, ... to layer names that collide within `items`.

    Operates *in place* on each item dict (sets `name` and stores the
    pristine value as `original_name`). Returns the same list for
    chaining convenience.

    Comparison is case-insensitive because OGR / GeoPackage treat layer
    names case-insensitively on lookup but preserve the original case.
    """
    seen: Dict[str, int] = {}
    for item in items:
        original = str(item.get("name", "")) or "layer"
        item.setdefault("original_name", original)

        candidate = original
        key = candidate.lower()
        if key not in seen:
            seen[key] = 0
            item["name"] = candidate
            continue

        # Collision: bump suffix until we find a free slot.
        seen[key] += 1
        while True:
            candidate = f"{original}_{seen[key]}"
            ckey = candidate.lower()
            if ckey not in seen:
                seen[ckey] = 0
                break
            seen[key] += 1
        item["name"] = candidate
    return items


# ---------------------------------------------------------------------------
# Bundle helper
# ---------------------------------------------------------------------------


def _make_bundle(output_path: Path, items: List[Dict]) -> Dict:
    """Build a bundle dict, applying name-conflict resolution to its items."""
    return {"output_path": output_path, "items": resolve_name_conflicts(items)}


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


def group_all_in_one(items: List[Dict], output_path: Path) -> List[Dict]:
    """
    Pack every item into a single GeoPackage at `output_path`.

    `output_path` must be the full path of the target `.gpkg` file
    (not a directory).
    """
    output_path = Path(output_path)
    return [_make_bundle(output_path, list(items))]


def group_by_crs(items: List[Dict], output_dir: Path) -> List[Dict]:
    """
    One GeoPackage per distinct CRS. File naming: `<dir>/by_crs_<token>.gpkg`.

    Items missing a `crs` key, or with `crs == "Unknown"`, are grouped
    together under `CRS_unknown`.
    """
    output_dir = Path(output_dir)
    buckets: OrderedDict[str, List[Dict]] = OrderedDict()
    for item in items:
        token = _crs_filename_token(item.get("crs"))  # type: ignore[arg-type]
        buckets.setdefault(token, []).append(item)

    return [
        _make_bundle(output_dir / f"by_crs_{token}.gpkg", group_items)
        for token, group_items in buckets.items()
    ]


def group_by_subfolder(
    items: List[Dict],
    output_dir: Path,
    mirror_layout: bool = False,
) -> List[Dict]:
    """
    One GeoPackage per source subfolder (Mode B).

    The bucket key is the immediate parent directory name of each item's
    `path`. Items missing a `path` (or with no usable parent name) are
    grouped under `unsorted`.

    Multi-segment ``subfolder`` labels (containing ``/`` or ``\\``) are
    always treated as a *relative path*: the output GeoPackage lands
    inside nested directories that mirror the original folder structure
    and is named after the deepest segment.

    When ``mirror_layout=True``, even single-segment labels get nested
    inside a folder of their own name — so the output is always
    ``<subfolder>/<subfolder>.gpkg`` for full structural symmetry.
    """
    output_dir = Path(output_dir)
    buckets: OrderedDict[str, List[Dict]] = OrderedDict()
    for item in items:
        explicit = item.get("subfolder")
        if explicit is not None:
            raw = str(explicit)
        else:
            path = item.get("path")
            raw = Path(path).parent.name if path else "unsorted"

        # Detect multi-segment "mirror" labels.
        normalised = raw.replace("\\", "/")
        if "/" in normalised:
            parts = [p for p in normalised.split("/") if p]
            sanitised_parts = [_sanitize_for_filename(p, fallback="unsorted") for p in parts]
            token = "/".join(sanitised_parts)
        else:
            token = _sanitize_for_filename(raw, fallback="unsorted")
        buckets.setdefault(token, []).append(item)

    bundles: List[Dict] = []
    for token, group_items in buckets.items():
        if "/" in token:
            # Mirror mode: the .gpkg lands inside its own replica
            # folder, mirroring the input structure exactly.
            #   token="BENI/Aree"  ->  output/BENI/Aree/Aree.gpkg
            parts = token.split("/")
            output_path = output_dir.joinpath(*parts, f"{parts[-1]}.gpkg")
        elif mirror_layout:
            # Single-level token but caller wants symmetrical nesting.
            output_path = output_dir / token / f"{token}.gpkg"
        else:
            output_path = output_dir / f"{token}.gpkg"
        bundles.append(_make_bundle(output_path, group_items))
    return bundles


def group_by_legend_group(items: List[Dict], output_dir: Path) -> List[Dict]:
    """
    One GeoPackage per legend group (Mode A).

    Items without a `legend_group` key (or with empty value) fall into
    a single bundle named `ungrouped.gpkg`.
    """
    output_dir = Path(output_dir)
    buckets: OrderedDict[str, List[Dict]] = OrderedDict()
    for item in items:
        raw = item.get("legend_group")
        label = str(raw).strip() if raw else ""
        token = _sanitize_for_filename(label, fallback="ungrouped") if label else "ungrouped"
        buckets.setdefault(token, []).append(item)

    return [
        _make_bundle(output_dir / f"{token}.gpkg", group_items)
        for token, group_items in buckets.items()
    ]


__all__ = [
    "resolve_name_conflicts",
    "group_all_in_one",
    "group_by_crs",
    "group_by_subfolder",
    "group_by_legend_group",
]
