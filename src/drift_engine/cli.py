"""`drift-engine` command line (Task 4.6; logging and error handling Task 4.7).

    drift-engine analyze --plan plan.json [--manifest detection_run.json]
                         [--output report.json] [--format json|yaml|console]
                         [--public-output drift_report.public.json]
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

With --public-output, the public drift report (Task 9B.4A, report_public.py) is
projected from the same report, verified independently and scanned before anything is
written. If that fails, nothing at all is written and the exit status is 70 with the
fixed code `public_projection_failed:<code>` (drift status unknown): the internal
report is never published in its place. Without the flag `analyze` is unchanged.

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
  70  also: --public-output could not be projected, verified or written
      (`public_projection_failed:<code>`, drift status unknown)
  73  the output file could not be written
  130 interrupted (Ctrl-C)
  141 standard output was closed early (broken pipe)

    drift-engine activity-logs --plan plan.json --manifest detection_run.json
                               [--lookback-days N] [--window-start TIME] [--not-before TIME]
                               [--output activity_log_evidence.json]
                               [--log-level ...] [--log-format text|json]

Collects Azure Activity Log evidence for the drifted resources of the same plan
(activity_logs.py, Task 7.1; evidence v2, Task 9B.1): read-only queries with the
current `az login` session, needing the `[azure]` extra only when there is drift to
look up. It is a manual / local collector; the drift workflow does not run it. The
evidence may hold callers (personal data): a new --output file is created readable
by its owner only. It never changes the drift report or its exit status.
--window-start sets an explicit run-level window start instead of the lookback;
--not-before refuses (no query, failed evidence) a collection started earlier. Both
take UTC ISO 8601 times (`Z` or `+00:00`). The pipeline's client ID for
`pipeline_identity` is read from the DRIFT_ENGINE_PIPELINE_PRINCIPAL environment
variable (never from the command line) and never written.

Exit status:
  0   evidence complete (every drifted resource was queried completely)
  1   evidence incomplete or failed (still written; see `outcome` and `scopes`)
  2   usage error
  70  unexpected internal error (nothing written)
  73  the output file could not be written
  130 / 141 as above

    drift-engine attribute --report drift_classification.json --evidence activity_log_evidence.json
                           [--output drift_attribution.json] [--log-level ...] [--log-format text|json]

Correlates the drift report with the Activity Log evidence of the same run
(attribution.py, Task 7.2) and writes drift_attribution.json. Deterministic: no
Azure, network or clock. `confirmed` only ever means "Azure recorded caller X
performing the successful delete of this exact resource under the correlation
rules"; everything else is `unknown` with a reason code. Confirmed callers are
personal data: a new --output file is created readable by its owner only, and the
summary line never shows a caller. Before anything is written, the result is
re-checked against the evidence it names. It never changes the drift report.

Exit status:
  0   attribution complete (every drifted resource evaluated against complete,
      settled evidence; `unknown` results are valid results)
  1   attribution incomplete or failed (still written; see `outcome` and `failure`)
  2   usage error
  70  the result failed its re-check against the evidence, or an unexpected
      internal error (nothing written)
  73  the output file could not be written
  130 / 141 as above

    drift-engine investigate --plan plan.json --manifest detection_run.json --report drift_report.json
                             [--anchors DIR --repository OWNER/NAME] [--lookback-days N]
                             [--output drift_investigation.restricted.json]
                             [--evidence-output activity_log_evidence.json]
                             [--log-level ...] [--log-format text|json]

Investigates the drifted resources of one run (investigation.py, Task 9B.2): checks
that --report is the report `analyze` writes for this plan and manifest, selects the
trusted last-in-sync anchors from --anchors (subdirectories with run.json and
drift_report.json; needs --repository), waits until the run's finished_at + 10 min
when there is something to query, collects the Activity Log (read-only, current az
login session; the pipeline client ID comes from DRIFT_ENGINE_PIPELINE_PRINCIPAL),
re-collects every 2 min up to finished_at + 20 min while a drifted resource has no
capable operation, and writes the restricted investigation (callers, resource IDs:
created readable by its owner only). Before anything is written, the result is
re-checked against the evidence it names. It never changes the drift report.

Exit status: 0 complete; 1 incomplete or failed (still written); 2 usage error; 70
re-check failure or internal error (nothing written); 73 write error; 130 / 141.
--public-output also writes the public drift_investigation.json (Task 9B.3): it is
projected, re-derived from the restricted document and leak-scanned first; if any
check fails nothing is written (exit 70).

    drift-engine investigation-check --public drift_investigation.json [--report drift_report.json]

Validates a public investigation (contract, leak scan, and the binding to --report).
Exit 0 valid, 1 rejected (a fixed code; never the offending value), 2 usage.

    drift-engine who --public drift_investigation.json --terraform state.json --output-dir DIR
                     [--report drift_report.json]

Local only (refuses in GitHub Actions): looks up, with the current az login session
(read-only), the caller Azure recorded for each operation of a public investigation,
prints it and writes DIR/who_evidence.local.json (0600; DIR created 0700). A recorded
caller of an operation is evidence, never a statement of who caused the drift. Exit 0
every operation matched, 1 otherwise, 2 usage or refusal, 70 internal, 73 write error.

Restricted output (activity-logs, attribute, investigate) is never written to standard
output in GitHub Actions (--output is required there), and their unexpected errors
show the exception type only.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import stat
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from drift_engine import (
    __version__, activity_logs, attribution, comparator, investigation, investigation_public, report_public, severity,
    who,
)
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
    analyze.add_argument("--public-output",
                         help="also write the public drift report (identifiers withheld, Task 9B.4A) to this file; "
                              "nothing is written if it cannot be projected and verified")
    analyze.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                         help="ANSI colors for --format console (default: auto)")
    analyze.add_argument("--log-level", choices=LOG_LEVELS,
                         help="emit structured logs at this level and above to standard error (default: off)")
    analyze.add_argument("--log-format", choices=LOG_FORMATS, default="text",
                         help="log line format when --log-level is set (default: text)")

    logs = commands.add_parser(
        "activity-logs",
        help="collect Azure Activity Log evidence for the drifted resources (read-only)",
        description=(
            "Query the Azure Activity Log (read-only, current az login session) for the resource groups "
            "of the drifted resources in plan.json and write activity_log_evidence.json. "
            "Needs the [azure] extra when there is drift to look up. Does not attribute changes."
        ),
    )
    logs.add_argument("--plan", required=True, help="plan.json written by terraform show -json")
    logs.add_argument("--manifest", required=True, help="run manifest (detection_run.json) of the same run")
    logs.add_argument("--lookback-days", type=_lookback_days, default=activity_logs.DEFAULT_LOOKBACK_DAYS,
                      help=f"query window in days, 1-{activity_logs.MAX_LOOKBACK_DAYS} "
                           f"(default: {activity_logs.DEFAULT_LOOKBACK_DAYS})")
    logs.add_argument("--window-start", type=_utc_time,
                      help="explicit run-level window start (UTC ISO 8601), at most "
                           f"{activity_logs.MAX_LOOKBACK_DAYS} days back; replaces --lookback-days")
    logs.add_argument("--not-before", type=_utc_time,
                      help="earliest allowed query time (UTC ISO 8601); an earlier run queries nothing")
    logs.add_argument("--output", help="write the evidence to this file instead of standard output")
    logs.add_argument("--log-level", choices=LOG_LEVELS,
                      help="emit structured logs at this level and above to standard error (default: off)")
    logs.add_argument("--log-format", choices=LOG_FORMATS, default="text",
                      help="log line format when --log-level is set (default: text)")

    attribute = commands.add_parser(
        "attribute",
        help="correlate drift with Activity Log evidence (deterministic, no Azure access)",
        description=(
            "Correlate a drift report with the activity_log_evidence.json of the same run and write "
            "drift_attribution.json. Only an external deletion can be confirmed, as the caller Azure recorded "
            "for the successful delete; everything else is unknown with a reason code."
        ),
    )
    attribute.add_argument("--report", required=True, help="drift report (JSON) written by drift-engine analyze")
    attribute.add_argument("--evidence", required=True,
                           help="activity_log_evidence.json written by drift-engine activity-logs")
    attribute.add_argument("--output", help="write the attribution to this file instead of standard output")
    attribute.add_argument("--log-level", choices=LOG_LEVELS,
                           help="emit structured logs at this level and above to standard error (default: off)")
    attribute.add_argument("--log-format", choices=LOG_FORMATS, default="text",
                           help="log line format when --log-level is set (default: text)")

    investigate_cmd = commands.add_parser(
        "investigate",
        help="investigate drifted resources against the Azure Activity Log (read-only; restricted output)",
        description=(
            "Correlate the drifted resources of one run with Azure Activity Log evidence (correlation v2, "
            "last-in-sync anchor) and write the restricted drift_investigation.restricted.json. Never "
            "confirms update drift; recorded callers are evidence, not attribution."
        ),
    )
    investigate_cmd.add_argument("--plan", required=True, help="plan.json written by terraform show -json")
    investigate_cmd.add_argument("--manifest", required=True, help="run manifest (detection_run.json) of the same run")
    investigate_cmd.add_argument("--report", required=True,
                                 help="internal drift report (JSON) written by drift-engine analyze for the same run")
    investigate_cmd.add_argument("--anchors", help="directory of anchor candidates (needs --repository)")
    investigate_cmd.add_argument("--repository", help="the current repository, OWNER/NAME (anchor trust check)")
    investigate_cmd.add_argument("--lookback-days", type=_lookback_days, default=activity_logs.DEFAULT_LOOKBACK_DAYS,
                                 help=f"lookback window without an anchor, 1-{activity_logs.MAX_LOOKBACK_DAYS} "
                                      f"(default: {activity_logs.DEFAULT_LOOKBACK_DAYS})")
    investigate_cmd.add_argument("--output", help="write the investigation to this file instead of standard output")
    investigate_cmd.add_argument("--evidence-output", help="also write the Activity Log evidence it is bound to")
    investigate_cmd.add_argument("--public-output",
                                 help="also write the public drift_investigation.json (checked before writing)")
    investigate_cmd.add_argument("--log-level", choices=LOG_LEVELS,
                                 help="emit structured logs at this level and above to standard error (default: off)")
    investigate_cmd.add_argument("--log-format", choices=LOG_FORMATS, default="text",
                                 help="log line format when --log-level is set (default: text)")

    check = commands.add_parser(
        "investigation-check",
        help="validate a public drift_investigation.json (contract, leak scan, binding)",
        description="Validate a public investigation: strict contract, fail-closed leak scan and, with --report, "
                    "its binding to that drift report.",
    )
    check.add_argument("--public", required=True, help="public drift_investigation.json")
    check.add_argument("--report", help="public drift report (JSON, analyze --public-output) it must be bound to")
    check.add_argument("--log-level", choices=LOG_LEVELS,
                       help="emit structured logs at this level and above to standard error (default: off)")
    check.add_argument("--log-format", choices=LOG_FORMATS, default="text",
                       help="log line format when --log-level is set (default: text)")

    who_cmd = commands.add_parser(
        "who",
        help="local only: look up the recorded caller of public investigation operations (read-only)",
        description="Local only (refuses in GitHub Actions). Re-query the Azure Activity Log for each operation of "
                    "a public investigation and show the caller Azure recorded. Writes only "
                    "who_evidence.local.json (0600) under --output-dir.",
    )
    who_cmd.add_argument("--public", required=True, help="public drift_investigation.json")
    who_cmd.add_argument("--terraform", required=True,
                         help="terraform show -json state (or plan JSON) mapping addresses to ARM IDs")
    who_cmd.add_argument("--output-dir", required=True, help="directory for who_evidence.local.json (local only)")
    who_cmd.add_argument("--report", help="public drift report (JSON) the public file must be bound to")
    who_cmd.add_argument("--log-level", choices=LOG_LEVELS,
                         help="emit structured logs at this level and above to standard error (default: off)")
    who_cmd.add_argument("--log-format", choices=LOG_FORMATS, default="text",
                         help="log line format when --log-level is set (default: text)")
    return parser


def _lookback_days(text: str) -> int:
    try:
        value = int(text, 10)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {text!r}") from None
    if not 1 <= value <= activity_logs.MAX_LOOKBACK_DAYS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {activity_logs.MAX_LOOKBACK_DAYS}")
    return value


def _utc_time(text: str) -> datetime:
    moment = activity_logs.parse_timestamp(text)
    if moment is None:
        raise argparse.ArgumentTypeError(f"not a UTC ISO 8601 time (Z or +00:00): {text!r}")
    return moment


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

    public_text = None
    if args.public_output is not None:
        try:
            public_text = report_public.publish_report(report, evaluation.plan or {}, _published_manifest(args, report))
        except Exception as exc:  # fixed codes only: an exception message could echo a withheld value
            code = exc.code if isinstance(exc, report_public.PublicReportError) else "verification_failed"
            log_event(logger, logging.ERROR, "public_projection_failed", "public drift report not produced",
                      code=code)
            print(f"ERROR: public_projection_failed:{code}; nothing was written.\n"
                  "  Drift status is UNKNOWN - this must not be treated as 'no drift'.", file=sys.stderr)
            return EXIT_INTERNAL_ERROR

    if public_text is not None:  # written first, so a failure leaves nothing behind
        try:
            _write_atomic(args.public_output, public_text)
        except OSError as exc:
            log_event(logger, logging.ERROR, "public_projection_failed", "public drift report not written",
                      code="write_failed", error_type=type(exc).__name__)
            print("ERROR: public_projection_failed:write_failed; nothing was written.\n"
                  "  Drift status is UNKNOWN - this must not be treated as 'no drift'.", file=sys.stderr)
            return EXIT_INTERNAL_ERROR

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
            if public_text is not None:  # never leave a public report without its internal source
                with contextlib.suppress(OSError):
                    os.unlink(args.public_output)
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


def _published_manifest(args: argparse.Namespace, report: dict) -> Any:
    """The run manifest published beside the public report (scanned too); None when there is none. A
    succeeded report whose manifest cannot be read again fails closed."""
    if args.manifest is None:
        return None
    try:
        with open(args.manifest, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, UnicodeDecodeError, ValueError):
        if report["outcome"] == "succeeded":
            raise report_public.PublicReportError("scan_failed") from None
        return None


def _refuse_restricted_stdout(args: argparse.Namespace) -> bool:
    """Restricted documents never go to standard output in GitHub Actions (public logs)."""
    if os.environ.get("GITHUB_ACTIONS") == "true" and args.output is None:
        print("ERROR: in GitHub Actions this command writes restricted data and needs --output FILE; "
              "it never writes to standard output.", file=sys.stderr)
        return True
    return False


def _read_input(path: str, limit: int) -> bytes | None:
    try:
        with open(path, "rb") as fh:
            data = fh.read(limit + 1)
    except OSError:
        return None
    return data if len(data) <= limit else None


def _activity_log_source() -> activity_logs.ActivityLogSource:
    """The Azure source; the SDK is imported only if a query is actually made."""
    return activity_logs.AzureMonitorSource()


def collect_activity_logs(args: argparse.Namespace) -> int:
    if _refuse_restricted_stdout(args):
        return EXIT_USAGE
    evidence = activity_logs.collect_evidence(
        args.plan,
        args.manifest,
        source=_activity_log_source(),
        queried_at=datetime.now(timezone.utc),
        lookback_days=args.lookback_days,
        window_start=args.window_start,
        not_before=args.not_before,
        pipeline_principal=os.environ.get(activity_logs.PIPELINE_PRINCIPAL_ENV, "").strip() or None,
    )
    text = activity_logs.render_evidence(evidence)
    if args.output is None:
        sys.stdout.write(text)
        sys.stdout.flush()
    else:
        try:
            _write_atomic(args.output, text, private=True)
        except OSError as exc:
            log_event(logger, logging.ERROR, "output_write_failed", "cannot write the Activity Log evidence",
                      output=args.output, error=str(exc))
            print(f"ERROR: cannot write {args.output}: {exc}", file=sys.stderr)
            return EXIT_CANT_WRITE
        log_event(logger, logging.INFO, "evidence_written", "Activity Log evidence written",
                  output=args.output, outcome=evidence.outcome)

    statuses = ", ".join(f"{k}={v}" for k, v in sorted(Counter(t.status for t in evidence.targets).items()))
    summary = (f"activity_log_outcome={evidence.outcome}  targets={len(evidence.targets)} [{statuses}]  "
               f"scopes={len(evidence.scopes)}  events={len(evidence.events)}")
    if evidence.outcome != "complete":
        reason = evidence.failure.reason if evidence.failure is not None else "incomplete"
        errors = sorted({s.error.code for s in evidence.scopes if s.error is not None})
        print(
            f"ACTIVITY LOG EVIDENCE {evidence.outcome.upper()} [{reason}]"
            + (f": {', '.join(errors)}" if errors else "") + "\n"
            "  Drift detection results are unaffected; this evidence cannot confirm or rule out any change.",
            file=sys.stderr,
        )
    if args.output is not None:
        print(summary)
        print(f"Evidence: {args.output}")
    return EXIT_OK if evidence.outcome == "complete" else EXIT_FAILED


def attribute_drift(args: argparse.Namespace) -> int:
    if _refuse_restricted_stdout(args):
        return EXIT_USAGE
    document, evidence_bytes = attribution.attribute_files(args.report, args.evidence)
    problems = attribution.verify_against_evidence(document, evidence_bytes)
    if problems:
        log_event(logger, logging.ERROR, "attribution_recheck_failed",
                  "attribution does not match the evidence it names", problems=len(problems))
        print(
            "ERROR: the attribution does not match the evidence it names; nothing was written.\n"
            "  This indicates an engine defect; please report it. Drift detection results are unaffected.",
            file=sys.stderr,
        )
        return EXIT_CONTRACT_VIOLATION
    text = attribution.render_attribution(document)
    if args.output is None:
        sys.stdout.write(text)
        sys.stdout.flush()
    else:
        try:
            _write_atomic(args.output, text, private=True)
        except OSError as exc:
            log_event(logger, logging.ERROR, "output_write_failed", "cannot write the attribution",
                      output=args.output, error=str(exc))
            print(f"ERROR: cannot write {args.output}: {exc}", file=sys.stderr)
            return EXIT_CANT_WRITE
        log_event(logger, logging.INFO, "attribution_written", "attribution written",
                  output=args.output, outcome=document.outcome)

    statuses = Counter(r.attribution.status for r in document.resources)
    summary = (f"attribution_outcome={document.outcome}  resources={len(document.resources)} "
               f"[confirmed={statuses['confirmed']}, unknown={statuses['unknown']}]")
    if document.outcome != "complete":
        reason = document.failure.reason if document.failure is not None else "incomplete"
        print(f"ATTRIBUTION {document.outcome.upper()} [{reason}]\n"
              "  Drift detection results are unaffected.", file=sys.stderr)
    if args.output is not None:
        print(summary)
        print(f"Attribution: {args.output}")
    return EXIT_OK if document.outcome == "complete" else EXIT_FAILED


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def investigate_drift(args: argparse.Namespace) -> int:
    if _refuse_restricted_stdout(args):
        return EXIT_USAGE
    if args.anchors is not None and not args.repository:
        print("ERROR: --anchors needs --repository OWNER/NAME", file=sys.stderr)
        return EXIT_USAGE
    report_bytes = _read_input(args.report, investigation.MAX_INPUT_BYTES)
    result = investigation.investigate(
        args.plan, args.manifest, report_bytes,
        source=_activity_log_source(), clock=_now, sleep=_sleep,
        anchors_dir=args.anchors, repository=args.repository,
        pipeline_principal=os.environ.get(activity_logs.PIPELINE_PRINCIPAL_ENV, "").strip() or None,
        lookback_days=args.lookback_days,
    )
    document = result.document
    problems = investigation.verify_against_evidence(document, result.evidence_bytes)
    if problems:
        log_event(logger, logging.ERROR, "investigation_recheck_failed",
                  "investigation does not match the evidence it names", problems=len(problems))
        print(
            "ERROR: the investigation does not match the evidence it names; nothing was written.\n"
            "  This indicates an engine defect; please report it. Drift detection results are unaffected.",
            file=sys.stderr,
        )
        return EXIT_CONTRACT_VIOLATION
    text = investigation.render_investigation(document)
    public_text = None
    if args.public_output is not None:
        public_text, public_problems = investigation.publish(document)
        if public_problems:
            log_event(logger, logging.ERROR, "public_projection_rejected",
                      "public investigation failed its checks", problems=len(public_problems))
            print("ERROR: the public investigation failed its contract, consistency or leak checks; nothing was "
                  "written.\n  This indicates an engine defect; please report it. Drift detection results are "
                  "unaffected.", file=sys.stderr)
            return EXIT_CONTRACT_VIOLATION
    try:
        if args.evidence_output is not None and result.evidence_bytes is not None:
            _write_atomic(args.evidence_output, result.evidence_bytes.decode("utf-8"), private=True)
        if args.output is None:
            sys.stdout.write(text)
            sys.stdout.flush()
        else:
            _write_atomic(args.output, text, private=True)
        if public_text is not None:
            _write_atomic(args.public_output, public_text)
    except OSError as exc:
        log_event(logger, logging.ERROR, "output_write_failed", "cannot write the investigation",
                  error_type=type(exc).__name__)
        print(f"ERROR: cannot write the investigation ({type(exc).__name__}).", file=sys.stderr)
        return EXIT_CANT_WRITE

    verdicts = Counter(r.verdict for r in document.resources)
    links = Counter(r.property_link for r in document.resources)
    summary = (f"investigation_outcome={document.outcome}  resources={len(document.resources)} "
               f"[{', '.join(f'{k}={v}' for k, v in sorted(verdicts.items()))}]  "
               f"property_links=[{', '.join(f'{k}={v}' for k, v in sorted(links.items()))}]")
    if document.outcome != "complete":
        reason = document.failure.reason if document.failure is not None else "incomplete"
        print(f"INVESTIGATION {document.outcome.upper()} [{reason}]\n"
              "  Drift detection results are unaffected.", file=sys.stderr)
    if args.output is not None:
        print(summary)
        print(f"Investigation: {args.output}")
    if public_text is not None:
        print(f"Public investigation: {args.public_output}")
    return EXIT_OK if document.outcome == "complete" else EXIT_FAILED


def check_public_investigation(args: argparse.Namespace) -> int:
    data = _read_input(args.public, investigation_public.MAX_INPUT_BYTES)
    try:
        if data is None:
            raise investigation_public.PublicInvestigationError("invalid_json")
        document = investigation_public.load_public(data)
        if args.report is not None:
            report = _read_input(args.report, investigation_public.MAX_INPUT_BYTES)
            if report is None:
                raise investigation_public.PublicInvestigationError("binding_mismatch")
            investigation_public.check_binding(document, report)
    except investigation_public.PublicInvestigationError as exc:
        kinds = Counter(f.rsplit(": ", 1)[-1] for f in exc.findings)
        detail = f" ({', '.join(f'{k}={v}' for k, v in sorted(kinds.items()))})" if kinds else ""
        log_event(logger, logging.WARNING, "public_investigation_rejected", "public investigation rejected",
                  code=exc.code, findings=len(exc.findings))
        print(f"PUBLIC INVESTIGATION REJECTED [{exc.code}]{detail}", file=sys.stderr)
        return EXIT_FAILED
    verdicts = Counter(r.verdict for r in document.resources)
    print(f"public_investigation=valid  outcome={document.outcome}  resources={len(document.resources)} "
          f"[{', '.join(f'{k}={v}' for k, v in sorted(verdicts.items()))}]")
    return EXIT_OK


def who_lookup(args: argparse.Namespace) -> int:
    try:
        who.refuse_in_ci(os.environ)
    except who.WhoRefused as exc:
        print(f"ERROR: {exc}.", file=sys.stderr)
        return EXIT_USAGE
    public_bytes = _read_input(args.public, investigation_public.MAX_INPUT_BYTES)
    terraform_bytes = _read_input(args.terraform, investigation.MAX_INPUT_BYTES)
    report_bytes = _read_input(args.report, investigation_public.MAX_INPUT_BYTES) if args.report else None
    if public_bytes is None or terraform_bytes is None or (args.report and report_bytes is None):
        print("ERROR: cannot read an input file.", file=sys.stderr)
        return EXIT_USAGE
    target = os.path.join(args.output_dir, who.WHO_FILE)
    if os.path.islink(args.output_dir) or os.path.islink(target):
        print("ERROR: refusing to write through a symbolic link.", file=sys.stderr)
        return EXIT_CANT_WRITE
    result = who.run_who(public_bytes, terraform_bytes, source=_activity_log_source(), now=_now(),
                         report_bytes=report_bytes)
    document = result.document
    try:
        os.makedirs(args.output_dir, mode=0o700, exist_ok=True)
        _write_atomic(target, json.dumps(document, indent=2, sort_keys=True) + "\n", private=True)
    except OSError as exc:
        print(f"ERROR: cannot write {who.WHO_FILE} ({type(exc).__name__}).", file=sys.stderr)
        return EXIT_CANT_WRITE
    if document["failure"] is not None:
        print(f"WHO LOOKUP FAILED [{document['failure']['code']}: {document['failure']['detail']}]", file=sys.stderr)
        return EXIT_FAILED
    for item in document["results"]:
        callers = ", ".join(item["callers"]) if item["callers"] else "(none recorded)"
        line = f"{item['address']} {item['op_id']} {item['operation_name']} {item['start']}  {item['status']}"
        print(f"{line}  recorded caller: {callers}" if item["status"] == "matched" else line)
    print("A recorded caller is the identity Azure logged for that operation; it is not proof of who caused the drift.")
    print(f"Local WHO evidence: {target}")
    return EXIT_OK if result.complete else EXIT_FAILED


def _target_mode(path: str, private: bool = False) -> int:
    """Permission bits for the new report at `path`.

    An existing regular file keeps its own rwx bits, so a restricted report (e.g.
    0600) is never widened; setuid/setgid/sticky bits are not carried over. A file we
    may not write is refused, as an in-place write would have been. Anything else
    (no file, or a symlink, which is replaced and never written through) gets 0666
    minus the umask, or 0600 when `private` (files that may hold personal data).
    """
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        existing = None
    if existing is not None and stat.S_ISREG(existing.st_mode):
        if not os.access(path, os.W_OK):
            raise PermissionError(f"{path} is not writable")
        return stat.S_IMODE(existing.st_mode) & 0o777
    if private:
        return 0o600
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def _write_atomic(path: str, text: str, private: bool = False) -> None:
    """Write `path` via a temporary file in the same directory and an atomic rename.

    On any failure the temporary file is removed and an existing `path` is left as it
    was (content and permissions). Permissions follow _target_mode. Being a rename,
    it needs a writable directory, gives `path` a new inode (other hard links keep the
    old content) and replaces a symlink at `path` rather than writing through it.
    """
    mode = _target_mode(path, private)
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
    command = {"activity-logs": collect_activity_logs, "attribute": attribute_drift,
               "investigate": investigate_drift, "investigation-check": check_public_investigation,
               "who": who_lookup}.get(args.command, analyze)
    try:
        return command(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return EXIT_INTERRUPTED
    except BrokenPipeError:
        return _stdout_closed()
    except Exception as exc:  # last resort: never a traceback-only exit, never "no drift"
        log_event(logger, logging.ERROR, "unexpected_error", "unexpected internal error",
                  error_type=type(exc).__name__)
        if command not in _RESTRICTED_COMMANDS:  # a traceback carries the exception message
            logger.debug("traceback", exc_info=True)
        consequence = {
            collect_activity_logs: "  No Activity Log evidence was written; drift detection results are unaffected.",
            attribute_drift: "  No attribution was written; drift detection results are unaffected.",
            investigate_drift: "  No investigation was written; drift detection results are unaffected.",
            check_public_investigation: "  The public investigation was not validated.",
            who_lookup: "  No WHO evidence was written.",
        }.get(command, "  Drift status is UNKNOWN - this must not be treated as 'no drift'.")
        if command in _RESTRICTED_COMMANDS:
            # restricted data: an exception message can echo input values (callers, IDs)
            print(f"INTERNAL ERROR: unexpected {type(exc).__name__}.\n{consequence}", file=sys.stderr)
        else:
            print(f"INTERNAL ERROR: unexpected {type(exc).__name__}: {exc}\n{consequence}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR


_RESTRICTED_COMMANDS = frozenset({collect_activity_logs, attribute_drift, investigate_drift,
                                  check_public_investigation, who_lookup})


if __name__ == "__main__":
    sys.exit(main())
