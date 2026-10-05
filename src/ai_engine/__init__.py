"""AI analysis engine (Phase 6; report v2, Task 9B.4).

Interprets a deterministic `drift_report.json`, and optionally the public drift
investigation bound to it (`drift_investigation.json`), with a LangGraph
pipeline and an optional OpenAI / Azure OpenAI model. It never detects drift and
never runs Terraform: drift_engine remains the source of truth, the
investigation is authoritative for WHEN / WHO / correlation, and analysis
degrades to complete deterministic output when no LLM is configured or
reachable. Of the investigation modules, `ai_engine` imports only
`drift_engine.investigation_public` (never the restricted document's modules).

`ai_engine.config` depends only on the core package; `ai_engine.graph` needs the
`ai` extra (`pip install '.[ai]'`).
"""

from __future__ import annotations

import logging

# Library convention, as in drift_engine: silent unless the application configures logging.
_logger = logging.getLogger(__name__)
if not any(isinstance(h, logging.NullHandler) for h in _logger.handlers):
    _logger.addHandler(logging.NullHandler())
