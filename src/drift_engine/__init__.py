"""Deterministic Terraform drift engine (Phase 4).

Package skeleton created in Task 4.1. The parser, models, comparator, severity
classifier and CLI are added by Tasks 4.2-4.6. Until then, drift detection is
performed by scripts/detect_drift.py (Phase 3).

Like the Phase 3 classifier, this package must not call Terraform, Azure, the
network or an LLM: it only interprets evidence that has already been produced.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("drift-engine")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
