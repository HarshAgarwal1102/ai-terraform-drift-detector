"""`drift-engine` command line (Task 4.6; logging and error handling Task 4.7).

    drift-engine analyze --plan plan.json [--manifest detection_run.json]
                         [--output report.json] [--format json|yaml|console]
                         [--color auto|always|never]
                         [--log-level debug|info|warning|error] [--log-format text|json]

Classifies plan.json (classifier.py), checks the result against the report models
(models.py), and writes it as JSON (default), YAML, or a console view that also
shows the deterministic severity (severity.py) and the configured/noise assessment
(comparator.py). Terraform's plan is the only source of truth; nothing here calls
Terraform, Azure, a network service or an LLM.

Pass the run manifest with --manifest whenever it exists: without it, the plan
exit-code and Terraform-version checks of the integrity gate are skipped (a
warning is printed and `run` holds only nulls).

Logging is off unless --log-level is given; structured log events (logs.py) then go
to standard error as text or JSON lines, never into the report. --output is
written atomically: a failed write leaves no partial file and keeps any earlier one,
and an existing report keeps its permission bits (see _write_atomic).

Exit status (process outcome only - drift is a valid result, not an error):
  0   evidence valid and classified (drift or not)
  1   evidence failed or rejected: drift status unknown (report still written)
  2   usage error
  70  the classifier's report does not satisfy the report contract; nothing is
      written and drift status is unknown. The integrity gate rejects malformed
      input first, so this indicates an engine defect (defense in depth).
  70  also: an unexpected internal error (nothing is written, drift status unknown)
  73  the output file could not be written
  130 interrupted (Ctrl-C)
  141 standard output was closed early (broken pipe)
"""

from __future__ import annotations

import argparse
import logging
import os
import stat
import sys
import tempfile

from pydantic import ValidationError

from drift_engine import __version__, comparator, severity
from drift_engine.classifier import evaluate
from drift_engine.formatters import FORMATS, render
from drift_engine.logs import LOG_FORMATS, LOG_LEVELS, configure_logging, log_event
from drift_engine.models import DriftReport

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_CONTRACT_VIOLATION = 70
EXIT_INTERNAL_ERROR = 70  # EX_SOFTWARE, as for a contract violation
EXIT_CANT_WRITE = 73
EXIT_INTERRUPTED = 130
EXIT_BROKEN_PIPE = 141


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
    analyze.add_argument("--log-level", choices=LOG_LEVELS,
                         help="emit structured logs at this level and above to standard error (default: off)")
    analyze.add_argument("--log-format", choices=LOG_FORMATS, default="text",
                         help="log line format when --log-level is set (default: text)")
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
        log_event(logger, logging.ERROR, "contract_violation", "report does not satisfy the report contract",
                  errors=exc.error_count())
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
        sys.stdout.flush()
    else:
        try:
            _write_atomic(args.output, text)
        except OSError as exc:
            log_event(logger, logging.ERROR, "output_write_failed", "cannot write the report",
                      output=args.output, error=str(exc))
            print(f"ERROR: cannot write {args.output}: {exc}", file=sys.stderr)
            return EXIT_CANT_WRITE
        log_event(logger, logging.INFO, "report_written", "report written",
                  output=args.output, format=args.format, outcome=report["outcome"])

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


def _target_mode(path: str) -> int:
    """Permission bits for the new report at `path`.

    An existing regular file keeps its own rwx bits, so a restricted report (e.g.
    0600) is never widened; setuid/setgid/sticky bits are not carried over. A file we
    may not write is refused, as an in-place write would have been. Anything else
    (no file, or a symlink, which is replaced and never written through) gets 0666
    minus the umask.
    """
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        existing = None
    if existing is not None and stat.S_ISREG(existing.st_mode):
        if not os.access(path, os.W_OK):
            raise PermissionError(f"{path} is not writable")
        return stat.S_IMODE(existing.st_mode) & 0o777
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def _write_atomic(path: str, text: str) -> None:
    """Write `path` via a temporary file in the same directory and an atomic rename.

    On any failure the temporary file is removed and an existing `path` is left as it
    was (content and permissions). Permissions follow _target_mode. Being a rename,
    it needs a writable directory, gives `path` a new inode (other hard links keep the
    old content) and replaces a symlink at `path` rather than writing through it.
    """
    mode = _target_mode(path)
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".drift-engine-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _stdout_closed() -> int:
    """Standard output went away (e.g. piped into `head`): stop quietly."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())  # so the interpreter's final flush cannot fail again
    except (OSError, ValueError, AttributeError):
        pass
    return EXIT_BROKEN_PIPE


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.log_level is not None:
        configure_logging(args.log_level, args.log_format)
    try:
        return analyze(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return EXIT_INTERRUPTED
    except BrokenPipeError:
        return _stdout_closed()
    except Exception as exc:  # last resort: never a traceback-only exit, never "no drift"
        log_event(logger, logging.ERROR, "unexpected_error", "unexpected internal error",
                  error_type=type(exc).__name__)
        logger.debug("traceback", exc_info=True)
        print(
            f"INTERNAL ERROR: unexpected {type(exc).__name__}: {exc}\n"
            "  Drift status is UNKNOWN - this must not be treated as 'no drift'.",
            file=sys.stderr,
        )
        return EXIT_INTERNAL_ERROR


if __name__ == "__main__":
    sys.exit(main())
