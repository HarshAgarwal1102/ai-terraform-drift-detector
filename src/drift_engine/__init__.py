"""Deterministic Terraform drift engine (Phase 4).

Modules: parser (Task 4.2), models (4.3), comparator (4.4), severity (4.5),
classifier, formatters and the `drift-engine` CLI (4.6), structured logging (4.7),
activity_logs (7.1). scripts/detect_drift.py is a thin wrapper over this package.

Like the Phase 3 classifier, this package must not call Terraform, Azure, the
network or an LLM: it only interprets evidence that has already been produced.
The one exception is the opt-in Activity Log collector (`drift-engine
activity-logs`): only activity_logs.AzureMonitorSource reads Azure, read-only, and
it imports the Azure SDK (`[azure]` extra) lazily, so drift detection
(`drift-engine analyze`, scripts/detect_drift.py) never imports it or calls Azure.
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("drift-engine")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0+unknown"

# Library convention: silent unless the application configures logging
# (drift_engine.logs.configure_logging, or the CLI's --log-level).
_logger = logging.getLogger(__name__)
if not any(isinstance(h, logging.NullHandler) for h in _logger.handlers):
    _logger.addHandler(logging.NullHandler())

__all__ = ["__version__"]
