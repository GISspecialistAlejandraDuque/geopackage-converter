"""
Shared helpers for the Processing algorithms.

Keeps the GUI-style "grouping strategy" enum and a couple of small
utilities in one place so both algorithms stay short.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List

from ..core.grouping_strategies import (
    group_all_in_one,
    group_by_legend_group,
    group_by_subfolder,
)

# Strategy constants used by both the GUI dispatcher and Processing
# algorithms. The integer values are stable and persisted in QSettings.
GROUPING_ALL_IN_ONE = 0
GROUPING_BY_SUBFOLDER = 1
GROUPING_BY_LEGEND_GROUP = 2

# Human-readable labels indexed by constant. The trailing
# "(solo modalità ...)" hint is gone now that the GUI filters the
# combo per-tab; Processing algorithms still see the full list.
GROUPING_LABELS: dict = {
    GROUPING_ALL_IN_ONE: "Tutto in un unico GeoPackage",
    GROUPING_BY_SUBFOLDER: "Un GeoPackage per sottocartella",
    GROUPING_BY_LEGEND_GROUP: "Un GeoPackage per gruppo della legenda",
}

# Backward-compat list (Processing algorithms read this for QgsProcessingParameterEnum).
GROUPING_OPTIONS: List[str] = [
    GROUPING_LABELS[GROUPING_ALL_IN_ONE],
    GROUPING_LABELS[GROUPING_BY_SUBFOLDER],
    GROUPING_LABELS[GROUPING_BY_LEGEND_GROUP],
]


def apply_grouping(
    strategy_index: int,
    items: list,
    output_path: Path,
) -> List[dict]:
    """
    Dispatch on `strategy_index`. For "all in one" the path must be a
    `.gpkg` file; for the other strategies it must be a directory.
    """
    if strategy_index == GROUPING_ALL_IN_ONE:
        return group_all_in_one(items, output_path)
    base = output_path.parent if output_path.suffix else output_path
    if strategy_index == GROUPING_BY_SUBFOLDER:
        return group_by_subfolder(items, base)
    if strategy_index == GROUPING_BY_LEGEND_GROUP:
        return group_by_legend_group(items, base)
    raise ValueError(f"Unknown grouping strategy index: {strategy_index}")


def make_feedback_progress(feedback) -> Callable[[int, str], None]:
    """Wrap a `QgsProcessingFeedback` so it matches our `ProgressCallback`."""

    def cb(percent: int, message: str) -> None:
        feedback.setProgress(percent)
        if message:
            feedback.pushInfo(message)

    return cb
