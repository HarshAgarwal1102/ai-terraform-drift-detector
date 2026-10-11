"""Unmanaged Azure resources in the AI report (Task 10.4, report v4). Deterministic; no LLM.

`ai-analysis --unmanaged DIR` reads exactly `unmanaged_inventory.json` and `unmanaged_cost.json`
(strict JSON, 10 MiB cap each) from the drift workflow's `unmanaged-resources-<run id>` artifact.
`unmanaged_input` validates them with drift_engine.unmanaged_cost.check_documents (leak scan, the two
strict contracts, the inventory bound to this public drift report and the cost to that inventory),
giving status `complete` with both documents, `not_available` (no input) or `rejected` with a fixed
code. `derive_unmanaged` turns that into fixed `unmanaged.*.v1` statements.

The section is separate from everything else in the report: unmanaged resources are not drift (they
never change the drift result, the investigation or the recommendation), and their Azure Retail
Prices API estimate is never added to, compared with or mixed into the Infracost cost section. The
LLM receives nothing from it. `complete` means the input was accepted, not that the inventory or the
pricing succeeded: the statements state the inventory outcome and pricing status as recorded.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from drift_engine import unmanaged_cost as uc
from drift_engine.investigation_public import canonical_sha256, strict_json
from drift_engine.logs import log_event

logger = logging.getLogger(__name__)

UNMANAGED_FILES = ("unmanaged_cost.json", "unmanaged_inventory.json")
MAX_FILE_BYTES = uc.MAX_INPUT_BYTES
NOT_PROVIDED = "unmanaged_input_not_provided"
INPUT_REJECTIONS = ("unmanaged_input_incomplete", "unmanaged_input_unreadable")
REJECTION_CODES = tuple(sorted(("binding_mismatch", "contract", "leak") + INPUT_REJECTIONS))
PRICING_SOURCE = uc.PRICING_SOURCE

_NOTE = "Azure Retail Prices API list price, not actual Azure billing"
UNMANAGED_TEMPLATES: dict[str, str] = {
    "unmanaged.status_not_available.v1": "No unmanaged resource inventory was provided: resources outside Terraform "
                                         "are not determinable from available evidence.",
    "unmanaged.status_rejected.v1": "The unmanaged resource inventory was rejected ({code}): resources outside "
                                    "Terraform are not determinable from available evidence.",
    "unmanaged.inventory.v1": "Inventory {outcome} for {groups} Terraform-managed resource group(s): {listed} "
                              "resource(s) listed, {managed} managed by Terraform, {unmanaged} not managed by "
                              "Terraform, {attached} attached to a Terraform-managed resource (not counted as "
                              "unmanaged). Unmanaged resources are not drift.",
    "unmanaged.inventory_not_complete.v1": "The inventory is {outcome} ({failure}): it is not a complete list of "
                                           "resources outside Terraform.",
    "unmanaged.by_type.v1": "Unmanaged resources by type: {types}.",
    "unmanaged.resource.v1": "{label} ({type}, {location}): not managed by Terraform; estimated {display} "
                             "({amount} USD per month; {estimate}); " + _NOTE + ".",
    "unmanaged.resource_unpriced.v1": "{label} ({type}, {location}): not managed by Terraform; monthly cost not "
                                      "determinable from available evidence ({reason}).",
    "unmanaged.total.v1": "Estimated monthly list-price cost of unmanaged resources: {display} ({amount} USD per "
                          "month) from {priced} of {resources} resource(s); separate from the Infracost "
                          "Terraform plan estimate; never drift cost.",
    # some resources have no or only a partial estimate: the amount is a lower bound, never the complete cost
    "unmanaged.total_incomplete.v1": "Estimated monthly list-price cost of unmanaged resources: at least {display} "
                                     "({amount} USD per month) — incomplete estimate: {unavailable} unavailable, "
                                     "{partial} partial (pricing {status}); {priced} of {resources} resource(s) "
                                     "fully priced; separate from the Infracost Terraform plan estimate; never drift "
                                     "cost.",
    "unmanaged.total_unavailable.v1": "Estimated monthly cost of unmanaged resources: not determinable from "
                                      "available evidence (pricing {status}, {failure}).",
}


def unmanaged_statement(template_id: str, **slots: Any) -> dict[str, str]:
    return {"id": template_id, "text": UNMANAGED_TEMPLATES[template_id].format(**slots)}


def _not_complete(status: str, reason: str, input_sha256: Mapping[str, str] | None = None) -> dict[str, Any]:
    return {"status": status, "reason": reason, "inventory": None, "cost": None,
            "input_sha256": dict(input_sha256) if input_sha256 else None}


NOT_AVAILABLE = _not_complete("not_available", NOT_PROVIDED)


def unmanaged_input(drift_report: Mapping[str, Any], inventory: Any, cost: Any) -> dict[str, Any]:
    """`complete` with both validated documents, or `rejected` with a check code. Hashes are the canonical
    SHA-256 of the parsed documents (set whenever both parsed)."""
    hashes = {"inventory": canonical_sha256(inventory), "cost": canonical_sha256(cost)}
    try:
        doc, priced = uc.check_documents(inventory, cost, drift_report)
    except uc.UnmanagedInputError as exc:
        return _not_complete("rejected", exc.code, hashes)
    return {"status": "complete", "reason": None, "inventory": doc.model_dump(mode="json"),
            "cost": priced.model_dump(mode="json"), "input_sha256": hashes}


def rejected_unmanaged(code: str) -> dict[str, Any]:
    return _not_complete("rejected", code)


def read_unmanaged_documents(directory: str | os.PathLike) -> dict[str, Any] | str:
    """{"inventory": ..., "cost": ...} parsed (strict JSON) from a directory holding exactly the two files, or the
    rejection code. Never raises for a bad directory and never returns file content in a code."""
    path = Path(directory)
    try:
        names = sorted(entry.name for entry in path.iterdir())
    except OSError:
        return "unmanaged_input_unreadable"
    if tuple(names) != UNMANAGED_FILES or not all((path / name).is_file() for name in names):
        return "unmanaged_input_incomplete"
    documents = {}
    for name in UNMANAGED_FILES:
        try:
            with open(path / name, "rb") as fh:
                data = fh.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                return "unmanaged_input_unreadable"
            documents[name] = strict_json(data)
        except (OSError, ValueError, RecursionError, UnicodeDecodeError):
            return "unmanaged_input_unreadable"
    return {"inventory": documents["unmanaged_inventory.json"], "cost": documents["unmanaged_cost.json"]}


def load_unmanaged_input(directory: str | os.PathLike, drift_report: Mapping[str, Any]) -> dict[str, Any]:
    documents = read_unmanaged_documents(directory)
    if isinstance(documents, str):
        return rejected_unmanaged(documents)
    return unmanaged_input(drift_report, documents["inventory"], documents["cost"])


# --------------------------------------------------------------------------- statements


def _label(entry: Mapping[str, Any]) -> str:
    return entry["name"] if entry["name"] else f"{entry['ref']} (name withheld)"


def resource_statement(entry: Mapping[str, Any]) -> dict[str, str]:
    location = entry["location"] or "location unknown"
    if entry["monthly_cost"] is None:
        return unmanaged_statement("unmanaged.resource_unpriced.v1", label=_label(entry), type=entry["type"],
                                   location=location, reason=entry["reason"])
    estimate = entry["estimate_status"] + (f": {entry['reason']}" if entry["reason"] else "")
    return unmanaged_statement("unmanaged.resource.v1", label=_label(entry), type=entry["type"], location=location,
                               display=entry["display"], amount=entry["monthly_cost"], estimate=estimate)


def unmanaged_statements(section: Mapping[str, Any]) -> list[dict[str, str]]:
    """Run-level statements: exactly one status statement unless `complete`."""
    if section["status"] == "not_available":
        return [unmanaged_statement("unmanaged.status_not_available.v1")]
    if section["status"] == "rejected":
        return [unmanaged_statement("unmanaged.status_rejected.v1", code=section["reason"])]
    inventory, cost = section["inventory"], section["cost"]
    counts = inventory["counts"]
    out = [unmanaged_statement("unmanaged.inventory.v1", outcome=inventory["outcome"],
                               groups=len(inventory["scopes"]), listed=counts["listed"], managed=counts["managed"],
                               unmanaged=counts["unmanaged"], attached=counts["attached_to_managed"])]
    if inventory["outcome"] != "complete":
        out.append(unmanaged_statement("unmanaged.inventory_not_complete.v1", outcome=inventory["outcome"],
                                       failure=inventory["failure"] or "incomplete"))
    if inventory["unmanaged_by_type"]:
        out.append(unmanaged_statement("unmanaged.by_type.v1", types=", ".join(
            f"{k} {v}" for k, v in inventory["unmanaged_by_type"].items())))
    totals = cost["totals"]
    if totals["estimated_monthly_cost"] is None:
        out.append(unmanaged_statement("unmanaged.total_unavailable.v1", status=cost["status"],
                                       failure=cost["failure"] or "no resource has an estimate"))
    else:
        priced = totals["resources"] - totals["unavailable"] - totals["partial"]
        if totals["complete"]:
            out.append(unmanaged_statement("unmanaged.total.v1", display=totals["display"],
                                           amount=totals["estimated_monthly_cost"], priced=priced,
                                           resources=totals["resources"]))
        else:
            out.append(unmanaged_statement("unmanaged.total_incomplete.v1", display=totals["display"],
                                           amount=totals["estimated_monthly_cost"], unavailable=totals["unavailable"],
                                           partial=totals["partial"], status=cost["status"], priced=priced,
                                           resources=totals["resources"]))
    return out


def derive_unmanaged(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph node: the deterministic unmanaged section. Re-checks a `complete` input against both contracts
    and this drift report (an inconsistent input is an internal error, never a silent result)."""
    given = state.get("unmanaged") or NOT_AVAILABLE  # an unset channel reads as LangGraph's empty seed
    status = given["status"]
    if status not in ("complete", "not_available", "rejected"):
        raise ValueError("unmanaged input status is invalid")
    section: dict[str, Any] = {"status": status, "reason": given["reason"], "inventory": None, "cost": None,
                               "input_sha256": given.get("input_sha256"), "resources": []}
    if status == "complete":
        plain = json.loads(json.dumps({"inventory": given["inventory"], "cost": given["cost"]}))
        try:
            inventory, cost = uc.check_documents(plain["inventory"], plain["cost"], state["drift_report"])
        except uc.UnmanagedInputError:
            raise ValueError("unmanaged input is not a valid document pair bound to this drift report") from None
        section["inventory"] = inventory.model_dump(mode="json")
        section["cost"] = cost.model_dump(mode="json")
        section["resources"] = [{"ref": entry["ref"], "statements": [resource_statement(entry)]}
                                for entry in section["cost"]["resources"]]
    elif given.get("inventory") is not None or given.get("cost") is not None \
            or (status == "rejected" and given["reason"] not in REJECTION_CODES) \
            or (status == "not_available" and given["reason"] != NOT_PROVIDED):
        raise ValueError("unmanaged input reason is inconsistent with its status")
    section["statements"] = unmanaged_statements(section)
    log_event(logger, logging.INFO, "unmanaged_derived", "unmanaged section derived", status=status,
              resources=len(section["resources"]))
    return {"unmanaged_section": section}
