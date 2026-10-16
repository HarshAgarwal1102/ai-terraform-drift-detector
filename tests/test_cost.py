"""Task 10.2: Terraform plan cost delta correlated with drift (src/drift_engine/cost.py).

Inputs are always produced the real way: the public drift report of the Task 10.1 synthetic
fixture plan, and the real scripts/sanitize_infracost.py run on the real Infracost v0.10.46
samples (tests/fixtures/infracost/raw/). Variants are built in memory from those outputs.
No network (conftest.py guard), no clock, no Azure.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from drift_engine import cost
from drift_engine.classifier import evaluate
from drift_engine.cost import CostDeltaError, attribute, cost_delta, format_monthly_usd
from drift_engine.investigation_public import canonical_sha256
from drift_engine.report_public import public_document

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "infracost"
SANITIZER = ROOT / "scripts" / "sanitize_infracost.py"
RAW_SKU = FIXTURE / "raw" / "service_plan_sku_drift.raw.json"
RAW_SYNC = FIXTURE / "raw" / "in_sync.raw.json"
RUN_ID = "synthetic-infracost-fixture"
PLAN_ADDRESS = "azurerm_service_plan.this"
RG_ADDRESS = "azurerm_resource_group.this"


def _load_sanitizer():
    spec = importlib.util.spec_from_file_location("sanitize_infracost_for_cost", SANITIZER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


san = _load_sanitizer()


@pytest.fixture(scope="module")
def report() -> dict:
    evaluation = evaluate(str(FIXTURE / "service_plan_sku_drift" / "plan.synthetic.json"),
                          str(FIXTURE / "service_plan_sku_drift" / "detection_run.json"))
    document = public_document(evaluation.report, evaluation.plan or {})
    assert document["run"]["run_id"] == RUN_ID
    return document


def _sanitized(tmp_path_factory, report: dict, raw: Path) -> tuple[dict, dict]:
    tmp = tmp_path_factory.mktemp("cost")
    (tmp / "drift_report.json").write_text(json.dumps(report), encoding="utf-8")
    out = tmp / "report"
    out.mkdir()
    rc = san.main(["--raw", str(raw), "--drift-report", str(tmp / "drift_report.json"), "--run-id", RUN_ID,
                   "--environment", "dev", "--infracost-version", "v0.10.46", "--output-dir", str(out)])
    assert rc == 0
    assert san.main(["--check", str(out), "--run-id", RUN_ID, "--drift-report", str(tmp / "drift_report.json")]) == 0
    return tuple(json.loads((out / name).read_text(encoding="utf-8")) for name in ("infracost.json", "cost_run.json"))


@pytest.fixture(scope="module")
def sku(tmp_path_factory, report) -> tuple[dict, dict]:
    return _sanitized(tmp_path_factory, report, RAW_SKU)


@pytest.fixture(scope="module")
def in_sync(tmp_path_factory, report) -> tuple[dict, dict]:
    return _sanitized(tmp_path_factory, report, RAW_SYNC)


def bound(report: dict, cost_run: dict) -> dict:
    """cost_run re-bound to a (modified) report, as the sanitiser would bind it."""
    return {**cost_run, "drift_report_sha256": canonical_sha256(report)}


def run(report: dict, infracost: dict, cost_run: dict) -> dict:
    return cost_delta(report, infracost, bound(report, cost_run))


def resource(doc: dict, address: str = PLAN_ADDRESS) -> dict:
    return next(r for r in doc["resources"] if r["address"] == address)


def set_class(report: dict, address: str, classification: str, drift_actions, ambiguous: bool = False) -> dict:
    changed = copy.deepcopy(report)
    for item in changed["resources"]:
        if item["address"] == address:
            item.update(classification=classification, drift_actions=drift_actions, ambiguous=ambiguous)
    return changed


def diff_lines(infracost: dict, project: int = 0) -> list[dict]:
    return infracost["projects"][project]["diff"]["resources"]


def assert_partition(doc: dict) -> None:
    """Every diff line is in exactly one group (or the residual): the groups' present amounts plus
    the unreconciled residual equal the Infracost plan delta, exactly."""
    totals = doc["totals"]
    parts = [Decimal(totals[g]["monthly_cost_delta"]) for g in cost.GROUPS if totals[g]["monthly_cost_delta"]]
    parts.append(Decimal(totals["unreconciled"]["monthly_cost_delta"]))
    assert sum(parts, Decimal(0)) == Decimal(totals["infracost_plan_delta"]["monthly_cost_delta"])


def no_floats(doc: dict) -> None:
    def reject(value):
        raise AssertionError(f"JSON float found: {value}")
    json.loads(json.dumps(doc), parse_float=reject)


# --------------------------------------------------------------------------- contract and real samples


def test_task_10_1_constants_are_unchanged():
    assert (cost.INFRACOST_VERSION, cost.MODE, cost.PRICING, cost.COST_SIGN_CONVENTION) == \
        (san.INFRACOST_VERSION, san.MODE, san.PRICING, san.COST_SIGN_CONVENTION)


def test_priced_sample_is_confirmed_drift(report, sku):
    doc = cost_delta(report, *sku)
    assert doc["cost_delta_version"] == "1"
    assert doc["binding"] == {"run_id": RUN_ID, "environment": "dev", "drift_report_sha256": canonical_sha256(report)}
    assert doc["source"]["currency"] == "USD" and doc["source"]["time_generated"] == sku[0]["timeGenerated"]
    assert doc["resources"] == [{
        "address": PLAN_ADDRESS, "type": "azurerm_service_plan", "classification": "external_drift",
        "drift_actions": ["update"], "attribution": "drift", "attribution_reason": None, "cost_status": "cost_line",
        "monthly_cost_delta": "106.58", "past_monthly_cost": "119.72", "desired_monthly_cost": "13.14",
        "display": "+$106.58/month"}]
    totals = doc["totals"]
    assert totals["confirmed_drift"] == {"monthly_cost_delta": "106.58", "display": "+$106.58/month",
                                         "with_cost": 1, "without_cost": 0, "complete": True}
    for group in ("configuration", "mixed", "ambiguous", "unmatched"):
        assert totals[group] == {"monthly_cost_delta": None, "display": None, "with_cost": 0, "without_cost": 0,
                                 "complete": True}
    assert totals["infracost_plan_delta"]["monthly_cost_delta"] == "106.58"
    assert "not a drift cost" in totals["infracost_plan_delta"]["label"]
    assert (totals["past_monthly_cost"], totals["desired_monthly_cost"]) == ("119.72", "13.14")
    assert doc["reconciliation"]["status"] == "reconciled" and doc["unmatched_cost_lines"] == []
    assert_partition(doc)
    no_floats(doc)


LIMITATION_CODES = ["list_prices_usd_no_usage_file", "exact_address_match", "absent_from_diff_is_not_zero",
                    "subresources_not_attributed", "mixed_not_split", "terraform_managed_resources_only",
                    "estimate_not_billing"]


@pytest.mark.parametrize("sample", ["sku", "in_sync"])
def test_every_document_states_it_is_a_managed_resource_estimate(request, report, sample):
    """Consumers must not read the amounts as actual Azure billing or as covering resources
    outside Terraform: every document carries both limitation codes and says so in its sign rule."""
    doc = cost_delta(report, *request.getfixturevalue(sample))
    assert doc["limitations"] == LIMITATION_CODES
    assert doc["source"]["pricing"] == "list_prices_usd_no_usage_file"
    sign = doc["sign_convention"]
    for phrase in ("list-price estimate of the refreshed current configuration (prior_state)",
                   "list-price estimate of the declared configuration (planned_values)",
                   "Terraform-managed resources only", "not actual Azure billing"):
        assert phrase in sign
    assert "actual (" not in sign and "costs more" not in sign


@pytest.mark.parametrize("limitations", [
    LIMITATION_CODES[:-1],                                    # missing estimate_not_billing
    [c for c in LIMITATION_CODES if c != "terraform_managed_resources_only"],  # missing managed-only
    [*LIMITATION_CODES[:-1], LIMITATION_CODES[0]],            # duplicate replacing a code (still 7 long)
    [*LIMITATION_CODES, LIMITATION_CODES[-1]],                # duplicate added
    [*LIMITATION_CODES[:-1], "actual_azure_billing"],         # unknown replacing a code
    [*LIMITATION_CODES, "other"],                             # unknown added
    [],
], ids=["missing_not_billing", "missing_managed_only", "duplicate_replacing", "duplicate_added",
        "unknown_replacing", "unknown_added", "empty"])
def test_contract_requires_exactly_the_seven_limitation_codes(report, sku, limitations):
    doc = cost_delta(report, *sku)
    with pytest.raises(ValidationError):
        cost.CostDelta.model_validate({**doc, "limitations": limitations})


def test_contract_accepts_the_published_document_and_fixes_its_wording(report, sku):
    doc = cost_delta(report, *sku)
    cost.CostDelta.model_validate(doc)  # the published document is exactly the contract
    assert doc["limitations"] == LIMITATION_CODES  # deterministic order in generated output
    cost.CostDelta.model_validate({**doc, "limitations": list(reversed(LIMITATION_CODES))})  # order not imposed
    with pytest.raises(ValidationError):
        cost.CostDelta.model_validate({**doc, "sign_convention": "actual - desired"})


def test_free_drift_is_null_never_zero(report, in_sync):
    """The in-sync sample prices nothing: the drifted resource gets no invented zero."""
    doc = cost_delta(report, *in_sync)
    item = resource(doc)
    assert (item["cost_status"], item["monthly_cost_delta"], item["past_monthly_cost"], item["display"]) == \
        ("not_in_cost_output", None, None, None)
    assert doc["totals"]["confirmed_drift"] == {"monthly_cost_delta": None, "display": None, "with_cost": 0,
                                                "without_cost": 1, "complete": False}
    assert doc["totals"]["infracost_plan_delta"]["monthly_cost_delta"] == "0"
    assert doc["reconciliation"]["status"] == "reconciled"
    assert_partition(doc)


def test_in_sync_report_has_no_resources(report, in_sync):
    synced = set_class(report, PLAN_ADDRESS, "in_sync", None)
    doc = run(synced, *in_sync)
    assert doc["resources"] == [] and doc["unmatched_cost_lines"] == []
    assert all(doc["totals"][g]["with_cost"] == doc["totals"][g]["without_cost"] == 0 for g in cost.GROUPS)


@pytest.mark.integration
def test_imports_no_restricted_module():
    """Phase 9B G14: ai_engine (Task 10.3) may import this module, so it must not load the Activity
    Log, attribution, investigation or WHO modules (or the Azure SDK)."""
    code = ("import sys, drift_engine.cost; print(','.join(sorted(m for m in sys.modules "
            "if m.startswith(('drift_engine', 'azure')))))")
    loaded = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert loaded.split(",") == ["drift_engine", "drift_engine.cost", "drift_engine.investigation_public",
                                 "drift_engine.models", "drift_engine.report_public"]


def test_inputs_unchanged_and_output_deterministic(report, sku):
    before = copy.deepcopy((report, *sku))
    first, second = cost_delta(report, *sku), cost_delta(report, *sku)
    assert (report, *sku) == before
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# --------------------------------------------------------------------------- attribution


@pytest.mark.parametrize("classification, drift_actions, ambiguous, expected", [
    ("external_drift", ["update"], False, ("drift", None)),
    ("external_deletion", ["delete"], False, ("drift", None)),
    ("converged_drift", ["update"], False, ("drift", None)),
    ("config_change", None, False, ("configuration", None)),
    ("resource_added", None, False, ("configuration", None)),
    ("resource_removed", None, False, ("configuration", None)),
    ("drift_and_config_change", ["update"], False, ("mixed", None)),
    ("drift_and_config_change", ["update"], True, ("ambiguous", "classifier_ambiguous")),
    ("undetermined", ["update"], True, ("ambiguous", "undetermined_classification")),
    ("undetermined", None, False, ("ambiguous", "undetermined_classification")),
    ("external_drift", ["update"], True, ("ambiguous", "classifier_ambiguous")),
    ("external_drift", None, False, ("ambiguous", "inconsistent_drift_evidence")),
    ("config_change", ["update"], False, ("ambiguous", "inconsistent_drift_evidence")),
    ("drift_and_config_change", None, False, ("ambiguous", "inconsistent_drift_evidence")),
])
def test_attribution_rules(classification, drift_actions, ambiguous, expected):
    assert attribute({"classification": classification, "drift_actions": drift_actions,
                      "ambiguous": ambiguous}) == expected


@pytest.mark.parametrize("classification, drift_actions, ambiguous, group", [
    ("config_change", None, False, "configuration"),
    ("drift_and_config_change", ["update"], False, "mixed"),
    ("undetermined", ["update"], True, "ambiguous"),
])
def test_non_drift_amounts_never_reach_confirmed_drift(report, sku, classification, drift_actions, ambiguous, group):
    doc = run(set_class(report, PLAN_ADDRESS, classification, drift_actions, ambiguous), *sku)
    assert doc["totals"][group]["monthly_cost_delta"] == "106.58"
    assert doc["totals"]["confirmed_drift"]["monthly_cost_delta"] is None
    assert doc["totals"]["confirmed_drift"]["with_cost"] == 0
    assert_partition(doc)


# --------------------------------------------------------------------------- cost status, optional amounts


def test_no_cost_change_listed_keeps_comparable_values_and_null_delta(report, sku):
    infracost = copy.deepcopy(sku[0])
    infracost["projects"][0]["diff"] = {"totalMonthlyCost": "0", "resources": []}
    doc = run(report, infracost, sku[1])
    item = resource(doc)
    assert (item["cost_status"], item["monthly_cost_delta"]) == ("no_cost_change_listed", None)
    assert (item["past_monthly_cost"], item["desired_monthly_cost"]) == ("119.72", "13.14")  # shown, never subtracted
    # Infracost's root diff total still says -106.58: reported as a residual, not enforced.
    assert doc["reconciliation"]["status"] == "residual"
    assert doc["reconciliation"]["root_vs_projects"]["residual"] == "-106.58"
    assert doc["totals"]["unreconciled"]["monthly_cost_delta"] == "106.58"
    assert_partition(doc)


def test_absent_optional_amounts_stay_null(report, sku):
    infracost = copy.deepcopy(sku[0])
    project = infracost["projects"][0]
    del project["breakdown"]["resources"][0]["monthlyCost"]
    del project["pastBreakdown"]
    del project["diff"]["resources"][0]["monthlyCost"]
    doc = run(report, infracost, sku[1])
    item = resource(doc)
    assert (item["cost_status"], item["monthly_cost_delta"], item["past_monthly_cost"],
            item["desired_monthly_cost"], item["display"]) == ("cost_line", None, None, None, None)
    assert doc["totals"]["confirmed_drift"]["complete"] is False
    project_check = doc["reconciliation"]["projects"][0]
    assert (project_check["lines_without_amount"], project_check["listed_diff_sum"]) == (1, "0")
    assert doc["reconciliation"]["status"] == "residual"
    assert_partition(doc)


def test_type_count_reasons(report, in_sync):
    drifted_rg = set_class(report, RG_ADDRESS, "external_drift", ["update"])
    doc = run(drifted_rg, *in_sync)  # azurerm_resource_group is listed only as a no-price type
    assert resource(doc, RG_ADDRESS)["cost_status"] == "no_price_resource_type"
    infracost = copy.deepcopy(in_sync[0])
    infracost["summary"]["unsupportedResourceCounts"] = {"azurerm_service_plan": 1}
    assert resource(run(report, infracost, in_sync[1]))["cost_status"] == "unsupported_resource_type"
    infracost["summary"]["noPriceResourceCounts"]["azurerm_service_plan"] = 1  # both lists: not decidable
    assert resource(run(report, infracost, in_sync[1]))["cost_status"] == "not_in_cost_output"


def test_negative_zero_is_written_as_zero(report, sku):
    infracost = copy.deepcopy(sku[0])
    diff_lines(infracost)[0]["monthlyCost"] = "0.00"
    item = resource(run(report, infracost, sku[1]))
    assert (item["monthly_cost_delta"], item["display"]) == ("0.00", "$0.00/month")


# --------------------------------------------------------------------------- unmatched and duplicate lines


def test_unmatched_lines_are_kept_with_their_amounts(report, sku):
    infracost = copy.deepcopy(sku[0])
    diff_lines(infracost).extend([
        {"name": 'module.network["main"].azurerm_service_plan.other["app"]', "resourceType": "azurerm_service_plan",
         "monthlyCost": "5.5"},
        {"name": RG_ADDRESS, "resourceType": "azurerm_resource_group", "monthlyCost": "-1.25"},
    ])
    doc = run(report, infracost, sku[1])
    assert [(line["name"], line["group"], line["reason"], line["monthly_cost_delta"])
            for line in doc["unmatched_cost_lines"]] == [
        ('module.network["main"].azurerm_service_plan.other["app"]', "unmatched", "no_report_address", "-5.5"),
        (RG_ADDRESS, "unmatched", "in_sync_in_report", "1.25")]
    assert doc["totals"]["unmatched"]["monthly_cost_delta"] == "-4.25"
    assert doc["totals"]["confirmed_drift"]["monthly_cost_delta"] == "106.58"  # unchanged
    assert doc["reconciliation"]["status"] == "residual"  # the project total was not changed
    assert_partition(doc)


def test_module_and_for_each_addresses_match_exactly(report, sku):
    address = 'module.plan["main"].azurerm_service_plan.this["app"]'
    renamed = copy.deepcopy(report)
    next(r for r in renamed["resources"] if r["address"] == PLAN_ADDRESS)["address"] = address
    infracost = copy.deepcopy(sku[0])
    for key in ("breakdown", "pastBreakdown", "diff"):
        infracost["projects"][0][key]["resources"][0]["name"] = address
    item = resource(run(renamed, infracost, sku[1]), address)
    assert (item["cost_status"], item["monthly_cost_delta"]) == ("cost_line", "106.58")
    infracost["projects"][0]["diff"]["resources"][0]["name"] = address.replace('"', "'")  # no loose matching
    doc = run(renamed, infracost, sku[1])
    assert resource(doc, address)["cost_status"] == "no_cost_change_listed"
    assert doc["unmatched_cost_lines"][0]["reason"] == "no_report_address"


def test_duplicate_names_are_ambiguous_and_still_summed(report, sku):
    infracost = copy.deepcopy(sku[0])
    infracost["projects"].append(copy.deepcopy(infracost["projects"][0]))
    infracost["diffTotalMonthlyCost"] = "-213.16"
    doc = run(report, infracost, sku[1])
    item = resource(doc)
    assert (item["attribution"], item["attribution_reason"], item["cost_status"], item["monthly_cost_delta"],
            item["past_monthly_cost"]) == ("ambiguous", "duplicate_cost_line", "duplicate_cost_lines", None, None)
    assert [(line["project"], line["group"], line["reason"]) for line in doc["unmatched_cost_lines"]] == \
        [(0, "ambiguous", "duplicate_name"), (1, "ambiguous", "duplicate_name")]
    assert doc["totals"]["ambiguous"] == {"monthly_cost_delta": "213.16", "display": "+$213.16/month",
                                          "with_cost": 2, "without_cost": 1, "complete": False}
    assert doc["totals"]["confirmed_drift"]["with_cost"] == 0
    assert_partition(doc)


def test_repeated_name_within_one_project_is_a_duplicate(report, sku):
    infracost = copy.deepcopy(sku[0])
    infracost["projects"][0]["pastBreakdown"]["resources"].append(
        copy.deepcopy(infracost["projects"][0]["pastBreakdown"]["resources"][0]))
    assert resource(run(report, infracost, sku[1]))["attribution_reason"] == "duplicate_cost_line"


def test_multiple_projects_are_summed(report, sku):
    infracost = copy.deepcopy(sku[0])
    second = copy.deepcopy(infracost["projects"][0])
    for key in ("breakdown", "pastBreakdown", "diff"):
        second[key]["resources"][0]["name"] = "azurerm_service_plan.second"
    infracost["projects"].append(second)
    infracost["diffTotalMonthlyCost"] = "-213.16"
    infracost["pastTotalMonthlyCost"], infracost["totalMonthlyCost"] = "239.44", "26.28"
    doc = run(report, infracost, sku[1])
    assert doc["reconciliation"]["status"] == "reconciled"
    assert doc["totals"]["infracost_plan_delta"]["monthly_cost_delta"] == "213.16"
    assert doc["totals"]["unmatched"]["monthly_cost_delta"] == "106.58"
    assert_partition(doc)


def test_residual_is_reported_not_enforced(report, sku):
    infracost = copy.deepcopy(sku[0])
    infracost["projects"][0]["diff"]["totalMonthlyCost"] = "-100"
    doc = run(report, infracost, sku[1])
    check = doc["reconciliation"]["projects"][0]
    assert (check["listed_diff_sum"], check["reported_diff_total"], check["residual"]) == ("-106.58", "-100", "6.58")
    assert doc["reconciliation"]["status"] == "residual"
    assert doc["totals"]["confirmed_drift"]["monthly_cost_delta"] == "106.58"


def test_project_without_diff(report, sku):
    infracost = copy.deepcopy(sku[0])
    del infracost["projects"][0]["diff"]
    doc = run(report, infracost, sku[1])
    assert doc["reconciliation"]["projects"][0] == {"project": 0, "has_diff": False, "lines": 0,
                                                    "lines_without_amount": 0, "listed_diff_sum": None,
                                                    "reported_diff_total": None, "residual": None}
    assert resource(doc)["cost_status"] == "no_cost_change_listed"
    assert_partition(doc)


# --------------------------------------------------------------------------- fail closed


def test_binding_failures(report, sku):
    infracost, cost_run = sku
    internal = {k: v for k, v in report.items() if k != "public_version"}
    cases = {
        "not_public_report": (internal, cost_run),
        "invalid_structure": ({**report, "summary": "broken"}, None),
        "binding_mismatch": (report, {**cost_run, "run_id": "github-1-1"}),
    }
    for code, (rep, manifest) in cases.items():
        with pytest.raises(CostDeltaError) as err:
            cost_delta(rep, infracost, manifest if manifest is not None else bound(rep, cost_run))
        assert err.value.code == code
    for key, value in {"environment": "prod", "drift_report_sha256": "0" * 64}.items():
        with pytest.raises(CostDeltaError) as err:
            cost_delta(report, infracost, {**cost_run, key: value})
        assert (err.value.code, err.value.where) == ("binding_mismatch", f"cost_run.{key}")
    for key in ("infracost_version", "mode", "pricing", "cost_sign_convention"):
        with pytest.raises(CostDeltaError) as err:
            cost_delta(report, infracost, {**cost_run, key: "other"})
        assert err.value.code == "unsupported_source"
    with pytest.raises(CostDeltaError) as err:
        cost_delta(report, {**infracost, "currency": "EUR"}, cost_run)
    assert err.value.code == "currency_not_usd"


@pytest.mark.parametrize("bad", [106.58, 106, None, True, "1e3", "1.", ".5", "+1", "", "1" * 41, " 1"])
def test_invalid_money_fails(report, sku, bad):
    infracost = copy.deepcopy(sku[0])
    diff_lines(infracost)[0]["monthlyCost"] = bad
    with pytest.raises(CostDeltaError) as err:
        run(report, infracost, sku[1])
    # Only the location is reported, never the value.
    assert str(err.value) == "invalid_decimal: infracost.projects[0].diff.resources[0].monthlyCost"


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(projects=[]),
    lambda d: d.update(projects={}),
    lambda d: d["projects"][0].pop("breakdown"),
    lambda d: d["projects"][0]["diff"].update(resources={}),
    lambda d: d["projects"][0]["diff"]["resources"][0].pop("name"),
    lambda d: d["projects"][0]["diff"]["resources"][0].update(resourceType=""),
    lambda d: d.update(summary=[]),
    lambda d: d.pop("timeGenerated"),
    lambda d: d["projects"][0]["diff"].pop("totalMonthlyCost"),
], ids=["no_projects", "projects_not_list", "no_breakdown", "resources_not_list", "no_name", "empty_type",
        "summary_not_object", "no_time", "no_diff_total"])
def test_invalid_structure_fails(report, sku, mutate):
    infracost = copy.deepcopy(sku[0])
    mutate(infracost)
    with pytest.raises(CostDeltaError) as err:
        run(report, infracost, sku[1])
    assert err.value.code in ("invalid_structure", "invalid_decimal")


# --------------------------------------------------------------------------- formatting


@pytest.mark.parametrize("value, text", [
    ("106.58", "+$106.58/month"), ("-13.14", "-$13.14/month"), ("0", "$0.00/month"), ("-0.00", "$0.00/month"),
    ("0.004", "$0.00/month"), ("0.005", "+$0.01/month"), ("-0.005", "-$0.01/month"), ("1234.5", "+$1234.50/month"),
    ("12345678901234567890123456789.995", "+$12345678901234567890123456790.00/month"),
])
def test_format_monthly_usd(value, text):
    assert format_monthly_usd(Decimal(value)) == text
