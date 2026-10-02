"""Smoke tests for the drift_engine package layout (Task 4.1).

Skipped when the package is not installed, so the stdlib-only Phase 3 suite still
runs with a plain `python3 -m unittest discover -s tests`. Install with
`pip install -e ".[dev]"` to run them.
"""

from __future__ import annotations

import importlib.util
import unittest
from importlib.metadata import PackageNotFoundError, version

# Checked through distribution metadata, not module lookup: scripts/detect_drift.py
# puts src/ on sys.path, which makes drift_engine importable without installing it.
# The metadata alone is not enough either: an editable install from a venv leaves
# src/drift_engine.egg-info behind, visible to any interpreter with src/ on sys.path.
# Installed therefore also means its runtime dependency is importable here.
try:
    version("drift-engine")
    INSTALLED = importlib.util.find_spec("pydantic") is not None
except PackageNotFoundError:
    INSTALLED = False


@unittest.skipUnless(INSTALLED, "drift_engine is not installed (pip install -e '.[dev]')")
class PackageTests(unittest.TestCase):
    def test_package_imports_with_installed_version(self) -> None:
        import drift_engine

        self.assertEqual(drift_engine.__version__, version("drift-engine"))

    def test_runtime_dependency_is_pydantic_v2(self) -> None:
        import pydantic

        self.assertEqual(pydantic.VERSION.split(".")[0], "2")


if __name__ == "__main__":
    unittest.main()
