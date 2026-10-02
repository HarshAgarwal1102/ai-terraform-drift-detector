"""Resource difference and comparison engine (Task 4.4).

Two parts:

1. Deep attribute diff between the S/R/D views of one resource (spec §6.2, Task 3.4
   detail). Migrated unchanged from scripts/detect_drift.py, which now imports it.

2. Assessment of each changed path (new in Task 4.4), separating what the user
   configured from noise:

     configured    the top-level attribute is set in the Terraform configuration
                   (plan.json `configuration` expressions): user intent
     noise         matched a declarative NOISE_RULES entry and is proven *not*
                   configured: provider-computed IDs, timestamps, read-only metadata
     unconfigured  not configured and not noise: e.g. an external change to a value
                   left at its provider default, which Terraform will still revert
     undetermined  the configuration does not cover this resource, so neither
                   configured nor noise can be proven

   Per spec §9 this runs after classification and only annotates: every change stays
   in the result, resource classifications and the report are untouched, and only
   `noise` is left out of `significant`. Anything not proven to be noise counts as
   significant.

Standard library only. No Terraform, Azure, network or LLM access.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any, Mapping

from drift_engine.logs import log_event
from drift_engine.parser import ParsedPlan, ResourceEvidence, normalize_action

logger = logging.getLogger(__name__)

# Attribute classes (spec §6.2)
DRIFTED = "drifted"
DRIFTED_CONVERGED = "drifted_converged"
CONFIG_CHANGED = "config_changed"
DRIFTED_AND_CONFIG_CHANGED = "drifted_and_config_changed"
UNKNOWN_UNTIL_APPLY = "unknown_until_apply"

DRIFT_CLASSES = frozenset({DRIFTED, DRIFTED_CONVERGED, DRIFTED_AND_CONFIG_CHANGED})

_MISSING = object()  # attribute absent from a view (distinct from JSON null)


# ---------------------------------------------------------------------------
# Attribute-level rule (spec §6.2, top-level attributes only)
# ---------------------------------------------------------------------------

def _contains_true(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, dict):
        return any(_contains_true(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_true(v) for v in value)
    return False


def classify_attributes(
    state: dict | None, real: dict | None, desired: dict | None, after_unknown: Any
) -> list[dict]:
    """Return changed top-level attributes with their §6.2 class.

    Only attribute names and classes are reported; values are Task 3.4 scope
    (and are withheld here so sensitive values cannot leak).
    """
    if not isinstance(state, dict) or not isinstance(real, dict) or not isinstance(desired, dict):
        return []  # object created or destroyed: no attribute-level comparison
    unknown = after_unknown if isinstance(after_unknown, dict) else {}

    result = []
    for name in sorted(set(state) | set(real) | set(desired) | set(unknown)):
        if _contains_true(unknown.get(name)):
            result.append({"name": name, "class": UNKNOWN_UNTIL_APPLY})
            continue
        cls = _attribute_class(
            state.get(name, _MISSING), real.get(name, _MISSING), desired.get(name, _MISSING)
        )
        if cls is not None:
            result.append({"name": name, "class": cls})
    return result


def _attribute_class(s: Any, r: Any, d: Any) -> str | None:
    """The §6.2 rule for one value in the three views; None when unchanged."""
    if s == r:
        return None if d == s else CONFIG_CHANGED
    if d == s:
        return DRIFTED
    if d == r:
        return DRIFTED_CONVERGED
    return DRIFTED_AND_CONFIG_CHANGED


# ---------------------------------------------------------------------------
# Attribute detail (Task 3.4): nested paths and values, sensitive values redacted
# ---------------------------------------------------------------------------
# Each view value is reported as {"status": ...}:
#   value     {"status": "value", "value": <JSON value, may be null>}
#   absent    the object or key does not exist in that view
#   unknown   desired value not known until apply (after_unknown)
#   redacted  flagged sensitive (before_sensitive / after_sensitive, spec §8.3); a
#             value reported whole (lists, incl. nested blocks) is redacted when the
#             mask flags it or anything inside it
# Maps/objects are descended key by key; lists are compared as whole values.

def _child(node: Any, key: str) -> Any:
    return node.get(key, _MISSING) if isinstance(node, dict) else _MISSING


def _child_mask(mask: Any, key: str) -> Any:
    if mask is True:
        return True  # a flag on a parent covers every child
    return mask.get(key) if isinstance(mask, dict) else None


def _view(value: Any, redacted: bool, unknown: bool = False) -> dict:
    if unknown:
        return {"status": "unknown"}
    if value is _MISSING:
        return {"status": "absent"}
    if redacted:
        return {"status": "redacted"}
    return {"status": "value", "value": value}


def _descend(nodes: tuple, unknown: Any) -> list[str] | None:
    """Sorted child keys when the path is a map/object in every view where it exists."""
    if not all(isinstance(v, dict) or v is _MISSING for v in nodes):
        return None
    partly_unknown = isinstance(unknown, dict) and _contains_true(unknown)
    if not any(isinstance(v, dict) for v in nodes) and not partly_unknown:
        return None
    keys: set[str] = set()
    for v in nodes:
        if isinstance(v, dict):
            keys |= set(v)
    if isinstance(unknown, dict):
        keys |= set(unknown)
    return sorted(keys)


def _walk(path: list[str], nodes: tuple, unknown: Any, masks: list, object_level: bool, out: list) -> None:
    s, r, d = nodes
    sensitive = any(m is True for m in masks)
    is_unknown = unknown is True
    if not sensitive and not is_unknown:
        keys = _descend(nodes, unknown)
        if keys is not None:
            before = len(out)
            for key in keys:
                _walk(
                    path + [key],
                    (_child(s, key), _child(r, key), _child(d, key)),
                    _child_mask(unknown, key),
                    [_child_mask(m, key) for m in masks],
                    object_level,
                    out,
                )
            if len(out) > before or s == r == d:
                return
            # e.g. {} versus absent: nothing below differs, so report this node itself
    if not is_unknown and s == r == d:
        return
    # This node is emitted whole (a list, a scalar, or an object not descended), so its
    # value carries every flagged path below it: a mask flagging anything inside it
    # (e.g. one field of a nested block, which plan JSON encodes as a list) redacts it.
    sensitive = any(_contains_true(m) for m in masks)
    if object_level:
        cls = None  # §6.2 applies only when the object exists in all three views
    elif is_unknown:
        cls = UNKNOWN_UNTIL_APPLY
    else:
        cls = _attribute_class(s, r, d)
    out.append({
        "path": path,
        "attribute": path[0],
        "class": cls,
        "state": _view(s, sensitive),
        "real": _view(r, sensitive),
        "desired": _view(d, sensitive, is_unknown),
        "redacted": sensitive and any(v is not _MISSING for v in nodes),
    })


def attribute_changes(
    state: Any, real: Any, desired: Any, after_unknown: Any, sensitive_masks: list
) -> list[dict]:
    """Leaf-level differences between the S, R and D views of one resource.

    `class` reuses the §6.2 rule at the leaf, or is null when the object is absent
    from a view (create/delete), where §6.2 does not apply. Values flagged
    sensitive in any mask are redacted in every view.
    """
    nodes = tuple(v if isinstance(v, dict) else _MISSING for v in (state, real, desired))
    object_level = any(v is _MISSING for v in nodes)
    out: list[dict] = []
    for key in _descend(nodes, after_unknown) or []:
        _walk(
            [key],
            (_child(nodes[0], key), _child(nodes[1], key), _child(nodes[2], key)),
            _child_mask(after_unknown, key),
            [_child_mask(m, key) for m in sensitive_masks],
            object_level,
            out,
        )
    return out


def evidence_changes(ev: ResourceEvidence) -> list[dict]:
    """attribute_changes for one parsed resource."""
    return attribute_changes(ev.state, ev.real, ev.desired, ev.after_unknown, list(ev.sensitive_masks))


# ---------------------------------------------------------------------------
# Noise rules (spec §9: declarative data, applied after classification)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NoiseRule:
    """A change matching this rule is noise, unless its attribute is configured.

    `paths` are prefixes of a change path, one fnmatch pattern per segment
    (("timeouts",) matches ["timeouts", "create"]). `resource_types` are fnmatch
    patterns. Optional conditions: `actions` (normalized planned action, empty =
    any) and `desired_unset` (desired view is null or absent).
    """

    id: str
    description: str
    paths: tuple[tuple[str, ...], ...]
    resource_types: tuple[str, ...] = ("*",)
    actions: tuple[str, ...] = ()
    desired_unset: bool = False

    def matches(self, resource_type: Any, action: str | None, change: dict) -> bool:
        if not any(fnmatchcase(str(resource_type), t) for t in self.resource_types):
            return False
        if self.actions and action not in self.actions:
            return False
        if self.desired_unset and change["desired"] not in ({"status": "absent"}, {"status": "value", "value": None}):
            return False
        path = change["path"]
        return any(
            len(pattern) <= len(path) and all(fnmatchcase(seg, pat) for seg, pat in zip(path, pattern))
            for pattern in self.paths
        )


NOISE_RULES: tuple[NoiseRule, ...] = (
    NoiseRule(
        "computed-id",
        "Provider-assigned resource ID; changes or becomes unknown when the object is (re)created.",
        (("id",),),
    ),
    NoiseRule(
        "timeouts",
        "Terraform operation timeouts block; not an Azure property.",
        (("timeouts",),),
    ),
    NoiseRule(
        "timestamps",
        "Creation and modification timestamps maintained by Azure.",
        tuple((p,) for p in (
            "created_at", "created_on", "creation_time", "creation_date", "created_date",
            "updated_at", "updated_on", "last_modified*", "last_updated*", "*_timestamp",
        )),
    ),
    NoiseRule(
        "read-only-metadata",
        "Read-only concurrency and provisioning metadata.",
        tuple((p,) for p in ("etag", "*_etag", "provisioning_state", "resource_guid")),
    ),
    NoiseRule(
        "replace-unset-optional",
        "On replace, desired values describe the new object; an optional attribute the "
        "configuration does not set shows as cleared (e.g. managed_by \"\" -> null).",
        (("*",),),
        actions=("replace",),
        desired_unset=True,
    ),
)


# ---------------------------------------------------------------------------
# Configured attributes (plan.json `configuration`)
# ---------------------------------------------------------------------------

def config_address(address: str) -> str:
    """Resource address without module and resource instance keys.

    'module.a["x"].azurerm_x.this["k.1"]' -> 'module.a.azurerm_x.this'
    """
    out: list[str] = []
    in_key = quoted = escaped = False  # inside [...]; inside a quoted string key
    for ch in address:
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
        elif in_key:
            if ch == '"':
                quoted = True
            elif ch == "]":
                in_key = False
        elif ch == "[":
            in_key = True
        else:
            out.append(ch)
    return "".join(out)


def configured_attributes(plan: Any) -> dict[str, frozenset[str]]:
    """Top-level attribute names set in the configuration, keyed by config address.

    Read from `configuration.root_module` and nested `module_calls`. Meta-arguments
    (count, for_each, depends_on, lifecycle) are not expressions and are not included.
    Returns {} when the plan has no usable configuration section.
    """
    result: dict[str, frozenset[str]] = {}
    root = plan.get("configuration") if isinstance(plan, dict) else None
    root = root.get("root_module") if isinstance(root, dict) else None
    stack = [("", root)]
    while stack:
        prefix, module = stack.pop()
        if not isinstance(module, dict):
            continue
        resources = module.get("resources")
        for resource in resources if isinstance(resources, list) else []:
            if isinstance(resource, dict) and isinstance(resource.get("address"), str):
                expressions = resource.get("expressions")
                names = frozenset(expressions) if isinstance(expressions, dict) else frozenset()
                result[prefix + resource["address"]] = names
        calls = module.get("module_calls")
        if isinstance(calls, dict):
            for name, call in calls.items():
                if isinstance(call, dict):
                    stack.append((f"{prefix}module.{name}.", call.get("module")))
    return result


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------

CONFIGURED = "configured"
UNCONFIGURED = "unconfigured"
NOISE = "noise"
UNDETERMINED = "undetermined"


@dataclass(frozen=True)
class ChangeAssessment:
    change: dict  # one attribute_changes entry, unmodified
    category: str  # CONFIGURED / UNCONFIGURED / NOISE / UNDETERMINED
    configured: bool | None  # None: the configuration does not cover this resource
    rule: str | None  # id of the matching noise rule (also recorded when overridden by configuration)

    @property
    def significant(self) -> bool:
        return self.category != NOISE

    @property
    def is_drift(self) -> bool:
        return self.change["class"] in DRIFT_CLASSES


@dataclass(frozen=True)
class ResourceComparison:
    address: str
    type: Any
    action: str | None
    changes: tuple[ChangeAssessment, ...]  # every attribute change, in report order

    @property
    def significant(self) -> tuple[ChangeAssessment, ...]:
        """Everything except proven noise."""
        return tuple(c for c in self.changes if c.significant)

    @property
    def noise(self) -> tuple[ChangeAssessment, ...]:
        return tuple(c for c in self.changes if not c.significant)

    @property
    def configured_drift(self) -> tuple[ChangeAssessment, ...]:
        """Drift (spec §6.2 drift classes) on attributes the user configured."""
        return tuple(c for c in self.changes if c.category == CONFIGURED and c.is_drift)


def assess_change(
    change: dict,
    resource_type: Any,
    action: str | None,
    configured: frozenset[str] | None,
    rules: tuple[NoiseRule, ...] = NOISE_RULES,
) -> ChangeAssessment:
    """Categorize one attribute change. Configuration wins over any noise rule."""
    rule = next((r.id for r in rules if r.matches(resource_type, action, change)), None)
    if configured is None:
        return ChangeAssessment(change, UNDETERMINED, None, rule)
    if change["attribute"] in configured:
        return ChangeAssessment(change, CONFIGURED, True, rule)
    return ChangeAssessment(change, NOISE if rule else UNCONFIGURED, False, rule)


def compare_resource(
    ev: ResourceEvidence,
    configured: Mapping[str, frozenset[str]],
    rules: tuple[NoiseRule, ...] = NOISE_RULES,
) -> ResourceComparison:
    """Diff one resource and assess every changed path.

    `configured` is configured_attributes(plan). A resource missing from it is
    `undetermined`, except when the configuration no longer declares it at all
    (planned delete, or nothing planned), where nothing counts as configured.
    """
    action = normalize_action(ev.actions)
    names = configured.get(config_address(ev.address))
    if names is None and configured and action in ("delete", None):
        names = frozenset()  # removed from the configuration
    return ResourceComparison(
        address=ev.address,
        type=ev.type,
        action=action,
        changes=tuple(assess_change(c, ev.type, action, names, rules) for c in evidence_changes(ev)),
    )


def compare_plan(
    parsed: ParsedPlan,
    configured: Mapping[str, frozenset[str]],
    rules: tuple[NoiseRule, ...] = NOISE_RULES,
) -> tuple[ResourceComparison, ...]:
    """compare_resource for every managed resource, in address order."""
    result = tuple(compare_resource(ev, configured, rules) for ev in parsed.resources)
    categories = Counter(c.category for r in result for c in r.changes)
    log_event(logger, logging.DEBUG, "comparison_finished", "attribute changes assessed",
              resources=len(result), changes=sum(categories.values()), categories=dict(sorted(categories.items())),
              configuration_evidence=bool(configured))
    return result
