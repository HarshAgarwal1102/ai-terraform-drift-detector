"""Tests for the dashboard's unmanaged-resource view (Task 13.3, data of Task 10.4).

Run from the repository root:
    pytest tests/test_dashboard_unmanaged.py

The documents are produced the real way, as in tests/test_unmanaged_ai.py: the public drift report of the
committed in-sync evidence, the inventory of drift_engine.inventory over scripted ARM responses (the portal
default set for one Linux VM), the estimate of drift_engine.unmanaged_cost over the real Retail Prices API
samples, and the AI report v4 built by the analysis graph without an LLM. No network, no Azure.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / ".." / "scripts"))

from drift_engine import inventory as inv  # noqa: E402
from drift_engine import unmanaged_cost as uc  # noqa: E402
from unmanaged_fixtures import (  # noqa: E402
    MANAGED_VNET, VNET_ADDRESS, FakePrices, plan_and_report, portal_vm_source, with_managed,
)

HAS_AI_EXTRA = all(importlib.util.find_spec(m) for m in ("langgraph", "langchain_openai"))
pytestmark = pytest.mark.skipif(not (HAS_AI_EXTRA and importlib.util.find_spec("fastapi")),
                                reason="needs the 'ai' and 'dashboard' extras")

NOW = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)
TOKEN = "u" * 40


@pytest.fixture(scope="module")
def documents(tmp_path_factory):
    from ai_engine.graph import run_analysis
    from ai_engine.nodes import unmanaged_resources as ur

    tmp = tmp_path_factory.mktemp("unmanaged")
    plan, report = plan_and_report(tmp)
    plan = with_managed(plan, (VNET_ADDRESS, "azurerm_virtual_network", MANAGED_VNET))
    inventory = json.loads(inv.render_inventory(inv.collect_inventory(plan, report, portal_vm_source(),
                                                                      now=lambda: NOW)))
    cost = json.loads(uc.render_cost(uc.estimate_costs(inv.load_inventory(inventory), inventory, FakePrices(),
                                                       now=lambda: NOW)))
    directory = tmp / "unmanaged-resources-1"
    directory.mkdir()
    (directory / "unmanaged_inventory.json").write_text(json.dumps(inventory))
    (directory / "unmanaged_cost.json").write_text(json.dumps(cost))
    docs = ur.read_unmanaged_documents(directory)
    state = run_analysis(report, unmanaged=ur.unmanaged_input(report, docs["inventory"], docs["cost"]))
    ai_report = json.loads(json.dumps(state["report"]))
    assert ai_report["report_version"] == "4" and ai_report["unmanaged"]["status"] == "complete"
    return report, inventory, cost, ai_report


def data_dir(tmp_path: Path, report: dict, inventory: dict | None, ai_report: dict | None) -> Path:
    data = tmp_path / "data"
    for name, file, doc in (("drift-report-1", "drift_report.json", report),
                            ("unmanaged-inventory-1", "unmanaged_inventory.json", inventory),
                            ("ai-analysis-report-1", "ai_analysis_report.json", ai_report)):
        if doc is not None:
            (data / name).mkdir(parents=True)
            (data / name / file).write_text(json.dumps(doc))
    return data


def client(tmp_path: Path, data: Path):
    from fastapi.testclient import TestClient

    from dashboard_api.app import create_app

    tmp_path.mkdir(parents=True, exist_ok=True)
    users = tmp_path / "users.json"
    users.write_text(json.dumps({"users": [{"name": "m", "token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
                                            "roles": ["viewer"]}]}))
    users.chmod(0o600)
    return TestClient(create_app(data_dir=str(data), users_file=str(users), environ={}, ui_dir=None))


def get(c, path: str) -> dict:
    response = c.get(path, headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_inventory_with_ai_cost(tmp_path, documents):
    report, inventory, cost, ai_report = documents
    c = client(tmp_path, data_dir(tmp_path, report, inventory, ai_report))
    run = get(c, "/api/unmanaged")["runs"][0]
    assert (run["available"], run["source"], run["outcome"]) == (True, "unmanaged_inventory_artifact", "complete")
    assert (run["counts"]["unmanaged"], run["counts"]["managed"], run["counts"]["attached_to_managed"]) == (6, 1, 0)
    assert run["cost"]["status"] == "complete"
    assert run["cost"]["pricing_source"] == "azure_retail_prices_api_list_prices_usd"
    assert run["cost"]["totals"] == cost["totals"]
    assert run["cost"]["totals"]["estimated_monthly_cost"] == "17.1055"
    by_ref = {r["ref"]: r for r in run["resources"]}
    for estimate in cost["resources"]:  # every amount is the AI report's, unchanged
        assert by_ref[estimate["ref"]]["estimate"] == {"status": estimate["estimate_status"], "reason": estimate["reason"],
                                                      "monthly_cost": estimate["monthly_cost"],
                                                      "display": estimate["display"]}
    vm = next(r for r in run["resources"] if r["type"] == "Microsoft.Compute/virtualMachines")
    assert (vm["name"], vm["category"], vm["estimate"]["monthly_cost"]) == ("manual-vm", "unmanaged", "8.1760")
    assert run["limitations"][-1] == "not_drift"
    text = json.dumps(run)
    assert "/subscriptions/" not in text and "00000000-0000-4000-8000-000000000001" not in text  # public data only
    summary = get(c, "/api/summary")
    env = summary["environments"][0]
    assert env["unmanaged"] == {"available": True, "outcome": "complete", "unmanaged": 6, "attached_to_managed": 0,
                                "cost_status": "complete", "estimated_monthly_cost": "17.1055",
                                "display": cost["totals"]["display"], "complete": True}
    assert env["artifacts"]["unmanaged_inventory"] is True
    assert summary["overview"]["active_drifts"] == 0  # unmanaged resources are never drift
    assert get(c, f"/api/reports/{report['run']['run_id']}")["unmanaged"]["counts"]["unmanaged"] == 6


def test_inventory_without_ai_report_has_no_amounts(tmp_path, documents):
    report, inventory, _, _ = documents
    run = get(client(tmp_path, data_dir(tmp_path, report, inventory, None)), "/api/unmanaged")["runs"][0]
    assert (run["available"], run["cost"]["status"], run["cost"]["totals"]) == (True, "no_ai_report", None)
    assert {r["estimate"] for r in run["resources"]} == {None}


def test_ai_report_alone_provides_the_listing(tmp_path, documents):
    report, _, cost, ai_report = documents
    run = get(client(tmp_path, data_dir(tmp_path, report, None, ai_report)), "/api/unmanaged")["runs"][0]
    assert (run["available"], run["source"], run["cost"]["status"]) == (True, "ai_report", "complete")
    assert run["cost"]["totals"] == cost["totals"]


def test_a_different_inventory_gets_no_ai_amounts(tmp_path, documents):
    report, inventory, _, ai_report = documents
    other = copy.deepcopy(inventory)
    other["collected_at"] = "2026-10-11T12:30:00.000000Z"  # still valid and bound, but not what was priced
    run = get(client(tmp_path, data_dir(tmp_path, report, other, ai_report)), "/api/unmanaged")["runs"][0]
    assert (run["available"], run["source"], run["cost"]["status"]) == (True, "unmanaged_inventory_artifact",
                                                                         "inventory_mismatch")
    assert {r["estimate"] for r in run["resources"]} == {None}


def test_unbound_or_invalid_inventories_are_not_used(tmp_path, documents):
    from dashboard_api import store

    report, inventory, _, _ = documents
    unbound = copy.deepcopy(inventory)
    unbound["binding"]["drift_report_sha256"] = "0" * 64
    data = data_dir(tmp_path, report, unbound, None)
    (data / "x-leak").mkdir()
    leaky = copy.deepcopy(inventory)
    leaky["resources"][0]["name"] = "someone@example.com"
    (data / "x-leak" / "unmanaged_inventory.json").write_text(json.dumps(leaky))
    index = store.load(str(data))
    assert index.bundles[0].inventory is None
    assert index.problems["unmanaged_inventory_invalid"] == 1
    run = get(client(tmp_path, data), "/api/unmanaged")["runs"][0]
    assert (run["available"], run["resources"], run["cost"]["status"]) == (False, [], "no_ai_report")


@pytest.fixture(scope="module")
def drift_cost(tmp_path_factory):
    """A real cost_delta v1 document (drift_engine.cost over the sanitised Infracost fixture of Task 10.2)."""
    import test_cost

    from drift_engine.investigation_public import canonical_sha256

    evaluation = test_cost.evaluate(str(test_cost.FIXTURE / "service_plan_sku_drift" / "plan.synthetic.json"),
                                    str(test_cost.FIXTURE / "service_plan_sku_drift" / "detection_run.json"))
    report = test_cost.public_document(evaluation.report, evaluation.plan or {})
    infracost, cost_run = test_cost._sanitized(tmp_path_factory, report, test_cost.RAW_SKU)
    return report, canonical_sha256(report), test_cost.cost_delta(report, infracost, cost_run)


def test_cost_impact_needs_a_validated_bound_v3_v4_cost_section(drift_cost):
    from dashboard_api import views
    from dashboard_api.store import Bundle

    report, sha, delta = drift_cost
    run_id = report["run"]["run_id"]
    expected = delta["totals"]["confirmed_drift"]

    def view(ai, rid=run_id, digest=sha):
        return views.cost_impact(Bundle(rid, report, digest, ai))

    def ai(version, cost):
        return {"report_version": version, "cost": cost}

    complete = {"status": "complete", "pricing_source": "infracost_list_prices_usd_no_usage_file", "cost_delta": delta}
    for version in ("3", "4"):
        assert view(ai(version, complete)) == {"status": "complete", "monthly_cost_delta": expected["monthly_cost_delta"],
                                               "display": expected["display"], "complete": expected["complete"],
                                               "with_cost": expected["with_cost"],
                                               "pricing_source": "infracost_list_prices_usd_no_usage_file"}
    assert expected["monthly_cost_delta"] is not None
    assert view(ai("2", {"monetary_impact": "not_determinable_from_evidence", "pricing_source": None}))["status"] \
        == "not_available"
    assert view(ai("2", complete))["status"] == "not_available"  # a v2 report never yields an amount
    assert view(ai("5", complete))["status"] == "unsupported_report_version"
    assert view({"cost": complete})["status"] == "unsupported_report_version"  # no version: refused
    assert view(ai("4", {"status": "not_available"}))["status"] == "not_available"
    tampered = json.loads(json.dumps(complete))
    tampered["cost_delta"]["totals"]["confirmed_drift"]["monthly_cost_delta"] = "not money"
    assert view(ai("4", tampered))["status"] == "cost_delta_invalid"
    assert view(ai("4", complete), rid="github-9-9")["status"] == "cost_delta_mismatch"  # another run's estimate
    assert view(ai("4", complete), digest="0" * 64)["status"] == "cost_delta_mismatch"
    assert view(None)["status"] == "no_ai_report"


def test_overview_cost_states(tmp_path_factory, drift_cost):
    """estimated: a validated cost line; no_drift_cost: validated, no confirmed-drift line (as in every real v3/v4
    in-sync run); not_available: anything else. Never an invented $0."""
    import test_cost

    from dashboard_api import views
    from dashboard_api.store import Bundle

    report, sha, delta = drift_cost
    infracost, cost_run = test_cost._sanitized(tmp_path_factory, report, test_cost.RAW_SYNC)
    in_sync = test_cost.cost_delta(report, infracost, cost_run)
    assert in_sync["totals"]["confirmed_drift"]["with_cost"] == 0

    def overview(cost):
        bundle = Bundle(report["run"]["run_id"], report, sha, {"report_version": "4", "cost": cost})
        return views.summary([bundle], [bundle], {})["overview"]["monthly_cost_impact"]

    complete = lambda doc: {"status": "complete", "pricing_source": "x", "cost_delta": doc}  # noqa: E731
    assert overview(complete(in_sync)) == {"status": "no_drift_cost", "monthly_cost_delta": None, "complete": False,
                                           "currency": None}
    estimated = overview(complete(delta))
    assert (estimated["status"], estimated["currency"]) == ("estimated", "USD")
    assert estimated["monthly_cost_delta"] == str(views._decimal(delta["totals"]["confirmed_drift"]["monthly_cost_delta"]))
    assert overview({"status": "not_available"})["status"] == "not_available"


def test_unmanaged_needs_report_v4(tmp_path, documents):
    report, inventory, _, ai_report = documents
    for version, status in (("3", "not_in_ai_report"), ("2", "not_in_ai_report"), ("9", "unsupported_report_version")):
        older = dict(ai_report, report_version=version)
        run = get(client(tmp_path / version, data_dir(tmp_path / version, report, inventory, older)),
                  "/api/unmanaged")["runs"][0]
        assert (run["cost"]["status"], run["cost"]["totals"]) == (status, None), version
        assert {r["estimate"] for r in run["resources"]} == {None}


def test_unmanaged_cost_of_another_run_is_refused(tmp_path, documents):
    report, inventory, _, ai_report = documents
    forged = json.loads(json.dumps(ai_report))
    forged["unmanaged"]["cost"]["binding"]["run_id"] = "github-9-9"  # same inventory hash, different run
    run = get(client(tmp_path, data_dir(tmp_path, report, inventory, forged)), "/api/unmanaged")["runs"][0]
    assert run["cost"]["status"] in ("inventory_mismatch", "ai_section_invalid")
    assert {r["estimate"] for r in run["resources"]} == {None}


def test_fetch_script_downloads_unmanaged_inventories():
    import fetch_dashboard_data as fdd

    match = fdd.ARTIFACT_NAME.match("unmanaged-inventory-38140497702")
    assert match and fdd.ARTIFACT_FILES[match.group(1)] == "unmanaged_inventory.json"
