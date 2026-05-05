"""
Shared pytest configuration.

We add the plugin's parent directory to `sys.path` so tests can
`import geopackage_converter.core.*` without installing the plugin.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PARENT = PLUGIN_ROOT.parent

if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))
