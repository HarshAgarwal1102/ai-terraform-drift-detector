"""Shared pieces of the LLM output sections (Tasks 6.3-6.7): strict base model,
cited-path type, and the deterministic free-text guards.

Guards (cost claims, attribution, remediation) run on every finding explanation
and summary. Task 6.7 hardened them against obfuscation:

1. **Suspicious input is decided on the original text**, before anything is
   normalized: Unicode format characters (category `Cf`: zero-width, bidi
   controls, ...) and words mixing Latin with a lookalike script (Cyrillic,
   Greek, fullwidth, mathematical, ...) are rejected as `suspicious_text`.
   Normalization never hides that evidence.
2. Each guard then matches the **original** text and a **separately
   normalized** copy (HTML entities unescaped, NFKC, format characters and
   combining marks removed, lookalike letters folded, `[at]` / `[dot]` folded,
   spaced-out letters collapsed). Matching both means normalization can only add
   detections, never remove one; the stored text is never altered.

Task 9B.4 adds three guards for the investigation (`free_text_violation(text, refs)`):
identity-like strings (the public leak-scan kinds; an IP address or URL only when quoted
from the Terraform evidence sent), verdict-upgrade wording (causation, proof, certainty, an
operation that "changed" a value), and references: any timestamp, Azure operation name or
`op-<n>` / `auto-<n>` absent from the evidence sent (`EvidenceRefs`) is rejected.

The broadened patterns are conservative: a rejected finding is counted and
dropped, while deterministic state is unaffected. Known tradeoffs (e.g. a
sentence starting with "Set" is read as an instruction; a plain person's name
doing something cannot be recognized without NER) are asserted in
tests/corpora/guards.json.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from drift_engine.investigation_public import leak_findings  # the only investigation module ai_engine may import


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


PathSegment = Annotated[str, Field(min_length=1, max_length=256)]
CitedPath = Annotated[list[PathSegment], Field(min_length=1, max_length=32)]


# --------------------------------------------------------------------------- suspicious input (original text)

# Scripts with letters that look like Latin letters; mixing them with Latin inside one word is an obfuscation signal.
_LOOKALIKE_SCRIPTS = frozenset({"CYRILLIC", "GREEK", "ARMENIAN", "CHEROKEE", "COPTIC", "FULLWIDTH", "MATHEMATICAL",
                                "HALFWIDTH", "CIRCLED", "PARENTHESIZED", "SQUARED", "NEGATIVE"})


def _script(ch: str) -> str:
    return unicodedata.name(ch, "UNKNOWN").split(" ", 1)[0]


def is_suspicious_text(text: str | None) -> bool:
    """True when the original text has format characters or a word mixing Latin with a lookalike script."""
    if not text:
        return False
    if any(unicodedata.category(ch) == "Cf" for ch in text):
        return True
    for word in re.findall(r"\w+", text):
        scripts = {_script(ch) for ch in word if ch.isalpha()}
        if "LATIN" in scripts and scripts & _LOOKALIKE_SCRIPTS:
            return True
    return False


# --------------------------------------------------------------------------- normalization (matching copy only)

_CONFUSABLES = str.maketrans({
    # Cyrillic
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d",
    "ӏ": "l", "һ": "h", "к": "k", "м": "m", "н": "h", "т": "t", "в": "b", "ԛ": "q", "ԝ": "w",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X",
    "У": "Y", "І": "I", "Ј": "J", "Ѕ": "S",
    # Greek
    "α": "a", "ο": "o", "ρ": "p", "ν": "v", "ι": "i", "κ": "k", "τ": "t", "υ": "u", "ε": "e", "χ": "x",
    "Α": "A", "Β": "B", "Ε": "E", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T",
    "Χ": "X", "Υ": "Y", "Ζ": "Z",
    # dashes
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
})
_OBFUSCATED_AT = re.compile(r"\s*[\[\(\{<]\s*at\s*[\]\)\}>]\s*", re.IGNORECASE)
_OBFUSCATED_DOT = re.compile(r"\s*[\[\(\{<]\s*dot\s*[\]\)\}>]\s*", re.IGNORECASE)
_SPACED_LETTERS = re.compile(r"(?<![^\W\d_])(?:[^\W\d_][ .\-_*·]){1,}[^\W\d_](?![^\W\d_])")


def normalize_for_guards(text: str) -> str:
    """A matching copy of `text`: decoded, folded and de-obfuscated. Never stored or shown."""
    out = text
    for _ in range(3):  # nested entities such as "&amp;#32;"
        decoded = html.unescape(out)
        if decoded == out:
            break
        out = decoded
    out = unicodedata.normalize("NFKC", out)
    out = "".join(ch for ch in out if unicodedata.category(ch) not in ("Cf", "Mn"))
    out = out.translate(_CONFUSABLES)
    out = _OBFUSCATED_AT.sub("@", out)
    out = _OBFUSCATED_DOT.sub(".", out)
    out = _SPACED_LETTERS.sub(lambda m: re.sub(r"[ .\-_*·]", "", m.group(0)), out)
    return re.sub(r"\s+", " ", out).strip()


def _matches(pattern: re.Pattern, extra: re.Pattern, text: str | None) -> bool:
    if not text:
        return False
    normalized = normalize_for_guards(text)
    return any(p.search(t) is not None for p in (pattern, extra) for t in (text, normalized))


# --------------------------------------------------------------------------- cost claims (Task 6.4)

# Discrete count nouns: "saves 3 rules" is not a money claim (targeted false-positive fix, Task 6.7).
_COUNT_NOUNS = (r"(?:rules?|copies|copy|regions?|zones?|nodes?|instances?|resources?|changes?|attributes?|steps?|"
                r"entries|entry|items?|records?|keys?|tags?|ports?|hosts?|vms?|disks?|files?|lines?|requests?|"
                r"replicas?|subnets?|addresses)")
_COST_CLAIM = re.compile(
    r"[$€£¥₹]"
    r"|\b(?:USD|EUR|GBP|INR|JPY|AUD|CAD|CHF|CNY)\b"
    r"|\b(?:dollars?|euros?|rupees?|cents?)\b"
    r"|\d[\d,.]*\s*(?:k\b|thousand|million)?\s*(?:/|per|a|an|each)\s*(?:month|mo|hour|hr|year|yr|day|week)\b"
    r"|\b(?:monthly|hourly|annual|yearly)\s+(?:cost|price|bill|charge|spend)\w*\s+(?:of|is|would be|=)\s*\d"
    r"|\b(?:cost|price|bill|charge|spend|sav(?:ing|ings))\w*\s*(?:of|by|about|around|roughly|to|is|=|:)?\s*"
    r"(?:about|around|roughly|approximately|~)?\s*\d"
    rf"|\bsav(?:e|es|ed)\b\s*(?:of|by|about|around|roughly|to|is|=|:)?\s*(?:about|around|roughly|approximately|~)?"
    rf"\s*\d[\d,.]*(?!\s*{_COUNT_NOUNS}\b)"
    r"|\d+(?:\.\d+)?\s*%\s*(?:cheaper|more expensive|saving|savings|increase|decrease|reduction|higher|lower)",
    re.IGNORECASE,
)
_PRICE_WORDS = r"(?:price|prices|pricing|cost|costs|bill|bills|billing|spend|spending|charges?|fees?|invoice)"
_COST_CLAIM_EXTRA = re.compile(
    r"\b(?:bucks|quid)\b"
    rf"|\b(?:twice|double[sd]?|triple[sd]?|quadruple[sd]?|half|halve[sd]?|\d+(?:\.\d+)?\s*(?:x|×|times))\b"
    rf"[^.]{{0,30}}\b{_PRICE_WORDS}\b"
    rf"|\b{_PRICE_WORDS}\b[^.]{{0,20}}\b(?:twice|double[sd]?|triple[sd]?|halve[sd]?|\d+(?:\.\d+)?\s*(?:x|×|times))\b",
    re.IGNORECASE,
)


def contains_cost_claim(text: str | None) -> bool:
    """True when free text states an amount, price, rate, currency or numeric saving."""
    return _matches(_COST_CLAIM, _COST_CLAIM_EXTRA, text)


# --------------------------------------------------------------------------- attribution (Task 6.5)

# Who made a change is unknown until Phase 7 Activity Log evidence. Free text that names or asserts an actor is
# rejected; possible channels are given only through the structured `possible_channels` field.
_ACTORS = (r"(?:user|users|admin|admins|administrator|administrators|operator|engineer|engineers|developer|"
           r"developers|someone|somebody|person|people|colleague|employee|team\s+member|owner|"
           r"service\s+principal|managed\s+identity|contractor|attacker|hacker)")
_CHANGE_VERBS = (r"(?:changed|modified|deleted|edited|updated|created|removed|disabled|enabled|added|made|altered|"
                 r"opened|set|reconfigured|tampered|rotated|scaled)")
# A passive auxiliary right before the verb makes the noun the changed object, not the actor ("a managed identity
# was added"): targeted false-positive fix, Task 6.7.
_FILLER = r"(?:\s+(?!(?:was|were|is|are|be|been|being|get|got|gets)\b){word}){{0,{n}}}?"
_ATTRIBUTION_CLAIM = re.compile(
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"  # email / UPN
    r"|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"  # object / client id
    rf"|\b{_CHANGE_VERBS}\s+(?:manually\s+|directly\s+)?by\s+(?!terraform\b|the\s+(?:plan|configuration|provider)\b)"
    rf"|\b{_ACTORS}\b{_FILLER.format(word=r'\w+', n=3)}\s+"
    r"(?:has\s+|had\s+|have\s+|probably\s+|likely\s+|must\s+have\s+)?"
    rf"{_CHANGE_VERBS}\b",
    re.IGNORECASE,
)
_MORE_ACTORS = (r"(?:team|ops|operations|staff|sre|devops|on-call|intern|maintainer|individual|human|insider)")
_MORE_VERBS = (r"(?:flipped|toggled|switched|turned|bumped|tweaked|reverted|rolled|did|performed|applied|deployed|"
               r"pushed|ran|executed|triggered|initiated|caused|edited|configured)")
_SEP = r"[\s\-_:]+"
_ATTRIBUTION_EXTRA = re.compile(
    rf"\b(?:{_CHANGE_VERBS[3:-1]}|{_MORE_VERBS[3:-1]}){_SEP}(?:manually{_SEP}|directly{_SEP})?by{_SEP}"
    r"(?!terraform\b|the\s+(?:plan|configuration|provider)\b)"
    rf"|\b(?:{_ACTORS[3:-1]}|{_MORE_ACTORS[3:-1]})\b"
    rf"{_FILLER.format(word=r'\S+', n=5)}\s+"
    r"(?:has\s+|had\s+|have\s+|probably\s+|likely\s+|must\s+have\s+)?"
    rf"(?:{_CHANGE_VERBS[3:-1]}|{_MORE_VERBS[3:-1]})\b"
    r"|\b(?:actor|culprit|perpetrator|initiator|author|caller|changer)\s+(?:was|is|were|appears\s+to\s+be|seems\s+to\s+be)"
    r"\s+(?!unknown\b|not\b|undetermined\b|unidentified\b|unconfirmed\b)"
    r"|\b(?:per|according\s+to|based\s+on)\s+the\s+(?:azure\s+)?activity\s+logs?\b"
    r"|\bactivity\s+logs?\s+(?:shows?|indicates?|records?|says|confirms?|reveals?|proves?)\b",
    re.IGNORECASE,
)


def contains_attribution_claim(text: str | None) -> bool:
    """True when free text names or asserts who made a change."""
    return _matches(_ATTRIBUTION_CLAIM, _ATTRIBUTION_EXTRA, text)


# --------------------------------------------------------------------------- remediation (Task 6.5)

# Fix instructions belong to the deterministic remediation options (Task 6.6). Describing what Terraform's plan would
# do ("applying the plan would revert it") is allowed; telling the reader what to do, or writing a command, is not.
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
_IMPERATIVES = (r"(?:revert|restore|reset|set|delete|remove|re-?apply|disable|enable|import|run|re-?run|execute|apply|"
                r"rotate|roll\s+back|rollback|recreate|redeploy|fix|patch|modify|add|tighten|undo|reconfigure|"
                r"replace|sync|align)")
_DESCRIPTIVE_AFTER = r"(?:would|will|could|can|may|might|is|was|were|has|have|by|of|shows|proposes|reverts|recreates)"
_REMEDIATION_EXTRA = re.compile(
    # Terraform CLI: always-commands, commands with flags/plan files, or written as a command (backtick / prompt / ":")
    r"\bterraform\s+(?:destroy|import|taint|untaint|force-unlock|workspace\s+(?:new|delete|select))\b"
    r"|\bterraform\s+state\s+(?:rm|mv|push|pull|replace-provider|list|show)\b"
    r"|\bterraform\s+(?:apply|plan|refresh|init)\s+(?:-{1,2}[a-z]|\S+\.tfplan\b)"
    rf"|(?:^|`|[:;>$#]\s*)terraform\s+(?:apply|plan|refresh|init)\b(?!\s+{_DESCRIPTIVE_AFTER}\b)"
    # Azure CLI / PowerShell
    r"|\baz\s+(?:account|group|storage|network|vm|keyvault|resource|role|webapp|appservice|monitor|policy|login|"
    r"deployment|sql|aks|acr|ad|identity|lock|tag|rest|functionapp|cosmosdb)\b"
    r"|\b(?:set|new|remove|update|add|get|invoke)-az[a-z]+"
    # sentence-initial imperatives ("Revert the tag ...")
    rf"|(?:^|[.!?;]\s+|\n\s*)(?:then\s+|now\s+|first\s+|simply\s+|just\s+)?{_IMPERATIVES}\b(?!\s+{_DESCRIPTIVE_AFTER}\b)"
    rf"|\b(?:set|change|revert|switch|move|put|turn|roll)\b[^.]{{0,40}}\bback\b"
    # advice phrasing
    r"|\bthe\s+(?:fix|remedy|remediation|solution|workaround)\s+(?:is|would\s+be)\b"
    r"|\bbest\s+practice\b|\b(?:is|would\s+be)\s+advisable\b|\bit\s+is\s+recommended\b|\brecommended\s+to\b"
    r"|\b(?:should|must|needs?\s+to|ought\s+to)\s+be\s+(?:reverted|restored|reset|set|removed|deleted|re-?applied|"
    r"updated|changed|fixed|disabled|enabled|rolled\s+back|imported|corrected|tightened|locked\s+down|closed|"
    r"replaced|rotated)\b",
    re.IGNORECASE,
)


def contains_remediation_claim(text: str | None) -> bool:
    """True when free text instructs a fix or writes a command (remediation is deterministic, Task 6.6)."""
    return _matches(_REMEDIATION_CLAIM, _REMEDIATION_EXTRA, text)


# --------------------------------------------------------------------------- investigation claims (Task 9B.4)

# The deterministic investigation (drift_engine.investigation_public) is authoritative for the verdict, property
# link, actor attribution, operations and timestamps. Free text may explain them but never claim more: no causal or
# proof wording, no identity-like strings, and no timestamp, Azure operation name or `op-<n>` / `auto-<n>` reference
# that the model was not given.
_UPGRADE_VERBS = r"(?:changed|set|modified|removed|added|updated|altered|wrote|deleted|created|introduced|edited)"
_VERDICT_UPGRADE = re.compile(
    r"\bcaus(?:e|es|ed|ing)\b"
    r"|\bresponsible\s+for\b"
    r"|\b(?:prov(?:e|es|ed|en|ing)|proof)\b"
    r"|\bconfirm(?:s|ed|ing|ation)?\b"
    r"|\b(?:definite(?:ly)?|definitive(?:ly)?|conclusive(?:ly)?|certain(?:ly)?|undoubtedly|unquestionably|"
    r"indisputabl[ey]|unambiguous(?:ly)?)\b"
    r"|\bwithout\s+(?:a\s+|any\s+)?doubt\b"
    r"|\b(?:is|was)\s+(?:the|its)\s+(?:author|origin|source|reason)\s+(?:of|for)\b"
    r"|\b(?:led|leads|lead)\s+to\s+(?:the|this)\s+drift\b"
    r"|\bresult(?:ed|s)?\s+in\s+(?:the|this)\s+drift\b"
    rf"|\b(?:op|auto)-\d+\b(?:\s+\S+){{0,2}}?\s+(?:has\s+|had\s+)?{_UPGRADE_VERBS}\b"
    rf"|\b(?:the|this|that)\s+(?:recorded\s+|decisive\s+|azure\s+|tags?\s+)?(?:operation|write|request)\s+"
    rf"(?:has\s+|had\s+)?{_UPGRADE_VERBS}\b",
    re.IGNORECASE,
)


def contains_verdict_upgrade(text: str | None) -> bool:
    """True when free text claims more than the deterministic verdict (causation, proof, certainty, an operation
    that changed a value)."""
    if not text:
        return False
    return any(_VERDICT_UPGRADE.search(t) for t in (text, normalize_for_guards(text)))


# Kinds of the public leak scan that never belong in AI text. IP addresses and URLs are allowed only when they
# appear verbatim in the Terraform evidence sent (e.g. an NSG source prefix); see `identity_like_violation`.
_ALWAYS_IDENTITY = ("at_sign", "guid", "providers_path", "subscriptions_path")
_IP_TOKEN = re.compile(r"[0-9A-Fa-f:.]+")
_URL_TOKEN = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*://|\bwww\.)\S*", re.IGNORECASE)


def _identity_kinds(text: str) -> set[str]:
    return {finding.rsplit(": ", 1)[1] for finding in leak_findings(text)}


@dataclass(frozen=True)
class EvidenceRefs:
    """What AI text may refer to: tokens taken from the evidence actually sent to the model."""

    timestamps: frozenset[str] = frozenset()  # normalized forms, see timestamp_forms
    operations: frozenset[str] = frozenset()  # case-folded Azure operation names
    refs: frozenset[str] = frozenset()  # lower-case `op-<n>` / `auto-<n>`
    evidence_text: str = ""  # the rendered Terraform evidence (for IP / URL tokens quoted from it)


NO_REFS = EvidenceRefs()


def timestamp_forms(timestamp: str) -> set[str]:
    """Every accepted spelling of a public timestamp `YYYY-MM-DDTHH:MM:SS.ffffffZ` (normalized as in
    `_normalize_timestamp`): the date, the date with minutes / seconds / any fraction prefix, and the same
    times without the date."""
    date, _, clock = timestamp.rstrip("Z").partition("T")
    forms = {date}
    if not clock:
        return forms
    hm, rest = clock[:5], clock[5:]
    seconds, _, fraction = rest.lstrip(":").partition(".")
    times = {hm}
    if seconds:
        times.add(f"{hm}:{seconds}")
        times.update(f"{hm}:{seconds}.{fraction[:n]}" for n in range(1, len(fraction) + 1))
    forms.update(times)
    forms.update(f"{date}T{t}" for t in times)
    return forms


_TIMESTAMP_TOKEN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?(?:\s*Z\b|\s*UTC\b)?"
    r"|\b\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:\s*Z\b|\s*UTC\b)?(?![\d:])"
)
# An Azure operation name (Namespace.Provider/type/.../action); not a URL host or path (handled as a URL).
_OPERATION_TOKEN = re.compile(r"(?<![\w./:@-])(?!www\.)[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+/[A-Za-z0-9._/-]*[A-Za-z0-9]")
_REF_TOKEN = re.compile(r"\b(?:op|auto)-\d+\b", re.IGNORECASE)


def _normalize_timestamp(token: str) -> str:
    token = re.sub(r"\s*(?:Z|UTC)$", "", token.strip())
    return re.sub(r"(\d{4}-\d{2}-\d{2}) ", r"\1T", token)


def reference_violation(text: str | None, refs: EvidenceRefs = NO_REFS) -> str | None:
    """`unsupported_timestamp` / `unsupported_operation` when free text cites a time, an Azure operation name or an
    operation reference that is not in the evidence sent; else None."""
    if not text:
        return None
    for variant in (text, normalize_for_guards(text)):
        if any(_normalize_timestamp(t) not in refs.timestamps for t in _TIMESTAMP_TOKEN.findall(variant)):
            return "unsupported_timestamp"
        if any(op.casefold() not in refs.operations for op in _OPERATION_TOKEN.findall(variant)):
            return "unsupported_operation"
        if any(ref.lower() not in refs.refs for ref in _REF_TOKEN.findall(variant)):
            return "unsupported_operation"
    return None


def identity_like_violation(text: str | None, refs: EvidenceRefs = NO_REFS) -> bool:
    """True when free text holds an identity-like string (public leak-scan kinds). An IP address or URL is allowed
    only when it is quoted verbatim from the Terraform evidence sent."""
    if not text:
        return False
    for variant in (text, normalize_for_guards(text)):
        kinds = _identity_kinds(variant)
        if kinds & set(_ALWAYS_IDENTITY):
            return True
        if "ip_address" in kinds:
            for token in _IP_TOKEN.findall(variant):
                candidate = token.strip(".")
                if _identity_kinds(candidate) and candidate not in refs.evidence_text:
                    return True
        if "url" in kinds and any(url.rstrip(".,;)") not in refs.evidence_text for url in _URL_TOKEN.findall(variant)):
            return True
    return False


def free_text_violation(text: str | None, refs: EvidenceRefs = NO_REFS) -> str | None:
    """The first deterministic guard that `text` breaks, as a rejection reason, or None.

    `refs` are the tokens of the evidence sent to the model (Task 9B.4); without them no timestamp, Azure
    operation name or operation reference is supported."""
    if is_suspicious_text(text):  # decided on the original text, before any normalization
        return "suspicious_text"
    if contains_cost_claim(text):
        return "unsupported_cost_claim"
    if contains_attribution_claim(text):
        return "unsupported_attribution"
    if contains_remediation_claim(text):
        return "remediation_not_allowed"
    if identity_like_violation(text, refs):
        return "identity_like_string"
    if contains_verdict_upgrade(text):
        return "verdict_upgrade"
    return reference_violation(text, refs)


# --------------------------------------------------------------------------- strict JSON for model replies (Task 6.7)


class DuplicateKeyError(ValueError):
    """A JSON object in a model reply repeats a key (json.loads would silently keep the last one)."""


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate key {key!r} in reply")
        out[key] = value
    return out


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-JSON constant {name}")


def strict_json_loads(text: str) -> object:
    """json.loads that rejects duplicate keys (at any depth) and NaN / Infinity."""
    return json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
