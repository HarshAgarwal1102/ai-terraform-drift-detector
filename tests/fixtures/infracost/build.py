"""Generate the synthetic Infracost plan used by Task 10.1 D9 (pre-implementation live check and tests).

NOT real Azure evidence: a `terraform show -json`-shaped plan with both `prior_state`
(the refreshed, real view) and `planned_values` (the desired view), so Infracost
v0.10.46 builds `pastBreakdown` from `prior_state` and `breakdown` from
`planned_values` (`infracost breakdown --path plan.synthetic.json --format json`).
No pricing data is stored here; prices come only from a live Infracost run.

Scenario `service_plan_sku_drift`:
  - `azurerm_resource_group.this`: no-op; a free resource type in Infracost.
  - `azurerm_service_plan.this` (Linux, 1 worker, centralindia): Terraform
    declares `B1`; the plan was scaled up outside Terraform to `P1v3`. The refreshed
    real view (`prior_state`) is `P1v3`, the desired view (`planned_values`) is `B1`,
    and the plan updates `sku_name` P1v3 -> B1 (`resource_drift` records B1 -> P1v3).

Expected (Task 10.1 D3): pastTotalMonthlyCost (P1v3) > totalMonthlyCost (B1), so
diffTotalMonthlyCost < 0 and drift cost = -diffTotalMonthlyCost > 0. Both totals
must be non-zero.

All identifiers are synthetic: the subscription is the `<AZURE_SUBSCRIPTION_ID>`
placeholder, names use the `aitdd-fixture-` prefix, and there are no credentials,
author data or sensitive values.

    python3 tests/fixtures/infracost/build.py     # rewrites the JSON files here
"""

from __future__ import annotations

import copy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SCENARIO = "service_plan_sku_drift"
PROVIDER = "registry.terraform.io/hashicorp/azurerm"
RG_ID = "/subscriptions/<AZURE_SUBSCRIPTION_ID>/resourceGroups/aitdd-fixture-rg"
TAGS = {"environment": "dev", "managed_by": "terraform", "project": "ai-terraform-drift-detector"}
TIMESTAMP = "2026-10-04T00:00:00Z"

RESOURCE_GROUP = {
    "id": RG_ID, "location": "centralindia", "managed_by": None, "name": "aitdd-fixture-rg",
    "tags": TAGS, "timeouts": None,
}
SERVICE_PLAN = {
    "app_service_environment_id": None,
    "id": f"{RG_ID}/providers/Microsoft.Web/serverFarms/aitdd-fixture-plan",
    "kind": "linux", "location": "centralindia", "maximum_elastic_worker_count": 1,
    "name": "aitdd-fixture-plan", "os_type": "Linux", "per_site_scaling_enabled": False,
    "premium_plan_auto_scale_enabled": False,
    "reserved": True, "resource_group_name": "aitdd-fixture-rg", "sku_name": "B1", "tags": TAGS, "timeouts": None,
    "worker_count": 1, "zone_balancing_enabled": False,
}
DESIRED_SKU = "B1"   # declared in configuration; planned_values
REAL_SKU = "P1v3"    # changed outside Terraform; refreshed prior_state


def plan_resource(rtype: str, values: dict, schema_version: int = 0) -> dict:
    return {"address": f"{rtype}.this", "mode": "managed", "type": rtype, "name": "this",
            "provider_name": PROVIDER, "schema_version": schema_version, "values": values,
            "sensitive_values": {"tags": {}}}


def change(rtype: str, before: dict, after: dict, actions: list[str]) -> dict:
    return {"address": f"{rtype}.this", "mode": "managed", "type": rtype, "name": "this",
            "provider_name": PROVIDER,
            "change": {"actions": actions, "before": before, "after": after, "after_unknown": {},
                       "before_sensitive": {"tags": {}}, "after_sensitive": {"tags": {}}}}


def build() -> dict:
    real_plan = {**copy.deepcopy(SERVICE_PLAN), "sku_name": REAL_SKU}
    desired_plan = {**copy.deepcopy(SERVICE_PLAN), "sku_name": DESIRED_SKU}
    state_plan = copy.deepcopy(desired_plan)  # last applied state: what Terraform wrote
    rg = copy.deepcopy(RESOURCE_GROUP)

    config_rg = {"address": "azurerm_resource_group.this", "mode": "managed", "type": "azurerm_resource_group",
                 "name": "this", "provider_config_key": "azurerm", "schema_version": 0,
                 "expressions": {"location": {"constant_value": "centralindia"},
                                 "name": {"constant_value": "aitdd-fixture-rg"},
                                 "tags": {"constant_value": TAGS}}}
    config_plan = {"address": "azurerm_service_plan.this", "mode": "managed", "type": "azurerm_service_plan",
                   "name": "this", "provider_config_key": "azurerm", "schema_version": 1,
                   "expressions": {
                       "location": {"references": ["azurerm_resource_group.this.location",
                                                   "azurerm_resource_group.this"]},
                       "name": {"constant_value": "aitdd-fixture-plan"},
                       "os_type": {"constant_value": "Linux"},
                       "resource_group_name": {"references": ["azurerm_resource_group.this.name",
                                                              "azurerm_resource_group.this"]},
                       "sku_name": {"constant_value": DESIRED_SKU},
                       "tags": {"constant_value": TAGS},
                       "worker_count": {"constant_value": 1}}}

    return {
        "format_version": "1.2",
        "terraform_version": "1.14.7",
        "planned_values": {"root_module": {"resources": [
            plan_resource("azurerm_resource_group", rg),
            plan_resource("azurerm_service_plan", desired_plan, 1),
        ]}},
        "resource_drift": [change("azurerm_service_plan", state_plan, real_plan, ["update"])],
        "resource_changes": [
            change("azurerm_resource_group", rg, rg, ["no-op"]),
            change("azurerm_service_plan", real_plan, desired_plan, ["update"]),
        ],
        "prior_state": {"format_version": "1.0", "terraform_version": "1.14.7",
                        "values": {"root_module": {"resources": [
                            plan_resource("azurerm_resource_group", rg),
                            plan_resource("azurerm_service_plan", real_plan, 1),
                        ]}}},
        "configuration": {
            "provider_config": {"azurerm": {"name": "azurerm", "full_name": PROVIDER, "version_constraint": "~> 5.0",
                                            "expressions": {"features": [{}]}}},
            "root_module": {"resources": [config_rg, config_plan]},
        },
        "relevant_attributes": [{"resource": "azurerm_service_plan.this", "attribute": ["sku_name"]}],
        "timestamp": TIMESTAMP,
        "applyable": True,
        "complete": True,
        "errored": False,
    }


def manifest() -> dict:
    return {"backend_key": "dev.tfstate", "environment": "dev", "failure_reason": None, "failure_stage": None,
            "finished_at": TIMESTAMP, "git_commit": None, "outcome": "succeeded", "plan_exit_code": 2,
            "run_id": "synthetic-infracost-fixture", "show_exit_code": 0, "started_at": TIMESTAMP,
            "terraform_version": "1.14.7", "working_dir": "terraform/environments/dev"}


def write(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main() -> None:
    out = os.path.join(HERE, SCENARIO)
    os.makedirs(out, exist_ok=True)
    write(os.path.join(out, "plan.synthetic.json"), build())
    write(os.path.join(out, "detection_run.json"), manifest())


if __name__ == "__main__":
    main()
