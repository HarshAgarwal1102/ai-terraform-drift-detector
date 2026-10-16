"""Task 10.4: the unmanaged-resource section of the AI report (report v4) and the G14 boundary.

Inputs are produced the real way: the public drift report of the committed in-sync evidence, the
inventory of drift_engine.inventory over scripted ARM responses, and the estimate of
drift_engine.unmanaged_cost over the real Retail Prices API samples. The LLM is a scripted fake that
records its prompts (no network, conftest.py guard).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from drift_engine import activity_logs, unmanaged_public
from drift_engine import inventory as inv
from drift_engine import unmanaged_cost as uc
from unmanaged_fixtures import (
    MANAGED_VNET, SUB, VNET_ADDRESS, FakeArm, FakePrices, plan_and_report, portal_vm_source, with_managed,
)

HAS_AI_EXTRA = all(importlib.util.find_spec(m) for m in ("langgraph", "langchain_openai"))
requires_ai = pytest.mark.skipif(not HAS_AI_EXTRA, reason="needs the 'ai' extra")

if HAS_AI_EXTRA:
    from ai_engine import cli as ai_cli
    from ai_engine import verify
    from ai_engine.graph import run_analysis
    from ai_engine.nodes import unmanaged_resources as ur
    from ai_engine.nodes.report_generator import UNMANAGED_LIMITATIONS, render_markdown

NOW = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)
FORBIDDEN = ("drift_engine.activity_logs", "drift_engine.attribution", "drift_engine.investigation", "drift_engine.who")


# --------------------------------------------------------------------------- module boundary (G14 addendum)


@pytest.mark.integration
@pytest.mark.parametrize("module", ["drift_engine.unmanaged_cost", "drift_engine.unmanaged_public"])
def test_public_modules_load_no_restricted_module_or_azure_sdk(module):
    code = (f"import sys, {module}; print(','.join(sorted(m for m in sys.modules "
            "if m.startswith(('drift_engine', 'azure')))))")
    loaded = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert not set(loaded.split(",")) & set(FORBIDDEN) and "azure" not in loaded
    assert set(loaded.split(",")) <= {"drift_engine", "drift_engine.investigation_public", "drift_engine.logs",
                                      "drift_engine.unmanaged_cost", "drift_engine.unmanaged_public"}


def test_copied_constants_match_the_activity_log_module():
    assert unmanaged_public.QUERY_FAILURE_CODES == activity_logs.QUERY_FAILURE_CODES
    assert uc.format_timestamp(NOW) == activity_logs.format_timestamp(NOW)
    assert inv.Inventory is unmanaged_public.Inventory and inv.load_inventory is unmanaged_public.load_inventory


# --------------------------------------------------------------------------- inputs


@pytest.fixture()
def case(tmp_path):
    plan, report = plan_and_report(tmp_path)
    return with_managed(plan, (VNET_ADDRESS, "azurerm_virtual_network", MANAGED_VNET)), report


def documents(case, source=None, prices=None) -> tuple[dict, dict]:
    plan, report = case
    doc = inv.collect_inventory(plan, report, source or portal_vm_source(), now=lambda: NOW)
    raw = json.loads(inv.render_inventory(doc))
    cost = uc.estimate_costs(inv.load_inventory(raw), raw, prices or FakePrices(), now=lambda: NOW)
    return raw, json.loads(uc.render_cost(cost))


def write_dir(tmp_path: Path, inventory: dict, cost: dict, name="unmanaged-resources-1") -> Path:
    out = tmp_path / name
    out.mkdir()
    (out / "unmanaged_inventory.json").write_text(json.dumps(inventory))
    (out / "unmanaged_cost.json").write_text(json.dumps(cost))
    return out


def analyse(report: dict, directory: Path | None = None, llm=None) -> tuple[dict, list[str], dict]:
    given, check = None, None
    if directory is not None:
        docs = ur.read_unmanaged_documents(directory)
        if isinstance(docs, str):
            given, check = ur.rejected_unmanaged(docs), {"rejected": docs}
        else:
            given, check = ur.unmanaged_input(report, docs["inventory"], docs["cost"]), docs
    kwargs = {"unmanaged": given} | ({"llm": llm} if llm is not None else {})
    state = run_analysis(report, **kwargs)
    out = json.loads(json.dumps(state["report"]))
    return out, verify.verify_report(out, report, None, None, check), check


class RecordingLLM:
    def __init__(self):
        self.prompts = []

    def invoke(self, messages):
        self.prompts.append(messages)
        empty = {"findings": [], "summary": ""}
        return json.dumps({k: empty for k in ("security_analysis", "cost_analysis", "configuration_analysis",
                                               "root_cause_analysis", "risk_assessment", "investigation_analysis")})


# --------------------------------------------------------------------------- complete


@requires_ai
def test_complete_section_states_the_portal_vm_exactly(case, tmp_path):
    report, problems, _ = analyse(case[1], write_dir(tmp_path, *documents(case)))
    assert problems == []
    u = report["unmanaged"]
    assert (report["report_version"], u["status"], u["reason"]) == ("4", "complete", None)
    assert u["pricing_source"] == "azure_retail_prices_api_list_prices_usd"
    assert report["provenance"]["versions"]["unmanaged_inventory"] == "1"
    texts = [s["text"] for s in u["statements"]]
    assert texts[0] == ("Inventory complete for 1 Terraform-managed resource group(s): 7 resource(s) listed, 1 managed "
                        "by Terraform, 6 not managed by Terraform, 0 attached to a Terraform-managed resource (not "
                        "counted as unmanaged). Unmanaged resources are not drift.")
    assert texts[-1] == ("Estimated monthly list-price cost of unmanaged resources: $17.11/month (17.1055 USD per "
                         "month) from 6 of 6 resource(s); separate from the Infracost Terraform plan estimate; never "
                         "drift cost.")
    vm = next(r for r in u["resources"] if "manual-vm (Microsoft.Compute/virtualMachines" in r["statements"][0]["text"])
    assert vm["statements"][0]["text"] == (
        "manual-vm (Microsoft.Compute/virtualMachines, centralindia): not managed by Terraform; estimated "
        "$8.18/month (8.1760 USD per month; estimated); Azure Retail Prices API list price, not actual Azure billing.")
    for line in UNMANAGED_LIMITATIONS["complete"]:
        assert line in report["limitations"]


@requires_ai
def test_unmanaged_input_never_changes_drift_cost_investigation_or_llm(tmp_path):
    plan, report = plan_and_report(tmp_path, "external_drift")  # drift: the LLM is called
    case = (plan, report)
    llm_a, llm_b = RecordingLLM(), RecordingLLM()
    without, _, _ = analyse(case[1], None, llm_a)
    with_, problems, _ = analyse(case[1], write_dir(tmp_path, *documents(case)), llm_b)
    assert problems == []
    for key in ("summary", "investigation", "resources", "analysis", "remediation", "cost", "llm"):
        assert without[key] == with_[key], key
    assert len(llm_a.prompts) == len(llm_b.prompts) == 1
    assert [m.content for m in llm_a.prompts[0]] == [m.content for m in llm_b.prompts[0]]  # nothing reaches the LLM
    assert "manual-vm" not in json.dumps([m.content for m in llm_b.prompts[0]])


@requires_ai
def test_markdown_section(case, tmp_path):
    report, _, _ = analyse(case[1], write_dir(tmp_path, *documents(case)))
    md = render_markdown(report)
    section = md.split("## Unmanaged resources (outside Terraform)")[1].split("## Recommendation & options")[0]
    assert "Not drift; not actual Azure billing; separate from the Infracost cost impact above." in section
    assert "| Ref | Type | Name | Location | Estimate (per month) | Status |" in section
    assert "| ` manual-vm ` | centralindia | $8\\.18/month | estimated |" in section
    assert "Unmanaged resources (outside Terraform, not drift): **complete**; 6 unmanaged" in md
    assert SUB not in md and "/subscriptions/" not in md


@requires_ai
def test_failed_inventory_is_stated_never_clean(case, tmp_path):
    raw, cost = documents(case, FakeArm([inv.InventorySourceError("authorization_failed", 403)]))
    report, problems, _ = analyse(case[1], write_dir(tmp_path, raw, cost))
    assert problems == [] and report["unmanaged"]["status"] == "complete"
    texts = [s["text"] for s in report["unmanaged"]["statements"]]
    assert ("The inventory is failed (listing_failed): it is not a complete list of resources outside Terraform."
            in texts)
    assert texts[-1] == ("Estimated monthly cost of unmanaged resources: not determinable from available evidence "
                         "(pricing not_run, inventory_not_complete).")
    assert "$0" not in json.dumps(report["unmanaged"]["statements"])


@requires_ai
def test_pricing_failure_is_stated(case, tmp_path):
    report, problems, _ = analyse(case[1], write_dir(tmp_path, *documents(case, prices=FakePrices(fail="throttled"))))
    assert problems == []
    total = report["unmanaged"]["statements"][-1]
    assert total == {"id": "unmanaged.total_incomplete.v1", "text": (
        "Estimated monthly list-price cost of unmanaged resources: at least $0.00/month (0 USD per month) — "
        "incomplete estimate: 3 unavailable, 0 partial (pricing failed); 3 of 6 resource(s) fully priced; separate "
        "from the Infracost Terraform plan estimate; never drift cost.")}


@requires_ai
@pytest.mark.parametrize("prices,display", [
    (FakePrices(override={"Standard_B1s": []}), "$8.93/month"),  # VM unavailable: disk 5.2795 + IP 3.650 known
    (FakePrices(fail="service_error"), "$0.00/month"),  # every billable resource unavailable
])
def test_incomplete_total_is_never_stated_as_complete(case, tmp_path, prices, display):
    """Final-review fix: with any unavailable estimate, the total is a lower bound in the statement and in the
    Markdown summary line; the per-resource statuses and the JSON totals are unchanged."""
    report, problems, _ = analyse(case[1], write_dir(tmp_path, *documents(case, prices=prices)))
    assert problems == []
    u = report["unmanaged"]
    total = u["statements"][-1]
    assert total["id"] == "unmanaged.total_incomplete.v1"
    assert total["text"].startswith(f"Estimated monthly list-price cost of unmanaged resources: at least {display} (")
    assert "— incomplete estimate:" in total["text"]
    assert not any(s["id"] == "unmanaged.total.v1" for s in u["statements"])
    assert u["cost"]["totals"]["complete"] is False and u["cost"]["totals"]["display"] == display  # data unchanged
    assert any(r["estimate_status"] == "unavailable" for r in u["cost"]["resources"])
    md = render_markdown(report)
    summary_line = next(line for line in md.splitlines() if line.startswith("- Unmanaged resources"))
    assert f"estimate At least {display.replace('.', chr(92) + '.')} — incomplete estimate" in summary_line


@requires_ai
def test_complete_total_keeps_the_complete_wording(case, tmp_path):
    report, problems, _ = analyse(case[1], write_dir(tmp_path, *documents(case)))
    assert problems == [] and report["unmanaged"]["statements"][-1]["id"] == "unmanaged.total.v1"
    summary_line = next(line for line in render_markdown(report).splitlines()
                        if line.startswith("- Unmanaged resources"))
    assert summary_line.endswith("estimate $17\\.11/month") and "At least" not in summary_line


@requires_ai
def test_verifier_rejects_complete_wording_for_an_incomplete_total(case, tmp_path):
    report, problems, check = analyse(case[1], write_dir(tmp_path, *documents(
        case, prices=FakePrices(override={"Standard_B1s": []}))))
    assert problems == []
    t = report["unmanaged"]["cost"]["totals"]
    report["unmanaged"]["statements"][-1] = ur.unmanaged_statement(
        "unmanaged.total.v1", display=t["display"], amount=t["estimated_monthly_cost"], priced=2, resources=6)
    assert "unmanaged: statements are not the fixed statements of the unmanaged input" in verify.verify_report(
        report, case[1], None, None, check)


# --------------------------------------------------------------------------- not_available / rejected


@requires_ai
def test_not_available(case):
    report, problems, _ = analyse(case[1])
    u = report["unmanaged"]
    assert problems == [] and (u["status"], u["reason"], u["inventory"], u["cost"]) == (
        "not_available", "unmanaged_input_not_provided", None, None)
    assert [s["id"] for s in u["statements"]] == ["unmanaged.status_not_available.v1"]
    assert report["provenance"]["unmanaged_input_sha256"] is None


@requires_ai
@pytest.mark.parametrize("make,code", [
    (lambda tmp, raw, cost: write_dir(tmp, raw, cost) / "missing", "unmanaged_input_unreadable"),
    (lambda tmp, raw, cost: (write_dir(tmp, raw, cost) / "unmanaged_cost.json").unlink() or tmp / "unmanaged-resources-1",
     "unmanaged_input_incomplete"),
    (lambda tmp, raw, cost: write_dir(tmp, dict(raw, counts={}), cost), "contract"),
    (lambda tmp, raw, cost: write_dir(tmp, dict(raw, x="a@b.example"), cost), "leak"),
    (lambda tmp, raw, cost: write_dir(tmp, raw, {**cost, "binding": {**cost["binding"], "inventory_sha256": "0" * 64}}),
     "binding_mismatch"),
])
def test_rejected_inputs_publish_no_resources(case, tmp_path, make, code):
    raw, cost = documents(case)
    report, problems, _ = analyse(case[1], make(tmp_path, raw, cost))
    u = report["unmanaged"]
    assert problems == [] and (u["status"], u["reason"]) == ("rejected", code)
    assert u["inventory"] is None and u["cost"] is None and u["resources"] == []
    assert "manual-vm" not in json.dumps(report)


@requires_ai
def test_inventory_of_another_report_is_rejected(case, tmp_path):
    raw, cost = documents(case)
    other = dict(case[1], has_drift=True)
    docs = ur.read_unmanaged_documents(write_dir(tmp_path, raw, cost))
    assert ur.unmanaged_input(other, docs["inventory"], docs["cost"])["reason"] == "binding_mismatch"


@requires_ai
def test_inconsistent_input_is_an_internal_error(case, tmp_path):
    raw, cost = documents(case)
    good = ur.unmanaged_input(case[1], raw, cost)
    with pytest.raises(ValueError):
        run_analysis(dict(case[1], has_drift=True), unmanaged=good)  # bound to another drift report
    with pytest.raises(ValueError):
        run_analysis(case[1], unmanaged={"status": "rejected", "reason": "free text", "inventory": None, "cost": None})
    with pytest.raises(ValueError):
        run_analysis(case[1], unmanaged={})


# --------------------------------------------------------------------------- verifier


@requires_ai
@pytest.mark.parametrize("tamper", [
    lambda r: r["unmanaged"]["cost"]["totals"].update(display="$1.00/month"),
    lambda r: r["unmanaged"]["statements"][-1].update(text="Estimated monthly cost: $0.00"),
    lambda r: r["unmanaged"]["resources"][0]["statements"][0].update(text="cheap"),
    lambda r: r["unmanaged"].update(pricing_source=None),
    lambda r: r["provenance"].update(unmanaged_input_sha256={"inventory": "0" * 64, "cost": "0" * 64}),
    lambda r: r["provenance"]["versions"].update(unmanaged_cost=None),
    lambda r: r["limitations"].remove(UNMANAGED_LIMITATIONS["complete"][1]),
    lambda r: r["unmanaged"].update(status="rejected", reason="contract", inventory=None, cost=None,
                                    pricing_source=None, resources=[],
                                    statements=[{"id": "unmanaged.status_rejected.v1", "text": "x"}]),
    lambda r: r["unmanaged"]["inventory"]["resources"][0].update(name="renamed"),
])
def test_verifier_rejects_tampering(case, tmp_path, tamper):
    report, problems, check = analyse(case[1], write_dir(tmp_path, *documents(case)))
    assert problems == []
    tamper(report)
    assert verify.verify_report(report, case[1], None, None, check) != []


@requires_ai
def test_verifier_requires_the_input_the_report_was_built_from(case, tmp_path):
    report, _, check = analyse(case[1], write_dir(tmp_path, *documents(case)))
    assert verify.verify_report(report, case[1], None, None, None) != []
    assert verify.verify_report(report, case[1], None, None, {"rejected": "contract"}) != []


# --------------------------------------------------------------------------- CLI


@requires_ai
def test_cli_unmanaged(case, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("AI_LLM_PROVIDER", "none")
    (tmp_path / "r.json").write_text(json.dumps(case[1]))
    directory = write_dir(tmp_path, *documents(case))
    assert ai_cli.main(["--report", str(tmp_path / "r.json"), "--unmanaged", str(directory),
                        "--output-dir", str(tmp_path / "out")]) == 0
    assert "unmanaged complete" in capsys.readouterr().out
    data = json.loads((tmp_path / "out" / "ai_analysis_report.json").read_text())
    assert data["unmanaged"]["cost"]["totals"]["estimated_monthly_cost"] == "17.1055"
    assert ai_cli.main(["--report", str(tmp_path / "r.json"), "--unmanaged", str(tmp_path / "nowhere"),
                        "--output-dir", str(tmp_path / "out2")]) == 0
    err = capsys.readouterr().err
    assert "unmanaged resources rejected (unmanaged_input_unreadable)" in err and str(tmp_path) not in err


def test_unmanaged_documents_do_not_change_inputs(case):
    raw, cost = documents(case)
    before = copy.deepcopy((raw, cost, case[1]))
    uc.check_documents(raw, cost, case[1])
    assert (raw, cost, case[1]) == before
