"""Deterministic, rules-based drift severity (Task 4.5).

Rates the changes found by the comparator (Task 4.4) as CRITICAL, HIGH, MEDIUM,
LOW or INFO. This is the fallback rating that exists before, and without, any AI
enrichment (spec §10): the same input always gives the same rating, with the ids
of the rules that produced it.

Change severity:
  1. Proven noise (comparator category `noise`) is INFO.
  2. Otherwise the highest severity among matching SEVERITY_RULES. A rule matches
     a resource type and a change-path prefix, and can escalate (e.g. HIGH ->
     CRITICAL) when the real or desired value is exposed, such as an inbound rule
     allowing any source.
  3. A significant change no rule matches is MEDIUM: unknown impact is never
     rated down.

Resource severity is the highest change severity, raised to a floor for some
resource classifications and actions (an object deleted outside Terraform is at
least HIGH, CRITICAL for security-sensitive types; a planned replace is at least
HIGH; `undetermined` is at least MEDIUM).

Rules are path-specific, so a tag change on a Key Vault is LOW while a change to
its access policies is CRITICAL. Severity describes the impact of the change; it
applies to drift and to planned configuration changes alike, and each result
records whether it is drift. It annotates only: nothing is dropped and no
classification changes.

Standard library only. No Terraform, Azure, network or LLM access.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any, Callable, Iterable, Mapping

from drift_engine.comparator import NOISE, ChangeAssessment, ResourceComparison
from drift_engine.logs import log_event
from drift_engine.parser import ParsedPlan, ResourceEvidence

logger = logging.getLogger(__name__)

INFO = "INFO"
LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
CRITICAL = "CRITICAL"
SEVERITIES = (INFO, LOW, MEDIUM, HIGH, CRITICAL)  # ascending
_RANK = {s: i for i, s in enumerate(SEVERITIES)}

DEFAULT_SEVERITY = MEDIUM  # significant change matched by no rule


def rank(severity: str) -> int:
    return _RANK[severity]


def highest(severities: Iterable[str], default: str = INFO) -> str:
    return max(severities, key=rank, default=default)


# ---------------------------------------------------------------------------
# Value checks used for escalation. They read the real (current Azure) and the
# desired (planned) value, and never see redacted or unknown values: those fall
# back to the rule's base severity.
# ---------------------------------------------------------------------------

Escalation = Callable[[ChangeAssessment, "ResourceEvidence | None"], bool]

_OPEN_SOURCES = {"*", "any", "internet", "0.0.0.0/0", "0.0.0.0", "::/0"}


def _values(assessment: ChangeAssessment) -> list[Any]:
    """The real and desired values of a change, where they are plain values."""
    change = assessment.change
    return [change[v]["value"] for v in ("real", "desired") if change[v]["status"] == "value"]


def _objects(evidence: ResourceEvidence | None) -> list[dict]:
    if evidence is None:
        return []
    return [o for o in (evidence.real, evidence.desired) if isinstance(o, dict)]


def _lower(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _open_inbound(rule: Any) -> bool:
    """An NSG rule that allows inbound traffic from any source."""
    if not isinstance(rule, dict):
        return False
    if _lower(rule.get("direction")) != "inbound" or _lower(rule.get("access")) != "allow":
        return False
    prefixes = [rule.get("source_address_prefix")]
    if isinstance(rule.get("source_address_prefixes"), list):
        prefixes += rule["source_address_prefixes"]
    return any(_lower(p) in _OPEN_SOURCES for p in prefixes)


def nsg_rules_open_inbound(assessment: ChangeAssessment, evidence: ResourceEvidence | None) -> bool:
    """azurerm_network_security_group: a security_rule allows inbound from anywhere."""
    for value in _values(assessment):
        rules = value if isinstance(value, list) else [value]
        if any(_open_inbound(r) for r in rules):
            return True
    return False


def standalone_rule_open_inbound(assessment: ChangeAssessment, evidence: ResourceEvidence | None) -> bool:
    """azurerm_network_security_rule: the rule resource itself allows inbound from anywhere."""
    return any(_open_inbound(o) for o in _objects(evidence))


def value_is_true(assessment: ChangeAssessment, evidence: ResourceEvidence | None) -> bool:
    return any(v is True for v in _values(assessment))


def value_is_false(assessment: ChangeAssessment, evidence: ResourceEvidence | None) -> bool:
    return any(v is False for v in _values(assessment))


def default_action_allow(assessment: ChangeAssessment, evidence: ResourceEvidence | None) -> bool:
    """network_rules / network_acls whose default action lets all traffic in."""
    for value in _values(assessment):
        blocks = value if isinstance(value, list) else [value]
        if any(isinstance(b, dict) and _lower(b.get("default_action")) == "allow" for b in blocks):
            return True
    return False


def resource_default_action_allow(assessment: ChangeAssessment, evidence: ResourceEvidence | None) -> bool:
    """A standalone network-rules resource whose default action lets all traffic in."""
    return any(_lower(o.get("default_action")) == "allow" for o in _objects(evidence))


def public_container_access(assessment: ChangeAssessment, evidence: ResourceEvidence | None) -> bool:
    return any(_lower(v) in ("blob", "container") for v in _values(assessment))


# ---------------------------------------------------------------------------
# Rules (declarative)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SeverityRule:
    """Severity for changes to `paths` (prefix fnmatch patterns, one per segment)
    of `resource_types`; raised to `escalate_to` when `escalate_when` holds.
    `redacted_only` rules match only changes whose values are redacted."""

    id: str
    severity: str
    description: str
    paths: tuple[tuple[str, ...], ...]
    resource_types: tuple[str, ...] = ("*",)
    escalate_to: str | None = None
    escalate_when: Escalation | None = None
    redacted_only: bool = False

    def __post_init__(self) -> None:
        for s in (self.severity, self.escalate_to):
            if s is not None and s not in _RANK:
                raise ValueError(f"rule {self.id}: unknown severity {s!r}")
        if (self.escalate_to is None) != (self.escalate_when is None):
            raise ValueError(f"rule {self.id}: escalate_to and escalate_when go together")

    def matches(self, resource_type: Any, change: dict) -> bool:
        if self.redacted_only and not change["redacted"]:
            return False
        if not any(fnmatchcase(str(resource_type), t) for t in self.resource_types):
            return False
        path = change["path"]
        return any(
            len(pattern) <= len(path) and all(fnmatchcase(seg, pat) for seg, pat in zip(path, pattern))
            for pattern in self.paths
        )

    def rate(self, assessment: ChangeAssessment, evidence: ResourceEvidence | None) -> str:
        if self.escalate_when is not None and self.escalate_when(assessment, evidence):
            return self.escalate_to  # type: ignore[return-value]
        return self.severity


ANY_PATH = (("*",),)

SEVERITY_RULES: tuple[SeverityRule, ...] = (
    # --- Key Vault ---------------------------------------------------------
    SeverityRule("key-vault-access-policy", CRITICAL,
                 "Key Vault access policies grant access to keys, secrets and certificates.",
                 (("access_policy",),), ("azurerm_key_vault",)),
    SeverityRule("key-vault-access-policy-resource", CRITICAL,
                 "Standalone Key Vault access policy resource.",
                 ANY_PATH, ("azurerm_key_vault_access_policy",)),
    SeverityRule("key-vault-rbac-mode", CRITICAL,
                 "Switching between access policies and Azure RBAC changes who can read secrets.",
                 (("enable_rbac_authorization",), ("rbac_authorization_enabled",)), ("azurerm_key_vault",)),
    SeverityRule("key-vault-network", HIGH,
                 "Key Vault network exposure; CRITICAL when public access is enabled or the default action is Allow.",
                 (("network_acls",),), ("azurerm_key_vault",),
                 CRITICAL, default_action_allow),
    SeverityRule("key-vault-public-access", HIGH,
                 "Key Vault public network access; CRITICAL when enabled.",
                 (("public_network_access_enabled",),), ("azurerm_key_vault",),
                 CRITICAL, value_is_true),
    SeverityRule("key-vault-recovery", HIGH,
                 "Purge protection and soft delete protect against permanent deletion.",
                 (("purge_protection_enabled",), ("soft_delete_retention_days",)), ("azurerm_key_vault",)),
    # --- Network security groups -------------------------------------------
    SeverityRule("nsg-security-rule", HIGH,
                 "NSG security rules; CRITICAL when an inbound rule allows any source.",
                 (("security_rule",),), ("azurerm_network_security_group",),
                 CRITICAL, nsg_rules_open_inbound),
    SeverityRule("nsg-rule-resource", HIGH,
                 "Standalone NSG rule; CRITICAL when it allows inbound traffic from any source.",
                 ANY_PATH, ("azurerm_network_security_rule",),
                 CRITICAL, standalone_rule_open_inbound),
    # --- Storage -------------------------------------------------------------
    SeverityRule("storage-public-network-access", HIGH,
                 "Storage account public network access; CRITICAL when enabled.",
                 (("public_network_access_enabled",),), ("azurerm_storage_account",),
                 CRITICAL, value_is_true),
    SeverityRule("storage-public-blob-access", HIGH,
                 "Anonymous public read access to blobs; CRITICAL when allowed.",
                 (("allow_nested_items_to_be_public",), ("allow_blob_public_access",)), ("azurerm_storage_account",),
                 CRITICAL, value_is_true),
    SeverityRule("storage-network-rules", HIGH,
                 "Storage firewall and IP allow list; CRITICAL when the default action is Allow.",
                 (("network_rules",),), ("azurerm_storage_account",),
                 CRITICAL, default_action_allow),
    SeverityRule("storage-network-rules-resource", HIGH,
                 "Standalone storage network rules; CRITICAL when the default action is Allow.",
                 ANY_PATH, ("azurerm_storage_account_network_rules",),
                 CRITICAL, resource_default_action_allow),
    SeverityRule("storage-transport-and-keys", HIGH,
                 "HTTPS-only, minimum TLS version and shared key access.",
                 (("https_traffic_only_enabled",), ("enable_https_traffic_only",), ("min_tls_version",),
                  ("shared_access_key_enabled",)), ("azurerm_storage_account",)),
    SeverityRule("storage-container-access", HIGH,
                 "Container access level; CRITICAL when anonymous (blob/container).",
                 (("container_access_type",),), ("azurerm_storage_container",),
                 CRITICAL, public_container_access),
    # --- Any resource ----------------------------------------------------------
    SeverityRule("sensitive-value", HIGH,
                 "A value Terraform marks sensitive changed; it is redacted, so its impact cannot be read.",
                 ANY_PATH, redacted_only=True),
    SeverityRule("tags", LOW,
                 "Resource tags: metadata, no effect on access or behavior.",
                 (("tags",),)),
    SeverityRule("description", LOW,
                 "Free-text description.",
                 (("description",),)),
)

# Floors for the resource as a whole (spec §6.1 classes, planned action).
SECURITY_SENSITIVE_TYPES = frozenset({
    "azurerm_key_vault", "azurerm_key_vault_access_policy",
    "azurerm_network_security_group", "azurerm_network_security_rule",
    "azurerm_storage_account", "azurerm_storage_account_network_rules", "azurerm_storage_container",
})


def resource_floor(
    classification: str | None, action: str | None, resource_type: Any
) -> tuple[str, str | None]:
    """(minimum severity, reason) implied by the resource classification and planned action."""
    floors = [(INFO, None)]
    if classification == "external_deletion":
        if isinstance(resource_type, str) and resource_type in SECURITY_SENSITIVE_TYPES:
            floors.append((CRITICAL, "security-sensitive resource deleted outside Terraform"))
        else:
            floors.append((HIGH, "resource deleted outside Terraform"))
    elif classification == "undetermined":
        floors.append((MEDIUM, "classification undetermined; needs review"))
    if action == "replace":
        floors.append((HIGH, "planned replace destroys and recreates the object"))
    return max(floors, key=lambda f: rank(f[0]))


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChangeSeverity:
    assessment: ChangeAssessment  # from the comparator, unmodified
    severity: str
    rules: tuple[str, ...]  # ids of the rules that set the severity; empty for noise/default

    @property
    def path(self) -> list[str]:
        return self.assessment.change["path"]

    @property
    def is_drift(self) -> bool:
        return self.assessment.is_drift


@dataclass(frozen=True)
class ResourceSeverity:
    address: str
    type: Any
    classification: str | None
    severity: str
    changes: tuple[ChangeSeverity, ...]  # one per comparator change, same order
    reasons: tuple[str, ...]  # why the resource has its severity


def change_severity(
    assessment: ChangeAssessment,
    resource_type: Any,
    evidence: ResourceEvidence | None = None,
    rules: tuple[SeverityRule, ...] = SEVERITY_RULES,
) -> ChangeSeverity:
    if assessment.category == NOISE:
        return ChangeSeverity(assessment, INFO, ())
    change = assessment.change
    rated = [
        (r.id, r.rate(assessment, evidence))
        for r in rules
        if r.matches(resource_type, change)
    ]
    if not rated:
        return ChangeSeverity(assessment, DEFAULT_SEVERITY, ())
    top = highest(s for _, s in rated)
    return ChangeSeverity(assessment, top, tuple(rid for rid, s in rated if s == top))


def resource_severity(
    comparison: ResourceComparison,
    evidence: ResourceEvidence | None = None,
    classification: str | None = None,
    rules: tuple[SeverityRule, ...] = SEVERITY_RULES,
) -> ResourceSeverity:
    if evidence is not None and evidence.address != comparison.address:
        raise ValueError(f"evidence for {evidence.address} given for {comparison.address}")
    changes = tuple(change_severity(a, comparison.type, evidence, rules) for a in comparison.changes)
    floor, floor_reason = resource_floor(classification, comparison.action, comparison.type)
    top = highest([c.severity for c in changes] + [floor])

    reasons = []
    if floor_reason and rank(floor) >= rank(top):
        reasons.append(floor_reason)
    for c in changes:
        if c.severity == top and top != INFO:
            reasons.append(f"{'.'.join(c.path)}: {', '.join(c.rules) or 'no rule matched (default ' + DEFAULT_SEVERITY + ')'}")
    return ResourceSeverity(comparison.address, comparison.type, classification, top, changes, tuple(reasons))


def plan_severity(
    parsed: ParsedPlan,
    comparisons: tuple[ResourceComparison, ...],
    classifications: Mapping[str, str] | None = None,
    rules: tuple[SeverityRule, ...] = SEVERITY_RULES,
) -> tuple[ResourceSeverity, ...]:
    """resource_severity for every resource of compare_plan(parsed, ...), in address order.

    `classifications` maps address -> spec §6.1 class (the classifier's
    `resources[].classification`); without it no classification floor applies.
    """
    if [c.address for c in comparisons] != [e.address for e in parsed.resources]:
        raise ValueError("comparisons do not match the parsed plan")
    classes = classifications or {}
    rated = tuple(
        resource_severity(c, e, classes.get(c.address), rules)
        for c, e in zip(comparisons, parsed.resources)
    )
    counts = Counter(r.severity for r in rated)
    log_event(logger, logging.DEBUG, "severity_rated", "resources rated",
              resources=len(rated), highest=highest(counts), severities={s: counts[s] for s in SEVERITIES if counts[s]},
              classification_floors=classifications is not None)
    return rated
