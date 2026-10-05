"""`ai-analysis` command: AI analysis report from a drift report (Tasks 9A.1, 9B.4).

Runs the analysis graph (`run_analysis`) over a valid drift report and, when
given, the public drift investigation bound to it, and writes report v2:
`ai_analysis_report.json` and `ai_analysis_report.md` (`write_report`). It never
changes the drift report, the drift result or `drift_detected`: the inputs are
read-only and the AI output is a separate document.

    ai-analysis --report drift_report.json --output-dir out/
    ai-analysis --report drift_report.json --investigation drift_investigation.json --output-dir out/

Without `--investigation` the report records `investigation.status =
not_available` and every drifted resource `not_investigated`
(`investigation_not_provided`). The investigation must be the **public** document
(drift_engine.investigation_public): strict JSON, leak-free, the public contract,
and bound to this exact drift report (canonical SHA-256, run id, plan timestamp,
observation window, drifted resources). Otherwise nothing is written (exit 1).

Before anything is written, the generated report is checked by the independent
verifier `ai_engine.verify.verify_report` against the drift report and the
investigation (design review D4); any problem means exit 70 and nothing written.

LLM use stays opt-in through `AI_LLM_PROVIDER` (Task 6.1). Inside GitHub
Actions the command refuses to run unless `AI_LLM_PROVIDER` is explicitly
`none`: a real LLM in CI is a separate, approval-gated decision.

This is a separate entry point on purpose: `drift-engine` never imports
`ai_engine`, so `pip install .` keeps working without the LLM stack (the
`ai` extra).

Exit codes (as for `drift-engine`):
    0   report written
    1   input rejected (unreadable or invalid drift report, a failed
        detection run whose drift status is unknown, or an unreadable,
        invalid or unbound investigation); nothing written
    2   usage error, refused environment, invalid AI configuration, or the
        `ai` extra is not installed
    70  internal error, or the generated report failed verification;
        nothing reliable was written
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
    parser.add_argument("--investigation", default=None,
                        help="public drift investigation (drift_investigation.json) bound to the drift report")
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
    from drift_engine.report_public import PublicDriftReport

    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, UnicodeDecodeError) as exc:
        return f"cannot read the drift report: {type(exc).__name__}"
    except json.JSONDecodeError as exc:
        return f"the drift report is not valid JSON (line {exc.lineno})"
    try:
        report = PublicDriftReport.model_validate(raw)
    except ValidationError as exc:
        return (f"the drift report does not match the public drift report contract ({exc.error_count()} error(s)); "
                "use the public report (drift-engine analyze --public-output), never the internal one")
    if report.outcome != "succeeded" or not isinstance(report.has_drift, bool):
        return "the detection run failed: drift status is unknown, so there is nothing to analyse"
    return raw


def _load_investigation(path: str, report: dict[str, Any]) -> dict[str, Any] | str:
    """The public investigation as a dict, or the reason it is rejected (fixed codes, never a value)."""
    from ai_engine.nodes.investigation_facts import InvestigationInputError, load_investigation
    from drift_engine import investigation_public as pub

    try:
        with open(path, "rb") as fh:
            data = fh.read(pub.MAX_INPUT_BYTES + 1)
    except OSError as exc:
        return f"cannot read the investigation: {type(exc).__name__}"
    try:
        pub.load_public(data)  # size, strict JSON, leak scan, public contract
        return load_investigation(pub.strict_json(data), report)  # binding and scope
    except pub.PublicInvestigationError as exc:
        return f"the investigation is rejected ({exc.code})"
    except InvestigationInputError as exc:
        return f"the investigation is rejected ({exc.code})"


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
        from ai_engine.verify import verify_report
    except ImportError as exc:
        _error(f"the 'ai' extra is not installed ({exc.name or exc}); install with: pip install '.[ai]'")
        return EXIT_USAGE

    loaded = _load_report(args.report)
    if isinstance(loaded, str):
        _error(f"{loaded}. Nothing was written.")
        return EXIT_REJECTED
    investigation = None
    if args.investigation is not None:
        investigation = _load_investigation(args.investigation, loaded)
        if isinstance(investigation, str):
            _error(f"{investigation}. Nothing was written.")
            return EXIT_REJECTED

    try:
        config = load_config(os.environ)
    except AiConfigError as exc:
        _error(f"invalid AI configuration: {exc}")
        return EXIT_USAGE

    try:
        state = run_analysis(loaded, config=config, investigation=investigation)
        problems = verify_report(state["report"], loaded, investigation)
        if problems:  # D4: the independent verifier must accept the report before anything is written
            _error(f"the generated report failed verification ({len(problems)} problem(s)). Nothing was written; "
                   "the drift result is unaffected.")
            return EXIT_INTERNAL_ERROR
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
          f"investigation {report['investigation']['status']}, LLM {llm['provider'] or 'none'}/{llm['status']})")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
