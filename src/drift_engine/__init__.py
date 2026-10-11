"""Deterministic Terraform drift engine (Phase 4).

Modules: parser (Task 4.2), models (4.3), comparator (4.4), severity (4.5),
classifier, formatters and the `drift-engine` CLI (4.6), structured logging (4.7),
activity_logs (7.1; evidence v2, 9B.1), attribution (7.2; rules v2, 9B.2),
investigation (9B.2; public projection 9B.3), investigation_public (9B.3; the only
investigation module ai_engine may use), who (9B.3; local only) and report_public
(9B.4A; the public drift report projection: everything that leaves the runner),
inventory and unmanaged_cost (10.4; resources Terraform does not manage, and their
list-price estimate: never drift).
scripts/detect_drift.py is a thin wrapper over this package.

Like the Phase 3 classifier, this package must not call Terraform, Azure, the
network or an LLM: it only interprets evidence that has already been produced.
The exceptions are opt-in and read-only: the Activity Log collection (`drift-engine
activity-logs`, `drift-engine investigate`: activity_logs.AzureMonitorSource), the unmanaged
resource inventory (`drift-engine inventory`: inventory.AzureResourceSource; both import the Azure
SDK, `[azure]` extra, lazily) and the unmanaged cost estimate (`drift-engine unmanaged-cost`:
unmanaged_cost.RetailPricesApi, the public Azure Retail Prices API over the standard library, no
credential). Drift detection (`drift-engine analyze`, scripts/detect_drift.py) never imports them
or calls Azure or the network.
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
