"""Security routing and the security section handler (Tasks 6.3-6.4).

`classify_drift` (deterministic, no LLM) routes the changes that are relevant to
security analysis into `AiState.security_targets`. It never re-classifies drift:
it reads only the report's own deterministic fields.

    rated      deterministic severity HIGH or CRITICAL. Every security rule of
               drift_engine.severity (NSG rules, Key Vault, storage exposure,
               TLS/HTTPS/shared key, ...) and the sensitive-value rule rate at
               least HIGH; tags and descriptions are LOW.
    redacted   a value Terraform marks sensitive changed (it cannot be read).
    unrated    MEDIUM with no rule: no severity rule covers the change, so its
               impact is unknown (this includes uncovered attributes of
               security-sensitive types, whose deletion also raises the
               resource floor). Unknown impact is examined, never ignored.

LOW (tags, description) and INFO (proven noise) changes are not routed.

The security section of the single LLM call (`ai_engine.nodes.analyze_drift`)
is validated here:

- `AiSecurityOutput` is strict (no extra fields); `parse_model_output` also
  accepts it as a standalone reply (one ```json fence tolerated);
- every finding must cite (address, path) pairs that were sent for the security
  section, else it is rejected as `unsupported_citation`; free text breaking a
  deterministic guard is rejected (`unsupported_cost_claim`,
  `unsupported_attribution`, `remediation_not_allowed`);
- every finding is `basis: "inference"`; the authoritative rating is the
  deterministic severity of the cited changes (`deterministic_severity`). The
  model's `ai_assessed_impact` is kept next to it, flagged when lower, and never
  replaces it.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError

from ai_engine.evidence import cited_keys, evidence_refs, severity_rank
from ai_engine.nodes.common import CitedPath, Strict, free_text_violation, strict_json_loads
from drift_engine.logs import log_event

logger = logging.getLogger(__name__)

SECTION = "security"
ROUTED_LEVELS = ("CRITICAL", "HIGH")

# --------------------------------------------------------------------------- routing (deterministic)


def _route_reason(change: Mapping[str, Any]) -> str | None:
    severity = change["severity"]
    if severity["level"] in ROUTED_LEVELS:
        rules = ", ".join(severity["rules"]) or "resource floor"
        return f"rated {severity['level']} ({rules})"
    if change["redacted"]:
        return "redacted sensitive value"
    if severity["level"] == "MEDIUM" and not severity["rules"]:
        return "unrated: no severity rule covers this change (impact unknown)"
    return None


def classify_drift(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph node: deterministic security-relevant routing into `security_targets`."""
    parsed = state["parsed_drift"]
    routed: list[dict[str, Any]] = []
    excluded: dict[str, int] = {}
    for resource in parsed["resources"]:
        for change in resource["attribute_changes"]:
            reason = _route_reason(change)
            if reason is None:
                level = change["severity"]["level"]
                excluded[level] = excluded.get(level, 0) + 1
                continue
            routed.append({"address": resource["address"], "path": list(change["path"]),
                           "severity": change["severity"]["level"], "section": SECTION, "reason": reason})
    targets = {
        "changes": routed,
        "addresses": sorted({r["address"] for r in routed}),
        "excluded_by_severity": dict(sorted(excluded.items())),
    }
    log_event(logger, logging.INFO, "security_routed", "security-relevant changes routed",
              routed=len(routed), resources=len(targets["addresses"]), excluded=targets["excluded_by_severity"])
    return {"security_targets": targets}


# --------------------------------------------------------------------------- AI output schema

Impact = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
Exposure = Literal["network_exposure", "public_access", "encryption", "identity_access", "secret_change",
                   "data_protection", "other"]
class AiSecurityFinding(Strict):
    address: Annotated[str, Field(min_length=1, max_length=512)]
    cited_paths: Annotated[list[CitedPath], Field(min_length=1, max_length=20)]
    exposure: Exposure
    ai_assessed_impact: Impact
    explanation: Annotated[str, Field(min_length=1, max_length=1500)]
    basis: Literal["inference"]


class AiSecurityOutput(Strict):
    findings: Annotated[list[AiSecurityFinding], Field(max_length=50)]
    summary: Annotated[str, Field(max_length=2000)]


class InvalidModelOutput(ValueError):
    """The model reply is not a JSON object matching AiSecurityOutput."""


_FENCE = re.compile(r"\A```(?:json)?[ \t]*\n(?P<body>.*)\n```\Z", re.DOTALL)


def parse_model_output(text: str) -> AiSecurityOutput:
    body = text.strip()
    fenced = _FENCE.match(body)
    if fenced:
        body = fenced.group("body").strip()
    try:
        strict_json_loads(body)  # rejects duplicate keys before schema validation
    except ValueError:
        raise InvalidModelOutput("reply is not strict JSON (malformed, duplicate key or NaN)") from None
    try:
        return AiSecurityOutput.model_validate_json(body)
    except ValidationError as exc:
        kinds = sorted({error["type"] for error in exc.errors()})
        raise InvalidModelOutput(f"reply does not match the finding schema ({', '.join(kinds)})") from None


def validate_findings(output: AiSecurityOutput, evidence: Mapping[str, Any]) -> tuple[list[dict], list[dict]]:
    """Keep findings whose every citation was sent for the security section; attach the authoritative severity."""
    known = cited_keys(evidence, SECTION)
    refs = evidence_refs(evidence)
    accepted: list[dict] = []
    rejected: list[dict] = []
    for index, finding in enumerate(output.findings):
        keys = [(finding.address, tuple(path)) for path in finding.cited_paths]
        if not all(key in known for key in keys):
            rejected.append({"index": index, "reason": "unsupported_citation"})
            continue
        violation = free_text_violation(finding.explanation, refs)  # all free-text guards
        if violation:
            rejected.append({"index": index, "reason": violation})
            continue
        deterministic = max((known[key] for key in keys), key=severity_rank)
        accepted.append({
            "address": finding.address,
            "cited_paths": [list(path) for path in finding.cited_paths],
            "exposure": finding.exposure,
            "deterministic_severity": deterministic,  # authoritative (drift_engine.severity)
            "ai_assessed_impact": finding.ai_assessed_impact,  # inference, never replaces the above
            "ai_impact_below_deterministic": severity_rank(finding.ai_assessed_impact) < severity_rank(deterministic),
            "explanation": finding.explanation,
            "basis": "inference",
        })
    return accepted, rejected
