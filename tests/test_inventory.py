"""Task 10.4: unmanaged Azure resource inventory (src/drift_engine/inventory.py).

The plan and public drift report are real (`evaluate` + `public_document` over the committed in-sync
evidence); Azure is a scripted source (unmanaged_fixtures.FakeArm) or the real azure-core pipeline over a
fake HTTP adapter. No network (conftest.py guard), no Azure.
"""

from __future__ import annotations

import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from drift_engine import cli
from drift_engine import inventory as inv
from drift_engine.investigation_public import canonical_sha256
from unmanaged_fixtures import (
    EXT, MANAGED_NSG, MANAGED_VM, MANAGED_VM_ADDRESS, MANAGED_VNET, NIC, NSG, NSG_ADDRESS, OS_DISK, PIP, RG, RG_NAME,
    SUB, VM, VNET_ADDRESS, FakeArm, disk_details, listing, nic_details, pip_details, plan_and_report,
    portal_vm_details, portal_vm_source, vm_details, with_managed,
)

NOW = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def case(tmp_path):
    plan, report = plan_and_report(tmp_path)
    return with_managed(plan, (VNET_ADDRESS, "azurerm_virtual_network", MANAGED_VNET),
                        (NSG_ADDRESS, "azurerm_network_security_group", MANAGED_NSG)), report


def collect(case, source, **kwargs):
    plan, report = case
    return inv.collect_inventory(plan, report, source, now=lambda: NOW, **kwargs)


def by_name(doc):
    return {r.name: r for r in doc.resources}


# --------------------------------------------------------------------------- comparison


def test_portal_vm_is_detected_and_grouped(case):
    doc = collect(case, portal_vm_source())
    assert doc.outcome == "complete" and doc.failure is None
    assert doc.counts.model_dump() == {"listed": 7, "duplicates_dropped": 0, "managed": 1, "attached_to_managed": 0,
                                       "unmanaged": 6}
    assert doc.unmanaged_by_type == {"Microsoft.Compute/disks": 1, "Microsoft.Compute/virtualMachines": 1,
                                     "Microsoft.Compute/virtualMachines/extensions": 1,
                                     "Microsoft.Network/networkInterfaces": 1,
                                     "Microsoft.Network/networkSecurityGroups": 1,
                                     "Microsoft.Network/publicIPAddresses": 1}
    r = by_name(doc)
    assert "aitdd-dev-main-vnet" not in r  # Terraform-managed: never listed as unmanaged
    vm_ref = r["manual-vm"].ref
    assert r["manual-vm/AzureMonitorLinuxAgent"].parent.model_dump() == {"kind": "inventory", "ref": vm_ref,
                                                                          "address": None}
    assert r["manual-vm-osdisk"].attached_to.ref == vm_ref and r["manual-vm-osdisk"].category == "unmanaged"
    assert r["manual-vm-nic"].attached_to.ref == vm_ref
    assert r["manual-vm-ip"].attached_to.ref == r["manual-vm-nic"].ref  # public IP -> NIC (its ipConfiguration)
    assert r["manual-vm-nsg"].attached_to is None and r["manual-vm-nsg"].detail_status == "not_required"
    assert r["manual-vm"].pricing_inputs.model_dump(exclude_none=True) == {
        "vm_size": "Standard_B1s", "os_type": "Linux", "image_publisher": "Canonical", "marketplace_plan": False,
        "power_state": "running"}
    assert r["manual-vm-osdisk"].pricing_inputs.model_dump(exclude_none=True) == {
        "disk_sku": "Premium_LRS", "disk_size_gb": 30, "disk_tier": "P4", "disk_state": "Attached"}
    assert r["manual-vm-ip"].pricing_inputs.model_dump(exclude_none=True) == {
        "ip_sku": "Standard", "ip_tier": "Regional", "ip_version": "IPv4", "ip_allocation": "Static"}
    assert {x.resource_group for x in doc.resources} == {RG_NAME} and {x.location for x in doc.resources} == {
        "centralindia"}


def test_published_document_has_no_ids_tags_ips_or_other_properties(case):
    text = inv.render_inventory(collect(case, portal_vm_source()))
    for forbidden in (SUB, "/subscriptions/", "/providers/", "someone@example.com", "owner", "20.192.0.10",
                      "10.10.1.4", "azureuser", "ipConfiguration", "managedBy"):
        assert forbidden not in text, forbidden
    assert json.loads(text)["binding"]["drift_report_sha256"] == canonical_sha256(case[1])


def test_ids_compare_case_insensitively(case):
    plan, report = case
    plan = with_managed(plan, ("azurerm_public_ip.tf", "azurerm_public_ip", PIP.upper().replace("/SUBSCRIPTIONS/",
                                                                                              "/subscriptions/")))
    entries = listing(VM, PIP, MANAGED_VNET.upper().replace("/SUBSCRIPTIONS/", "/subscriptions/"))
    entries[0]["id"] = VM.lower()  # ARM keeps the canonical type even when an ID's case differs
    source = FakeArm([entries], {VM: vm_details(VM.lower())})
    doc = inv.collect_inventory(plan, report, source, now=lambda: NOW)
    assert doc.counts.managed == 2 and doc.counts.unmanaged == 1  # PIP and VNet managed despite the case
    assert [r.type for r in doc.resources] == ["Microsoft.Compute/virtualMachines"]


def test_managed_resources_missing_from_azure_change_nothing(case):
    doc = collect(case, FakeArm([listing(NSG)]))  # neither managed VNet nor NSG listed
    assert doc.outcome == "complete" and doc.counts.managed == 0 and doc.counts.unmanaged == 1


def test_empty_resource_group_is_a_complete_clean_inventory(case):
    doc = collect(case, FakeArm([[]]))
    assert doc.outcome == "complete" and doc.counts.listed == 0 and doc.resources == []


def test_duplicate_listing_entries_count_once(case):
    doc = collect(case, FakeArm([listing(NSG, NSG.lower(), MANAGED_VNET, MANAGED_VNET)]))
    assert doc.counts.duplicates_dropped == 2 and doc.counts.unmanaged == 1 and doc.counts.managed == 1
    assert doc.scopes[0].listed == 4


def test_child_of_a_managed_parent_is_unmanaged_with_its_managed_parent(case):
    plan, report = case
    plan = with_managed(plan, (MANAGED_VM_ADDRESS, "azurerm_linux_virtual_machine", MANAGED_VM))
    child = f"{MANAGED_VM}/extensions/CustomScript"
    doc = inv.collect_inventory(plan, report, FakeArm([listing(MANAGED_VM, child)]), now=lambda: NOW)
    (item,) = doc.resources
    assert item.category == "unmanaged" and item.name == "tf-vm/CustomScript"
    assert item.parent.model_dump() == {"kind": "managed", "ref": None, "address": MANAGED_VM_ADDRESS}


def test_disk_attached_to_a_managed_vm_is_never_unmanaged(case):
    plan, report = case
    plan = with_managed(plan, (MANAGED_VM_ADDRESS, "azurerm_linux_virtual_machine", MANAGED_VM))
    disk = f"{RG}/providers/Microsoft.Compute/disks/tf-vm-osdisk"
    source = FakeArm([listing(MANAGED_VM, disk)], {disk: disk_details(disk, managed_by=MANAGED_VM)})
    doc = inv.collect_inventory(plan, report, source, now=lambda: NOW)
    (item,) = doc.resources
    assert item.category == "attached_to_managed" and item.attached_to.address == MANAGED_VM_ADDRESS
    assert doc.counts.unmanaged == 0 and doc.counts.attached_to_managed == 1 and doc.unmanaged_by_type == {}
    assert list(inv.iter_unmanaged(doc)) == []


def test_attachment_to_a_resource_outside_scope_is_other(case):
    elsewhere = f"/subscriptions/{SUB}/resourceGroups/other-rg/providers/Microsoft.Compute/virtualMachines/x"
    source = FakeArm([listing(OS_DISK)], {OS_DISK: disk_details(managed_by=elsewhere)})
    (item,) = collect(case, source).resources
    assert item.category == "unmanaged" and item.attached_to.kind == "other"


def test_only_detail_types_are_read_and_only_get_urls_in_scope(case):
    source = portal_vm_source()
    collect(case, source)
    details = [u for u in source.urls if "/resources?" not in u]
    assert len(details) == 4 and all(inv.allowed_url(u) for u in source.urls)
    assert any("$expand=instanceView" in u for u in details)
    assert not any(NSG in u or EXT in u for u in details)


@pytest.mark.parametrize("name", [
    "12345678-1234-1234-1234-123456789abc",  # GUID
    "disk-12345678-1234-1234-1234-123456789ABC",  # embedded GUID, upper case
    "owner@example.com",  # e-mail / identity
    "vm@corp",  # any @
    "www.example.com",  # URL
    "10.0.0.4",  # IPv4 address
    "fe80..1",  # not an address: published (control for the IP rule below)
])
def test_identifier_like_names_are_withheld(case, name):
    rid = f"{RG}/providers/Microsoft.Network/networkSecurityGroups/{name}"
    (item,) = collect(case, FakeArm([listing(rid)])).resources
    if name == "fe80..1":
        assert item.name == name and item.name_status == "published"
        return
    assert item.name is None and item.name_status == "withheld_identifier_like"
    assert name not in inv.render_inventory(collect(case, FakeArm([listing(rid)])))


@pytest.mark.parametrize("name", ["manual-vm_OsDisk_1_0123456789abcdef0123456789abcdef",
                                  "vm_OsDisk_1_0123456789ABCDEF0123456789ABCDEF", "0123456789abcdef0123456789abcdef-disk"])
def test_portal_os_disk_names_with_a_hex_suffix_are_published(case, name):
    """Review fix (2026-10-11): an undashed 32-hex suffix is the disk's own generated name, not a subscription,
    tenant or resource identifier; it is published like any other name (decision 3)."""
    rid = f"{RG}/providers/Microsoft.Compute/disks/{name}"
    doc = collect(case, FakeArm([listing(rid)], {rid: disk_details(rid, managed_by=None)}))
    (item,) = doc.resources
    assert item.name == name and item.name_status == "published"
    assert inv.load_inventory(json.loads(inv.render_inventory(doc))).resources[0].name == name  # passes the leak scan


def test_name_rule_never_publishes_an_id_or_subscription_path():
    for name in (f"/subscriptions/{SUB}", f"x/providers/Microsoft.Network/y", SUB, VM):
        assert not inv.publishable_name(name), name


# --------------------------------------------------------------------------- failures and bounds


@pytest.mark.parametrize("code,status", [("authorization_failed", 403), ("throttled", 429), ("not_found", 404),
                                         ("service_error", 503), ("credential_unavailable", None)])
def test_listing_failure_is_a_failed_inventory_never_clean(case, code, status):
    doc = collect(case, FakeArm([inv.InventorySourceError(code, status)]))
    assert doc.outcome == "failed" and doc.failure == "listing_failed"
    assert doc.scopes[0].status == "failed" and doc.scopes[0].error == code and doc.scopes[0].http_status == status


def test_failure_on_a_later_page_keeps_what_was_seen_but_fails(case):
    doc = collect(case, FakeArm([(listing(NSG), "next"), inv.InventorySourceError("throttled", 429)]))
    assert doc.outcome == "failed" and doc.scopes[0].pages == 1 and doc.counts.unmanaged == 1


def test_paging_is_followed(case):
    nxt = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{RG_NAME}/resources?$skiptoken=x"
    source = FakeArm([(listing(NSG), nxt), listing(MANAGED_VNET)])
    doc = collect(case, source)
    assert doc.outcome == "complete" and doc.scopes[0].pages == 2 and source.urls[1] == nxt


def test_page_limit_is_incomplete(case):
    doc = collect(case, FakeArm([(listing(NSG), "n")] * 3), limits=inv.Limits(max_pages_per_scope=2))
    assert doc.outcome == "incomplete" and doc.scopes[0].error == "page_limit_exceeded"


def test_resource_limit_is_incomplete(case):
    doc = collect(case, FakeArm([listing(NSG, VM, PIP)]), limits=inv.Limits(max_resources_per_scope=2))
    assert doc.outcome == "incomplete" and doc.scopes[0].error == "resource_limit_exceeded"


def test_deadline_is_incomplete(case):
    ticks = iter([0.0, 1000.0])
    doc = collect(case, FakeArm([listing(NSG)]), clock=lambda: next(ticks, 1000.0),
                  limits=inv.Limits(deadline_seconds=10))
    assert doc.outcome == "incomplete" and doc.scopes[0].error == "deadline_exceeded"


def test_failed_detail_read_is_incomplete(case):
    details = portal_vm_details()
    details[VM] = inv.InventorySourceError("authorization_failed", 403)
    doc = collect(case, FakeArm([listing(VM, NSG)], details))
    vm = by_name(doc)["manual-vm"]
    assert doc.outcome == "incomplete" and vm.detail_status == "failed" and vm.detail_error == "authorization_failed"
    assert vm.pricing_inputs.model_dump(exclude_none=True) == {}


def test_detail_for_another_resource_is_rejected(case):
    doc = collect(case, FakeArm([listing(VM)], {VM: vm_details(rid=PIP)}))
    assert doc.outcome == "incomplete" and doc.resources[0].detail_error == "invalid_details"


def test_detail_read_limit_is_incomplete(case):
    doc = collect(case, portal_vm_source(), limits=inv.Limits(max_detail_reads=1))
    assert doc.outcome == "incomplete" and sum(r.detail_status == "failed" for r in doc.resources) == 3


@pytest.mark.parametrize("bad", [
    {"id": f"/subscriptions/{SUB}/resourceGroups/other-rg/providers/Microsoft.Network/networkSecurityGroups/x"},
    {"id": "not-an-id"}, {"id": RG}, "not-an-object"])
def test_listing_entry_outside_scope_or_invalid_fails(case, bad):
    doc = collect(case, FakeArm([[bad]]))
    assert doc.outcome == "failed" and doc.scopes[0].error == "invalid_response"


def test_invalid_property_values_are_left_out(case):
    details = {VM: vm_details(size="Standard B1s; drop", os_type="Plan9")}
    (item,) = collect(case, FakeArm([listing(VM)], details)).resources
    assert item.pricing_inputs.vm_size is None and item.pricing_inputs.os_type is None


# --------------------------------------------------------------------------- inputs and binding


def test_not_a_public_report_is_rejected(case):
    plan, report = case
    with pytest.raises(inv.InventoryInputError) as exc:
        inv.collect_inventory(plan, {**report, "public_version": None}, FakeArm([]))
    assert exc.value.code == "not_public_report"


def test_report_of_another_plan_is_rejected(case):
    plan, report = case
    with pytest.raises(inv.InventoryInputError) as exc:
        inv.collect_inventory({**plan, "timestamp": "2026-01-01T00:00:00Z"}, report, FakeArm([]))
    assert exc.value.code == "binding_mismatch"
    with pytest.raises(inv.InventoryInputError):
        inv.collect_inventory([], report, FakeArm([]))


def test_plan_without_a_managed_resource_group_is_a_failed_inventory(case):
    plan, report = case
    plan = json.loads(json.dumps(plan))
    plan["prior_state"]["values"]["root_module"] = {"resources": []}
    plan["resource_changes"], plan["planned_values"] = [], {}
    doc = inv.collect_inventory(plan, report, FakeArm([]), now=lambda: NOW)
    assert doc.outcome == "failed" and doc.failure == "no_managed_resource_group" and doc.scopes == []


def test_scope_is_the_managed_resource_groups(case):
    managed = inv.managed_index(case[0])
    assert [s.resource_group for s in managed.scopes] == [RG_NAME]
    assert managed.keys[MANAGED_VNET.lower()] == VNET_ADDRESS


# --------------------------------------------------------------------------- contract


def test_rendering_is_deterministic_and_round_trips(case):
    a, b = (inv.render_inventory(collect(case, portal_vm_source())) for _ in range(2))
    assert a == b
    assert inv.render_inventory(inv.load_inventory(json.loads(a))) == a


@pytest.mark.parametrize("mutate", [
    lambda d: d["counts"].update(unmanaged=5),
    lambda d: d["counts"].update(managed=0),
    lambda d: d.update(outcome="complete", failure=None) or d["scopes"][0].update(status="failed",
                                                                                  error="throttled"),
    lambda d: d["resources"][0].update(name=f"/subscriptions/{SUB}/x"),
    lambda d: d["resources"][0].update(name="someone@example.com"),
    lambda d: d["resources"][0].update(ref="res-9"),
    lambda d: d["resources"][1].update(parent={"kind": "inventory", "ref": "res-99", "address": None}),
    lambda d: d.update(unmanaged_by_type={}),
    lambda d: d["limitations"].pop(),
    lambda d: d["resources"][0].update(resource_group="other-rg"),
    lambda d: d["resources"][0]["pricing_inputs"].update(vm_size="x y"),
    lambda d: d["resources"][0].update(extra=1),
    lambda d: d.update(outcome="incomplete"),
    lambda d: d["scopes"][0].update(error="throttled"),  # complete scope with an error
    lambda d: d["scopes"][0].update(status="truncated", error="throttled"),  # not a limit code
    lambda d: d["scopes"][0].update(status="failed", error="page_limit_exceeded"),  # not a failure code
    lambda d: d["resources"][1].update(parent={"kind": "managed", "ref": "res-1", "address": None}),
    lambda d: d["resources"][0].update(name=None),  # published status without a name
    lambda d: d["resources"][0].update(detail_error="throttled"),  # error without a failed read
    lambda d: d["resources"][0].update(category="attached_to_managed"),  # no managed attachment
    lambda d: d.update(failure="listing_failed"),  # failure on a complete inventory
    lambda d: d.update(collected_at=None),
    lambda d: d["scopes"].append(dict(d["scopes"][0])),  # repeated scope
    lambda d: d["counts"].update(listed=8, managed=2),  # more than the scopes listed
])

def test_contract_rejects_inconsistent_documents(case, mutate):
    doc = json.loads(inv.render_inventory(collect(case, portal_vm_source())))
    mutate(doc)
    with pytest.raises(ValidationError):
        inv.load_inventory(doc)


def test_contract_rejects_an_input_failure_with_content(case):
    doc = json.loads(inv.render_inventory(collect(case, portal_vm_source())))
    doc.update(outcome="failed", failure="no_managed_resource_group")
    with pytest.raises(ValidationError):
        inv.load_inventory(doc)


def test_url_guard():
    base = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{RG_NAME}"
    assert inv.allowed_url(f"{base}/resources?api-version=2021-04-01")
    assert inv.allowed_url(f"https://management.azure.com{VM}?api-version=2024-07-01&$expand=instanceView")
    for bad in (f"http://management.azure.com{VM}", f"https://evil.example{VM}", f"https://management.azure.com:8443{VM}",
                f"https://user:pw@management.azure.com{VM}", f"https://management.azure.com{VM}#x",
                f"https://management.azure.com/subscriptions/{SUB}/resources", f"https://management.azure.com/{RG}",
                f"https://management.azure.com{RG}", "https://[::1", "not a url"):
        assert not inv.allowed_url(bad), bad


# --------------------------------------------------------------------------- Azure Resource Manager source


azure = pytest.importorskip("azure.core")
requests = pytest.importorskip("requests")
urllib3 = pytest.importorskip("urllib3")
from azure.core.credentials import AccessToken  # noqa: E402
from azure.core.pipeline.transport import RequestsTransport  # noqa: E402


class FakeAzure(requests.adapters.HTTPAdapter):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)
        self.requests = []

    def send(self, request, **kwargs):
        self.requests.append(request)
        item = self.responses.pop(0) if self.responses else (500, {"error": {}})
        if isinstance(item, BaseException):
            raise item
        status, body, *rest = item
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        raw = urllib3.HTTPResponse(body=io.BytesIO(data), status=status,
                                   headers={"Content-Type": "application/json", **(rest[0] if rest else {})},
                                   preload_content=False, decode_content=False)
        return self.build_response(request, raw)


class NoSleepTransport(RequestsTransport):
    def sleep(self, duration):
        pass


class FakeCredential:
    def __init__(self):
        self.calls = 0

    def get_token(self, *scopes, **kwargs):
        self.calls += 1
        return AccessToken("fake-token", int(time.time()) + 3600)


def arm_source(responses):
    fake = FakeAzure(responses)
    session = requests.Session()
    session.mount("https://", fake)
    credential = FakeCredential()
    source = inv.AzureResourceSource(credential, transport=NoSleepTransport(session=session, session_owner=False),
                                     settings=inv.RequestSettings(retry_total=1, retry_backoff_factor=0))
    return source, fake, credential


LIST_URL = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{RG_NAME}/resources?api-version=2021-04-01"


def test_arm_source_lists_pages_with_get_and_the_arm_audience():
    nxt = LIST_URL + "&$skiptoken=abc"
    source, fake, credential = arm_source([(200, {"value": listing(NSG), "nextLink": nxt}),
                                           (200, {"value": listing(VM)})])
    items, link = source.list_page(LIST_URL)
    assert [i["id"] for i in items] == [NSG] and link == nxt
    items, link = source.list_page(link)
    assert [i["id"] for i in items] == [VM] and link is None
    assert [r.method for r in fake.requests] == ["GET", "GET"]
    assert all(r.headers["Authorization"] == "Bearer fake-token" for r in fake.requests)


def test_arm_source_reads_a_resource():
    source, fake, _ = arm_source([(200, vm_details())])
    assert source.get(f"https://management.azure.com{VM}?api-version=2024-07-01")["id"] == VM


@pytest.mark.parametrize("status,code", [(400, "bad_request"), (401, "authentication_failed"),
                                         (403, "authorization_failed"), (404, "not_found"), (409, "http_error")])
def test_arm_source_maps_http_errors(status, code):
    source, _, _ = arm_source([(status, {"error": {"code": "X", "message": f"secret {SUB}"}})])
    with pytest.raises(inv.InventorySourceError) as exc:
        source.list_page(LIST_URL)
    assert (exc.value.code, exc.value.http_status) == (code, status) and SUB not in str(exc.value)


def test_arm_source_retries_throttling_then_reports_it():
    source, fake, _ = arm_source([(429, {}, {"Retry-After": "1"}), (429, {}, {"Retry-After": "1"})])
    with pytest.raises(inv.InventorySourceError) as exc:
        source.list_page(LIST_URL)
    assert exc.value.code == "throttled" and len(fake.requests) == 2


def test_arm_source_recovers_after_a_transient_error():
    source, fake, _ = arm_source([(503, {}), (200, {"value": []})])
    assert source.list_page(LIST_URL) == ([], None) and len(fake.requests) == 2


@pytest.mark.parametrize("body", [b"not json", {"value": "x"}, {"value": [], "nextLink": 5}, b'{"a":1,"a":2}'])
def test_arm_source_rejects_invalid_responses(body):
    source, _, _ = arm_source([(200, body)])
    with pytest.raises(inv.InventorySourceError) as exc:
        source.list_page(LIST_URL)
    assert exc.value.code == "invalid_response"


def test_arm_source_never_follows_a_next_link_elsewhere():
    source, fake, _ = arm_source([(200, {"value": [], "nextLink": "https://evil.example/resources"})])
    with pytest.raises(inv.InventorySourceError) as exc:
        source.list_page(LIST_URL)
    assert exc.value.code == "blocked_request" and len(fake.requests) == 1


def test_arm_source_blocks_other_urls_before_any_token():
    source, fake, credential = arm_source([])
    for url in ("https://evil.example/x", f"https://management.azure.com/subscriptions/{SUB}/providers/x"):
        with pytest.raises(inv.InventorySourceError) as exc:
            source.get(url)
        assert exc.value.code == "blocked_request"
    assert fake.requests == [] and credential.calls == 0


def test_arm_source_maps_connection_errors():
    source, _, _ = arm_source([requests.exceptions.ConnectionError("down"), requests.exceptions.ConnectionError("x")])
    with pytest.raises(inv.InventorySourceError) as exc:
        source.list_page(LIST_URL)
    assert exc.value.code == "connection_failed"


def test_end_to_end_through_the_real_pipeline(case):
    responses = [(200, {"value": listing(VM, NSG, MANAGED_VNET)}), (200, vm_details())]
    source, fake, _ = arm_source(responses)
    doc = collect(case, source)
    assert doc.outcome == "complete" and doc.counts.unmanaged == 2 and doc.counts.managed == 1
    assert len(fake.requests) == 2


# --------------------------------------------------------------------------- CLI


def write(path, data):
    path.write_text(json.dumps(data))
    return str(path)


def test_cli_inventory_writes_the_public_document(case, tmp_path, monkeypatch, capsys):
    plan, report = case
    monkeypatch.setattr(cli, "_inventory_source", portal_vm_source)
    out = tmp_path / "unmanaged_inventory.json"
    rc = cli.main(["inventory", "--plan", write(tmp_path / "p.json", plan), "--report",
                   write(tmp_path / "r.json", report), "--output", str(out)])
    assert rc == 0
    doc = inv.load_inventory(json.loads(out.read_text()))
    assert doc.counts.unmanaged == 6
    assert "unmanaged_inventory_outcome=complete" in capsys.readouterr().out


def test_cli_inventory_incomplete_is_exit_1_and_still_written(case, tmp_path, monkeypatch, capsys):
    plan, report = case
    monkeypatch.setattr(cli, "_inventory_source", lambda: FakeArm([inv.InventorySourceError("throttled", 429)]))
    out = tmp_path / "inv.json"
    rc = cli.main(["inventory", "--plan", write(tmp_path / "p.json", plan), "--report",
                   write(tmp_path / "r.json", report), "--output", str(out)])
    assert rc == 1 and json.loads(out.read_text())["outcome"] == "failed"
    err = capsys.readouterr().err
    assert "UNMANAGED INVENTORY FAILED [listing_failed]" in err and SUB not in err


def test_cli_inventory_unusable_input_writes_nothing(case, tmp_path, capsys):
    plan, report = case
    out = tmp_path / "inv.json"
    (tmp_path / "bad.json").write_text("{")
    assert cli.main(["inventory", "--plan", str(tmp_path / "bad.json"), "--report",
                     write(tmp_path / "r.json", report), "--output", str(out)]) == 2
    assert cli.main(["inventory", "--plan", write(tmp_path / "p.json", plan), "--report",
                     write(tmp_path / "r.json", {"x": 1}), "--output", str(out)]) == 2
    assert not out.exists()
    assert "[not_public_report]" in capsys.readouterr().err


def test_cli_inventory_reads_the_plan_with_the_plan_parser_limit(case, tmp_path, monkeypatch):
    """Review fix: --plan uses the plan parser's 50 MiB limit (as analyze/investigate); the unmanaged documents
    keep their 10 MiB limit."""
    from drift_engine import parser, unmanaged_cost

    plan, report = case
    seen = []
    real = cli._read_input

    def spy(path, limit):
        seen.append((Path(path).name, limit))
        return real(path, limit)
    monkeypatch.setattr(cli, "_read_input", spy)
    monkeypatch.setattr(cli, "_inventory_source", portal_vm_source)
    assert cli.main(["inventory", "--plan", write(tmp_path / "p.json", plan), "--report",
                     write(tmp_path / "r.json", report), "--output", str(tmp_path / "o.json")]) == 0
    assert seen == [("p.json", parser.MAX_PLAN_BYTES), ("r.json", unmanaged_cost.MAX_INPUT_BYTES)]
    assert parser.MAX_PLAN_BYTES == 50 * 1024 * 1024 and unmanaged_cost.MAX_INPUT_BYTES == 10 * 1024 * 1024


def test_cli_inventory_accepts_a_plan_larger_than_10_mib(case, tmp_path, monkeypatch):
    plan, report = case
    big = dict(plan, padding="x" * (11 * 1024 * 1024))  # an unread key: only the size matters here
    monkeypatch.setattr(cli, "_inventory_source", portal_vm_source)
    path = write(tmp_path / "p.json", big)
    assert Path(path).stat().st_size > 10 * 1024 * 1024
    assert cli.main(["inventory", "--plan", path, "--report", write(tmp_path / "r.json", report), "--output",
                     str(tmp_path / "o.json")]) == 0


def test_cli_inventory_rejects_a_plan_over_the_parser_limit(case, tmp_path, monkeypatch, capsys):
    from drift_engine import parser

    plan, report = case
    monkeypatch.setattr(cli, "MAX_PLAN_BYTES", 1024)  # the same rule as 50 MiB, without writing 50 MiB
    monkeypatch.setattr(cli, "_inventory_source", lambda: pytest.fail("must not reach Azure"))
    assert parser.MAX_PLAN_BYTES == 50 * 1024 * 1024
    assert cli.main(["inventory", "--plan", write(tmp_path / "p.json", plan), "--report",
                     write(tmp_path / "r.json", report), "--output", str(tmp_path / "o.json")]) == 2
    assert not (tmp_path / "o.json").exists() and "cannot read --plan or --report" in capsys.readouterr().err


def test_cli_inventory_internal_error_shows_the_type_only(case, tmp_path, monkeypatch, capsys):
    plan, report = case

    def boom():
        raise RuntimeError(f"secret {SUB}")
    monkeypatch.setattr(cli, "_inventory_source", boom)
    rc = cli.main(["inventory", "--plan", write(tmp_path / "p.json", plan), "--report",
                   write(tmp_path / "r.json", report), "--output", str(tmp_path / "o.json")])
    err = capsys.readouterr().err
    assert rc == 70 and "RuntimeError" in err and SUB not in err
