"""Load the integration's pure modules without triggering the HA package.

The package ``__init__.py`` imports ``homeassistant`` modules which are not
installed in this lightweight test environment. ``pdu_api`` and ``energy`` are
deliberately HA-free so they can be exercised standalone.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PACKAGE_DIR = (
    Path(__file__).resolve().parent.parent / "custom_components" / "value_pdu"
)


def load_module(name: str, filename: str):
    path = _PACKAGE_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
