"""Load the integration's pure-Python modules without Home Assistant.

The package ``__init__`` imports Home Assistant; the modules under test do not.
A stand-in package pointing at the same directory lets their relative imports
work without executing that ``__init__``.
"""

import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "zwift_map"

pkg = types.ModuleType("zwift_map_pure")
pkg.__path__ = [str(PKG_DIR)]
sys.modules.setdefault("zwift_map_pure", pkg)
