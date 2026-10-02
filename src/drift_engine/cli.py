"""`drift-engine` command line (Task 4.6).

    drift-engine analyze --plan plan.json [--manifest detection_run.json]
                         [--output report.json] [--format json|yaml|console]
                         [--color auto|always|never]

Classifies plan.json (classifier.py), checks the result against the report models
(models.py), and writes it as JSON (default), YAML, or a console view that also
shows the deterministic severity (severity.py) and the configured/noise assessment
(comparator.py). Terraform's plan is the only source of truth; nothing here calls
Terraform, Azure, a network service or an LLM.

Pass the run manifest with --manifest whenever it exists: without it, the plan
exit-code and Terraform-version checks of the integrity gate are skipped (a
warning is printed and `run` holds only nulls).

Exit status (process outcome only - drift is a valid result, not an error):
  0   evidence valid and classified (drift or not)
  1   evidence failed or rejected: drift status unknown (report still written)
  2   usage error
  70  the classifier's report does not satisfy the report contract; nothing is
      written and drift status is unknown. The integrity gate rejects malformed
      input first, so this indicates an engine defect (defense in depth).
  73  the output file could not be written
"""

from __future__ import annotations

import argparse
import os
import sys

from pydantic import ValidationError

from drift_engine import __version__, comparator, severity
from drift_engine.classifier import evaluate
from drift_engine.formatters import FORMATS, render
from drift_engine.models import DriftReport

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_CONTRACT_VIOLATION = 70
EXIT_CANT_WRITE = 73


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="drift-engine", description="Deterministic Terraform drift engine.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    analyze = commands.add_parser(
        "analyze",
        help="classify a Terraform plan.json and write the drift report",
        description="Classify a Terraform plan.json (terraform show -json) and write the drift report.",
    )
    analyze.add_argument("--plan", required=True, help="plan.json written by terraform show -json")
    analyze.add_argument("--manifest", help="run manifest (detection_run.json); enables the full integrity gate")
    analyze.add_argument("--output", help="write the report to this file instead of standard output")
    analyze.add_argument("--format", choices=FORMATS, default="json", help="output format (default: json)")
    analyze.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                         help="ANSI colors for --format console (default: auto)")
    return parser


def _use_color(choice: str, to_terminal: bool) -> bool:
    if choice == "always":
        return True
    if choice == "never":
        return False
    return to_terminal and sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def analyze(args: argparse.Namespace) -> int:
    if args.manifest is None:
        print("WARNING: no --manifest given: plan exit-code and Terraform-version checks are skipped.",
              file=sys.stderr)

    evaluation = evaluate(args.plan, args.manifest)
    try:
        report = DriftReport.model_validate(evaluation.report).model_dump(mode="json")
    except ValidationError as exc:
        print(
            "ERROR: the report does not satisfy the report contract (schemas/drift_report.schema.json); "
            "no report was written.\n"
            "  The integrity gate accepted this plan, so this is an engine defect; please report it.\n"
            "  Drift status is UNKNOWN - this must not be treated as 'no drift'.\n"
            f"{exc}",
            file=sys.stderr,
        )
        return EXIT_CONTRACT_VIOLATION

    ratings = None
    if evaluation.parsed is not None:
        comparisons = comparator.compare_plan(evaluation.parsed, comparator.configured_attributes(evaluation.plan))
        classes = {r["address"]: r["classification"] for r in report["resources"]}
        ratings = {r.address: r for r in severity.plan_severity(evaluation.parsed, comparisons, classes)}

    text = render(args.format, report, ratings, _use_color(args.color, args.output is None))
    if args.output is None:
        sys.stdout.write(text)
    else:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            print(f"ERROR: cannot write {args.output}: {exc}", file=sys.stderr)
            return EXIT_CANT_WRITE

    if report["outcome"] != "succeeded":
        failure = report["failure"]
        print(
            f"CLASSIFICATION FAILED [{failure['source']}/{failure['stage']}]: {failure['reason']}\n"
            "  Drift status is UNKNOWN - this must not be treated as 'no drift'.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    if args.output is not None:
        counts = ", ".join(f"{k}={v}" for k, v in report["summary"]["classification_counts"].items())
        top = severity.highest(r.severity for r in ratings.values()) if ratings else severity.INFO
        print(f"has_drift={str(report['has_drift']).lower()}  [{counts}]  severity={top}")
        print(f"Report: {args.output}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return analyze(args)


if __name__ == "__main__":
    sys.exit(main())
