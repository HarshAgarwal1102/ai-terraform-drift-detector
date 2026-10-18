"""The dashboard's "Check GitHub for new runs" job (Phase 13 design amendment, Task 13.4).

One background job at a time runs the existing `scripts/fetch_dashboard_data.py` (no second
GitHub-fetch implementation) and records its outcome for `GET /api/fetch/status`:

- the GitHub token is held in this object only, in memory (Task 13.5: entered in the dashboard and
  verified by `connect()`, or, deprecated, received from `dashboard-api --github-token-fd`; never
  from an environment variable) and reaches the fetch script on its standard input
  (`--token-stdin`): never an argument, an environment variable, a log line, a response or a file.
  It is never persisted: a restart of the dashboard forgets it;
- `connect(token)` first runs the same script with `--verify-only` (three read-only GETs); a token
  that fails is discarded and the previous one, if any, stays. The outcome is a fixed category
  (`invalid_token`, `insufficient_permissions`, `repository_not_accessible`, `rate_limited`,
  `network_error`, `api_error`) with the HTTP status when GitHub gave one;
- the subprocess has a fixed argument list (no shell), a fixed script path, the server's own
  Python and a minimal environment: `PATH`, `LANG`, `PYTHONDONTWRITEBYTECODE`, plus only the
  proxy and CA-certificate variables in PASS_THROUGH_ENV when the server has them (for networks
  that need them). Never `GITHUB_API_URL` (it would redirect the token), never `GH_TOKEN`; no
  request input reaches the command;
- one job at a time (`fetch_in_progress`), a cooldown between starts (`fetch_cooldown`) and
  an overall timeout;
- stopping: on the timeout or when the dashboard shuts down (`shutdown()`, called by the app's
  lifespan), the script's process group gets SIGTERM, on which the script removes its own
  staging files and exits; after TERMINATE_GRACE_SECONDS it gets SIGKILL (hidden staging that
  survives a SIGKILL is never read and is removed by a later fetch after an hour);
- the worker never stays `running`: any unexpected error ends the job as `failed`/`internal_error`;
- only the script's fixed lines are parsed (`dashboard_stage=...` while it runs, then
  `dashboard_fetch=ok|partial|failed ...`); its standard error is discarded, never returned or logged.

Statuses: `idle`, `running`, `new_artifacts`, `no_new_artifacts`, `partial` (artifacts
fetched, issue state not updated) and `failed`, with a fixed `code` for the last two
(`timeout`, `shutdown`, `internal_error`, `artifacts_*`, ...). When no fetch can run,
`unavailable_reason` says why with a fixed code: `disabled` (`dashboard-api --no-github`),
`not_connected` (no token), `local_only`
(GitHub Actions), `no_data_dir`, `fetch_script_missing` or `shutting_down`.
"""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from drift_engine.logs import log_event

logger = logging.getLogger(__name__)

REPOSITORY = "HarshAgarwal1102/ai-terraform-drift-detector"
DEFAULT_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                              "scripts", "fetch_dashboard_data.py")
COOLDOWN_SECONDS = 120
TIMEOUT_SECONDS = 600
TERMINATE_GRACE_SECONDS = 5
MAX_OUTPUT_BYTES = 64 * 1024
# Network settings the fetch may legitimately need (a proxy, a corporate CA bundle). Passed through
# unchanged when present; they choose how to reach api.github.com, never which host gets the token
# (the script only sends it to the fixed API URL and checks every download URL).
PASS_THROUGH_ENV = ("HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR")

_COUNTS = r"((?: [a-z_]{1,40}=[0-9]{1,9})*)"
_DETAIL = r"(?: detail=(http_[1-5][0-9]{2}|[A-Za-z_]{1,40}))?"
_OK = re.compile(r"^dashboard_fetch=ok at=[0-9TZ:-]{20}" + _COUNTS + r"$")
_PARTIAL = re.compile(r"^dashboard_fetch=partial step=issues reason=(listing_failed|write_failed)" + _DETAIL + _COUNTS + r"$")
_FAILED = re.compile(r"^dashboard_fetch=failed step=artifacts reason=(listing_failed|write_failed)" + _DETAIL + r"$")
_PAIR = re.compile(r"([a-z_]{1,40})=([0-9]{1,9})")
_STAGE = re.compile(r"^dashboard_stage=(listing|downloading|issues)$")
_VERIFY_OK = re.compile(r"^dashboard_verify=ok(?: warning=insufficient_permissions http=403 need=issues)?$")
_VERIFY_FAILED = re.compile(r"^dashboard_verify=failed reason=([a-z_]{1,40})(?: http=([1-5][0-9]{2}))?"
                            r"(?: need=(actions|issues))?$")
VERIFY_REASONS = ("invalid_token", "insufficient_permissions", "repository_not_accessible", "sso_required",
                  "rate_limited", "network_error", "api_error")
AUTH_CATEGORIES = ("invalid_token", "insufficient_permissions", "repository_not_accessible", "sso_required")
VERIFY_TIMEOUT_SECONDS = 60
VERIFY_GAP_SECONDS = 2  # least time between two verifications (a bad token cannot be hammered at GitHub)
MAX_TOKEN_CHARS = 1024
MAX_LINE_BYTES = 4096


class FetchRefused(Exception):
    """A start was refused; `code` and `status` are fixed, `retry_after` seconds for a cooldown."""

    def __init__(self, code: str, status: int, retry_after: int | None = None) -> None:
        super().__init__(code)
        self.code, self.status, self.retry_after = code, status, retry_after


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _counts(text: str) -> dict[str, int]:
    return {key: int(value) for key, value in _PAIR.findall(text or "")}


def valid_token(token: object) -> bool:
    """One printable, non-space ASCII line of at most MAX_TOKEN_CHARS (the same rule as the script's)."""
    return (isinstance(token, str) and 0 < len(token) <= MAX_TOKEN_CHARS and token.isascii()
            and all(c.isprintable() and not c.isspace() for c in token))


def classify(step: str, reason: str, detail: str | None) -> tuple[str, int | None]:
    """(fixed category, HTTP status when known) of a failed step, from the script's fixed detail."""
    detail = (detail or "").lower()
    match = re.fullmatch(r"http_([1-5][0-9]{2})", detail)
    status = int(match.group(1)) if match else None
    if status == 401:
        return "invalid_token", status
    if status == 403:
        return "insufficient_permissions", status
    if status == 404:
        return "repository_not_accessible", status
    if detail == "sso_required":
        return "sso_required", 403
    if status == 429 or detail == "rate_limited":
        return "rate_limited", status
    if detail == "network":
        return "network_error", status
    if reason == "write_failed":
        return "write_failed", status
    return ("artifacts_listing_failed" if step == "artifacts" else "issues_listing_failed"), status


def parse_result(returncode: int, stdout: str) -> dict:
    """The job outcome from the script's exit code and its last non-empty result line (stage lines
    are progress markers, not results)."""
    lines = [line.strip() for line in stdout.splitlines() if line.strip() and not _STAGE.match(line.strip())]
    last = lines[-1] if lines else ""
    base = {"category": None, "http_status": None, "need": None}
    if match := _OK.match(last):
        counts = _counts(match.group(1))
        if returncode != 0:
            return dict(base, status="failed", code="unexpected_exit", counts=counts)
        return dict(base, status="new_artifacts" if counts.get("fetched", 0) > 0 else "no_new_artifacts", code=None,
                    counts=counts)
    if match := _PARTIAL.match(last):
        detail = match.group(2)
        code = "issues_" + match.group(1) + ("_" + detail.lower() if detail else "")
        category, http = classify("issues", match.group(1), detail)
        return dict(base, status="partial", code=code, counts=_counts(match.group(3)), category=category,
                    http_status=http, need="issues")
    if match := _FAILED.match(last):
        detail = match.group(2)
        code = "artifacts_" + match.group(1) + ("_" + detail.lower() if detail else "")
        category, http = classify("artifacts", match.group(1), detail)
        return dict(base, status="failed", code=code, counts={}, category=category, http_status=http,
                    need="actions")
    return dict(base, status="failed", code="usage" if returncode == 2 else "unexpected_output", counts={})


def parse_verification(returncode: int, stdout: str) -> dict:
    """The verification outcome from the script's one fixed line."""
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    last = lines[-1] if lines else ""
    if _VERIFY_OK.match(last) and returncode == 0:
        warning = ({"category": "insufficient_permissions", "http_status": 403, "need": "issues"}
                   if " warning=" in last else None)
        return {"ok": True, "category": None, "http_status": None, "need": None, "warning": warning}
    if (match := _VERIFY_FAILED.match(last)) and match.group(1) in VERIFY_REASONS:
        return {"ok": False, "category": match.group(1), "http_status": int(match.group(2)) if match.group(2) else None,
                "need": match.group(3), "warning": None}
    return {"ok": False, "category": "unexpected_output", "http_status": None, "need": None, "warning": None}


class GitHubFetcher:
    """Connects a GitHub token, starts and tracks the single fetch job. Thread-safe; the token never
    leaves this object except through a subprocess's standard input."""

    def __init__(self, *, token: str | None, data_dir: str, repository: str = REPOSITORY,
                 script: str = DEFAULT_SCRIPT, python: str = sys.executable,
                 cooldown_seconds: int = COOLDOWN_SECONDS, timeout_seconds: int = TIMEOUT_SECONDS,
                 verify_timeout_seconds: int = VERIFY_TIMEOUT_SECONDS, verify_gap_seconds: int = VERIFY_GAP_SECONDS,
                 environ: Mapping[str, str] = os.environ, monotonic: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc), disabled: bool = False) -> None:
        self._disabled = disabled  # `dashboard-api --no-github`: no token is ever accepted, no fetch ever runs
        self._token = None if disabled else (token or None)
        self._data_dir = os.path.abspath(data_dir) if data_dir else ""
        self._repository, self._script, self._python = repository, script, python
        self._cooldown, self._timeout = cooldown_seconds, timeout_seconds
        self._verify_timeout, self._verify_gap = verify_timeout_seconds, verify_gap_seconds
        self._in_ci = environ.get("GITHUB_ACTIONS") == "true"
        self._network_env = {k: environ[k] for k in PASS_THROUGH_ENV
                             if isinstance(environ.get(k), str) and environ[k] and "\n" not in environ[k]}
        self._monotonic, self._now = monotonic, now
        self._lock = threading.Lock()
        self._verify_lock = threading.Lock()
        self._last_start: float | None = None
        self._last_verify: float | None = None
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self._closing = False
        self._stop_reason: str | None = None  # "timeout" or "shutdown" when the job is being stopped
        self._started_mono: float | None = None
        self._elapsed: float | None = None  # seconds of the last finished job
        self._state = {"status": "idle", "code": None, "started_at": None, "finished_at": None, "counts": {},
                       "stage": None, "category": None, "http_status": None, "need": None}
        # What is known about the token, never the token: how it got here, whether GitHub accepted it,
        # the last problem a fetch hit, and the outcome of the last verification attempt.
        # `last_error`: GitHub refused the token or its required (Actions) access; `warning`: the token works
        # for reports but lacks Issues: Read (drift issue states are not updated).
        self._connection = {"source": "startup" if self._token else None, "verified": False, "verified_at": None,
                            "last_error": None, "warning": None, "last_attempt": None}

    def __repr__(self) -> str:  # never shows the token
        return f"GitHubFetcher(available={self.available})"

    def _blocked_reason(self) -> str | None:
        if self._disabled:
            return "disabled"
        if self._in_ci:
            return "local_only"
        if not self._data_dir:
            return "no_data_dir"
        if not os.path.isfile(self._script):
            return "fetch_script_missing"
        if self._closing:
            return "shutting_down"
        return None

    def unavailable_reason(self) -> str | None:
        """Why no fetch can run (a fixed code, never a path or a value), or None."""
        blocked = self._blocked_reason()
        if blocked in ("disabled", "local_only"):
            return blocked
        if self._token is None:
            return "not_connected"
        return blocked

    @property
    def available(self) -> bool:
        return self.unavailable_reason() is None

    def status(self) -> dict:
        with self._lock:
            state = dict(self._state, counts=dict(self._state["counts"]))
            connection = dict(self._connection, connected=self._token is not None)
            elapsed = self._elapsed
            if state["status"] == "running" and self._started_mono is not None:
                elapsed = self._monotonic() - self._started_mono
        retry = None
        if self._last_start is not None and state["status"] != "running":
            retry = max(0, int(self._last_start + self._cooldown - self._monotonic() + 0.999))
        reason = self.unavailable_reason()
        return dict(state, available=reason is None, unavailable_reason=reason, cooldown_seconds=self._cooldown,
                    retry_after_seconds=retry or None, connection=connection,
                    elapsed_seconds=None if elapsed is None else int(elapsed))

    def connect(self, token: str) -> dict:
        """Verifies `token` with read-only GitHub requests (the script's --verify-only) and, only when
        GitHub accepts it, keeps it in memory in place of any earlier one. Returns the verification
        outcome `{ok, category, http_status, need}`; a failed token is discarded. Raises FetchRefused
        for a malformed token, a running fetch, a verification in progress or too soon."""
        blocked = self._blocked_reason()
        if blocked is not None:
            raise FetchRefused(blocked if blocked in ("disabled", "local_only") else "fetch_unavailable", 503)
        if not valid_token(token):
            raise FetchRefused("invalid_token_format", 422)
        if not self._verify_lock.acquire(blocking=False):
            raise FetchRefused("verification_in_progress", 409)
        try:
            with self._lock:
                if self._state["status"] == "running":
                    raise FetchRefused("fetch_in_progress", 409)
                moment = self._monotonic()
                if self._last_verify is not None and moment - self._last_verify < self._verify_gap:
                    raise FetchRefused("verify_too_soon", 429,
                                       int(self._last_verify + self._verify_gap - moment + 0.999))
                self._last_verify = moment
            try:
                result = self._run_verify(token)
            except Exception:  # noqa: BLE001  (never an exception text: it could carry request details)
                result = {"ok": False, "category": "internal_error", "http_status": None, "need": None, "warning": None}
            with self._lock:
                self._connection["last_attempt"] = {key: result[key] for key in ("category", "http_status", "need")}
                self._connection["last_attempt"]["ok"] = result["ok"]
                self._connection["last_attempt"]["at"] = _timestamp(self._now())
                if result["ok"]:
                    self._token = token
                    self._connection.update(source="dashboard", verified=True, verified_at=_timestamp(self._now()),
                                            last_error=None, warning=result.get("warning"))
            log_event(logger, logging.INFO if result["ok"] else logging.WARNING, "dashboard_github_verified",
                      "GitHub token verified" if result["ok"] else "GitHub token not accepted",
                      category=result["category"], http_status=result["http_status"])
            return result
        finally:
            # Only drops this frame's name for the string: Python cannot wipe a string, and copies may live on
            # (the parsed request body, the subprocess pipe buffer) until they are garbage-collected.
            token = None
            self._verify_lock.release()

    def disconnect(self) -> None:
        """Forgets the token (not while a fetch runs, which already holds its own copy for its process)."""
        with self._lock:
            if self._state["status"] == "running":
                raise FetchRefused("fetch_in_progress", 409)
            self._token = None
            self._connection.update(source=None, verified=False, verified_at=None, last_error=None, warning=None)
        log_event(logger, logging.INFO, "dashboard_github_disconnected", "GitHub token forgotten")

    def start(self) -> dict:
        reason = self.unavailable_reason()
        if reason in ("disabled", "local_only"):
            raise FetchRefused(reason, 503)
        if reason is not None:
            raise FetchRefused("fetch_unavailable", 503)
        with self._lock:
            if self._state["status"] == "running":
                raise FetchRefused("fetch_in_progress", 409)
            moment = self._monotonic()
            if self._last_start is not None and moment - self._last_start < self._cooldown:
                raise FetchRefused("fetch_cooldown", 429, int(self._last_start + self._cooldown - moment + 0.999))
            self._last_start = self._started_mono = moment
            self._elapsed = None
            self._state = {"status": "running", "code": None, "started_at": _timestamp(self._now()),
                           "finished_at": None, "counts": {}, "stage": "connecting", "category": None,
                           "http_status": None, "need": None}
            self._thread = threading.Thread(target=self._run, args=(self._token,), name="dashboard-github-fetch",
                                            daemon=True)
            self._thread.start()
        log_event(logger, logging.INFO, "dashboard_fetch_started", "GitHub fetch started")
        return self.status()

    def wait(self, timeout: float | None = None) -> None:
        """For tests and shutdown: wait for the running job, if any."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def shutdown(self, grace_seconds: float = TERMINATE_GRACE_SECONDS) -> None:
        """Dashboard shutdown: refuse new jobs, stop a running fetch (SIGTERM, then SIGKILL after
        `grace_seconds`) and wait for the worker to record it as `failed`/`shutdown`."""
        with self._lock:
            self._closing = True
            process = self._process
            if process is not None and self._stop_reason is None:
                self._stop_reason = "shutdown"
        if process is not None:
            _terminate(process, grace_seconds)
        self.wait(grace_seconds + 5)

    def _command(self) -> list[str]:
        return [self._python, self._script, "--token-stdin", "--repository", self._repository,
                "--data-dir", self._data_dir]

    def _verify_command(self) -> list[str]:
        return [self._python, self._script, "--verify-only", "--token-stdin", "--repository", self._repository]

    def _environment(self) -> dict[str, str]:
        # Minimal on purpose: nothing else from the server's environment, so no GITHUB_API_URL (which
        # would redirect the token), no GH_TOKEN and no unrelated secrets reach the script.
        return {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", **self._network_env}

    def _run_verify(self, token: str) -> dict:
        try:
            process = subprocess.Popen(self._verify_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, env=self._environment(), close_fds=True,
                                       start_new_session=True, cwd=os.path.dirname(self._script))
        except OSError:
            return {"ok": False, "category": "internal_error", "http_status": None, "need": None, "warning": None}
        try:
            out, _ = process.communicate(input=(token + "\n").encode(), timeout=self._verify_timeout)
        except subprocess.TimeoutExpired:
            _terminate(process, TERMINATE_GRACE_SECONDS)
            process.communicate()
            return {"ok": False, "category": "network_error", "http_status": None, "need": None, "warning": None}
        return parse_verification(process.returncode, out[:MAX_OUTPUT_BYTES].decode("utf-8", "replace"))

    def _run(self, token: str) -> None:
        result = {"status": "failed", "code": "internal_error", "counts": {}, "category": None, "http_status": None,
                  "need": None}
        try:
            result = self._run_process(token)
        except Exception:  # noqa: BLE001  (never stay `running`: any unexpected error ends the job as failed)
            result = dict(result)
            with self._lock:
                process = self._process
            if process is not None:
                try:
                    _terminate(process, TERMINATE_GRACE_SECONDS)
                except Exception:  # noqa: BLE001
                    pass
        finally:
            token = None  # drops this frame's name only; see connect() on why strings cannot be wiped
            with self._lock:
                self._process = None
                self._stop_reason = None
                self._elapsed = self._monotonic() - (self._started_mono or self._monotonic())
                self._state = dict(self._state, status=result["status"], code=result["code"],
                                   counts=result["counts"], finished_at=_timestamp(self._now()),
                                   category=result["category"], http_status=result["http_status"],
                                   need=result["need"])
                self._note_outcome(result)
            try:
                log_event(logger, logging.INFO if result["status"] != "failed" else logging.WARNING,
                          "dashboard_fetch_finished", "GitHub fetch finished", status=result["status"],
                          code=result["code"], category=result["category"], http_status=result["http_status"],
                          counts=result["counts"])
            except Exception:  # noqa: BLE001  (a logging failure must not leave the job running)
                pass

    def _note_outcome(self, result: dict) -> None:
        """Under the lock: what a finished fetch says about the token. Reports downloaded (ok, or partial
        because only the issue listing was refused) prove the required access; only a refusal of the token
        or of its Actions access marks it unverified. An Issues-only refusal is a warning, never an error."""
        problem = {"category": result["category"], "http_status": result["http_status"], "need": result["need"]}
        if result["status"] in ("new_artifacts", "no_new_artifacts"):
            self._connection.update(verified=True, last_error=None, warning=None)
        elif (result["status"] == "partial" and result["category"] == "insufficient_permissions"
              and result["need"] == "issues"):
            self._connection.update(verified=True, last_error=None, warning=problem)
        elif result["category"] in AUTH_CATEGORIES:
            self._connection.update(verified=False, last_error=problem)

    def _read_output(self, process: subprocess.Popen, lines: list[str]) -> None:
        """Stage markers update the state; other lines (the result line) are kept, bounded."""
        total = 0
        try:
            for raw in iter(lambda: process.stdout.readline(MAX_LINE_BYTES), b""):
                total += len(raw)
                text = raw.decode("utf-8", "replace").strip()
                if match := _STAGE.match(text):
                    with self._lock:
                        if self._state["status"] == "running":
                            self._state["stage"] = match.group(1)
                elif text and total <= MAX_OUTPUT_BYTES:
                    lines.append(text)
        except (OSError, ValueError):
            pass

    def _run_process(self, token: str) -> dict:
        try:
            process = subprocess.Popen(self._command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, env=self._environment(), close_fds=True,
                                       start_new_session=True, cwd=os.path.dirname(self._script))
        except OSError:
            return {"status": "failed", "code": "start_failed", "counts": {}, "category": None, "http_status": None,
                    "need": None}
        with self._lock:
            self._process = process
            closing = self._closing
            if closing:
                self._stop_reason = "shutdown"
        if closing:  # shutdown began while the process was starting
            _terminate(process, TERMINATE_GRACE_SECONDS)
        lines: list[str] = []
        reader = threading.Thread(target=self._read_output, args=(process, lines), daemon=True)
        reader.start()
        try:
            process.stdin.write((token + "\n").encode())
            process.stdin.close()
        except OSError:  # the script ended before reading it: its exit code and output say why
            pass
        try:
            process.wait(timeout=self._timeout)
        except subprocess.TimeoutExpired:
            with self._lock:
                if self._stop_reason is None:
                    self._stop_reason = "timeout"
            _terminate(process, TERMINATE_GRACE_SECONDS)
            process.wait()
        reader.join(5)
        with self._lock:
            stopped = self._stop_reason
        if stopped is not None:
            return {"status": "failed", "code": stopped, "counts": {}, "category": None, "http_status": None,
                    "need": None}
        return parse_result(process.returncode, "\n".join(lines))


def _terminate(process: subprocess.Popen, grace_seconds: float) -> None:
    """SIGTERM to the process group (the script cleans up its own staging), then SIGKILL."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        process.terminate()
    try:
        process.wait(grace_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)  # the script and anything it started
        except OSError:
            process.kill()
        process.wait()
