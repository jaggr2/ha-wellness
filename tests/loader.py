"""Load the integration's pure modules without triggering the HA package.

``ledger.py`` is deliberately HA-free so it can be exercised standalone.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PACKAGE_DIR = (
    Path(__file__).resolve().parent.parent / "custom_components" / "wellness"
)


def load_module(name: str, filename: str):
    path = _PACKAGE_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
