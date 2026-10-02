"""AI analysis engine (Phase 6).

Interprets a deterministic `drift_report.json` with a LangGraph pipeline and an
optional OpenAI / Azure OpenAI model. It never detects drift and never runs
Terraform: drift_engine remains the source of truth, and analysis degrades to
deterministic-only output when no LLM is configured or reachable.

`ai_engine.config` depends only on the core package; `ai_engine.graph` needs the
`ai` extra (`pip install '.[ai]'`).
"""

from __future__ import annotations

import logging

# Library convention, as in drift_engine: silent unless the application configures logging.
_logger = logging.getLogger(__name__)
if not any(isinstance(h, logging.NullHandler) for h in _logger.handlers):
    _logger.addHandler(logging.NullHandler())
