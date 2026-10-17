"""Dashboard data API (Phase 13, Task 13.1).

A read-only FastAPI backend over the real artifacts of the drift detection and AI
analysis workflows (`drift_report.json`, `ai_analysis_report.json`,
`drift_investigation.json`, `cost_run.json`), plus the on-demand
`Caller recorded by Azure` lookup, which reuses the Phase 9B WHO matching
(`drift_engine.who.lookup_operation`). Needs the `dashboard` extra.

Caller identity is returned only to authenticated users with the `caller_reader`
role, is never stored (there is no database, cache or output file) and never logged.
"""

API_VERSION = "1"
