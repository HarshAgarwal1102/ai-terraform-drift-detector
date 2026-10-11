"""Task 10.4: monthly list-price estimate of unmanaged resources (src/drift_engine/unmanaged_cost.py).

Prices are the real Azure Retail Prices API samples in tests/fixtures/retail_prices/ (Central India,
2026-10-11); the inventory is produced by drift_engine.inventory from scripted ARM responses. Every
expected amount below is unit price x quantity from those samples. No network (conftest.py guard).
"""

from __future__ import annotations

import email.message
import io
import json
import urllib.error
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from drift_engine import cli
from drift_engine import inventory as inv
from drift_engine import unmanaged_cost as uc
from drift_engine.investigation_public import canonical_sha256
from unmanaged_fixtures import (
    MANAGED_VM, MANAGED_VM_ADDRESS, MANAGED_VNET, NSG, VNET_ADDRESS, OS_DISK, PIP, RG, SUB, VM, FakeArm, FakePrices, disk_details, listing,
    pip_details, plan_and_report, portal_vm_details, portal_vm_source, price_items, vm_details, with_managed,
)

NOW = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 10, 11, 12, 5, 0, tzinfo=timezone.utc)


@pytest.fixture()
def case(tmp_path):
    plan, report = plan_and_report(tmp_path)
    return with_managed(plan, (VNET_ADDRESS, "azurerm_virtual_network", MANAGED_VNET)), report


def inventory_of(case, source, plan=None):
    doc = inv.collect_inventory(plan or case[0], case[1], source, now=lambda: NOW)
    raw = json.loads(inv.render_inventory(doc))
    return inv.load_inventory(raw), raw


def price(case, source, prices=None, plan=None):
    doc, raw = inventory_of(case, source, plan)
    return uc.estimate_costs(doc, raw, prices or FakePrices(), now=lambda: LATER), raw


def by_name(cost):
    return {r.name: r for r in cost.resources}


def single(case, rid, details, prices=None):
    cost, _ = price(case, FakeArm([listing(rid)], {rid: details}), prices)
    (entry,) = cost.resources
    return cost, entry


# --------------------------------------------------------------------------- the portal VM (real samples)


def test_portal_vm_is_priced_exactly_from_the_real_samples(case):
    cost, raw = price(case, portal_vm_source())
    r = by_name(cost)
    assert cost.status == "complete" and cost.failure is None
    assert (r["manual-vm"].monthly_cost, r["manual-vm"].display) == ("8.1760", "$8.18/month")  # 0.0112 x 730
    assert (r["manual-vm-osdisk"].monthly_cost, r["manual-vm-osdisk"].display) == ("5.2795", "$5.28/month")
    assert (r["manual-vm-ip"].monthly_cost, r["manual-vm-ip"].display) == ("3.650", "$3.65/month")  # 0.005 x 730
    for free in ("manual-vm-nic", "manual-vm-nsg", "manual-vm/AzureMonitorLinuxAgent"):
        assert (r[free].estimate_status, r[free].monthly_cost, r[free].components) == ("no_direct_charge", "0", [])
    t = cost.totals
    assert (t.estimated_monthly_cost, t.display, t.complete) == ("17.1055", "$17.11/month", True)
    assert (t.resources, t.estimated, t.partial, t.no_direct_charge, t.unavailable) == (6, 3, 0, 3, 0)
    assert cost.binding.inventory_sha256 == canonical_sha256(raw)
    assert cost.binding.drift_report_sha256 == canonical_sha256(case[1])
    assert cost.source.queried_at == "2026-10-11T12:05:00.000000Z"


def test_matched_meters_are_the_right_ones(case):
    cost, _ = price(case, portal_vm_source())
    r = by_name(cost)
    vm = r["manual-vm"].components[0]
    assert (vm.product_name, vm.meter_name, vm.unit_of_measure, vm.unit_price, vm.quantity) == (
        "Virtual Machines BS Series", "B1s", "1 Hour", "0.0112", "730")  # Linux, not the Windows product
    disk = r["manual-vm-osdisk"].components[0]
    assert (disk.product_name, disk.meter_name, disk.quantity) == ("Premium SSD Managed Disks", "P4 LRS Disk", "1")
    ip = r["manual-vm-ip"].components[0]
    assert (ip.product_name, ip.meter_name) == ("IP Addresses", "Standard IPv4 Static Public IP")
    assert r["manual-vm"].assumptions == ["compute_only_disks_and_ips_priced_separately", "pay_as_you_go_list_price",
                                          "runs_730_hours_per_month"]
    assert r["manual-vm-osdisk"].assumptions == ["disk_billed_at_tier_size", "pay_as_you_go_list_price"]


def test_amounts_are_exact_decimals_never_floats(case):
    text = uc.render_cost(price(case, portal_vm_source())[0])
    doc = json.loads(text, parse_float=lambda v: pytest.fail(f"float in document: {v}"))
    assert all(isinstance(r["monthly_cost"], str) for r in doc["resources"])


def test_no_double_counting(case):
    cost, _ = price(case, portal_vm_source())
    refs = [r.ref for r in cost.resources]
    assert len(refs) == len(set(refs)) == 6
    meters = [(r.ref, c.product_name) for r in cost.resources for c in r.components]
    assert len(meters) == 3  # VM compute, disk, IP: the VM never includes its disk or IP
    assert Decimal(cost.totals.estimated_monthly_cost) == sum(Decimal(r.monthly_cost) for r in cost.resources)


def test_attached_to_managed_disk_is_never_priced(case):
    plan = with_managed(case[0], (MANAGED_VM_ADDRESS, "azurerm_linux_virtual_machine", MANAGED_VM))
    disk = f"{RG}/providers/Microsoft.Compute/disks/tf-vm-osdisk"
    prices = FakePrices()
    cost, _ = price(case, FakeArm([listing(MANAGED_VM, disk)], {disk: disk_details(disk, managed_by=MANAGED_VM)}),
                    prices, plan)
    assert cost.resources == [] and prices.filters == [] and cost.status == "complete"
    assert (cost.totals.estimated_monthly_cost, cost.totals.display) == ("0", "$0.00/month")


def test_same_sku_is_queried_once(case):
    vm2 = VM + "2"
    prices = FakePrices()
    cost, _ = price(case, FakeArm([listing(VM, vm2)], {VM: vm_details(), vm2: vm_details(vm2)}), prices)
    assert len(prices.filters) == 1 and [r.monthly_cost for r in cost.resources] == ["8.1760", "8.1760"]
    assert cost.totals.estimated_monthly_cost == "16.3520"


def test_nothing_unmanaged_is_a_complete_zero(case):
    cost, _ = price(case, FakeArm([[]]))
    assert cost.status == "complete" and cost.totals.estimated_monthly_cost == "0" and cost.resources == []


# --------------------------------------------------------------------------- VM rules


def test_windows_vm_uses_the_windows_meter_and_excludes_spot(case):
    _, entry = single(case, VM, vm_details(size="Standard_D2s_v5", os_type="Windows"))
    c = entry.components[0]
    assert (c.product_name, c.meter_name, entry.monthly_cost) == ("Virtual Machines Dsv5 Series Windows", "D2s v5",
                                                                  "140.890")
    assert "windows_license_included" in entry.assumptions


def test_windows_with_azure_hybrid_benefit_uses_the_linux_rate(case):
    _, entry = single(case, VM, vm_details(size="Standard_D2s_v5", os_type="Windows", licenseType="Windows_Server"))
    assert entry.components[0].product_name == "Virtual Machines Dsv5 Series" and entry.monthly_cost == "73.730"
    assert "linux_rate_azure_hybrid_benefit" in entry.assumptions


def test_linux_d2s_v5_never_picks_spot_or_low_priority(case):
    _, entry = single(case, VM, vm_details(size="Standard_D2s_v5"))
    assert (entry.components[0].meter_name, entry.monthly_cost) == ("D2s v5", "73.730")


@pytest.mark.parametrize("priority", ["Spot", "Low"])
def test_spot_and_low_priority_vms_are_unavailable(case, priority):
    cost, entry = single(case, VM, vm_details(priority=priority))
    assert (entry.estimate_status, entry.reason, entry.monthly_cost) == ("unavailable", "spot_or_low_priority", None)
    assert cost.status == "partial" and cost.totals.estimated_monthly_cost is None and not cost.totals.complete


@pytest.mark.parametrize("details", [{"publisher": "RedHat"}, {"publisher": "SUSE"},
                                     {"publisher": "MicrosoftSQLServer"}])
def test_paid_images_are_partial(case, details):
    cost, entry = single(case, VM, vm_details(**details))
    assert (entry.estimate_status, entry.reason, entry.monthly_cost) == (
        "partial", "image_software_license_not_priced", "8.1760")
    assert "image_software_license" in entry.exclusions
    assert cost.status == "partial" and cost.totals.partial == 1 and not cost.totals.complete
    assert cost.totals.estimated_monthly_cost == "8.1760"  # a lower bound: listed as partial, never complete


def test_marketplace_plan_is_partial(case):
    details = vm_details()
    details["plan"] = {"name": "x", "publisher": "y", "product": "z"}
    _, entry = single(case, VM, details)
    assert entry.estimate_status == "partial"


def test_deallocated_vm_is_priced_as_running_and_says_so(case):
    _, entry = single(case, VM, vm_details(power="deallocated"))
    assert entry.monthly_cost == "8.1760" and "observed_deallocated_priced_as_running" in entry.assumptions


def test_vm_without_a_size_is_missing_input(case):
    details = vm_details()
    del details["properties"]["hardwareProfile"]
    _, entry = single(case, VM, details)
    assert (entry.estimate_status, entry.reason) == ("unavailable", "missing_pricing_input")


# --------------------------------------------------------------------------- disk rules


@pytest.mark.parametrize("letter,size,tier", [("S", 1, "S4"), ("S", 32, "S4"), ("S", 33, "S6"), ("P", 4, "P1"),
                                              ("P", 30, "P4"), ("E", 129, "E15"), ("P", 1024, "P30"),
                                              ("P", 32767, "P80"), ("P", 32768, None)])
def test_disk_tier_is_the_smallest_tier_at_least_as_large(letter, size, tier):
    assert uc.disk_tier(letter, size) == tier


@pytest.mark.parametrize("sku,size,tier,amount,product", [
    ("Standard_LRS", 30, None, "1.6896", "Standard HDD Managed Disks"),
    ("StandardSSD_LRS", 32, None, "2.64", "Standard SSD Managed Disks"),
    ("Premium_LRS", 32, "P4", "5.2795", "Premium SSD Managed Disks")])
def test_disk_skus(case, sku, size, tier, amount, product):
    _, entry = single(case, OS_DISK, disk_details(sku=sku, size=size, tier=tier, managed_by=None))
    assert (entry.monthly_cost, entry.components[0].product_name) == (amount, product)
    assert ("disk_transactions" in entry.exclusions) == (sku != "Premium_LRS")


@pytest.mark.parametrize("details,reason", [
    (dict(sku="UltraSSD_LRS"), "unsupported_sku"), (dict(sku="PremiumV2_LRS"), "unsupported_sku"),
    (dict(size=40000, tier=None), "unsupported_disk_size"), (dict(tier="P30"), "performance_tier_differs"),
    (dict(maxShares=2), "shared_disk")])
def test_disk_cases_without_an_estimate(case, details, reason):
    _, entry = single(case, OS_DISK, disk_details(managed_by=None, **details))
    assert (entry.estimate_status, entry.reason, entry.monthly_cost) == ("unavailable", reason, None)


# --------------------------------------------------------------------------- public IP and other types


@pytest.mark.parametrize("details,reason", [(dict(sku="Basic"), "unsupported_sku"),
                                            (dict(version="IPv6"), "unsupported_ip_configuration"),
                                            (dict(tier="Global"), "unsupported_ip_configuration")])
def test_public_ip_cases_without_an_estimate(case, details, reason):
    _, entry = single(case, PIP, pip_details(nic=None, **details))
    assert (entry.estimate_status, entry.reason) == ("unavailable", reason)


def test_unsupported_type_is_unavailable_never_zero(case):
    rid = f"{RG}/providers/Microsoft.Storage/storageAccounts/manualsa"
    cost, _ = price(case, FakeArm([listing(rid, NSG)]))
    r = by_name(cost)
    assert (r["manualsa"].estimate_status, r["manualsa"].reason, r["manualsa"].monthly_cost) == (
        "unavailable", "unsupported_resource_type", None)
    assert cost.status == "partial" and cost.totals.estimated_monthly_cost == "0" and cost.totals.unavailable == 1
    assert not cost.totals.complete  # the 0 is the known part only, never "complete"


def test_unknown_location_is_unavailable(case):
    entries = listing(VM)
    entries[0]["location"] = None
    cost, _ = price(case, FakeArm([entries], {VM: vm_details()}))
    assert cost.resources[0].reason == "location_unknown"


# --------------------------------------------------------------------------- missing and ambiguous prices


def test_price_not_found(case):
    _, entry = single(case, VM, vm_details(), FakePrices(override={"Standard_B1s": []}))
    assert (entry.estimate_status, entry.reason, entry.monthly_cost) == ("unavailable", "price_not_found", None)


def test_ambiguous_price(case):
    items = price_items("vm_standard_b1s")
    other = dict(items[0], retailPrice=Decimal("0.02"), productName="Virtual Machines BS Series")
    _, entry = single(case, VM, vm_details(), FakePrices(override={"Standard_B1s": items + [other]}))
    assert entry.reason == "ambiguous_price"


def test_an_identical_repeated_meter_is_one_meter(case):
    items = price_items("vm_standard_b1s")
    _, entry = single(case, VM, vm_details(), FakePrices(override={"Standard_B1s": items + items}))
    assert entry.monthly_cost == "8.1760"


@pytest.mark.parametrize("change", [dict(retailPrice=0.0112), dict(retailPrice="0.0112"), dict(currencyCode="INR"),
                                    dict(type="Reservation"), dict(tierMinimumUnits=Decimal("1")),
                                    dict(retailPrice=Decimal("-1")), dict(productName=None), dict(retailPrice=True)])
def test_invalid_price_items_are_never_used(case, change):
    items = [dict(i, **change) for i in price_items("vm_standard_b1s")]
    _, entry = single(case, VM, vm_details(), FakePrices(override={"Standard_B1s": items}))
    assert entry.reason == "price_not_found"


# --------------------------------------------------------------------------- failures


@pytest.mark.parametrize("code", uc.API_FAILURES)
def test_api_failure_is_an_explicit_failed_status(case, code):
    cost, _ = price(case, portal_vm_source(), FakePrices(fail=code))
    assert cost.status == "failed" and cost.failure == code
    r = by_name(cost)
    assert r["manual-vm"].reason == "pricing_api_failed" and r["manual-vm"].monthly_cost is None
    assert r["manual-vm-nic"].monthly_cost == "0"  # known no-charge types stay known
    assert cost.totals.estimated_monthly_cost == "0" and not cost.totals.complete


@pytest.mark.parametrize("failure", [inv.InventorySourceError("throttled", 429), None])
def test_incomplete_inventory_is_not_priced(case, failure):
    source = FakeArm([failure]) if failure else FakeArm([listing(VM)], {VM: inv.InventorySourceError("timeout")})
    prices = FakePrices()
    cost, _ = price(case, source, prices)
    assert cost.status == "not_run" and cost.failure == "inventory_not_complete" and cost.resources == []
    assert cost.totals.estimated_monthly_cost is None and prices.filters == [] and cost.source.queried_at is None


# --------------------------------------------------------------------------- contract and binding


@pytest.mark.parametrize("mutate", [
    lambda d: d["resources"][0].update(monthly_cost="1"),
    lambda d: d["resources"][0]["components"][0].update(monthly_cost="9"),
    lambda d: d["resources"][0]["components"][0].update(quantity="730"),  # res-1 is the disk: a monthly meter
    lambda d: d["resources"][0].update(display="$1.00/month"),
    lambda d: d["totals"].update(estimated_monthly_cost="1"),
    lambda d: d["totals"].update(complete=False),
    lambda d: d["totals"].update(label="cost"),
    lambda d: d["totals"].update(unavailable=1),
    lambda d: d.update(status="partial"),
    lambda d: d.update(failure="throttled"),
    lambda d: d["limitations"].pop(),
    lambda d: d["resources"][3].update(monthly_cost="1", display="$1.00/month"),  # no_direct_charge is exactly 0
    lambda d: d["resources"][0].update(reason="price_not_found"),
    lambda d: d["resources"][0].update(estimate_status="unavailable", reason="price_not_found"),
    lambda d: d["resources"][0].update(name=f"/subscriptions/{SUB}"),
    lambda d: d["resources"][0].update(assumptions=["runs_730_hours_per_month", "pay_as_you_go_list_price"]),
    lambda d: d["resources"].reverse(),
    lambda d: d["source"].update(endpoint="https://prices.azure.com/api/retail/prices"),
    lambda d: d.update(extra=1),
])
def test_contract_rejects_tampering(case, mutate):
    doc = json.loads(uc.render_cost(price(case, portal_vm_source())[0]))
    mutate(doc)
    with pytest.raises(ValidationError):
        uc.load_cost(doc)


def test_check_documents_accepts_a_bound_pair_and_rejects_others(case, tmp_path):
    cost, raw = price(case, portal_vm_source())
    cost_raw = json.loads(uc.render_cost(cost))
    uc.check_documents(raw, cost_raw, case[1])
    other_report = dict(case[1], has_drift=True)
    for args, code in [((raw, cost_raw, other_report), "binding_mismatch"),
                       ((dict(raw, counts={}), cost_raw, case[1]), "contract"),
                       ((raw, dict(cost_raw, resources=cost_raw["resources"][:-1]), case[1]), "contract"),
                       ((raw, {**cost_raw, "binding": {**cost_raw["binding"], "inventory_sha256": "0" * 64}},
                         case[1]), "binding_mismatch"),
                       ((dict(raw, note=f"/subscriptions/{SUB}"), cost_raw, case[1]), "leak")]:
        with pytest.raises(uc.UnmanagedInputError) as exc:
            uc.check_documents(*args)
        assert exc.value.code == code


@pytest.mark.parametrize("prices,row", [
    (FakePrices(override={"Standard_B1s": []}),
     "| Estimated monthly cost | At least $8.93/month — incomplete estimate (2 estimated, 0 partial, 3 no direct "
     "charge, 1 unavailable) |"),
    (FakePrices(fail="throttled"),
     "| Estimated monthly cost | At least $0.00/month — incomplete estimate (0 estimated, 0 partial, 3 no direct "
     "charge, 3 unavailable) |"),
    (FakePrices(),
     "| Estimated monthly cost | $17.11/month (3 estimated, 0 partial, 3 no direct charge, 0 unavailable) |"),
])
def test_summary_total_is_a_lower_bound_when_incomplete(case, prices, row):
    """Final-review fix: the public step summary never presents an incomplete total as the complete cost; the
    per-resource rows keep their own statuses."""
    cost, raw = price(case, portal_vm_source(), prices)
    text = uc.summary_markdown(inv.load_inventory(raw), cost)
    assert row in text.splitlines()
    if not cost.totals.complete:
        assert "| unavailable | `unavailable`" in text  # the per-resource status is still shown


def test_summary_total_with_a_partial_estimate_is_a_lower_bound(case):
    cost, raw = price(case, FakeArm([listing(VM)], {VM: vm_details(publisher="RedHat")}))
    assert cost.status == "partial" and cost.totals.partial == 1
    assert "| Estimated monthly cost | At least $8.18/month — incomplete estimate (0 estimated, 1 partial" in \
        uc.summary_markdown(inv.load_inventory(raw), cost)


def test_total_text():
    assert uc.total_text({"display": "$17.11/month", "complete": True}) == "$17.11/month"
    assert uc.total_text({"display": "$0.00/month", "complete": False}) == "At least $0.00/month — incomplete estimate"
    assert uc.total_text({"display": None, "complete": False}) == "not determinable"


def test_cli_cost_line_marks_an_incomplete_total(case, tmp_path, monkeypatch, capsys):
    _, raw = inventory_of(case, portal_vm_source())
    (tmp_path / "i.json").write_text(json.dumps(raw))
    (tmp_path / "r.json").write_text(json.dumps(case[1]))
    monkeypatch.setattr(cli, "_price_source", lambda: FakePrices(override={"Standard_B1s": []}))
    assert cli.main(["unmanaged-cost", "--inventory", str(tmp_path / "i.json"), "--report", str(tmp_path / "r.json"),
                     "--output", str(tmp_path / "c.json")]) == 0
    assert "total=8.9295 (at least: incomplete estimate)" in capsys.readouterr().out


def test_summary_markdown(case):
    cost, raw = price(case, portal_vm_source())
    text = uc.summary_markdown(inv.load_inventory(raw), cost)
    assert "| Estimated monthly cost | $17.11/month (3 estimated, 0 partial, 3 no direct charge, 0 unavailable) |" in text
    assert "`manual-vm`" in text and "`Microsoft.Compute/virtualMachines`" in text and "Not drift" in text
    assert "separate from the Infracost Terraform plan estimate" in text
    assert SUB not in text and "/subscriptions/" not in text


# --------------------------------------------------------------------------- Retail Prices API client


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request.get_method(), request.full_url, timeout))
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return FakeResponse(item if isinstance(item, bytes) else json.dumps(item).encode())


def http_error(code, retry_after=None):
    headers = email.message.Message()
    if retry_after:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://prices.azure.com/api/retail/prices", code, "x", headers, None)


def api(responses, **settings):
    sleeps = []
    opener = FakeOpener(responses)
    return uc.RetailPricesApi(opener=opener, sleep=sleeps.append, settings=uc.PriceSettings(**settings)), opener, sleeps


NEXT = "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&$skip=100"


def test_api_follows_pages_and_parses_prices_as_decimal():
    body = b'{"Items": [{"retailPrice": 0.0112}], "NextPageLink": "' + NEXT.encode() + b'"}'
    source, opener, _ = api([body, {"Items": [{"retailPrice": 1}], "NextPageLink": None}])
    items = source.items("serviceName eq 'Virtual Machines'")
    assert items == [{"retailPrice": Decimal("0.0112")}, {"retailPrice": 1}]
    method, url, timeout = opener.requests[0]
    assert method == "GET" and url.startswith("https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&")
    assert "%24filter=serviceName+eq+%27Virtual+Machines%27" in url and opener.requests[1][1] == NEXT


def test_api_retries_throttling_and_honours_retry_after():
    source, opener, sleeps = api([http_error(429, "7"), {"Items": []}])
    assert source.items("x") == [] and len(opener.requests) == 2 and 7.0 in sleeps


@pytest.mark.parametrize("responses,code", [
    ([http_error(500)] * 4, "service_error"), ([http_error(429)] * 4, "throttled"), ([http_error(404)], "http_error"),
    ([urllib.error.URLError("down")] * 4, "connection_failed"), ([TimeoutError()] * 4, "timeout"),
    ([b"not json"], "invalid_response"), ([{"Items": "x"}], "invalid_response"), ([b'{"Items": [], "x": NaN}'],
                                                                                    "invalid_response"),
    ([{"Items": [], "NextPageLink": "https://evil.example/api/retail/prices"}], "blocked_request"),
    ([{"Items": [], "NextPageLink": NEXT}] * 2, "page_limit_exceeded")])
def test_api_failures(responses, code):
    source, _, _ = api(responses, max_pages=2)
    with pytest.raises(uc.PricingSourceError) as exc:
        source.items("x")
    assert exc.value.code == code


def test_api_rejects_oversized_responses():
    source, _, _ = api([b'{"Items": []}' + b" " * 100], max_bytes=50)
    with pytest.raises(uc.PricingSourceError) as exc:
        source.items("x")
    assert exc.value.code == "invalid_response"


def test_api_never_follows_redirects():
    with pytest.raises(uc.PricingSourceError) as exc:
        uc._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.example/")
    assert exc.value.code == "blocked_request"


def test_price_url_guard():
    assert uc.allowed_price_url(uc.query_url("x"))
    for bad in ("http://prices.azure.com/api/retail/prices", "https://prices.azure.com/other",
                "https://prices.azure.com:8443/api/retail/prices", "https://a@prices.azure.com/api/retail/prices",
                "https://prices.azure.com.evil/api/retail/prices", "https://[::1"):
        assert not uc.allowed_price_url(bad), bad


def test_filters_carry_only_service_sku_and_region(case):
    prices = FakePrices()
    price(case, portal_vm_source(), prices)
    joined = " ".join(prices.filters)
    for name in ("manual-vm", "osdisk", SUB, "aitdd-dev-main-rg"):
        assert name not in joined
    assert len(prices.filters) == 3


# --------------------------------------------------------------------------- CLI


def test_cli_cost_and_check_end_to_end(case, tmp_path, monkeypatch, capsys):
    plan, report = case
    monkeypatch.setattr(cli, "_inventory_source", portal_vm_source)
    monkeypatch.setattr(cli, "_price_source", FakePrices)
    (tmp_path / "p.json").write_text(json.dumps(plan))
    (tmp_path / "r.json").write_text(json.dumps(report))
    inv_file, cost_file, summary = tmp_path / "unmanaged_inventory.json", tmp_path / "unmanaged_cost.json", tmp_path / "s.md"
    assert cli.main(["inventory", "--plan", str(tmp_path / "p.json"), "--report", str(tmp_path / "r.json"),
                     "--output", str(inv_file)]) == 0
    assert cli.main(["unmanaged-cost", "--inventory", str(inv_file), "--report", str(tmp_path / "r.json"),
                     "--output", str(cost_file)]) == 0
    assert "unmanaged_cost_status=complete" in capsys.readouterr().out
    assert cli.main(["unmanaged-check", "--inventory", str(inv_file), "--cost", str(cost_file), "--report",
                     str(tmp_path / "r.json"), "--summary-markdown", str(summary)]) == 0
    assert "$17.11/month" in summary.read_text()


def test_cli_cost_failure_is_exit_1_and_written(case, tmp_path, monkeypatch, capsys):
    cost_raw = None
    doc, raw = inventory_of(case, portal_vm_source())
    (tmp_path / "i.json").write_text(json.dumps(raw))
    (tmp_path / "r.json").write_text(json.dumps(case[1]))
    monkeypatch.setattr(cli, "_price_source", lambda: FakePrices(fail="throttled"))
    out = tmp_path / "c.json"
    rc = cli.main(["unmanaged-cost", "--inventory", str(tmp_path / "i.json"), "--report", str(tmp_path / "r.json"),
                   "--output", str(out)])
    cost_raw = json.loads(out.read_text())
    assert rc == 1 and cost_raw["status"] == "failed"
    assert "UNMANAGED COST FAILED [throttled]: estimates are unavailable, never $0." in capsys.readouterr().err


def test_cli_cost_rejects_an_unbound_or_invalid_inventory(case, tmp_path, monkeypatch, capsys):
    _, raw = inventory_of(case, portal_vm_source())
    (tmp_path / "r.json").write_text(json.dumps(dict(case[1], has_drift=True)))
    monkeypatch.setattr(cli, "_price_source", lambda: pytest.fail("must not price"))
    for name, data in (("i.json", raw), ("bad.json", dict(raw, counts={})), ("leak.json", dict(raw, x="a@b.c"))):
        (tmp_path / name).write_text(json.dumps(data))
        assert cli.main(["unmanaged-cost", "--inventory", str(tmp_path / name), "--report", str(tmp_path / "r.json"),
                         "--output", str(tmp_path / "c.json")]) == 2
    err = capsys.readouterr().err
    assert "[binding_mismatch]" in err and "[contract]" in err and "[leak]" in err
    assert not (tmp_path / "c.json").exists()


def test_cli_check_rejects_with_a_code(case, tmp_path, capsys):
    (tmp_path / "x.json").write_text("{")
    assert cli.main(["unmanaged-check", "--inventory", str(tmp_path / "x.json"), "--cost", str(tmp_path / "x.json"),
                     "--report", str(tmp_path / "x.json")]) == 1
    assert "UNMANAGED DOCUMENTS REJECTED [unreadable]" in capsys.readouterr().err
