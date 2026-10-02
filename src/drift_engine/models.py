"""Typed drift report models (Task 4.3).

Pydantic models for the drift report written by scripts/detect_drift.py
(`drift_classification.json`, which the plan calls `drift_report.json`). They mirror
schemas/drift_report.schema.json (Task 3.5) field for field: there is one report
contract, and these models are its Python form, not a second format.

  DriftReport      the whole document
  DriftSummary     `summary`
  DriftItem        one entry of `resources`
  AttributeChange  one entry of `resources[].attribute_changes`
  ChangeSeverity, ChangeAssessment, ResourceSeverity
                   the deterministic severity (drift_engine.severity) and the
                   comparator assessment it rests on (classification_version 2)

Every model is strict (no type coercion: "1" is not 1, 1 is not True), rejects
unknown fields and is immutable. Reports load with `DriftReport.model_validate_json`
or `model_validate`, and `model_dump(mode="json")` returns exactly the classifier's
JSON. Field names follow the report; the attribute class is exposed as
`class_` because `class` is a Python keyword, and is read and written as "class".
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, JsonValue, model_validator

CLASSIFICATION_VERSION = "2"

ResourceClass = Literal[
    "in_sync",
    "external_drift",
    "external_deletion",
    "converged_drift",
    "config_change",
    "resource_added",
    "resource_removed",
    "drift_and_config_change",
    "undetermined",
]
AttributeClass = Literal[
    "drifted",
    "drifted_converged",
    "config_changed",
    "drifted_and_config_changed",
    "unknown_until_apply",
]
Action = Literal["no-op", "read", "create", "update", "delete", "replace", "unrecognized"]
Outcome = Literal["succeeded", "failed"]
Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
AssessmentCategory = Literal["configured", "unconfigured", "noise", "undetermined"]
FailureSource = Literal["detection_run", "classifier"]

Count = Annotated[int, Field(ge=0)]
TerraformActions = Annotated[list[str], Field(min_length=1)]
ClassificationCounts = dict[ResourceClass, Count]
SeverityCounts = dict[Severity, Count]


def _exactly(expected: bool):
    def check(value: bool) -> bool:
        if value is not expected:
            raise ValueError(f"must be {str(expected).lower()}")
        return value
    return AfterValidator(check)


# Literal[False] would accept 0 (0 == False); a strict bool with a value check does not.
FalseFlag = Annotated[bool, _exactly(False)]
TrueFlag = Annotated[bool, _exactly(True)]


class _Model(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )


# ---------------------------------------------------------------------------
# Attribute detail
# ---------------------------------------------------------------------------

class ValueView(_Model):
    """A view that holds a value; `None` is a value (JSON null), not absence."""

    status: Literal["value"]
    value: JsonValue


class StatusView(_Model):
    """A view without a value: absent from that view, unknown until apply, or redacted."""

    status: Literal["absent", "unknown", "redacted"]


ViewValue = Annotated[Union[ValueView, StatusView], Field(discriminator="status")]


class ChangeSeverity(_Model):
    """Deterministic severity of one change (drift_engine.severity). Authoritative:
    consumers may explain it but never re-derive, lower or replace it.

    `rules` are the ids of the SEVERITY_RULES that set the level; empty for proven
    noise (INFO) and for a significant change no rule matches (MEDIUM).
    """

    level: Severity
    rules: list[str]


class ChangeAssessment(_Model):
    """The comparator's assessment of one change (Task 4.4) that the severity rests on.

    `noise_rule` is the matching noise rule id, recorded even when configuration
    overrides it (then `category` is "configured").
    """

    category: AssessmentCategory
    noise_rule: str | None


class AttributeChange(_Model):
    """One changed leaf path with its state (S), real (R) and desired (D) views.

    `class_` is None for create/delete, where the spec §6.2 rule does not apply.
    """

    path: Annotated[list[str], Field(min_length=1)]
    attribute: str
    class_: AttributeClass | None = Field(alias="class")
    state: ViewValue
    real: ViewValue
    desired: ViewValue
    redacted: bool
    severity: ChangeSeverity
    assessment: ChangeAssessment


class AttributeSummary(_Model):
    """A changed top-level attribute and its §6.2 class (names only, no values)."""

    name: str
    class_: AttributeClass = Field(alias="class")


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

class ResourceSeverity(_Model):
    """Deterministic severity of a resource: its highest change severity, raised to
    the classification/action floor (drift_engine.severity). `reasons` name the
    floor and the rules behind the level."""

    level: Severity
    reasons: list[str]


class DriftItem(_Model):
    """One managed resource address and its classification."""

    address: Annotated[str, Field(min_length=1)]
    module_address: str | None
    mode: Literal["managed"]
    type: str
    name: str
    index: str | int | None
    provider_name: str | None
    classification: ResourceClass
    action: Action | None
    actions: TerraformActions | None
    action_reason: str | None
    drift_action: Action | None
    drift_actions: TerraformActions | None
    previous_address: str | None
    importing: bool
    attributes: list[AttributeSummary]
    attribute_changes: list[AttributeChange]
    ambiguous: bool
    notes: list[str]
    severity: ResourceSeverity


class ResourceTypeGroup(_Model):
    """Resources grouped by Terraform type."""

    type: str
    resource_count: Annotated[int, Field(ge=1)]
    addresses: Annotated[list[str], Field(min_length=1)]
    classification_counts: ClassificationCounts


class OutputChange(_Model):
    name: str
    action: Action | None
    actions: TerraformActions


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class Failure(_Model):
    """Why drift status is unknown."""

    source: FailureSource
    stage: str | None
    reason: str | None


class RunInfo(_Model):
    """Copied from the run manifest (detection_run.json)."""

    run_id: str | None
    environment: str | None
    working_dir: str | None
    backend_key: str | None
    git_commit: str | None
    started_at: str | None
    finished_at: str | None
    terraform_version: str | None
    plan_exit_code: int | None
    show_exit_code: int | None
    detection_outcome: str | None


class PlanInfo(_Model):
    """Copied from plan.json. Only an error-free, complete plan can appear in a report."""

    format_version: str
    terraform_version: str
    timestamp: str | None
    applyable: bool | None
    errored: FalseFlag
    complete: TrueFlag


class DriftSummary(_Model):
    resources_total: Count
    drifted_resources: Count
    classification_counts: ClassificationCounts
    ambiguous_resources: Count
    highest_severity: Severity
    severity_counts: SeverityCounts
    has_pending_resource_changes: bool
    has_pending_output_changes: bool
    output_only_change: bool


class DriftReport(_Model):
    """The drift report. `has_drift` is None when evidence failed: unknown, never "no drift"."""

    classification_version: Literal["2"]
    outcome: Outcome
    has_drift: bool | None
    failure: Failure | None
    run: RunInfo | None
    plan: PlanInfo | None
    summary: DriftSummary | None
    resources: list[DriftItem]
    resource_types: list[ResourceTypeGroup]
    output_changes: list[OutputChange]

    @model_validator(mode="after")
    def _outcome_invariants(self) -> DriftReport:
        """The schema's succeeded/failed rules (schemas/drift_report.schema.json, allOf)."""
        if self.outcome == "succeeded":
            problems = [
                name for name, bad in (
                    ("has_drift must be true or false", self.has_drift is None),
                    ("failure must be null", self.failure is not None),
                    ("run is required", self.run is None),
                    ("plan is required", self.plan is None),
                    ("summary is required", self.summary is None),
                ) if bad
            ]
        else:
            problems = [
                name for name, bad in (
                    ("has_drift must be null (drift status unknown)", self.has_drift is not None),
                    ("failure is required", self.failure is None),
                    ("plan must be null", self.plan is not None),
                    ("summary must be null", self.summary is not None),
                    ("resources must be empty", bool(self.resources)),
                    ("resource_types must be empty", bool(self.resource_types)),
                    ("output_changes must be empty", bool(self.output_changes)),
                ) if bad
            ]
        if problems:
            raise ValueError(f"{self.outcome} report: " + "; ".join(problems))
        return self
