"""Shared fixtures for the Task 10.4 tests (unmanaged inventory and its cost estimate).

The plan and the public drift report are produced the real way (`evaluate` + `public_document`) from
the committed in-sync plan evidence, with a test subscription GUID instead of the placeholder. The
Azure side is a scripted InventorySource (`FakeArm`) shaped like real ARM responses: the portal
default set for one Linux VM (VM, OS disk, NIC, public IP, NSG, extension). Prices come from the real
Retail Prices API samples in tests/fixtures/retail_prices/ (`FakePrices`). No network, no Azure.
"""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from drift_engine.classifier import evaluate
from drift_engine.inventory import InventorySourceError
from drift_engine.report_public import public_document
from drift_engine.unmanaged_cost import PricingSourceError

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "tests" / "fixtures" / "plan_evidence" / "in_sync"
PRICES = ROOT / "tests" / "fixtures" / "retail_prices"
SUB = "00000000-0000-4000-8000-000000000001"
RG_NAME = "aitdd-dev-main-rg"
RG = f"/subscriptions/{SUB}/resourceGroups/{RG_NAME}"
VM = f"{RG}/providers/Microsoft.Compute/virtualMachines/manual-vm"
OS_DISK = f"{RG}/providers/Microsoft.Compute/disks/manual-vm-osdisk"
NIC = f"{RG}/providers/Microsoft.Network/networkInterfaces/manual-vm-nic"
PIP = f"{RG}/providers/Microsoft.Network/publicIPAddresses/manual-vm-ip"
NSG = f"{RG}/providers/Microsoft.Network/networkSecurityGroups/manual-vm-nsg"
EXT = f"{VM}/extensions/AzureMonitorLinuxAgent"
MANAGED_VNET = f"{RG}/providers/Microsoft.Network/virtualNetworks/aitdd-dev-main-vnet"
MANAGED_NSG = f"{RG}/providers/Microsoft.Network/networkSecurityGroups/aitdd-dev-main-app-nsg"
MANAGED_VM = f"{RG}/providers/Microsoft.Compute/virtualMachines/tf-vm"
VNET_ADDRESS = 'module.network["main"].azurerm_virtual_network.this'
NSG_ADDRESS = 'module.network["main"].azurerm_network_security_group.this["app"]'
MANAGED_VM_ADDRESS = "azurerm_linux_virtual_machine.tf"


def plan_and_report(tmp_path: Path, fixture: str = "in_sync") -> tuple[dict, dict]:
    """(plan, public drift report) of committed plan evidence (default in-sync) with a real-looking subscription
    GUID instead of the placeholder."""
    evidence = EVIDENCE.parent / fixture
    plan_path = tmp_path / f"plan-{fixture}.json"
    plan_path.write_text((evidence / "plan.sanitized.json").read_text().replace("<AZURE_SUBSCRIPTION_ID>", SUB))
    evaluation = evaluate(str(plan_path), str(evidence / "detection_run.json"))
    return evaluation.plan, public_document(evaluation.report, evaluation.plan)


def with_managed(plan: dict, *resources: tuple[str, str, str]) -> dict:
    """The plan with extra managed resources (address, type, id) in its prior state. The drift report is
    unchanged (the binding only checks the plan timestamp); build_index reads prior state."""
    plan = copy.deepcopy(plan)
    module = plan["prior_state"]["values"]["root_module"]
    module.setdefault("resources", [])
    for address, rtype, rid in resources:
        module["resources"].append({"address": address, "mode": "managed", "type": rtype, "name": "x",
                                    "values": {"id": rid}})
    return plan


def listing(*ids: str, location: str = "centralindia") -> list[dict]:
    out = []
    for rid in ids:
        parts = rid.split("/")
        i = [n for n, p in enumerate(parts) if p.lower() == "providers"][-1]
        rtype = "/".join([parts[i + 1]] + parts[i + 2::2])
        out.append({"id": rid, "name": parts[-1], "type": rtype, "location": location,
                    "tags": {"owner": "someone@example.com"}})  # tags are never read
    return out


def vm_details(rid: str = VM, size: str = "Standard_B1s", os_type: str = "Linux", **props) -> dict:
    properties = {"hardwareProfile": {"vmSize": size},
                  "storageProfile": {"osDisk": {"osType": os_type, "managedDisk": {"id": OS_DISK}},
                                     "imageReference": {"publisher": props.pop("publisher", "Canonical")}},
                  "osProfile": {"adminUsername": "azureuser", "computerName": "manual-vm"},
                  "instanceView": {"statuses": [{"code": "ProvisioningState/succeeded"},
                                                {"code": f"PowerState/{props.pop('power', 'running')}"}]}}
    properties.update(props)
    return {"id": rid, "name": rid.rsplit("/", 1)[-1], "location": "centralindia", "properties": properties}


def disk_details(rid: str = OS_DISK, sku: str = "Premium_LRS", size: int = 30, tier: str | None = "P4",
                 managed_by: str | None = VM, **props) -> dict:
    properties = {"diskSizeGB": size, "diskState": "Attached" if managed_by else "Unattached", **props}
    if tier:
        properties["tier"] = tier
    doc = {"id": rid, "sku": {"name": sku}, "properties": properties}
    if managed_by:
        doc["managedBy"] = managed_by
    return doc


def nic_details(rid: str = NIC, vm: str | None = VM) -> dict:
    props = {"ipConfigurations": [{"properties": {"privateIPAddress": "10.10.1.4"}}]}
    if vm:
        props["virtualMachine"] = {"id": vm}
    return {"id": rid, "properties": props}


def pip_details(rid: str = PIP, sku: str = "Standard", tier: str = "Regional", version: str = "IPv4",
                nic: str | None = NIC) -> dict:
    props = {"publicIPAddressVersion": version, "publicIPAllocationMethod": "Static", "ipAddress": "20.192.0.10"}
    if nic:
        props["ipConfiguration"] = {"id": f"{nic}/ipConfigurations/ipconfig1"}
    return {"id": rid, "sku": {"name": sku, "tier": tier}, "properties": props}


def portal_vm_details() -> dict:
    return {VM: vm_details(), OS_DISK: disk_details(), NIC: nic_details(), PIP: pip_details()}


class FakeArm:
    """Scripted InventorySource. `pages` is a list of listing pages (or InventorySourceError); `details` maps an ARM
    ID (any case) to its document or an InventorySourceError. Records every URL."""

    def __init__(self, pages, details=None):
        self.pages = list(pages)
        self.details = {k.lower(): v for k, v in (details or {}).items()}
        self.urls: list[str] = []

    def list_page(self, url):
        self.urls.append(url)
        page = self.pages.pop(0)
        if isinstance(page, BaseException):
            raise page
        items, next_link = page if isinstance(page, tuple) else (page, None)
        return copy.deepcopy(items), next_link

    def get(self, url):
        self.urls.append(url)
        item = self.details.get(urlsplit(url).path.lower(), InventorySourceError("not_found", 404))
        if isinstance(item, BaseException):
            raise item
        return copy.deepcopy(item)


def portal_vm_source() -> FakeArm:
    return FakeArm([listing(VM, OS_DISK, NIC, PIP, NSG, EXT, MANAGED_VNET)], portal_vm_details())


def price_items(name: str) -> list:
    return json.loads((PRICES / f"{name}.json").read_text(), parse_float=Decimal)["Items"]


class FakePrices:
    """RetailPriceSource answering from the real samples by filter; records every filter."""

    SAMPLES = {
        "Standard_B1s": "vm_standard_b1s", "Standard_D2s_v5": "vm_standard_d2s_v5", "'P4 LRS'": "disk_p4_lrs",
        "'E4 LRS'": "disk_e4_lrs", "'S4 LRS'": "disk_s4_lrs", "'IP Addresses'": "ip_addresses",
    }

    def __init__(self, fail: str | None = None, override: dict | None = None):
        self.fail = fail
        self.override = override or {}
        self.filters: list[str] = []

    def items(self, odata_filter):
        self.filters.append(odata_filter)
        if self.fail:
            raise PricingSourceError(self.fail)
        for key, value in self.override.items():
            if key in odata_filter:
                return copy.deepcopy(value)
        for key, name in self.SAMPLES.items():
            if key in odata_filter:
                return price_items(name)
        return []
