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
