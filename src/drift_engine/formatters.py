"""Report formatters (Task 4.6): JSON and YAML for machines, console for people.

JSON and YAML render the drift report exactly as defined by
schemas/drift_report.schema.json; the JSON is byte-identical to the file written
by scripts/detect_drift.py. The console view shows the deterministic severity
(Task 4.5) and the configured/noise assessment (Task 4.4); since
classification_version 2 both are also in the report, and the console ratings are
computed by the same function from the same evidence (tested to agree).

Every format is deterministic: the same report gives the same text.
"""

from __future__ import annotations

import json
from typing import Mapping

import yaml

from drift_engine.comparator import NOISE
from drift_engine.severity import CRITICAL, HIGH, INFO, LOW, MEDIUM, ResourceSeverity, highest, rank

FORMATS = ("json", "yaml", "console")


def render_json(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_yaml(report: dict) -> str:
    return yaml.safe_dump(report, sort_keys=True, default_flow_style=False, allow_unicode=True, width=1_000_000)


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------

_SEVERITY_STYLE = {CRITICAL: "1;31", HIGH: "31", MEDIUM: "33", LOW: "36", INFO: "2"}
_VALUE_WIDTH = 60


class _Style:
    def __init__(self, color: bool) -> None:
        self.color = color

    def __call__(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color and code else text

    def severity(self, severity: str, width: int = 0) -> str:
        return self(severity.ljust(width), _SEVERITY_STYLE.get(severity, ""))


def _value(view: dict) -> str:
    status = view["status"]
    if status == "absent":
        return "(absent)"
    if status == "unknown":
        return "(known after apply)"
    if status == "redacted":
        return "(sensitive)"
    text = json.dumps(view["value"], sort_keys=True, ensure_ascii=False)
    return text if len(text) <= _VALUE_WIDTH else text[: _VALUE_WIDTH - 1] + "…"


def _field(label: str, text: str) -> str:
    return f"{label:<12}{text}"


def _counts(counts: Mapping[str, int]) -> str:
    return ", ".join(f"{k}={v}" for k, v in counts.items()) or "none"


def _header(report: dict, style: _Style, overall: str | None) -> list[str]:
    lines = ["Terraform drift analysis", "========================"]
    if report["outcome"] != "succeeded":
        failure = report["failure"] or {}
        lines.append(_field("Outcome", style('FAILED: drift status UNKNOWN (must not be treated as "no drift")', "1;31")))
        lines.append(_field("Failure", f"{failure.get('source')}/{failure.get('stage')}: {failure.get('reason')}"))
    else:
        summary = report["summary"]
        lines.append(_field("Outcome", "succeeded"))
        if report["has_drift"]:
            drift = style(f"DETECTED: {summary['drifted_resources']} of {summary['resources_total']} resources drifted", "1")
        else:
            drift = "none detected"
        lines.append(_field("Drift", drift))
        lines.append(_field("Severity", f"{style.severity(overall or INFO)} (highest across resources)"))
        plan = report["plan"]
        lines.append(_field("Plan", f"Terraform {plan['terraform_version']}, format {plan['format_version']}, "
                                    f"planned {plan['timestamp'] or 'unknown'}"))
    run = report["run"]
    if run is not None:
        if all(v is None for v in run.values()):
            lines.append(_field("Run", "no run manifest: plan exit-code and Terraform-version checks were skipped"))
        else:
            def show(key: str) -> str:
                return "unknown" if run[key] is None else str(run[key])
            lines.append(_field("Run", f"environment {show('environment')}, backend {show('backend_key')}, "
                                       f"plan exit code {show('plan_exit_code')}, run {show('run_id')}"))
    if report["outcome"] == "succeeded":
        summary = report["summary"]
        lines.append(_field("Resources", f"{summary['resources_total']} total: {_counts(summary['classification_counts'])}"))
        if summary["ambiguous_resources"]:
            lines.append(_field("Ambiguous", f"{summary['ambiguous_resources']} resource(s) need review"))
        pending = [name for name, flag in (("resources", summary["has_pending_resource_changes"]),
                                           ("outputs", summary["has_pending_output_changes"])) if flag]
        lines.append(_field("Pending", ", ".join(pending) + " (terraform plan proposes changes)" if pending else "none"))
    return lines


def _resource_block(resource: dict, rated: ResourceSeverity | None, style: _Style, cls_width: int) -> list[str]:
    severity = rated.severity if rated else None
    head = (f"{style.severity(severity, 8) if severity else '-'.ljust(8)}  "
            f"{resource['classification'].ljust(cls_width)}  {(resource['action'] or '-').ljust(7)}  {resource['address']}")
    lines = [head]
    by_path = {tuple(c.path): c for c in rated.changes} if rated else {}
    noise = []
    for change in resource["attribute_changes"]:
        assessed = by_path.get(tuple(change["path"]))
        path = ".".join(change["path"])
        if assessed is not None and assessed.assessment.category == NOISE:
            noise.append(f"{path} [{assessed.assessment.rule}]")
            continue
        parts = [path, change["class"] or "-"]
        if assessed is not None:
            parts += [assessed.assessment.category, style.severity(assessed.severity)]
            if assessed.rules:
                parts.append(f"({', '.join(assessed.rules)})")
        lines.append("    " + "  ".join(parts))
        lines.append(f"      state: {_value(change['state'])}   real: {_value(change['real'])}   "
                     f"desired: {_value(change['desired'])}")
    if noise:
        lines.append("    " + style(f"noise ({INFO}): " + ", ".join(noise), _SEVERITY_STYLE[INFO]))
    if rated:
        for reason in rated.reasons:
            if not any(reason.startswith(".".join(c["path"]) + ":") for c in resource["attribute_changes"]):
                lines.append(f"    severity: {reason}")
    if resource["ambiguous"]:
        lines.append("    " + style("ambiguous: needs review", "33"))
    for note in resource["notes"]:
        lines.append(f"    note: {note}")
    return lines


def render_console(
    report: dict,
    severities: Mapping[str, ResourceSeverity] | None = None,
    color: bool = False,
) -> str:
    """Human-readable view. `severities` maps address -> rating (severity.plan_severity)."""
    style = _Style(color)
    rated = dict(severities or {})
    overall = highest(r.severity for r in rated.values()) if rated else None
    lines = _header(report, style, overall)

    listed = [r for r in report["resources"] if r["classification"] != "in_sync" or r["attribute_changes"]]
    if listed:
        lines += ["", "Resources with changes", "----------------------"]
        listed.sort(key=lambda r: (-rank(rated[r["address"]].severity) if r["address"] in rated else 0, r["address"]))
        width = max(len(r["classification"]) for r in listed)
        for resource in listed:
            lines += _resource_block(resource, rated.get(resource["address"]), style, width)
    in_sync = len(report["resources"]) - len(listed)
    if report["outcome"] == "succeeded":
        lines += ["", _field("In sync", f"{in_sync} resource(s) without changes")]
    changed_outputs = [o for o in report["output_changes"] if o["action"] != "no-op"]
    if changed_outputs:
        lines.append(_field("Outputs", ", ".join(f"{o['name']}: {o['action']}" for o in changed_outputs)))
    return "\n".join(lines) + "\n"


def render(fmt: str, report: dict, severities: Mapping[str, ResourceSeverity] | None = None,
           color: bool = False) -> str:
    if fmt == "json":
        return render_json(report)
    if fmt == "yaml":
        return render_yaml(report)
    if fmt == "console":
        return render_console(report, severities, color)
    raise ValueError(f"unknown format {fmt!r}; expected one of {', '.join(FORMATS)}")


__all__ = ["FORMATS", "render", "render_console", "render_json", "render_yaml"]
