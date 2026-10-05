"""Public drift report: the deterministic projection of the internal report (Task 9B.4A).

The engine's `drift_report.json` (drift_engine.models.DriftReport, schemas/drift_report.schema.json)
is the internal deterministic document. It is unchanged, and in CI it stays on the runner:
Terraform values that are not flagged sensitive can hold ARM resource IDs (with the
subscription ID), GUIDs or email-like identities. Everything that leaves the runner uses this
module's public projection instead (PROJECT_PLAN.md, Phase 9B, P1-P4 and G11):

- Same fields, structure, order, classification, severity, counts, addresses, run and plan
  blocks and notes as the internal report, plus `public_version: "1"` and one extra view
  status, `withheld`.
- A view value holding a withheld class (an ARM/resource ID or subscription/provider path, a
  GUID, a UPN/email-like identity) becomes `{"status": "withheld", "kinds": [...],
  "resource": <address> | null, "ref": "id-<n>" | null}`:
    - a scalar ARM ID equal to the ID of exactly one managed resource of the same plan names
      that resource's Terraform address;
    - any other withheld scalar gets a per-report ordinal `id-<n>` (order of first
      occurrence; the same raw value gets the same ref, so S/R/D inequality stays visible);
    - a list/map value with any withheld-class leaf or key is withheld as a whole (no
      `resource` / `ref`).
  Configured IP addresses, CIDRs and URLs are Terraform evidence and stay (P2). `withheld` is
  distinct from Terraform's `redacted`, which is unchanged.
- A withheld-class map key in a change path becomes `withheld-key-<n>` everywhere that path is
  spelled (`path`, `attribute`, `attributes[].name`, and the resource severity reason naming
  that path, matched exactly), and that change's views are all withheld.
- Any other field holding a withheld class (address, module address, index, previous
  address, resource types, outputs, run, plan, notes, ...) is never rewritten: the projection
  fails with `identifier_in_structure` (P3, fail closed).

`publish_report` = project -> strict public model -> `verify_public_report` (an independent
field-by-field re-derivation) -> `identifier_findings` (a fail-closed scan of every string and
key), all before anything is rendered. `public_sha256` is the canonical SHA-256 (sorted keys,
compact separators, UTF-8) of the public document: the only drift report hash any public
artifact may carry. Errors carry fixed codes only, never a value.

This module imports nothing from activity_logs, attribution, investigation or who.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Annotated, Any, Literal, Union

from pydantic import Field, ValidationError, model_validator

from drift_engine.investigation_public import canonical_sha256
from drift_engine.models import (
    AttributeChange,
    DriftItem,
    DriftReport,
    StatusView,
    ValueView,
    _Model,
)

PUBLIC_VERSION = "1"
KINDS = ("arm_resource_id", "guid", "identity")
CODES = ("identifier_in_structure", "index_invalid", "scan_failed", "verification_failed", "write_failed")
KEY_PLACEHOLDER = "withheld-key-{n}"
REF = "id-{n}"

_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_ARM_PATH = re.compile(r"/(?:subscriptions|providers)/", re.IGNORECASE)
_IDENTITY = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")


class PublicReportError(Exception):
    """The public projection could not be produced or verified. `code` is fixed, never a value."""

    def __init__(self, code: str) -> None:
        if code not in CODES:
            raise ValueError(f"unknown code {code!r}")
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------
# Identifier classes
# ---------------------------------------------------------------------------

def identifier_kinds(text: str) -> set[str]:
    """The withheld classes found in one string (empty: nothing to withhold)."""
    kinds = set()
    if _ARM_PATH.search(text):
        kinds.add("arm_resource_id")
    if _GUID.search(text):
        kinds.add("guid")
    if _IDENTITY.search(text):
        kinds.add("identity")
    return kinds


def _value_kinds(value: Any) -> set[str]:
    """Withheld classes in a JSON value, keys included."""
    if isinstance(value, str):
        return identifier_kinds(value)
    if isinstance(value, Mapping):
        out: set[str] = set()
        for key, item in value.items():
            out |= identifier_kinds(str(key)) | _value_kinds(item)
        return out
    if isinstance(value, (list, tuple)):
        return set().union(*(_value_kinds(item) for item in value)) if value else set()
    return set()


def identifier_findings(value: Any, path: str = "$") -> list[str]:
    """`<json path>: <kind>` for every string or key holding a withheld class. Values are never echoed;
    content keys are shown as `<key>`."""
    findings = []
    if isinstance(value, str):
        findings += [f"{path}: {kind}" for kind in sorted(identifier_kinds(value))]
    elif isinstance(value, Mapping):
        for key, item in value.items():
            segment = key if isinstance(key, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,40}", key) else "<key>"
            findings += [f"{path}.{segment}<key>: {kind}" for kind in sorted(identifier_kinds(str(key)))]
            findings += identifier_findings(item, f"{path}.{segment}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            findings += identifier_findings(item, f"{path}[{index}]")
    return findings


# ---------------------------------------------------------------------------
# Public model (strict, frozen; the internal models plus `withheld`)
# ---------------------------------------------------------------------------

class WithheldView(_Model):
    """A view whose value holds a withheld class (P2)."""

    status: Literal["withheld"]
    kinds: Annotated[list[Literal[KINDS]], Field(min_length=1)]
    resource: Annotated[str, Field(min_length=1)] | None
    ref: Annotated[str, Field(pattern=r"^id-[1-9][0-9]*$")] | None

    @model_validator(mode="after")
    def _consistent(self) -> WithheldView:
        if list(self.kinds) != sorted(set(self.kinds)):
            raise ValueError("kinds must be sorted and unique")
        if self.resource is not None and self.ref is not None:
            raise ValueError("a withheld view names a resource or a ref, not both")
        return self


PublicViewValue = Annotated[Union[ValueView, StatusView, WithheldView], Field(discriminator="status")]


class PublicAttributeChange(AttributeChange):
    state: PublicViewValue
    real: PublicViewValue
    desired: PublicViewValue


class PublicDriftItem(DriftItem):
    attribute_changes: list[PublicAttributeChange]


class PublicDriftReport(DriftReport):
    """The public drift report (`public_version` 1). The internal DriftReport rejects it (unknown
    field `public_version`), and it rejects an internal report (missing `public_version`)."""

    public_version: Literal["1"]
    resources: list[PublicDriftItem]


def validate_public(document: Any) -> PublicDriftReport:
    """Strict JSON-semantics validation of a public drift report (raises ValidationError)."""
    return PublicDriftReport.model_validate_json(json.dumps(document))


def public_sha256(document: Any) -> str:
    """Canonical SHA-256 of the public drift report: the only drift report hash a public artifact
    may carry (G11)."""
    return canonical_sha256(document)


# ---------------------------------------------------------------------------
# Address / ARM ID index (runner-only, never published)
# ---------------------------------------------------------------------------

def _module_resources(module: Any) -> Iterable[tuple[str, Any]]:
    if not isinstance(module, Mapping):
        return
    for resource in module.get("resources") or []:
        if isinstance(resource, Mapping) and resource.get("mode") == "managed":
            yield resource.get("address"), (resource.get("values") or {}).get("id")
    for child in module.get("child_modules") or []:
        yield from _module_resources(child)


def build_index(plan: Any) -> dict[str, str | None]:
    """case-folded ARM ID -> the Terraform address of the one managed resource with that ID in this plan
    (None when several addresses share it). Read from prior state, planned values and the before/after
    `id` of resource changes and drift. Raises PublicReportError("index_invalid") for a non-object plan."""
    if not isinstance(plan, Mapping):
        raise PublicReportError("index_invalid")
    pairs: list[tuple[Any, Any]] = []
    for root in ((plan.get("prior_state") or {}).get("values"), plan.get("planned_values")):
        if isinstance(root, Mapping):
            pairs += list(_module_resources(root.get("root_module")))
    for key in ("resource_changes", "resource_drift"):
        for entry in plan.get(key) or []:
            if not isinstance(entry, Mapping) or entry.get("mode") != "managed":
                continue
            change = entry.get("change") or {}
            for side in ("before", "after"):
                values = change.get(side)
                if isinstance(values, Mapping):
                    pairs.append((entry.get("address"), values.get("id")))
    seen: dict[str, set[str]] = {}
    for address, rid in pairs:
        if isinstance(address, str) and isinstance(rid, str) and "arm_resource_id" in identifier_kinds(rid):
            seen.setdefault(rid.casefold(), set()).add(address)
    return {rid: (next(iter(addresses)) if len(addresses) == 1 else None) for rid, addresses in sorted(seen.items())}


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------

class _Refs:
    """Deterministic ordinals: the same raw value always gets the same placeholder."""

    def __init__(self, template: str) -> None:
        self.template, self.seen = template, {}

    def __call__(self, raw: str) -> str:
        if raw not in self.seen:
            self.seen[raw] = self.template.format(n=len(self.seen) + 1)
        return self.seen[raw]


def _withheld(kinds: set[str], resource: str | None = None, ref: str | None = None) -> dict[str, Any]:
    return {"status": "withheld", "kinds": sorted(kinds), "resource": resource, "ref": ref}


def _project_view(view: Mapping[str, Any], forced: set[str], index: Mapping[str, str | None],
                  refs: _Refs) -> dict[str, Any]:
    if view["status"] != "value":
        return dict(view) if not forced else _withheld(forced)
    value = view["value"]
    kinds = _value_kinds(value)
    if not kinds and not forced:
        return {"status": "value", "value": value}
    if forced or not isinstance(value, str):
        return _withheld(kinds | forced)
    address = index.get(value.casefold()) if "arm_resource_id" in kinds else None
    return _withheld(kinds, resource=address) if address else _withheld(kinds, ref=refs(value))


def project(internal: Mapping[str, Any], index: Mapping[str, str | None]) -> dict[str, Any]:
    """The public document for an internal report (JSON form). Raises
    PublicReportError("identifier_in_structure") if a withheld class sits in a field that is never
    rewritten."""
    report = json.loads(json.dumps(internal))
    refs, keys = _Refs(REF), _Refs(KEY_PLACEHOLDER)
    resources = []
    for resource in report["resources"]:
        renamed: dict[str, str] = {}  # dotted internal path -> dotted public path
        changes = []
        for change in resource["attribute_changes"]:
            key_kinds = set().union(*(identifier_kinds(s) for s in change["path"]))
            path = [keys(s) if identifier_kinds(s) else s for s in change["path"]]
            if key_kinds:
                renamed[".".join(change["path"])] = ".".join(path)
            projected = dict(change, path=path, attribute=path[0])
            for name in ("state", "real", "desired"):
                projected[name] = _project_view(change[name], key_kinds, index, refs)
            changes.append(projected)
        reasons = []
        for reason in resource["severity"]["reasons"]:
            for old, new in renamed.items():
                if reason.startswith(old + ": "):
                    reason = new + reason[len(old):]
                    break
            reasons.append(reason)
        attributes = [dict(a, name=keys(a["name"]) if identifier_kinds(a["name"]) else a["name"])
                      for a in resource["attributes"]]
        resources.append(dict(resource, attribute_changes=changes, attributes=attributes,
                              severity=dict(resource["severity"], reasons=reasons)))
    public = dict(report, resources=resources, public_version=PUBLIC_VERSION)
    if identifier_findings(_structure(public)):
        raise PublicReportError("identifier_in_structure")
    return public


def _structure(document: Mapping[str, Any]) -> dict[str, Any]:
    """Everything except the (already projected) views: the fields that are never rewritten."""
    return dict(document, resources=[
        dict(r, attribute_changes=[{k: v for k, v in c.items() if k not in ("state", "real", "desired")}
                                   for c in r["attribute_changes"]])
        for r in document["resources"]])


# ---------------------------------------------------------------------------
# Independent verification (a separate re-derivation, not a re-run of `project`)
# ---------------------------------------------------------------------------

def verify_public_report(public: Mapping[str, Any], internal: Mapping[str, Any],
                         index: Mapping[str, str | None]) -> list[str]:
    """Problems if `public` is not exactly the projection of `internal` (empty list = valid). Messages name
    locations only, never values."""
    try:
        validate_public(public)
    except (ValidationError, TypeError, ValueError):
        return ["contract: not a valid public drift report"]
    problems: list[str] = []
    add = problems.append
    for key in sorted(set(internal) | set(public)):
        if key in ("resources", "public_version"):
            continue
        if public.get(key) != internal.get(key) or key not in public:
            add(f"{key}: differs from the internal report")
    if len(public["resources"]) != len(internal["resources"]):
        return problems + ["resources: count differs"]
    key_map: dict[str, str] = {}
    ref_map: dict[str, str] = {}

    def placeholder(raw: str, given: str, table: dict[str, str], prefix: str, where: str) -> None:
        if raw in table:
            if table[raw] != given:
                add(f"{where}: placeholder is not stable for the same value")
            return
        expected = f"{prefix}{len(table) + 1}"
        if given != expected:
            add(f"{where}: placeholders are not numbered in order of first occurrence")
        table[raw] = given

    for r, (pub, raw) in enumerate(zip(public["resources"], internal["resources"])):
        where = f"resources[{r}]"
        for field in sorted(set(raw) | set(pub)):
            if field in ("attribute_changes", "attributes", "severity"):
                continue
            if pub.get(field) != raw.get(field):
                add(f"{where}.{field}: differs from the internal report")
        if pub["severity"]["level"] != raw["severity"]["level"]:
            add(f"{where}.severity.level: differs")
        if len(pub["attribute_changes"]) != len(raw["attribute_changes"]):
            add(f"{where}.attribute_changes: count differs")
            continue
        renamed = {}
        for c, (pc, rc) in enumerate(zip(pub["attribute_changes"], raw["attribute_changes"])):
            at = f"{where}.attribute_changes[{c}]"
            if len(pc["path"]) != len(rc["path"]):
                add(f"{at}.path: length differs")
                continue
            key_kinds: set[str] = set()
            for s, (ps, rs) in enumerate(zip(pc["path"], rc["path"])):
                found = _kinds_of(rs)
                if found:
                    key_kinds |= found
                    placeholder(rs, ps, key_map, "withheld-key-", f"{at}.path[{s}]")
                elif ps != rs:
                    add(f"{at}.path[{s}]: differs from the internal report")
            if key_kinds:
                renamed[".".join(rc["path"])] = ".".join(pc["path"])
            if pc["attribute"] != pc["path"][0]:
                add(f"{at}.attribute: does not match the path")
            for field in ("class", "redacted", "severity", "assessment"):
                if pc.get(field) != rc.get(field):
                    add(f"{at}.{field}: differs from the internal report")
            for view in ("state", "real", "desired"):
                _check_view(pc[view], rc[view], key_kinds, index, ref_map, placeholder, f"{at}.{view}", add)
        for a, (pa, ra) in enumerate(zip(pub["attributes"], raw["attributes"])):
            if pa.get("class") != ra.get("class"):
                add(f"{where}.attributes[{a}]: class differs")
            if _kinds_of(ra["name"]):
                if key_map.get(ra["name"]) != pa["name"]:
                    add(f"{where}.attributes[{a}]: name is not its key placeholder")
            elif pa["name"] != ra["name"]:
                add(f"{where}.attributes[{a}]: name differs")
        if len(pub["attributes"]) != len(raw["attributes"]):
            add(f"{where}.attributes: count differs")
        expected_reasons = []
        for reason in raw["severity"]["reasons"]:
            prefix = reason.split(": ", 1)[0]
            expected_reasons.append(renamed[prefix] + reason[len(prefix):] if prefix in renamed else reason)
        if pub["severity"]["reasons"] != expected_reasons:
            add(f"{where}.severity.reasons: differ from the internal report")
    findings = identifier_findings(public)
    if findings:
        add(f"scan: {len(findings)} identifier finding(s)")
    return problems


def _kinds_of(text: str) -> set[str]:
    """Withheld classes of one string (verification's own restatement of `identifier_kinds`)."""
    return {kind for kind, pattern in (("arm_resource_id", _ARM_PATH), ("guid", _GUID), ("identity", _IDENTITY))
            if pattern.search(text)}


def _check_view(pub: Mapping[str, Any], raw: Mapping[str, Any], key_kinds: set[str], index, ref_map, placeholder,
                where: str, add) -> None:
    withheld_key = bool(key_kinds)
    if raw["status"] != "value":
        if withheld_key:
            ok = (pub.get("status") == "withheld" and pub.get("resource") is None and pub.get("ref") is None
                  and list(pub.get("kinds", [])) == sorted(key_kinds))
        else:
            ok = dict(pub) == dict(raw)
        if not ok:
            add(f"{where}: a value-less view must be copied (or withheld under a withheld key)")
        return
    value = raw["value"]
    leaves = list(_strings(value))
    kinds = set()
    for leaf in leaves:
        kinds |= _kinds_of(leaf)
    if not kinds and not withheld_key:
        if dict(pub) != {"status": "value", "value": value}:
            add(f"{where}: a view without identifiers must be copied unchanged")
        return
    if pub.get("status") != "withheld":
        add(f"{where}: a view with identifiers must be withheld")
        return
    if withheld_key:
        if pub.get("resource") is not None or pub.get("ref") is not None:
            add(f"{where}: a view under a withheld key names no resource or ref")
        if list(pub.get("kinds", [])) != sorted(kinds | key_kinds):
            add(f"{where}: kinds differ from the key and the value")
        return
    if sorted(kinds) != list(pub.get("kinds", [])):
        add(f"{where}: kinds differ from the value")
    if not isinstance(value, str):
        if pub.get("resource") is not None or pub.get("ref") is not None:
            add(f"{where}: a withheld container names no resource or ref")
        return
    address = index.get(value.casefold()) if _ARM_PATH.search(value) else None
    if address:
        if pub.get("resource") != address or pub.get("ref") is not None:
            add(f"{where}: an ARM ID of a plan resource must name its address")
    elif pub.get("resource") is not None or pub.get("ref") is None:
        add(f"{where}: a withheld scalar needs a ref")
    else:
        placeholder(value, pub["ref"], ref_map, "id-", where)


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------

def render_public(document: Mapping[str, Any]) -> str:
    """Sorted keys, two-space indent, trailing newline: byte-stable."""
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def publish_report(internal: Mapping[str, Any], plan: Any, manifest: Any = None) -> str:
    """The rendered public drift report: project, validate, verify independently and scan (the report and, when
    given, the run manifest that is published beside it). Raises PublicReportError with a fixed code."""
    index = build_index(plan)
    public = project(internal, index)
    if verify_public_report(public, internal, index):
        raise PublicReportError("verification_failed")
    if identifier_findings(public) or (manifest is not None and identifier_findings(manifest)):
        raise PublicReportError("scan_failed")
    return render_public(validate_public(public).model_dump(mode="json"))


def public_document(internal: Mapping[str, Any], plan: Any, manifest: Any = None) -> dict[str, Any]:
    """`publish_report` as a parsed JSON object."""
    return json.loads(publish_report(internal, plan, manifest))
