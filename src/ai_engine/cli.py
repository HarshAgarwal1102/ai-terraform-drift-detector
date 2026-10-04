"""`ai-analysis` command: AI analysis report from a drift report (Task 9A.1).

Runs the Phase 6 graph (`run_analysis`) over a valid drift report and writes
`ai_analysis_report.json` and `ai_analysis_report.md` (`write_report`). It never
changes the drift report, the drift result or `drift_detected`: the report is
read-only input and the AI output is a separate document.

    ai-analysis --report drift_report.json --output-dir out/

LLM use stays opt-in through `AI_LLM_PROVIDER` (Task 6.1). Inside GitHub
Actions the command refuses to run unless `AI_LLM_PROVIDER` is explicitly
`none`: a real LLM in CI is a separate, approval-gated decision.

This is a separate entry point on purpose: `drift-engine` never imports
`ai_engine`, so `pip install .` keeps working without the LLM stack (the
`ai` extra).

Exit codes (as for `drift-engine`):
    0   report written
    1   input rejected (unreadable or invalid drift report, or a failed
        detection run whose drift status is unknown); nothing written
    2   usage error, refused environment, invalid AI configuration, or the
        `ai` extra is not installed
    70  internal error; nothing reliable was written
    73  the output could not be written
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_USAGE = 2
EXIT_INTERNAL_ERROR = 70
EXIT_CANT_WRITE = 73


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-analysis",
        description="Write the AI analysis report (JSON + Markdown) for a valid drift report. "
                    "The drift report and the drift result are never changed.",
    )
    parser.add_argument("--report", required=True, help="drift report JSON (drift_report.json)")
    parser.add_argument("--output-dir", required=True,
                        help="directory for ai_analysis_report.json and ai_analysis_report.md")
    return parser


def _error(message: str) -> None:
    print(f"ai-analysis: {message}", file=sys.stderr)


def _environment_refusal(env: dict[str, str] | os._Environ[str]) -> str | None:
    """In GitHub Actions the provider must be set explicitly to `none`."""
    if env.get("GITHUB_ACTIONS") == "true" and env.get("AI_LLM_PROVIDER") != "none":
        return ("refusing to run in GitHub Actions unless AI_LLM_PROVIDER is explicitly 'none' "
                "(a real LLM in CI is a separate, approval-gated decision)")
    return None


def _load_report(path: str) -> dict[str, Any] | str:
    """The drift report as a dict, or the reason it is rejected."""
    from drift_engine.models import DriftReport

    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, UnicodeDecodeError) as exc:
        return f"cannot read the drift report: {type(exc).__name__}"
    except json.JSONDecodeError as exc:
        return f"the drift report is not valid JSON (line {exc.lineno})"
    try:
        report = DriftReport.model_validate(raw)
    except ValidationError as exc:
        return f"the drift report does not match the report contract ({exc.error_count()} error(s))"
    if report.outcome != "succeeded" or not isinstance(report.has_drift, bool):
        return "the detection run failed: drift status is unknown, so there is nothing to analyse"
    return raw


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    refusal = _environment_refusal(os.environ)
    if refusal:
        _error(refusal)
        return EXIT_USAGE

    try:
        from ai_engine.config import AiConfigError, load_config
        from ai_engine.graph import run_analysis
        from ai_engine.nodes.report_generator import write_report
    except ImportError as exc:
        _error(f"the 'ai' extra is not installed ({exc.name or exc}); install with: pip install '.[ai]'")
        return EXIT_USAGE

    loaded = _load_report(args.report)
    if isinstance(loaded, str):
        _error(f"{loaded}. Nothing was written.")
        return EXIT_REJECTED

    try:
        config = load_config(os.environ)
    except AiConfigError as exc:
        _error(f"invalid AI configuration: {exc}")
        return EXIT_USAGE

    try:
        state = run_analysis(loaded, config=config)
        try:
            paths = write_report(state, args.output_dir)
        except OSError as exc:
            _error(f"cannot write the AI analysis report to {args.output_dir}: {type(exc).__name__}")
            return EXIT_CANT_WRITE
    except Exception as exc:  # last resort: never a traceback-only exit
        _error(f"internal error: unexpected {type(exc).__name__}. The drift result is unaffected.")
        return EXIT_INTERNAL_ERROR

    report = state["report"]
    llm = report["llm"]
    print(f"AI analysis report written: {paths['json']} and {paths['markdown']} "
          f"(resources {len(report['resources'])}, remediation options {len(report['remediation']['options'])}, "
          f"LLM {llm['provider'] or 'none'}/{llm['status']})")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
