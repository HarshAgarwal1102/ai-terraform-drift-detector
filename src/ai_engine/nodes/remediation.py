"""Deterministic remediation options (Task 6.6). No LLM, no execution.

`plan_remediation` turns the deterministic evidence (`parsed_drift`,
`origin_facts`) into the write-once `AiState.remediation_plan`: for every
changed resource, the options a human can choose between. It runs before the
single LLM call, and nothing the model writes can create or alter an option.

- **The option set** comes from a fixed table over the resource classification,
  the planned action and the attribute classes. The first option always
  mirrors the current Terraform plan (`plan_default = true`). `plan_default`
  means only "this is what the current plan would do"; it is **not** a
  recommendation, and options are never ranked.
- **Commands** come only from COMMAND_CATALOGUE. Values substituted into them
  (working directory, resource address) are taken from the report and
  shell-quoted. The var file is not in the evidence, so it stays the literal
  placeholder `<var_file>` (listed in `placeholders`). Nothing is executed:
  every option has `approval.status = "pending"`, `execution.allowed = false`
  and `automatic_apply = false`. Approval gates and apply are Phase 11.
- **Destructive** is derived from the plan action (replace, delete); recreating
  an object deleted outside Terraform is flagged `data_not_restored`.
- **HCL value fragments** are built only from the `real` view of a changed
  path, with `${` / `%{` escaped so a value cannot become an interpolation. No
  fragment is produced for redacted, unknown-until-apply, absent or
  object-level values. A fragment never says where the value is defined
  (`location = "not_determined"`): resource block, module input or tfvars is
  not in the evidence. File edits are Phase 8.
"""

from __future__ import annotations

import json
import logging
import re
import shlex
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field

from ai_engine.nodes.common import Strict
from drift_engine.logs import log_event

logger = logging.getLogger(__name__)

CATALOGUE_VERSION = "1"
NOISE = "noise"
DRIFT_CLASSES = ("drifted", "drifted_and_config_changed")
MAX_FRAGMENT_CHARS = 4000

# template_id -> (command template, read_only, mutates)
COMMAND_CATALOGUE: dict[str, tuple[str, bool, str]] = {
    "plan_review": ("terraform -chdir={working_dir} plan -var-file={var_file} -detailed-exitcode", True, "none"),
    "plan_save": ("terraform -chdir={working_dir} plan -var-file={var_file} -out=reviewed.tfplan", True, "none"),
    "apply_reviewed_plan": ("terraform -chdir={working_dir} apply reviewed.tfplan", False, "infrastructure"),
    "plan_refresh_only": ("terraform -chdir={working_dir} plan -refresh-only -var-file={var_file} -out=refresh.tfplan",
                          True, "none"),
    "apply_refresh_only": ("terraform -chdir={working_dir} apply refresh.tfplan", False, "state"),
    "state_rm": ("terraform -chdir={working_dir} state rm {address}", False, "state"),
}
VAR_FILE_PLACEHOLDER = "<var_file>"
WORKING_DIR_PLACEHOLDER = "<working_dir>"


def render_command(template_id: str, working_dir: str | None, address: str | None = None) -> dict[str, Any]:
    template, read_only, mutates = COMMAND_CATALOGUE[template_id]
    placeholders = ["var_file"] if "{var_file}" in template else []
    if working_dir is None:
        placeholders.append("working_dir")
    command = template.format(
        working_dir=shlex.quote(working_dir) if working_dir is not None else WORKING_DIR_PLACEHOLDER,
        var_file=VAR_FILE_PLACEHOLDER,
        address=shlex.quote(address) if address is not None else "",
    )
    return {"template_id": template_id, "command": command, "read_only": read_only, "mutates": mutates,
            "placeholders": sorted(placeholders)}


# --------------------------------------------------------------------------- HCL value rendering

_IDENTIFIER = re.compile(r"\A[A-Za-z_][A-Za-z0-9_-]*\Z")


def hcl_string(value: str) -> str:
    out = []
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    # Template sequences: a literal "${" / "%{" must be written "$${" / "%%{".
    return '"' + "".join(out).replace("${", "$${").replace("%{", "%%{") + '"'


def hcl_value(value: Any) -> str:
    """Render a JSON value as an HCL expression (deterministic)."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return hcl_string(value)
    if isinstance(value, list):
        return "[" + ", ".join(hcl_value(v) for v in value) + "]"
    if isinstance(value, Mapping):
        items = []
        for key in sorted(value):
            name = key if _IDENTIFIER.match(key) else hcl_string(key)
            items.append(f"{name} = {hcl_value(value[key])}")
        return "{ " + ", ".join(items) + " }" if items else "{}"
    raise TypeError(f"not a JSON value: {type(value).__name__}")


def value_fragment(change: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """HCL fragment for keeping the remote (`real`) value of a change, or (None, reason)."""
    if change["class"] is None:
        return None, "object_level"
    if change["redacted"] or change["real"]["status"] == "redacted":
        return None, "redacted"
    status = change["real"]["status"]
    if status == "unknown" or change["class"] == "unknown_until_apply":
        return None, "unknown_until_apply"
    if status == "absent":
        return None, "value_absent"
    text = hcl_value(change["real"]["value"])
    if len(text) > MAX_FRAGMENT_CHARS:
        return None, "value_too_large"
    path = list(change["path"])
    fragment = {"path": path, "value_hcl": text, "value_source": "real_view", "location": "not_determined"}
    fragment["assignment_hcl"] = f"{path[0]} = {text}" if len(path) == 1 and _IDENTIFIER.match(path[0]) else None
    return fragment, None


# --------------------------------------------------------------------------- option schema

Direction = Literal["apply_plan", "accept_remote", "keep_current", "state_only", "stop_managing", "investigate",
                    "none"]
Kind = Literal["restore_declared", "apply_pending_change", "create_declared_object", "delete_undeclared_object",
               "replace_object", "recreate_deleted_object", "no_infrastructure_change", "accept_remote_value",
               "keep_current_value", "refresh_state_only", "stop_managing_without_destroy", "investigate"]
Mutates = Literal["infrastructure", "state", "configuration", "configuration_and_state", "none"]


class Command(Strict):
    template_id: str
    command: str
    read_only: bool
    mutates: Literal["infrastructure", "state", "none"]
    placeholders: list[str]


class Fragment(Strict):
    path: Annotated[list[str], Field(min_length=1)]
    value_hcl: str
    value_source: Literal["real_view"]
    location: Literal["not_determined"]
    assignment_hcl: str | None


class FragmentGap(Strict):
    path: Annotated[list[str], Field(min_length=1)]
    reason: Literal["object_level", "redacted", "unknown_until_apply", "value_absent", "value_too_large"]


class EvidenceRef(Strict):
    path: Annotated[list[str], Field(min_length=1)]
    attribute_class: str | None
    assessment: str
    origin: str
    severity: str


class Approval(Strict):
    required: Literal[True]
    status: Literal["pending"]
    approver: None
    decided_at: None
    destructive_confirmation_required: bool


class Execution(Strict):
    allowed: Literal[False]
    automatic_apply: Literal[False]
    mode: Literal["manual_after_approval"]


class RemediationOption(Strict):
    option_id: str
    address: str
    kind: Kind
    direction: Direction
    plan_default: bool  # matches the current Terraform plan direction; NOT a recommendation
    terraform_plan_action: str | None
    destructive: bool
    data_not_restored: bool
    mutates: Mutates
    human_decision_required: bool
    description: str
    fragments: list[Fragment]
    fragment_gaps: list[FragmentGap]
    commands: list[Command]
    preconditions: list[str]
    evidence: list[EvidenceRef]
    approval: Approval
    execution: Execution


class RemediationPlan(Strict):
    catalogue_version: Literal["1"]
    options: list[RemediationOption]
    approval_required: Literal[True]
    automatic_apply: Literal[False]
    ranking: Literal["none"]  # options are never ranked or recommended
    reason: str | None


# --------------------------------------------------------------------------- option table

PRECONDITIONS = (
    "Re-run terraform plan and confirm its diff matches this report (drift_report_sha256).",
    "Obtain the required human approval; nothing in this report is executed automatically.",
)
DESCRIPTIONS = {
    "restore_declared": "Apply the reviewed plan: Terraform sets Azure back to the declared values.",
    "apply_pending_change": "Apply the reviewed plan: Terraform deploys the pending configuration change.",
    "create_declared_object": "Apply the reviewed plan: Terraform creates the declared object.",
    "delete_undeclared_object": "Apply the reviewed plan: Terraform deletes an object the configuration no longer "
                                "declares.",
    "replace_object": "Apply the reviewed plan: Terraform destroys the object and creates a new one.",
    "recreate_deleted_object": "Apply the reviewed plan: Terraform creates the object again. Data of the deleted "
                               "object is not restored.",
    "no_infrastructure_change": "The current plan proposes no infrastructure change for this object.",
    "accept_remote_value": "Keep the value now in Azure: change the declared value to match it, then re-plan.",
    "keep_current_value": "Keep the currently recorded value: change the declaration back to it, then re-plan.",
    "refresh_state_only": "Record the current Azure values in state without changing infrastructure.",
    "stop_managing_without_destroy": "Stop managing the object without destroying it: remove it from state (and "
                                     "from the configuration).",
    "investigate": "Remote and declared values both changed or the change is unexplained: decide manually which "
                   "side is intended before any change.",
}


def _plan_kind(resource: Mapping[str, Any]) -> tuple[str, str]:
    action, cls = resource["action"], resource["classification"]
    if action in (None, "no-op", "read"):
        return "no_infrastructure_change", "none"
    if action == "replace":
        return "replace_object", "apply_plan"
    if action == "delete":
        return "delete_undeclared_object", "apply_plan"
    if action == "create":
        return ("recreate_deleted_object" if cls == "external_deletion" else "create_declared_object"), "apply_plan"
    if cls in ("external_drift", "drift_and_config_change", "undetermined"):
        return "restore_declared", "apply_plan"
    return "apply_pending_change", "apply_plan"


def _commands(kind: str, working_dir: str | None, address: str) -> list[dict[str, Any]]:
    if kind in ("no_infrastructure_change", "investigate", "accept_remote_value", "keep_current_value"):
        ids = ["plan_review"]
    elif kind == "refresh_state_only":
        ids = ["plan_refresh_only", "apply_refresh_only"]
    elif kind == "stop_managing_without_destroy":
        ids = ["state_rm", "plan_review"]
    else:
        ids = ["plan_review", "plan_save", "apply_reviewed_plan"]
    return [render_command(i, working_dir, address if i == "state_rm" else None) for i in ids]


def _mutates(kind: str) -> str:
    return {"no_infrastructure_change": "none", "investigate": "none", "accept_remote_value": "configuration",
            "keep_current_value": "configuration", "refresh_state_only": "state",
            "stop_managing_without_destroy": "configuration_and_state"}.get(kind, "infrastructure")


def resource_options(resource: Mapping[str, Any], origins: Mapping, working_dir: str | None) -> list[dict[str, Any]]:
    changes = [c for c in resource["attribute_changes"] if c["assessment"]["category"] != NOISE]
    cls, action = resource["classification"], resource["action"]
    human = bool(resource["ambiguous"]) or cls in ("drift_and_config_change", "undetermined")
    evidence = [{"path": list(c["path"]), "attribute_class": c["class"], "assessment": c["assessment"]["category"],
                 "origin": origins[(resource["address"], tuple(c["path"]))]["origin"],
                 "severity": c["severity"]["level"]} for c in changes]

    plan_kind, plan_direction = _plan_kind(resource)
    specs: list[tuple[str, str, bool, list]] = [(plan_kind, plan_direction, True, [])]
    if any(c["class"] in DRIFT_CLASSES for c in changes):
        specs.append(("accept_remote_value", "accept_remote", False,
                      [c for c in changes if c["class"] in DRIFT_CLASSES]))
    if cls == "config_change" and action in ("update", "replace"):
        specs.append(("keep_current_value", "keep_current", False,
                      [c for c in changes if c["class"] == "config_changed"]))
    if cls == "converged_drift":
        specs.append(("refresh_state_only", "state_only", False, []))
    if action == "delete" or cls == "external_deletion":
        specs.append(("stop_managing_without_destroy", "stop_managing", False, []))
    if human:
        specs.append(("investigate", "investigate", False, []))

    options = []
    for n, (kind, direction, plan_default, fragment_changes) in enumerate(specs, start=1):
        destructive = plan_default and action in ("replace", "delete")
        fragments, gaps = [], []
        for change in fragment_changes:
            fragment, reason = value_fragment(change)
            if fragment is None:
                gaps.append({"path": list(change["path"]), "reason": reason})
            else:
                fragments.append(fragment)
        options.append({
            "option_id": f"{resource['address']}#{n}",
            "address": resource["address"],
            "kind": kind,
            "direction": direction,
            "plan_default": plan_default,
            "terraform_plan_action": action if plan_default else None,
            "destructive": destructive,
            "data_not_restored": kind == "recreate_deleted_object",
            "mutates": _mutates(kind),
            "human_decision_required": human,
            "description": DESCRIPTIONS[kind],
            "fragments": fragments,
            "fragment_gaps": gaps,
            "commands": _commands(kind, working_dir, resource["address"]),
            "preconditions": list(PRECONDITIONS),
            "evidence": evidence,
            "approval": {"required": True, "status": "pending", "approver": None, "decided_at": None,
                         "destructive_confirmation_required": destructive},
            "execution": {"allowed": False, "automatic_apply": False, "mode": "manual_after_approval"},
        })
    return options


def plan_remediation(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph node: deterministic remediation options for every changed resource."""
    parsed = state["parsed_drift"]
    facts = state["origin_facts"]
    reason = None
    options: list[dict[str, Any]] = []
    if parsed["outcome"] != "succeeded":
        reason = "drift detection failed: drift status unknown; no remediation options"
    else:
        run = (state["drift_report"].get("run") or {})
        working_dir = run.get("working_dir")
        origins = {(c["address"], tuple(c["path"])): c for c in facts["changes"]}
        for resource in parsed["resources"]:
            options += resource_options(resource, origins, working_dir)
    plan = RemediationPlan.model_validate_json(json.dumps({  # strict JSON semantics, as for the LLM sections
        "catalogue_version": CATALOGUE_VERSION, "options": options, "approval_required": True,
        "automatic_apply": False, "ranking": "none", "reason": reason,
    })).model_dump(mode="json")
    log_event(logger, logging.INFO, "remediation_planned", "deterministic remediation options built",
              options=len(options), destructive=sum(o["destructive"] for o in options))
    return {"remediation_plan": plan}
