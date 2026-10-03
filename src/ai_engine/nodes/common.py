"""Shared pieces of the LLM output sections (Tasks 6.3-6.4): strict base model,
cited-path type, and the deterministic guard against invented cost claims."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


PathSegment = Annotated[str, Field(min_length=1, max_length=256)]
CitedPath = Annotated[list[PathSegment], Field(min_length=1, max_length=32)]


_COST_CLAIM = re.compile(
    r"[$€£¥₹]"
    r"|\b(?:USD|EUR|GBP|INR|JPY|AUD|CAD|CHF|CNY)\b"
    r"|\b(?:dollars?|euros?|rupees?|cents?)\b"
    r"|\d[\d,.]*\s*(?:k\b|thousand|million)?\s*(?:/|per|a|an|each)\s*(?:month|mo|hour|hr|year|yr|day|week)\b"
    r"|\b(?:monthly|hourly|annual|yearly)\s+(?:cost|price|bill|charge|spend)\w*\s+(?:of|is|would be|=)\s*\d"
    r"|\b(?:cost|price|bill|charge|spend|sav(?:e|es|ed|ing|ings))\w*\s*(?:of|by|about|around|roughly|to|is|=|:)?\s*"
    r"(?:about|around|roughly|approximately|~)?\s*\d"
    r"|\d+(?:\.\d+)?\s*%\s*(?:cheaper|more expensive|saving|savings|increase|decrease|reduction|higher|lower)",
    re.IGNORECASE,
)


def contains_cost_claim(text: str | None) -> bool:
    """True when free text states an amount, price, rate, currency or numeric saving."""
    return bool(text) and _COST_CLAIM.search(text) is not None


# Attribution guard (Task 6.5): who made a change is unknown until Phase 7 Activity
# Log evidence. Free text that names or asserts an actor is rejected; possible
# channels are given only through the structured `possible_channels` field.
_ACTORS = (r"(?:user|users|admin|admins|administrator|administrators|operator|engineer|engineers|developer|"
           r"developers|someone|somebody|person|people|colleague|employee|team\s+member|owner|"
           r"service\s+principal|managed\s+identity|contractor|attacker|hacker)")
_CHANGE_VERBS = (r"(?:changed|modified|deleted|edited|updated|created|removed|disabled|enabled|added|made|altered|"
                 r"opened|set|reconfigured|tampered|rotated|scaled)")
_ATTRIBUTION_CLAIM = re.compile(
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"  # email / UPN
    r"|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"  # object / client id
    rf"|\b{_CHANGE_VERBS}\s+(?:manually\s+|directly\s+)?by\s+(?!terraform\b|the\s+(?:plan|configuration|provider)\b)"
    rf"|\b{_ACTORS}\b(?:\s+\w+){{0,3}}?\s+(?:has\s+|had\s+|have\s+|probably\s+|likely\s+|must\s+have\s+)?"
    rf"{_CHANGE_VERBS}\b",
    re.IGNORECASE,
)

# Remediation guard (Task 6.5): fix instructions belong to Task 6.6. Describing what
# Terraform's plan would do ("apply would revert it") is allowed; telling the reader
# what to do is not.
_REMEDIATION_CLAIM = re.compile(
    r"\b(?:run|execute|use|perform|do)\s+`?terraform\s+(?:apply|import|state|plan|taint|refresh|destroy)\b"
    r"|\bterraform\s+(?:import|state\s+(?:rm|mv)|taint|untaint)\b"
    r"|\b(?:you|we|they|teams?|operators?)\s+(?:should|must|need\s+to|ought\s+to|have\s+to)\b"
    r"|\b(?:we|i)\s+(?:recommend|suggest|advise|propose)\b"
    r"|\b(?:recommended|suggested)\s+(?:fix|action|remediation|step|change)s?\b"
    r"|\bto\s+(?:fix|remediate|resolve|correct)\s+(?:this|it|the)\b"
    r"|\b(?:please|consider)\s+(?:reverting|revert|re-?apply|updating|update|changing|change|setting|set|removing|"
    r"remove|adding|add|importing|import|running|run)\b",
    re.IGNORECASE,
)


def contains_attribution_claim(text: str | None) -> bool:
    """True when free text names or asserts who made a change."""
    return bool(text) and _ATTRIBUTION_CLAIM.search(text) is not None


def contains_remediation_claim(text: str | None) -> bool:
    """True when free text instructs a fix (remediation is Task 6.6)."""
    return bool(text) and _REMEDIATION_CLAIM.search(text) is not None


def free_text_violation(text: str | None) -> str | None:
    """The first deterministic guard that `text` breaks, as a rejection reason, or None."""
    if contains_cost_claim(text):
        return "unsupported_cost_claim"
    if contains_attribution_claim(text):
        return "unsupported_attribution"
    if contains_remediation_claim(text):
        return "remediation_not_allowed"
    return None
