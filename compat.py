"""
Qt5/Qt6 compatibility helpers for GeoPackage Converter.

Why this module exists
----------------------
The plugin must run on QGIS 3.34+ (Qt5), QGIS 3.44 (Qt5 *and* Qt6),
and QGIS 4.0+ (Qt6 only). The `qgis.PyQt` shim already routes most
imports to the right binding, but a few API differences still leak
through and need explicit handling:

* Several enums in Qt6 are *only* accessible via their fully-qualified
  scoped form (e.g. `Qt.AlignmentFlag.AlignCenter`). The unscoped
  spelling (`Qt.AlignCenter`) is deprecated in PyQt5 and **removed**
  in PyQt6.
* `QDialog.exec_()` has been removed in PyQt6; only `exec()` remains.
* `QAction` moved from `QtWidgets` (Qt5) to `QtGui` (Qt6).
* `QVariant` semantics differ between bindings on a few edge cases.

Rather than scattering `try/except ImportError` blocks across the
codebase, every cross-binding concern lives here.

Usage
-----
Always import Qt symbols from `qgis.PyQt.*`. Use the helpers in this
module only for things the shim does not already normalize.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qgis.PyQt.QtCore import QT_VERSION_STR, Qt

if TYPE_CHECKING:
    from qgis.PyQt.QtWidgets import QDialog


# ---------------------------------------------------------------------------
# Version detection
# ---------------------------------------------------------------------------

#: Major Qt version as integer (5 or 6). Computed once at import time.
QT_MAJOR_VERSION: int = int(QT_VERSION_STR.split(".", 1)[0])


def is_qt6() -> bool:
    """Return True when running under Qt6 (PyQt6 / QGIS 4.x or 3.44 Qt6)."""
    return QT_MAJOR_VERSION >= 6


def is_qt5() -> bool:
    """Return True when running under Qt5."""
    return QT_MAJOR_VERSION == 5


# ---------------------------------------------------------------------------
# QAction location shim
# ---------------------------------------------------------------------------
# In Qt6, QAction lives in QtGui. In Qt5 it is in QtWidgets. The
# `qgis.PyQt.QtGui` re-export handles this transparently for most setups,
# but importing from a single canonical location here avoids subtle bugs
# on older QGIS builds where the shim is incomplete.
try:
    from qgis.PyQt.QtGui import QAction  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - Qt5 fallback path
    from qgis.PyQt.QtWidgets import QAction  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Dialog execution
# ---------------------------------------------------------------------------


def exec_dialog(dialog: QDialog) -> int:
    """
    Show a modal dialog and return its result code.

    Use this helper instead of calling `dialog.exec_()` (Qt5 only) or
    `dialog.exec()` (works on both, but linters flag the bare name as
    a built-in shadow). Centralising the call keeps a single audit point.
    """
    return dialog.exec()


# ---------------------------------------------------------------------------
# Fully-qualified enum re-exports
# ---------------------------------------------------------------------------
# These constants are the ones the plugin actually uses. Adding more
# here is cheap; importing from `Qt.<Name>` directly elsewhere is the
# pattern that breaks on Qt6, so prefer these aliases when convenient.

ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter
ALIGN_LEFT = Qt.AlignmentFlag.AlignLeft
ALIGN_RIGHT = Qt.AlignmentFlag.AlignRight
ALIGN_VCENTER = Qt.AlignmentFlag.AlignVCenter

CHECKED = Qt.CheckState.Checked
UNCHECKED = Qt.CheckState.Unchecked
PARTIALLY_CHECKED = Qt.CheckState.PartiallyChecked

ITEM_IS_USER_CHECKABLE = Qt.ItemFlag.ItemIsUserCheckable
ITEM_IS_ENABLED = Qt.ItemFlag.ItemIsEnabled
ITEM_IS_SELECTABLE = Qt.ItemFlag.ItemIsSelectable

ORIENTATION_HORIZONTAL = Qt.Orientation.Horizontal
ORIENTATION_VERTICAL = Qt.Orientation.Vertical

WAIT_CURSOR = Qt.CursorShape.WaitCursor
ARROW_CURSOR = Qt.CursorShape.ArrowCursor

USER_ROLE = Qt.ItemDataRole.UserRole
NO_ITEM_FLAGS = Qt.ItemFlag.NoItemFlags


# ---------------------------------------------------------------------------
# QVariant normalisation
# ---------------------------------------------------------------------------
# In PyQt5 a "null" QVariant is a distinct object; in PyQt6 most APIs
# return plain `None` instead. Code that compares against QVariant()
# breaks on Qt6. Use `is_null_variant(value)` for a binding-agnostic check.


def is_null_variant(value: Any) -> bool:
    """
    Return True when `value` represents a null/absent QVariant.

    Works across PyQt5 and PyQt6. In PyQt6 this is just `value is None`.
    In PyQt5 it also catches `QVariant()` and `QVariant.isNull()` cases.
    """
    if value is None:
        return True
    is_null = getattr(value, "isNull", None)
    if callable(is_null):
        try:
            return bool(is_null())
        except TypeError:  # pragma: no cover - defensive
            return False
    return False


__all__ = [
    "QT_MAJOR_VERSION",
    "QAction",
    "is_qt5",
    "is_qt6",
    "exec_dialog",
    "is_null_variant",
    "ALIGN_CENTER",
    "ALIGN_LEFT",
    "ALIGN_RIGHT",
    "ALIGN_VCENTER",
    "CHECKED",
    "UNCHECKED",
    "PARTIALLY_CHECKED",
    "ITEM_IS_USER_CHECKABLE",
    "ITEM_IS_ENABLED",
    "ITEM_IS_SELECTABLE",
    "ORIENTATION_HORIZONTAL",
    "ORIENTATION_VERTICAL",
    "WAIT_CURSOR",
    "ARROW_CURSOR",
]
