#!/usr/bin/env python3
"""Deterministic drift issue creator (Task 8.1) and issue lifecycle (Task 8.3).

Creates or updates one GitHub Issue per drifted resource of a valid drifted
detection run, from that run's drift report artifact (drift_report.json) only,
and closes automation issues whose resource the run reports as present and no
longer drifted (Task 8.3).

Public-repository profile (PROJECT_PLAN.md Phase 8):
  * input is the public drift report only (Task 9B.4A: identifiers withheld; an
    internal report is rejected as report_invalid): no AI report, no Activity Log evidence or
    attribution, no caller identity and no origin line;
  * bodies are structure only: never real/state/desired values, HCL fragments or
    severity reasons; the paths are withheld (reduced body) unless the resource is
    INFO/LOW, not a security-sensitive type and has no redacted change;
  * subscription/tenant GUIDs and ARM IDs are masked; untrusted text (addresses,
    types, path segments) appears only inside code spans, after control, bidi,
    zero-width and format characters are stripped.

Publication is deterministic and idempotent. The first body line is a versioned
marker: SHA-256 fingerprint of (environment, address), SHA-256 content hash and
the run_id / plan.timestamp of the run that last changed the content. An open
issue is updated only when the new evidence is newer *and* the content differs;
older or equal evidence never updates (stale_evidence / conflicting_evidence when
the content differs). The guard relies on the workflow's concurrency group and on
the exact attempt binding run.run_id == github-<GITHUB_RUN_ID>-<GITHUB_RUN_ATTEMPT>.

Lifecycle (Task 8.3): a valid 'true' or 'false' run closes an open automation
issue only when its marker fingerprint equals fp(environment, address) for an
address present in this report with drift_action == null, and the run's
plan.timestamp is newer than the marker's. A 'false' run never creates or
updates. Closing is exactly PATCH {"state": "closed", "state_reason": "completed"}:
no body, title, label or comment, so human edits are never overwritten. A
recurrence gets a new issue (matching is open-issues-only); issues are never
reopened. Issues whose fingerprint matches no report address stay open
(resource_not_in_report warning). Per-issue anomalies (marker_invalid,
marker_version_unsupported, conflicting_evidence, stale_evidence) skip only that
issue and make the run exit 1.

Dry-run is the default (no network; rendered requests are written to --out-dir;
closures need the issue list, so a preview shows only create requests).
--publish is accepted only inside GitHub Actions. The GitHub client is the
standard library only: api.github.com, no redirects, GET/PATCH retried, an
issue-creating POST never retried. This script never creates labels, comments,
reopens or assigns issues and never imports ai_engine,
drift_engine.activity_logs or drift_engine.attribution.

Usage:
  github_automation.py --report drift_report.json --environment dev \
      --drift-detected true (--out-dir DIR | --publish) [--repository OWNER/NAME]

Exit status: 0 done (incl. skipped and unchanged), 1 a failure code was reported,
2 usage error, 70 internal error.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import dataclasses
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from typing import Any

try:
    from drift_engine.report_public import PublicDriftItem as DriftItem
    from drift_engine.report_public import PublicDriftReport as DriftReport
    from drift_engine.severity import SECURITY_SENSITIVE_TYPES, rank
except ImportError:  # running from a source tree without installation
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
    from drift_engine.report_public import PublicDriftItem as DriftItem
    from drift_engine.report_public import PublicDriftReport as DriftReport
    from drift_engine.severity import SECURITY_SENSITIVE_TYPES, rank

from pydantic import ValidationError

# --------------------------------------------------------------------------- constants

MARKER_VERSION = 1
RENDERER_VERSION = 1
LABEL = "drift-detected"
BOT_LOGIN = "github-actions[bot]"
BOT_TYPE = "Bot"
API_URL = "https://api.github.com"
SERVER_URL = "https://github.com"
API_VERSION = "2022-11-28"
USER_AGENT = "ai-terraform-drift-detector-issues"

MAX_WRITES_PER_RUN = 10      # creates + updates per run
MAX_PATHS = 50               # changed paths listed per issue
MAX_TITLE = 200
MAX_PAGES = 10               # issue listing pages (100 per page)
MAX_ATTEMPTS = 3             # GET/PATCH attempts
RETRY_AFTER_CAP = 60.0       # seconds
TIMEOUT = 30.0               # seconds per request
MAX_REPORT_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 10 * 1024 * 1024

FULL_LEVELS = frozenset({"INFO", "LOW"})
CLOSE_PAYLOAD = {"state": "closed", "state_reason": "completed"}  # never a body: closing must not overwrite edits
PATH_PLACEHOLDER = "<withheld>"

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_INTERNAL = 0, 1, 2, 70

# Fixed codes. Failures make the run exit 1; warnings and "skipped" do not.
FAILURE_CODES = frozenset({
    # input / binding
    "report_missing", "report_invalid", "report_failed", "report_inconsistent", "run_mismatch",
    "attempt_mismatch", "environment_invalid", "environment_mismatch", "publish_outside_actions",
    "repository_invalid", "api_url_invalid", "token_missing",
    # marker / evidence
    "marker_invalid", "marker_version_unsupported", "stale_evidence", "conflicting_evidence",
    # GitHub
    "label_missing", "auth_failed", "forbidden", "not_found", "gone", "validation_failed",
    "rate_limited", "server_error", "http_error", "timeout", "connection_failed", "invalid_response",
    "blocked_request", "pagination_limit", "cap_exceeded",
    # dry-run output
    "out_dir_not_empty", "out_dir_unwritable",
})
WARNING_CODES = frozenset({"duplicate_issues", "resource_not_in_report"})
SKIP_CODES = frozenset({"not_drift_detected"})

_ENV_RE = re.compile(r"^[a-z0-9-]{1,32}\Z")
_REPO_RE = re.compile(r"^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}\Z")
_RUN_ID_RE = re.compile(r"^github-([0-9]{1,20})-([0-9]{1,6})\Z")
_TIMESTAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_DIGITS_RE = re.compile(r"^[0-9]{1,20}\Z")
_GUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
_ARM_ID_RE = re.compile(r"/subscriptions/[^\s\"'`\]]*", re.IGNORECASE)
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}\Z")
_TITLE_CHAR_RE = re.compile(r"[^A-Za-z0-9_.\-\[\]\" ]")
_MARKER_PREFIX = "<!-- drift-issue "
_MARKER_RE = re.compile(
    r"^<!-- drift-issue v=(?P<v>[0-9]{1,4}) fp=(?P<fp>[0-9a-f]{64}) content=(?P<content>[0-9a-f]{64}) "
    r"run=(?P<run>github-[0-9]{1,20}-[0-9]{1,6}) plan=(?P<plan>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z) -->\Z"
)
_MARKER_VERSION_RE = re.compile(r"\bv=([0-9]{1,4})\b")
_MARKER_FP_RE = re.compile(r"\bfp=([0-9a-f]{64})\b")
_STRIP_CATEGORIES = frozenset({"Cc", "Cf", "Co", "Cs", "Cn", "Zl", "Zp"})


class AutomationError(Exception):
    """A fixed failure code; the message is the code only (never values, URLs or tokens)."""

    def __init__(self, code: str):
        assert code in FAILURE_CODES, code
        super().__init__(code)
        self.code = code


# --------------------------------------------------------------------------- input and gating

@dataclasses.dataclass(frozen=True)
class Evidence:
    environment: str
    run_id: str
    plan_timestamp: str
    resources: tuple[DriftItem, ...]  # issue set, in processing order
    resolved: tuple[str, ...] = ()    # addresses present in the report with drift_action == null (Task 8.3)


def validate_environment(environment: str) -> str:
    if not isinstance(environment, str) or not _ENV_RE.match(environment):
        raise AutomationError("environment_invalid")
    return environment


def load_report(data: bytes) -> DriftReport:
    if len(data) > MAX_REPORT_BYTES:
        raise AutomationError("report_invalid")
    try:
        return DriftReport.model_validate_json(data)
    except (ValidationError, ValueError):
        raise AutomationError("report_invalid") from None


def issue_set(report: DriftReport) -> tuple[DriftItem, ...]:
    """Resources with drift_action != null (the has_drift set), severity descending then address."""
    drifted = [r for r in report.resources if r.drift_action is not None]
    addresses = [r.address for r in drifted]
    if (not drifted or len(set(addresses)) != len(addresses)
            or report.summary is None or len(drifted) != report.summary.drifted_resources):
        raise AutomationError("report_inconsistent")
    return tuple(sorted(drifted, key=lambda r: (-rank(r.severity.level), r.address)))


def evidence_from_report(report: DriftReport, environment: str, drift_detected: bool = True) -> Evidence:
    """The gate on the report itself: succeeded, has_drift agrees with the workflow's
    drift_detected ('true' or 'false'), same environment, unique addresses."""
    if report.outcome != "succeeded":
        raise AutomationError("report_failed")
    if report.has_drift is not drift_detected:
        raise AutomationError("report_inconsistent")
    assert report.run is not None and report.plan is not None  # guaranteed by DriftReport for succeeded
    if report.run.environment != environment:
        raise AutomationError("environment_mismatch")
    run_id, plan_ts = report.run.run_id, report.plan.timestamp
    if not isinstance(run_id, str) or not _RUN_ID_RE.match(run_id):
        raise AutomationError("run_mismatch")  # only CI evidence (github-<run>-<attempt>) can be published or previewed
    if not isinstance(plan_ts, str) or not _TIMESTAMP_RE.match(plan_ts):
        raise AutomationError("report_inconsistent")
    addresses = [r.address for r in report.resources]
    if len(set(addresses)) != len(addresses):
        raise AutomationError("report_inconsistent")
    if drift_detected:
        drifted = issue_set(report)
    elif (report.summary is None or report.summary.drifted_resources != 0
            or any(r.drift_action is not None for r in report.resources)):
        raise AutomationError("report_inconsistent")
    else:
        drifted = ()
    resolved = tuple(sorted(r.address for r in report.resources if r.drift_action is None))
    return Evidence(environment, run_id, plan_ts, drifted, resolved)


def check_publish_binding(evidence: Evidence, env: Mapping[str, str]) -> str:
    """--publish preconditions; returns the repository. Exact attempt binding:
    run.run_id must equal github-<GITHUB_RUN_ID>-<GITHUB_RUN_ATTEMPT>."""
    if env.get("GITHUB_ACTIONS") != "true":
        raise AutomationError("publish_outside_actions")
    if env.get("GITHUB_API_URL", API_URL) != API_URL or env.get("GITHUB_SERVER_URL", SERVER_URL) != SERVER_URL:
        raise AutomationError("api_url_invalid")
    repository = env.get("GITHUB_REPOSITORY", "")
    if not _REPO_RE.match(repository):
        raise AutomationError("repository_invalid")
    run_id, attempt = env.get("GITHUB_RUN_ID", ""), env.get("GITHUB_RUN_ATTEMPT", "")
    if not _DIGITS_RE.match(run_id) or not _DIGITS_RE.match(attempt):
        raise AutomationError("run_mismatch")
    if evidence.run_id != f"github-{run_id}-{attempt}":
        match = _RUN_ID_RE.match(evidence.run_id)
        raise AutomationError("attempt_mismatch" if match and match.group(1) == run_id else "run_mismatch")
    if not env.get("GITHUB_TOKEN"):
        raise AutomationError("token_missing")
    return repository


# --------------------------------------------------------------------------- rendering

def strip_unsafe(text: str) -> str:
    """Drop control, format (bidi, zero-width), private-use, surrogate, unassigned and
    line/paragraph separator characters; collapse whitespace to single spaces."""
    spaced = "".join(" " if ch.isspace() else ch for ch in str(text))  # line breaks never join words
    kept = "".join(ch for ch in spaced if unicodedata.category(ch) not in _STRIP_CATEGORIES)
    return " ".join(kept.split())


def mask(text: str) -> str:
    """Mask ARM IDs (whole /subscriptions/... path) and then any remaining GUID."""
    return _GUID_RE.sub("<guid>", _ARM_ID_RE.sub("<arm-id>", text))


def clean(text: Any) -> str:
    return mask(strip_unsafe(str(text)))


def code(text: str) -> str:
    """Inline code span whose fence is longer than any backtick run inside (never interpreted)."""
    text = text or " "
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith(("`", " ")) or text.endswith(("`", " ")) else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def safe_segment(segment: str) -> str:
    cleaned = clean(segment)
    return cleaned if _SEGMENT_RE.match(cleaned) else PATH_PLACEHOLDER


def fingerprint(environment: str, address: str) -> str:
    return hashlib.sha256(f"drift-issue-fingerprint:v{MARKER_VERSION}\n{environment}\n{address}".encode()).hexdigest()


def render_title(environment: str, address: str, fp: str) -> str:
    safe_address = _TITLE_CHAR_RE.sub("_", clean(address))
    title = f"Drift detected: {safe_address} ({environment})"
    if len(title) > MAX_TITLE:
        title = f"{title[:MAX_TITLE - 13]}~{fp[:12]}"
    return title


def full_body_allowed(resource: DriftItem) -> bool:
    """Full structure-only body only for INFO/LOW, non-security-sensitive types and no redaction."""
    return (resource.severity.level in FULL_LEVELS
            and resource.type not in SECURITY_SENSITIVE_TYPES
            and not any(change.redacted or "redacted" in (change.state.status, change.real.status, change.desired.status)
                        for change in resource.attribute_changes))


def render_canonical(environment: str, resource: DriftItem) -> str:
    """The deterministic body content (no marker, no run-specific line)."""
    lines = [
        "## Terraform drift detected",
        "",
        "Opened by the drift detection workflow from the deterministic drift report. "
        "No attribute values, AI analysis, Activity Log data or remediation are published in this repository.",
        "",
        f"- Environment: {code(environment)}",
        f"- Resource: {code(clean(resource.address))}",
        f"- Type: {code(clean(resource.type))}",
        f"- Classification: {code(resource.classification)}",
        f"- Drift action: {code(str(resource.drift_action))}",
        f"- Severity: {code(resource.severity.level)}",
        f"- Ambiguous: {code(str(resource.ambiguous).lower())}",
        "",
    ]
    changes = sorted(resource.attribute_changes, key=lambda c: c.path)
    if full_body_allowed(resource):
        lines.append(f"### Changed paths ({len(changes)})")
        lines.append("")
        for change in changes[:MAX_PATHS]:
            path = ".".join(safe_segment(segment) for segment in change.path)
            attribute_class = change.class_ or "none"
            lines.append(f"- {code(path)}: class {code(attribute_class)}; state {code(change.state.status)}, "
                         f"real {code(change.real.status)}, desired {code(change.desired.status)}")
        if len(changes) > MAX_PATHS:
            lines.append(f"- …and {len(changes) - MAX_PATHS} more")
    else:
        lines += [
            "### Details withheld",
            "",
            f"{len(changes)} changed path(s). Paths are not published for security-sensitive, "
            "higher-severity or redacted drift; see the run's drift report artifact.",
        ]
    lines += ["", "---", f"Drift issue renderer v{RENDERER_VERSION}."]
    return "\n".join(lines)


def content_hash(title: str, canonical: str) -> str:
    return hashlib.sha256(f"renderer:v{RENDERER_VERSION}\n{title}\n{canonical}".encode()).hexdigest()


def marker_line(fp: str, content: str, run_id: str, plan_timestamp: str) -> str:
    return f"{_MARKER_PREFIX}v={MARKER_VERSION} fp={fp} content={content} run={run_id} plan={plan_timestamp} -->"


def run_url(repository: str | None, run_id: str) -> str | None:
    match = _RUN_ID_RE.match(run_id)
    if not repository or not _REPO_RE.match(repository) or not match:
        return None
    return f"{SERVER_URL}/{repository}/actions/runs/{match.group(1)}/attempts/{match.group(2)}"


@dataclasses.dataclass(frozen=True)
class Rendered:
    address: str
    fingerprint: str
    title: str
    content_hash: str
    body: str


def render_issue(evidence: Evidence, resource: DriftItem, repository: str | None) -> Rendered:
    fp = fingerprint(evidence.environment, resource.address)
    title = render_title(evidence.environment, resource.address, fp)
    canonical = render_canonical(evidence.environment, resource)
    digest = content_hash(title, canonical)
    url = run_url(repository, evidence.run_id)
    run_line = (f"Content last changed by detection run {code(evidence.run_id)} "
                f"(plan {code(evidence.plan_timestamp)})" + (f": {url}" if url else ""))
    body = "\n".join([marker_line(fp, digest, evidence.run_id, evidence.plan_timestamp), canonical, "", run_line, ""])
    return Rendered(resource.address, fp, title, digest, body)


# --------------------------------------------------------------------------- matching and decisions

@dataclasses.dataclass(frozen=True)
class Marker:
    version: int
    fingerprint: str
    content_hash: str
    run_id: str
    plan_timestamp: str


def marker_fingerprint(body: Any) -> tuple[str | None, str | None]:
    """(version, fingerprint) of a first-line drift marker, or (None, None) if the first line is not one."""
    if not isinstance(body, str):
        return None, None
    first = body.split("\n", 1)[0].rstrip("\r")
    if not first.startswith(_MARKER_PREFIX):
        return None, None
    version, fp = _MARKER_VERSION_RE.search(first), _MARKER_FP_RE.search(first)
    return (version.group(1) if version else None), (fp.group(1) if fp else None)


def parse_marker(body: str) -> Marker:
    first = body.split("\n", 1)[0].rstrip("\r")
    version, _ = marker_fingerprint(body)
    if version is not None and version != str(MARKER_VERSION):
        raise AutomationError("marker_version_unsupported")
    match = _MARKER_RE.match(first)
    if not match:
        raise AutomationError("marker_invalid")
    return Marker(int(match["v"]), match["fp"], match["content"], match["run"], match["plan"])


def is_automation_issue(item: Any) -> bool:
    """Open issue (not a PR) created by github-actions[bot] that carries the automation label."""
    if not isinstance(item, dict) or "pull_request" in item or item.get("state") != "open":
        return False
    user = item.get("user")
    if not isinstance(user, dict) or user.get("login") != BOT_LOGIN or user.get("type") != BOT_TYPE:
        return False
    labels = item.get("labels")
    if not isinstance(labels, list) or not any(isinstance(lb, dict) and lb.get("name") == LABEL for lb in labels):
        return False
    return isinstance(item.get("number"), int) and not isinstance(item.get("number"), bool)


def matching_issues(items: Iterable[Any], fp: str) -> list[dict]:
    found = [item for item in items if is_automation_issue(item) and marker_fingerprint(item.get("body"))[1] == fp]
    return sorted(found, key=lambda item: item["number"])


@dataclasses.dataclass(frozen=True)
class Decision:
    action: str            # create | update | unchanged | refused | close | skip
    number: int | None
    code: str | None       # failure/warning code, if any
    duplicates: bool = False


def decide(rendered: Rendered, evidence: Evidence, matches: list[dict]) -> Decision:
    """Last-change marker semantics (PROJECT_PLAN.md Task 8.1)."""
    if not matches:
        return Decision("create", None, None)
    try:
        markers = [parse_marker(item["body"]) for item in matches]
    except AutomationError as exc:  # any invalid/unsupported marker for this fingerprint fails closed
        return Decision("refused", matches[0]["number"], exc.code)
    target, marker = matches[0], markers[0]
    duplicates = len(matches) > 1
    same = marker.content_hash == rendered.content_hash
    if evidence.plan_timestamp > marker.plan_timestamp:   # fixed-width UTC "...Z": lexical order = time order
        if same:
            return Decision("unchanged", target["number"], None, duplicates)
        return Decision("update", target["number"], None, duplicates)
    if same:
        return Decision("unchanged", target["number"], None, duplicates)
    code_ = "conflicting_evidence" if evidence.plan_timestamp == marker.plan_timestamp else "stale_evidence"
    return Decision("refused", target["number"], code_, duplicates)


def plan_closures(evidence: Evidence, items: Iterable[Any]) -> list[Decision]:
    """Task 8.3 closure decisions, by issue number. Closable: an open automation issue
    whose fingerprint is fp(environment, address) for a present, non-drifted address
    and whose marker is valid and older than this run's evidence."""
    drifted = {fingerprint(evidence.environment, r.address) for r in evidence.resources}
    resolvable = {fingerprint(evidence.environment, address) for address in evidence.resolved}
    candidates = sorted((i for i in items if is_automation_issue(i)), key=lambda i: i["number"])
    fps = [marker_fingerprint(i.get("body"))[1] for i in candidates]
    counts = collections.Counter(fp for fp in fps if fp in resolvable)
    decisions = []
    for item, fp in zip(candidates, fps):
        number = item["number"]
        if fp is None or fp in drifted:   # not a drift issue, or handled by the 8.1 create/update path
            continue
        if fp not in resolvable:          # removed/moved resource or another environment: never closed
            decisions.append(Decision("skip", number, "resource_not_in_report"))
            continue
        duplicates = counts[fp] > 1
        try:
            marker = parse_marker(item["body"])
        except AutomationError as exc:
            decisions.append(Decision("refused", number, exc.code, duplicates))
            continue
        if marker.plan_timestamp < evidence.plan_timestamp:
            decisions.append(Decision("close", number, None, duplicates))
        elif marker.plan_timestamp == evidence.plan_timestamp:
            decisions.append(Decision("refused", number, "conflicting_evidence", duplicates))
        else:
            decisions.append(Decision("refused", number, "stale_evidence", duplicates))
    return decisions


# --------------------------------------------------------------------------- GitHub REST client

@dataclasses.dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    data: Any


class GitHubClient:
    """Standard-library GitHub REST client: api.github.com only, no redirects, fixed headers.

    GET and PATCH are retried (at most MAX_ATTEMPTS, Retry-After capped at
    RETRY_AFTER_CAP) on timeouts, connection errors, 429 and 5xx; an issue-creating
    POST is never retried. Errors surface as fixed codes only.
    """

    import urllib.error as _error
    import urllib.request as _request

    class _NoRedirect(_request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib hook
            return None  # a 3xx then surfaces as HTTPError -> blocked_request

    def __init__(self, token: str, repository: str, opener: Any = None, sleep: Callable[[float], None] = time.sleep):
        if not _REPO_RE.match(repository):
            raise AutomationError("repository_invalid")
        self._token = token
        self.repository = repository
        self._opener = opener or self._request.build_opener(self._NoRedirect())
        self._sleep = sleep

    def __repr__(self) -> str:
        return f"GitHubClient(repository={self.repository!r})"

    def _url_allowed(self, url: str) -> bool:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc != "api.github.com" or parts.fragment or parts.username:
            return False
        return parts.path == f"/repos/{self.repository}/issues" or bool(re.fullmatch(r"/repositories/[0-9]+/issues", parts.path))

    def request(self, method: str, path: str, payload: Any = None, *, url: str | None = None) -> Response:
        target = url if url is not None else API_URL + path
        if url is not None and not self._url_allowed(url):
            raise AutomationError("blocked_request")
        if not target.startswith(API_URL + "/"):
            raise AutomationError("blocked_request")
        body = None if payload is None else json.dumps(payload, sort_keys=True).encode()
        attempts = 1 if method == "POST" else MAX_ATTEMPTS
        for attempt in range(1, attempts + 1):
            req = self._request.Request(target, data=body, method=method)
            req.add_header("Accept", "application/vnd.github+json")
            req.add_header("Authorization", f"Bearer {self._token}")
            req.add_header("X-GitHub-Api-Version", API_VERSION)
            req.add_header("User-Agent", USER_AGENT)
            if body is not None:
                req.add_header("Content-Type", "application/json")
            try:
                with self._opener.open(req, timeout=TIMEOUT) as resp:
                    raw = resp.read(MAX_RESPONSE_BYTES + 1)
                    status, headers = resp.status, {k.lower(): v for k, v in resp.headers.items()}
            except self._error.HTTPError as exc:
                status, headers = exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}
                exc.close()
                code_ = self._status_code(status, headers)
                if code_ in ("rate_limited_retry", "server_error") and attempt < attempts:
                    self._sleep(self._delay(headers, attempt))
                    continue
                raise AutomationError("rate_limited" if code_ == "rate_limited_retry" else code_) from None
            except (TimeoutError, self._error.URLError, OSError) as exc:
                timed_out = isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)
                if attempt < attempts:
                    self._sleep(self._delay({}, attempt))
                    continue
                raise AutomationError("timeout" if timed_out else "connection_failed") from None
            if not 200 <= status < 300 or len(raw) > MAX_RESPONSE_BYTES:
                raise AutomationError("invalid_response")
            try:
                data = json.loads(raw) if raw else None
            except ValueError:
                raise AutomationError("invalid_response") from None
            return Response(status, headers, data)
        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    def _status_code(status: int, headers: Mapping[str, str]) -> str:
        if 300 <= status < 400:
            return "blocked_request"
        if status == 401:
            return "auth_failed"
        if status == 403:
            limited = headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers
            return "rate_limited" if limited else "forbidden"
        if status == 404:
            return "not_found"
        if status == 410:
            return "gone"
        if status == 422:
            return "validation_failed"
        if status == 429:
            return "rate_limited_retry"
        if 500 <= status < 600:
            return "server_error"
        return "http_error"

    @staticmethod
    def _delay(headers: Mapping[str, str], attempt: int) -> float:
        value = headers.get("retry-after", "")
        if value.isdigit():
            return min(float(value), RETRY_AFTER_CAP)
        return float(min(2 ** (attempt - 1), RETRY_AFTER_CAP))

    # -- endpoints ---------------------------------------------------------------

    def label_exists(self, name: str) -> bool:
        from urllib.parse import quote
        try:
            response = self.request("GET", f"/repos/{self.repository}/labels/{quote(name, safe='')}")
        except AutomationError as exc:
            if exc.code == "not_found":
                return False
            raise
        return isinstance(response.data, dict) and response.data.get("name") == name

    def open_automation_issues(self) -> list[dict]:
        from urllib.parse import quote
        path = (f"/repos/{self.repository}/issues?state=open&labels={quote(LABEL, safe='')}"
                f"&creator={quote(BOT_LOGIN, safe='')}&sort=created&direction=asc&per_page=100")
        items: list[dict] = []
        response = self.request("GET", path)
        for page in range(1, MAX_PAGES + 1):
            if not isinstance(response.data, list):
                raise AutomationError("invalid_response")
            items.extend(response.data)
            next_url = _next_link(response.headers.get("link", ""))
            if next_url is None:
                return items
            if page < MAX_PAGES:
                response = self.request("GET", "", url=next_url)
        raise AutomationError("pagination_limit")

    def create_issue(self, title: str, body: str) -> int:
        response = self.request("POST", f"/repos/{self.repository}/issues",
                                {"title": title, "body": body, "labels": [LABEL]})
        return _issue_number(response.data)

    def update_issue(self, number: int, title: str, body: str) -> int:
        response = self.request("PATCH", f"/repos/{self.repository}/issues/{int(number)}", {"title": title, "body": body})
        return _issue_number(response.data)

    def close_issue(self, number: int) -> int:
        """Idempotent close (retried like any PATCH); never sends a body, title or label."""
        response = self.request("PATCH", f"/repos/{self.repository}/issues/{int(number)}", dict(CLOSE_PAYLOAD))
        return _issue_number(response.data)


def _issue_number(data: Any) -> int:
    number = data.get("number") if isinstance(data, dict) else None
    if not isinstance(number, int) or isinstance(number, bool):
        raise AutomationError("invalid_response")
    return number


def _next_link(header: str) -> str | None:
    for part in header.split(","):
        match = re.fullmatch(r'\s*<([^<>]+)>\s*;\s*rel="next"\s*', part)
        if match:
            return match.group(1)
    return None


# --------------------------------------------------------------------------- run

@dataclasses.dataclass
class Result:
    mode: str
    codes: list[str] = dataclasses.field(default_factory=list)
    created: list[int] = dataclasses.field(default_factory=list)
    updated: list[int] = dataclasses.field(default_factory=list)
    closed: list[int] = dataclasses.field(default_factory=list)
    unchanged: list[int] = dataclasses.field(default_factory=list)
    planned: int = 0
    not_processed: int = 0

    def add(self, code_: str) -> None:
        if code_ not in self.codes:
            self.codes.append(code_)

    @property
    def outcome(self) -> str:
        if any(c in FAILURE_CODES for c in self.codes):
            return "failed"
        if any(c in SKIP_CODES for c in self.codes):
            return "skipped"
        return "ok"

    def summary(self) -> dict:
        return {"mode": self.mode, "outcome": self.outcome, "codes": sorted(self.codes),
                "created": self.created, "updated": self.updated, "closed": self.closed, "unchanged": self.unchanged,
                "planned": self.planned, "not_processed": self.not_processed}


def publish(evidence: Evidence, client: GitHubClient, result: Result) -> None:
    if not client.label_exists(LABEL):
        raise AutomationError("label_missing")
    existing = client.open_automation_issues()
    writes = 0
    for index, resource in enumerate(evidence.resources):
        rendered = render_issue(evidence, resource, client.repository)
        decision = decide(rendered, evidence, matching_issues(existing, rendered.fingerprint))
        if decision.duplicates:
            result.add("duplicate_issues")
        if decision.code:
            result.add(decision.code)
        if decision.action == "unchanged":
            result.unchanged.append(decision.number)
            continue
        if decision.action == "refused":
            continue
        if writes >= MAX_WRITES_PER_RUN:
            result.add("cap_exceeded")
            result.not_processed = len(evidence.resources) - index
            return
        writes += 1
        if decision.action == "create":
            result.created.append(client.create_issue(rendered.title, rendered.body))
        else:
            result.updated.append(client.update_issue(decision.number, rendered.title, rendered.body))
    closures = plan_closures(evidence, existing)
    for index, decision_ in enumerate(closures):
        if decision_.duplicates:
            result.add("duplicate_issues")
        if decision_.code:
            result.add(decision_.code)
        if decision_.action != "close":
            continue
        if MAX_WRITES_PER_RUN <= writes:   # one cap shared by creates, updates and closes
            result.add("cap_exceeded")
            result.not_processed = sum(1 for d in closures[index:] if d.action == "close")
            return
        writes += 1
        result.closed.append(client.close_issue(decision_.number))


def dry_run(evidence: Evidence, out_dir: str, repository: str | None, result: Result) -> None:
    """No network: every resource is rendered as the create request it would be."""
    requests = []
    for resource in evidence.resources:
        rendered = render_issue(evidence, resource, repository)
        requests.append({"method": "POST", "path": "/repos/{repository}/issues", "address_fingerprint": rendered.fingerprint,
                         "content_hash": rendered.content_hash,
                         "payload": {"title": rendered.title, "body": rendered.body, "labels": [LABEL]}})
    result.planned = len(requests)
    try:
        os.makedirs(out_dir, exist_ok=True)
        if os.listdir(out_dir):
            raise AutomationError("out_dir_not_empty")  # never mix in files from an earlier preview
    except OSError:
        raise AutomationError("out_dir_unwritable") from None
    _write_atomic(os.path.join(out_dir, "requests.json"), json.dumps(requests, indent=2, sort_keys=True) + "\n")
    for n, request in enumerate(requests, 1):
        payload = request["payload"]
        _write_atomic(os.path.join(out_dir, f"issue-{n:03d}.md"), f"# {payload['title']}\n\n{payload['body']}")


def _write_atomic(path: str, text: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def run(args: argparse.Namespace, env: Mapping[str, str],
        client_factory: Callable[[str, str], GitHubClient] | None = None) -> Result:
    result = Result("publish" if args.publish else "dry_run")
    try:
        environment = validate_environment(args.environment)
        if args.drift_detected not in ("true", "false"):   # unknown/failed runs never act
            result.add("not_drift_detected")
            return result
        try:
            with open(args.report, "rb") as fh:
                data = fh.read(MAX_REPORT_BYTES + 1)
        except OSError:
            raise AutomationError("report_missing") from None
        evidence = evidence_from_report(load_report(data), environment, args.drift_detected == "true")
        if args.publish:
            repository = check_publish_binding(evidence, env)
            factory = client_factory or (lambda token, repo: GitHubClient(token, repo))
            publish(evidence, factory(env["GITHUB_TOKEN"], repository), result)
        else:
            repository = args.repository or env.get("GITHUB_REPOSITORY") or None
            if repository is not None and not _REPO_RE.match(repository):
                raise AutomationError("repository_invalid")
            dry_run(evidence, args.out_dir, repository, result)
    except AutomationError as exc:
        result.add(exc.code)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create, update and close drift issues (Tasks 8.1 and 8.3).")
    parser.add_argument("--report", required=True, help="drift_report.json of this run")
    parser.add_argument("--environment", required=True, help="workflow environment (e.g. dev)")
    parser.add_argument("--drift-detected", required=True, help="the workflow's drift_detected output")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out-dir", help="dry-run (default mode): write the rendered requests here; no network")
    mode.add_argument("--publish", action="store_true", help="call the GitHub API (only inside GitHub Actions)")
    parser.add_argument("--repository", help="OWNER/NAME for run links in dry-run output")
    return parser


def _step_summary(result: Result, env: Mapping[str, str]) -> None:
    path = env.get("GITHUB_STEP_SUMMARY")
    if not path or result.mode != "publish":
        return
    summary = result.summary()
    lines = ["## Drift issues", "", f"- Outcome: `{summary['outcome']}`",
             f"- Created: {len(result.created)}, updated: {len(result.updated)}, closed: {len(result.closed)}, "
             f"unchanged: {len(result.unchanged)}, not processed: {result.not_processed}",
             f"- Closed issues: {', '.join(f'#{n}' for n in result.closed) or 'none'}",
             f"- Codes: {', '.join(f'`{c}`' for c in summary['codes']) or 'none'}", ""]
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if exc.code == 0 else EXIT_USAGE
    try:
        result = run(args, env)
        print(json.dumps(result.summary(), sort_keys=True))
        _step_summary(result, env)
    except Exception as exc:  # never print exception messages: they could carry request data
        print(f"internal error ({type(exc).__name__})", file=sys.stderr)
        return EXIT_INTERNAL
    return EXIT_FAILED if result.outcome == "failed" else EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
