"""Deterministic investigation facts and the statement templates of report v2 (Task 9B.4). No LLM.

`derive_investigation` (a LangGraph node after `derive_origin_risk`) turns the
**public** drift investigation (`drift_investigation.json`, drift_engine.investigation_public;
never the restricted document) and the drift report into the write-once
`AiState.investigation_facts`: per changed resource the recorded Azure operations,
WHEN, WHO and the correlation, each with fixed, versioned statements.

The investigation is authoritative: verdict, reason, property link, actor
attribution, operations and timestamps are copied, never re-decided, and the LLM
cannot change any of them. Three claims stay apart (PROJECT_PLAN.md, Phase 9B, G3):
the recorded operation (evidence), its relationship to the drift (verdict and
property link), and actor attribution (`confirmed` only with a confirmed property
link). A recorded caller is never presented as the author of the drift, and the
caller identity is always `withheld` (it is not in the public document).

Scope (design review D1-D3):
- drifted resources (`drift_actions` present) have `investigation_scope = drift`.
  Without an investigation they are `not_investigated` (`investigation_not_provided`);
  with a bindable failed investigation, `not_investigated` (`investigation_failed`);
- `config_change`, `resource_added` and `resource_removed` (no `drift_actions`) are
  `not_drift`: investigation, WHEN, WHO and correlation are `not_applicable`;
- `recorded_caller.status`: `recorded` | `not_recorded` (reason `caller_missing` /
  `caller_inconsistent`) for the decisive operation of `sole` / `latest`;
  `multiple_operations` for `ambiguous` with two or more candidate operations;
  `no_decisive_operation` otherwise; `not_investigated`; `not_applicable`.

`load_investigation` checks a public document before use: leak scan, the strict
public contract, the binding to this exact drift report (canonical SHA-256, run id,
plan timestamp, observation window) and the resource scope (exactly the drifted
resources, with the drift action and relevant property areas the drift report
implies). Every fact the evidence cannot prove renders as NOT_CONFIRMED.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import Field

from ai_engine.evidence import refs_from_investigation, render_evidence
from ai_engine.nodes.common import Strict, free_text_violation
from drift_engine import investigation_public as pub
from drift_engine.logs import log_event

logger = logging.getLogger(__name__)

STATEMENTS_VERSION = "1"
NOT_CONFIRMED = "not confirmed by available evidence"
EXPOSURE = {"caller_identity": "withheld", "resource_id": "withheld", "event_id": "withheld",
            "correlation_id": "withheld", "who_path": "local_only"}
REPORT_REASONS = ("investigation_failed", "investigation_not_provided")
DRIFT_CLASSES = ("drifted", "drifted_converged", "drifted_and_config_changed")
NOISE = "noise"


class InvestigationInputError(ValueError):
    """The public investigation cannot be used for this drift report. `code` is fixed, never a value."""

    CODES = ("binding_mismatch", "contract", "invalid_json", "leak", "scope_mismatch", "too_large")

    def __init__(self, code: str) -> None:
        if code not in self.CODES:
            raise ValueError(f"unknown code {code!r}")
        super().__init__(code)
        self.code = code


# --------------------------------------------------------------------------- loading and binding

_TIMESTAMP = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(?:Z|\+00:00)")


def parse_utc(value: Any) -> datetime | None:
    """ISO 8601 UTC (`Z` or `+00:00`, up to 9 fractional digits, truncated to microseconds), else None."""
    match = _TIMESTAMP.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return None
    fraction = (match.group(7) or "").ljust(6, "0")[:6]
    try:
        return datetime(*(int(match.group(n)) for n in range(1, 7)), int(fraction), tzinfo=timezone.utc)
    except ValueError:
        return None


def format_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def observation_of(drift_report: Mapping[str, Any]) -> dict[str, str] | None:
    """The detection run's observation window [started_at, finished_at] (G7), or None when unknown."""
    run = drift_report.get("run") or {}
    started, finished = parse_utc(run.get("started_at")), parse_utc(run.get("finished_at"))
    if started is None or finished is None or started > finished:
        return None
    return {"started_at": format_utc(started), "finished_at": format_utc(finished)}


def drifted_items(drift_report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The drifted resources (`drift_actions` present), sorted by address: the investigation's scope."""
    return sorted((r for r in drift_report.get("resources") or [] if r.get("drift_actions") is not None),
                  key=lambda r: r["address"])


def relevant_areas(item: Mapping[str, Any]) -> list[str]:
    """The drifted property areas of a drift report resource (G6)."""
    action = item.get("drift_action")
    if action == "delete":
        return ["existence_delete"]
    if action == "create":
        return ["existence_create"]
    if action == "replace":
        return ["existence_create", "existence_delete"]
    areas = {"tags" if change["path"][0] == "tags" else "other"
             for change in item.get("attribute_changes") or []
             if change.get("class") in DRIFT_CLASSES and (change.get("assessment") or {}).get("category") != NOISE}
    return sorted(areas) or ["other"]


def load_investigation(raw: Any, drift_report: Mapping[str, Any]) -> dict[str, Any]:
    """The public investigation as plain JSON, after the leak scan, the strict public contract, the binding to
    `drift_report` and the scope check. Raises InvestigationInputError."""
    if not isinstance(raw, Mapping):
        raise InvestigationInputError("contract")
    document = json.loads(json.dumps(raw))
    if pub.leak_findings(document):
        raise InvestigationInputError("leak")
    try:
        model = pub.PublicInvestigation.model_validate_json(json.dumps(document))
    except ValueError:
        raise InvestigationInputError("contract") from None
    binding = model.binding
    run, plan = drift_report.get("run") or {}, drift_report.get("plan") or {}
    if (binding.drift_report_sha256 != pub.canonical_sha256(drift_report)
            or binding.run_id != run.get("run_id") or binding.plan_timestamp != plan.get("timestamp")):
        raise InvestigationInputError("binding_mismatch")
    if binding.observation is not None and binding.observation.model_dump() != observation_of(drift_report):
        raise InvestigationInputError("binding_mismatch")
    drifted = drifted_items(drift_report)
    if model.outcome == "failed" and not model.resources:
        return document  # an input-stage failure lists no resources (D3)
    if [r.address for r in model.resources] != [r["address"] for r in drifted]:
        raise InvestigationInputError("scope_mismatch")
    for public, item in zip(model.resources, drifted):
        if public.drift_action != item.get("drift_action") or public.relevant_areas != relevant_areas(item):
            raise InvestigationInputError("scope_mismatch")
    return document


# --------------------------------------------------------------------------- statement templates (version 1)

TEMPLATES: dict[str, str] = {
    # WHAT (Terraform evidence)
    "what.terraform.v1": "Terraform reports {classification} on {address} (planned action {action}, deterministic "
                         "severity {severity}) with {changes} changed attribute(s). Expected values are the declared "
                         "configuration (desired); actual values are what Azure returned (real).",
    # recorded operations and correlation
    "operations.recorded.v1": "Azure recorded {count} operation group(s) on this resource ({capable} capable, "
                              "{unclassified} unclassified, {irrelevant} irrelevant, {after} after the observation).",
    "operations.none.v1": "Azure recorded no operation on this resource in the investigated window among events "
                          "available at {queried_at}.",
    "operations.not_investigated.v1": "Recorded Azure operations: " + NOT_CONFIRMED + " (not investigated: "
                                      "{reason}).",
    "operations.children.v1": "{count} recorded operation(s) on contained or child resources ({names}) never decide "
                              "the verdict.",
    "operations.automated.v1": "{count} Azure Policy or Autoscale event(s) recorded; {signals} counted as automated "
                               "activity.",
    "correlation.sole.v1": "Verdict sole_capable_operation: since the last in-sync observation, exactly one recorded "
                           "operation ({op}, {name}) can explain every drifted property area ({areas}).",
    "correlation.latest.v1": "Verdict latest_capable_operation: there is no last in-sync observation; the most recent "
                             "recorded operation in the lookback window ({op}, {name}) can explain every drifted "
                             "property area ({areas}); {earlier} earlier candidate operation(s).",
    "correlation.ambiguous.v1": "Verdict ambiguous ({reason}): {detail} No single operation is decisive.",
    "correlation.none.v1": "Verdict no_capable_operation_found: among events available at {queried_at}, no recorded "
                           "operation that can explain the drift was found in the window. This does not mean that "
                           "no change happened.",
    "correlation.not_investigated.v1": "Verdict not_investigated ({reason}): the relationship between Azure "
                                       "operations and this drift is " + NOT_CONFIRMED + ".",
    "correlation.not_applicable.v1": "Not applicable: Terraform found no Azure-side drift on this resource "
                                     "(configuration-side change), so no Activity Log investigation applies.",
    "link.inferred.v1": "Property link inferred_not_provable: the Activity Log records operations, not property "
                        "values, so the link to the drifted attributes is " + NOT_CONFIRMED + ".",
    "link.deletion_not_confirmed.v1": "The deletion rule did not confirm the deletion ({reason}).",
    "link.not_decisive.v1": "The deletion rule matched a recorded delete, but the property link stays inferred "
                            "({reason}).",
    "link.confirmed.v1": "Property link confirmed by rule {rule}: Azure recorded a successful delete of this "
                         "resource after it was last proven to exist.",
    "link.none.v1": "Property link: " + NOT_CONFIRMED + " (no recorded operation that can explain the drift).",
    "correlation.completeness.v1": "Completeness: events available at {queried_at} after {polls} poll(s); "
                                   "settled: {settled}.",
    # WHEN
    "when.decisive.v1": "Event time: operation {op} ran from {start} to {end} (Activity Log event time; available "
                        "in the Activity Log at {available}).",
    "when.not_confirmed.v1": "Event time of the change: " + NOT_CONFIRMED + ".",
    "when.detection.v1": "Detection time: Terraform observed Azure from {started} to {finished} (plan timestamp "
                         "{plan}).",
    "when.gap.v1": "The operation ended {gap} s before the observation started.",
    "when.last_in_sync.v1": "Last in-sync observation: drift run {run} saw this resource in sync from {started} to "
                            "{finished}; the correlation window starts at {window}.",
    "when.lookback.v1": "No last in-sync observation within retention: the correlation window is the lookback from "
                        "{window}.",
    "when.no_window.v1": "Correlation window: " + NOT_CONFIRMED + ".",
    "when.not_applicable.v1": "Not applicable: no Azure-side drift to date.",
    # WHO
    "who.recorded.v1": "Recorded caller of {op}: caller type {caller_type}, client application {client}, pipeline "
                       "identity {pipeline}. The identity is withheld in public reports; maintainers can look it up "
                       "locally with drift-engine who.",
    "who.not_recorded.v1": "Recorded caller of {op}: " + NOT_CONFIRMED + " ({reason}).",
    "who.multiple.v1": "Recorded caller: " + NOT_CONFIRMED + " ({count} candidate operations, none decisive). Each "
                       "operation's caller type and client application are listed with the recorded operations.",
    "who.no_decisive.v1": "Recorded caller: " + NOT_CONFIRMED + " (no decisive operation; {count} candidate "
                          "operation(s)).",
    "who.not_investigated.v1": "Recorded caller: " + NOT_CONFIRMED + " (not investigated: {reason}).",
    "who.not_applicable.v1": "Not applicable: no Azure-side drift to attribute.",
    "who.azure_cli.v1": "The azure_cli client application also covers Terraform run locally with Azure CLI "
                        "authentication.",
    "who.actor_confirmed.v1": "Actor attribution: confirmed by rule {rule} ({claim}); the identity is withheld in "
                              "public reports.",
    "who.actor_not_confirmed.v1": "Actor attribution: " + NOT_CONFIRMED + ". A recorded caller is never presented as "
                                  "the author of the drift.",
    # recommendation (policy v1)
    "recommendation.recommended.v1": "Recommended option (policy v1, rule {rule}, {rationale}): {kind}. Human "
                                     "approval is required; nothing is executed automatically.",
    "recommendation.human.v1": "No option is recommended (policy v1, rule {rule}, {rationale}): a human decision is "
                               "required. Nothing is executed automatically.",
    "recommendation.no_options.v1": "No remediation options (policy v1, rule R0).",
    "recommendation.note.v1": "{note}",
}

AMBIGUOUS_DETAIL = {
    "multiple_capable_operations": "more than one recorded operation can explain the drift.",
    "partial_capability": "no single recorded operation can explain every drifted property area.",
    "unclassified_operation": "an operation outside the capable-operations table was recorded on this resource.",
    "during_observation": "an operation ran during the detection run's observation.",
    "unresolved_operation": "the outcome of a recorded operation is unresolved.",
    "automated_activity": "Azure Policy or Autoscale activity was recorded in the window.",
    "unreadable_events_in_scope": "some Activity Log events in this resource's scope could not be read.",
}


def _slot(value: Any) -> str:
    if value is None:
        return NOT_CONFIRMED
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def statement(template_id: str, **slots: Any) -> dict[str, str]:
    """One fixed statement: its template id and the text with every slot filled (None -> NOT_CONFIRMED)."""
    return {"id": template_id, "text": TEMPLATES[template_id].format(**{k: _slot(v) for k, v in slots.items()})}


def recommendation_statements(recommendation: Mapping[str, Any]) -> list[dict[str, str]]:
    """The fixed statements of a policy v1 recommendation (ai_engine.nodes.remediation.recommend)."""
    decision = recommendation["decision"]
    if decision == "recommended":
        out = [statement("recommendation.recommended.v1", rule=recommendation["policy_rule"],
                         rationale=recommendation["rationale"], kind=recommendation["kind"])]
    elif decision == "human_decision_required":
        out = [statement("recommendation.human.v1", rule=recommendation["policy_rule"],
                         rationale=recommendation["rationale"])]
    else:
        out = [statement("recommendation.no_options.v1")]
    return out + [statement("recommendation.note.v1", note=note) for note in recommendation["notes"]]


def what_statements(resource: Mapping[str, Any]) -> list[dict[str, str]]:
    return [statement("what.terraform.v1", classification=resource["classification"], address=resource["address"],
                      action=resource["action"] or "none", severity=resource["severity"]["level"],
                      changes=len(resource["attribute_changes"]))]


# --------------------------------------------------------------------------- per-resource facts

def is_candidate(op: Mapping[str, Any]) -> bool:
    """A G4 candidate: a successful or unresolved capable / unclassified group in the window, not after it."""
    return (op["role"] in ("capable", "unclassified") and op["outcome"] != "failed"
            and op["timing"] != "after_observation" and op["in_window"])


def _counts(operations: list[Mapping[str, Any]], automated: list[Mapping[str, Any]], descendants: int) -> dict:
    return {
        "operations": len(operations),
        "capable": sum(op["role"] == "capable" for op in operations),
        "unclassified": sum(op["role"] == "unclassified" for op in operations),
        "irrelevant": sum(op["role"] == "irrelevant" for op in operations),
        "candidates": sum(is_candidate(op) for op in operations),
        "after_observation": sum(op["timing"] == "after_observation" for op in operations),
        "child": descendants,
        "automated_signals": sum(event["signal"] for event in automated),
    }


def _not_applicable(address: str) -> dict[str, Any]:
    return {
        "address": address, "investigation_scope": "not_drift", "drift_action": None, "operations": [],
        "automated_events": [],
        "when": {"status": "not_applicable", "decisive_operation": None, "event_start": None, "event_end": None,
                 "available_at": None, "last_in_sync": None, "window": None, "observation": None,
                 "plan_timestamp": None, "gap_seconds": None, "statements": [statement("when.not_applicable.v1")]},
        "who": {"recorded_caller": {"status": "not_applicable", "reason": None, "operation": None,
                                    "candidate_operations": 0, "caller_type": None, "client_app": None,
                                    "pipeline_identity": None, "identity": "withheld"},
                "actor_attribution": {"status": "not_applicable", "rule": None, "claim": None},
                "statements": [statement("who.not_applicable.v1")]},
        "correlation": {"status": "not_applicable", "verdict": None, "reason": None, "property_link": None,
                        "property_link_reason": None, "relevant_areas": [], "deletion_rule": None,
                        "unreadable_events_in_scope": False, "counts": _counts([], [], 0),
                        "descendant_operations": {}, "statements": [statement("correlation.not_applicable.v1")]},
    }


def _public_resource(item: Mapping[str, Any], public: Mapping[str, Any] | None, reason: str | None) -> dict:
    """The investigation of one drifted resource: the public entry, or not_investigated with `reason`."""
    if reason is None:
        if public is None:  # load_investigation guarantees exactly the drifted resources
            raise ValueError(f"the investigation has no entry for {item['address']}")
        return dict(public)
    return {"address": item["address"], "drift_action": item.get("drift_action"), "relevant_areas": relevant_areas(item),
            "window": None, "verdict": "not_investigated", "reason": reason, "decisive_operation": None,
            "property_link": "none", "property_link_reason": None, "deletion_rule": None,
            "actor_attribution": {"status": "not_confirmed", "rule": None, "claim": None},
            "unreadable_events_in_scope": False, "operations": [], "automated_events": [], "descendant_events": 0,
            "descendant_operations": {}}


def _recorded_caller(r: Mapping[str, Any], decisive: Mapping[str, Any] | None, candidates: int) -> dict[str, Any]:
    base = {"status": None, "reason": None, "operation": None, "candidate_operations": candidates,
            "caller_type": None, "client_app": None, "pipeline_identity": None, "identity": "withheld"}
    if r["verdict"] == "not_investigated":
        return base | {"status": "not_investigated"}
    if decisive is not None:
        if decisive["caller_status"] == "recorded":
            return base | {"status": "recorded", "operation": decisive["op_id"], "caller_type": decisive["caller_type"],
                           "client_app": decisive["client_app"], "pipeline_identity": decisive["pipeline_identity"]}
        reason = "caller_missing" if decisive["caller_status"] == "missing" else "caller_inconsistent"
        return base | {"status": "not_recorded", "reason": reason, "operation": decisive["op_id"]}
    if r["verdict"] == "ambiguous" and candidates >= 2:
        return base | {"status": "multiple_operations"}
    return base | {"status": "no_decisive_operation"}


def _drift_resource(item: Mapping[str, Any], r: Mapping[str, Any], run: Mapping[str, Any],
                    plan_timestamp: str | None) -> dict[str, Any]:
    operations = [dict(op) | {"caller_identity": "withheld", "basis": "activity_log_evidence"}
                  for op in r["operations"]]
    automated = [dict(event) | {"basis": "activity_log_evidence"} for event in r["automated_events"]]
    by_id = {op["op_id"]: op for op in operations}
    decisive = by_id.get(r["decisive_operation"]) if r["decisive_operation"] else None
    counts = _counts(operations, automated, r["descendant_events"])
    observation, completeness = run["observation"], run["completeness"]
    investigated = r["verdict"] != "not_investigated"
    reason = r["reason"]

    # WHEN
    window = r["window"]
    anchor = window["anchor"] if window else None
    gap = None
    if decisive is not None and observation is not None:
        gap = round((parse_utc(observation["started_at"]) - parse_utc(decisive["end"])).total_seconds(), 6)
    when_statements = []
    if decisive is not None:
        when_statements.append(statement("when.decisive.v1", op=decisive["op_id"], start=decisive["start"],
                                         end=decisive["end"], available=decisive["available_at"]))
    else:
        when_statements.append(statement("when.not_confirmed.v1"))
    when_statements.append(statement("when.detection.v1", started=(observation or {}).get("started_at"),
                                     finished=(observation or {}).get("finished_at"), plan=plan_timestamp))
    if gap is not None:
        when_statements.append(statement("when.gap.v1", gap=f"{gap:.6f}".rstrip("0").rstrip(".")))
    if anchor is not None:
        when_statements.append(statement("when.last_in_sync.v1", run=anchor["run_id"], started=anchor["started_at"],
                                         finished=anchor["finished_at"], window=window["start"]))
    elif window is not None:
        when_statements.append(statement("when.lookback.v1", window=window["start"]))
    else:
        when_statements.append(statement("when.no_window.v1"))
    when = {"status": "decisive_operation" if decisive is not None else "not_confirmed",
            "decisive_operation": decisive["op_id"] if decisive else None,
            "event_start": decisive["start"] if decisive else None, "event_end": decisive["end"] if decisive else None,
            "available_at": decisive["available_at"] if decisive else None,
            "last_in_sync": dict(anchor) if anchor else None,
            "window": {"kind": window["kind"], "start": window["start"]} if window else None,
            "observation": dict(observation) if observation else None, "plan_timestamp": plan_timestamp,
            "gap_seconds": gap, "statements": when_statements}

    # WHO
    caller = _recorded_caller(r, decisive, counts["candidates"])
    status = caller["status"]
    if status == "recorded":
        who_statements = [statement("who.recorded.v1", op=caller["operation"], caller_type=caller["caller_type"],
                                    client=caller["client_app"], pipeline=caller["pipeline_identity"])]
    elif status == "not_recorded":
        who_statements = [statement("who.not_recorded.v1", op=caller["operation"], reason=caller["reason"])]
    elif status == "multiple_operations":
        who_statements = [statement("who.multiple.v1", count=counts["candidates"])]
    elif status == "no_decisive_operation":
        who_statements = [statement("who.no_decisive.v1", count=counts["candidates"])]
    else:
        who_statements = [statement("who.not_investigated.v1", reason=reason)]
    if any(op["client_app"] == "azure_cli" for op in operations):
        who_statements.append(statement("who.azure_cli.v1"))
    attribution = r["actor_attribution"]
    if attribution["status"] == "confirmed":
        actor = {"status": "confirmed", "rule": attribution["rule"], "claim": attribution["claim"]}
        who_statements.append(statement("who.actor_confirmed.v1", rule=actor["rule"], claim=actor["claim"]))
    else:
        actor = {"status": "not_confirmed_by_available_evidence", "rule": None, "claim": None}
        who_statements.append(statement("who.actor_not_confirmed.v1"))
    who = {"recorded_caller": caller, "actor_attribution": actor, "statements": who_statements}

    # correlation
    queried_at = (completeness or {}).get("queried_at")
    corr: list[dict[str, str]] = []
    if not investigated:
        corr.append(statement("operations.not_investigated.v1", reason=reason))
    elif operations:
        corr.append(statement("operations.recorded.v1", count=counts["operations"], capable=counts["capable"],
                              unclassified=counts["unclassified"], irrelevant=counts["irrelevant"],
                              after=counts["after_observation"]))
    else:
        corr.append(statement("operations.none.v1", queried_at=queried_at))
    if r["descendant_events"]:
        corr.append(statement("operations.children.v1", count=r["descendant_events"],
                              names=", ".join(r["descendant_operations"])))
    if automated:
        corr.append(statement("operations.automated.v1", count=len(automated), signals=counts["automated_signals"]))
    verdict = r["verdict"]
    if verdict == "sole_capable_operation":
        corr.append(statement("correlation.sole.v1", op=decisive["op_id"], name=decisive["operation_name"],
                              areas=", ".join(r["relevant_areas"])))
    elif verdict == "latest_capable_operation":
        corr.append(statement("correlation.latest.v1", op=decisive["op_id"], name=decisive["operation_name"],
                              areas=", ".join(r["relevant_areas"]), earlier=counts["candidates"] - 1))
    elif verdict == "ambiguous":
        corr.append(statement("correlation.ambiguous.v1", reason=reason, detail=AMBIGUOUS_DETAIL[reason]))
    elif verdict == "no_capable_operation_found":
        corr.append(statement("correlation.none.v1", queried_at=queried_at))
    else:
        corr.append(statement("correlation.not_investigated.v1", reason=reason))
    if r["property_link"] == "confirmed":
        corr.append(statement("link.confirmed.v1", rule=r["deletion_rule"]["rule"]))
    elif r["property_link"] == "inferred_not_provable":
        corr.append(statement("link.inferred.v1"))
        if r["property_link_reason"] == "deletion_rule_not_confirmed" and r["deletion_rule"]:
            corr.append(statement("link.deletion_not_confirmed.v1", reason=r["deletion_rule"]["reason"]))
        elif r["property_link_reason"] in ("verdict_not_decisive", "decisive_operation_mismatch"):
            corr.append(statement("link.not_decisive.v1", reason=r["property_link_reason"]))
    else:
        corr.append(statement("link.none.v1"))
    if investigated and completeness is not None:
        corr.append(statement("correlation.completeness.v1", queried_at=queried_at, polls=completeness["polls"],
                              settled=completeness["settled"]))
    correlation = {"status": "investigated" if investigated else "not_investigated", "verdict": verdict,
                   "reason": reason, "property_link": r["property_link"],
                   "property_link_reason": r["property_link_reason"], "relevant_areas": list(r["relevant_areas"]),
                   "deletion_rule": dict(r["deletion_rule"]) if r["deletion_rule"] else None,
                   "unreadable_events_in_scope": r["unreadable_events_in_scope"], "counts": counts,
                   "descendant_operations": dict(r["descendant_operations"]), "statements": corr}
    return {"address": item["address"], "investigation_scope": "drift", "drift_action": r["drift_action"],
            "operations": operations,
            "automated_events": automated, "when": when, "who": who, "correlation": correlation}


def build_facts(drift_report: Mapping[str, Any], parsed_resources: list[Mapping[str, Any]],
                investigation: Mapping[str, Any] | None) -> dict[str, Any]:
    """Investigation facts for every changed resource (`parsed_resources`, in report order)."""
    observation = observation_of(drift_report)
    plan_timestamp = (drift_report.get("plan") or {}).get("timestamp")
    if investigation is None:
        status, reason, public_by_address = "not_available", "investigation_not_provided", {}
        run = {"failure": None, "completeness": None, "anchors": None, "rules": None}
    else:
        status = investigation["outcome"]
        reason = "investigation_failed" if status == "failed" else None
        public_by_address = {r["address"]: r for r in investigation["resources"]}
        run = {"failure": investigation["failure"], "completeness": investigation["completeness"],
               "anchors": investigation["anchors"], "rules": investigation["rules"]}
    run["observation"] = observation
    resources = []
    for item in parsed_resources:
        if item.get("drift_actions") is None:
            resources.append(_not_applicable(item["address"]))
            continue
        public = _public_resource(item, public_by_address.get(item["address"]), reason)
        resources.append(_drift_resource(item, public, run, plan_timestamp))
    return {
        "status": status,
        "sha256": pub.canonical_sha256(investigation) if investigation is not None else None,
        "versions": {"investigation_public": investigation["public_version"] if investigation else None,
                     "capable_operations_table": investigation["rules"]["table_version"] if investigation else None,
                     "deletion_rules": investigation["rules"]["deletion_rules_version"] if investigation else None,
                     "statements": STATEMENTS_VERSION},
        "run": run,
        "exposure": dict(EXPOSURE),
        "resources": resources,
    }


def derive_investigation(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph node: the deterministic investigation facts (Task 9B.4)."""
    drift_report = state["drift_report"]
    raw = state.get("investigation") or None
    investigation = load_investigation(raw, drift_report) if raw else None
    parsed = state["parsed_drift"]
    facts = build_facts(drift_report, list(parsed["resources"]), investigation)
    log_event(logger, logging.INFO, "investigation_facts_derived", "deterministic investigation facts derived",
              status=facts["status"], resources=len(facts["resources"]),
              drift=sum(r["investigation_scope"] == "drift" for r in facts["resources"]))
    return {"investigation_facts": facts}


# --------------------------------------------------------------------------- the LLM investigation section

# Part of the single `analyze_drift` call (section `investigation_analysis`). The model may explain whether the
# recorded operations are consistent with the drift, and the impact and risk; it can change no deterministic field.
# `consistency` is checked against the operations' deterministic roles: `consistent_with_drift` only for successful
# capable operations in the window of a resource with a candidate-based verdict, `not_consistent_with_drift` only for
# operations that cannot explain it.

OpRef = Annotated[str, Field(pattern=r"^op-[1-9][0-9]*$")]
Consistency = Literal["consistent_with_drift", "not_consistent_with_drift", "undetermined"]
CONSISTENT_VERDICTS = ("sole_capable_operation", "latest_capable_operation", "ambiguous")


class InvestigationFinding(Strict):
    address: Annotated[str, Field(min_length=1, max_length=1024)]
    cited_operations: Annotated[list[OpRef], Field(max_length=20)]
    consistency: Consistency
    explanation: Annotated[str, Field(min_length=1, max_length=600)]
    basis: Literal["inference"]


class InvestigationSection(Strict):
    findings: Annotated[list[InvestigationFinding], Field(max_length=20)]
    summary: Annotated[str, Field(max_length=1000)]


def can_explain(op: Mapping[str, Any]) -> bool:
    """A successful capable operation in the window, not after the observation."""
    return (op["role"] == "capable" and op["outcome"] == "successful" and op["in_window"]
            and op["timing"] != "after_observation")


def consistency_problem(consistency: str, verdict: str, cited: list[Mapping[str, Any]]) -> str | None:
    if consistency == "consistent_with_drift" and not (
            cited and verdict in CONSISTENT_VERDICTS and all(can_explain(op) for op in cited)):
        return "consistency_exceeds_evidence"
    if consistency == "not_consistent_with_drift" and not (cited and not any(can_explain(op) for op in cited)):
        return "consistency_contradicts_evidence"
    return None


def validate_investigation_section(output: InvestigationSection,
                                   evidence: Mapping[str, Any]) -> tuple[list[dict], list[dict]]:
    """Keep findings that cite operations sent for their resource, claim no more than the deterministic evidence
    and pass every free-text guard (with references limited to that resource); attach the deterministic facts."""
    investigation = evidence.get("investigation") or {"resources": [], "run": None}
    by_address = {r["address"]: r for r in investigation["resources"]}
    text = render_evidence(evidence)
    accepted, rejected = [], []
    for index, finding in enumerate(output.findings):
        resource = by_address.get(finding.address)
        ops = {op["op_id"]: op for op in (resource or {}).get("operations", [])}
        cited_ids = list(dict.fromkeys(finding.cited_operations))
        if resource is None or not all(op_id in ops for op_id in cited_ids):
            rejected.append({"index": index, "reason": "unsupported_citation"})
            continue
        refs = refs_from_investigation({"resources": [resource], "run": investigation["run"]}, text)
        violation = free_text_violation(finding.explanation, refs)
        if violation:
            rejected.append({"index": index, "reason": violation})
            continue
        problem = consistency_problem(finding.consistency, resource["verdict"], [ops[i] for i in cited_ids])
        if problem:
            rejected.append({"index": index, "reason": problem})
            continue
        accepted.append({
            "address": finding.address,
            "cited_operations": cited_ids,
            "consistency": finding.consistency,  # inference, bounded by the operations' deterministic roles
            "verdict": resource["verdict"],  # deterministic, authoritative
            "property_link": resource["property_link"],  # deterministic, authoritative
            "actor_attribution": resource["actor_attribution"],  # deterministic (report wording), authoritative
            "explanation": finding.explanation,
            "basis": "inference",
        })
    return accepted, rejected
