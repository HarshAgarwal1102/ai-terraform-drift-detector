"""`parse_drift`: deterministic state preparation from `drift_report.json` (Task 6.2).

The node validates `AiState.drift_report` against the **public** drift report
contract (`drift_engine.report_public.PublicDriftReport`, Task 9B.4A: the
internal report with identifiers withheld; schemas/drift_report.public.schema.json)
and writes `AiState.parsed_drift`. The internal report is rejected: the AI engine
only ever sees what may leave the runner.


- `resources`: every resource that is not `in_sync`, exactly as the contract's
  `DriftItem` JSON (type, address, actions, attribute changes with their
  state/real/desired views). No field is renamed, added or reinterpreted.
- `resource_types`: the sorted Terraform types of those resources.
- `resource_summaries`: one compact, value-free entry per resource, the
  initial resource list later nodes iterate over.

It defines no classification of its own: `classification`, the actions and
the attribute classes come from the report, and `is_drift` applies the
classifier's own rule (`drift_actions` present, as counted in
`summary.drifted_resources`). Severity is copied, never computed: since
classification_version 2 the report carries drift_engine.severity's rating per
change and per resource, computed by drift_engine from the raw plan, which the
AI engine never reads. That rating is authoritative; AI nodes may explain it
but must not lower or replace it.

No LLM call, no network, no Terraform. A `failed` report (drift status unknown)
is valid input: it yields an empty resource list and a warning. A report that
breaks the contract raises `DriftReportError`, whose message names the failing
fields but never their values.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypedDict

from pydantic import ValidationError

from drift_engine.logs import log_event
from drift_engine.report_public import PublicDriftItem as DriftItem
from drift_engine.report_public import PublicDriftReport as DriftReport

logger = logging.getLogger(__name__)

IN_SYNC = "in_sync"


class DriftReportError(ValueError):
    """`drift_report` is not valid against the drift_engine report contract."""


class ResourceSummary(TypedDict):
    address: str
    type: str
    classification: str
    action: str | None
    drift_action: str | None
    is_drift: bool
    severity: str
    changed_attributes: list[str]
    attribute_change_count: int
    redacted_change_count: int
    ambiguous: bool


class ParsedDrift(TypedDict):
    outcome: str
    has_drift: bool | None
    resources: list[dict[str, Any]]
    resource_types: list[str]
    resource_summaries: list[ResourceSummary]


def _contract_error(exc: ValidationError) -> DriftReportError:
    # pydantic's own message quotes input values; report only locations and error types.
    locations = sorted({".".join(str(part) for part in error["loc"]) or "<root>" for error in exc.errors()})
    shown = ", ".join(locations[:10]) + (f" (+{len(locations) - 10} more)" if len(locations) > 10 else "")
    return DriftReportError(f"drift_report does not match the public drift report contract "
                            f"({exc.error_count()} error(s) at: {shown})")


def validate_drift_report(report: Any) -> DriftReport:
    """Validate parsed JSON against the report contract."""
    if not isinstance(report, Mapping):
        raise DriftReportError("drift_report must be a JSON object")
    try:
        return DriftReport.model_validate(report)
    except ValidationError as exc:
        raise _contract_error(exc) from None


def _reject_constant(name: str) -> None:
    raise DriftReportError(f"drift_report.json contains the non-JSON constant {name}")


def load_drift_report(path: str | Path) -> dict[str, Any]:
    """Read and validate a `drift_report.json` file; return the parsed JSON object."""
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise DriftReportError(f"drift_report.json is not valid JSON (line {exc.lineno}, column {exc.colno})") from None
    validate_drift_report(report)
    return report


def summarize_resource(item: DriftItem) -> ResourceSummary:
    changes = item.attribute_changes
    return ResourceSummary(
        address=item.address,
        type=item.type,
        classification=item.classification,
        action=item.action,
        drift_action=item.drift_action,
        is_drift=item.drift_actions is not None,
        severity=item.severity.level,
        changed_attributes=sorted({change.attribute for change in changes}),
        attribute_change_count=len(changes),
        redacted_change_count=sum(1 for change in changes if change.redacted),
        ambiguous=item.ambiguous,
    )


def parse_report(report: DriftReport) -> ParsedDrift:
    targets = [item for item in report.resources if item.classification != IN_SYNC]
    return ParsedDrift(
        outcome=report.outcome,
        has_drift=report.has_drift,
        resources=[item.model_dump(mode="json") for item in targets],
        resource_types=sorted({item.type for item in targets}),
        resource_summaries=[summarize_resource(item) for item in targets],
    )


def parse_drift(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph node: populate `parsed_drift` from the `drift_report` evidence."""
    report = validate_drift_report(state.get("drift_report"))
    parsed = parse_report(report)
    update: dict[str, Any] = {"parsed_drift": parsed}
    if report.outcome == "failed":
        failure = report.failure
        where = failure.source + (f", stage {failure.stage}" if failure.stage else "")
        update["warnings"] = [f"drift detection failed ({where}): drift status unknown, no resources to analyze"]
    log_event(logger, logging.INFO, "drift_parsed", "drift report parsed for AI analysis",
              outcome=parsed["outcome"], has_drift=parsed["has_drift"],
              resources_total=len(report.resources), target_resources=len(parsed["resources"]),
              resource_types=parsed["resource_types"])
    return update
