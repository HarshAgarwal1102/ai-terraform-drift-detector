"""FastAPI application of the dashboard data API (Task 13.1).

Endpoints (all GET, all require `Authorization: Bearer <token>` of a `viewer`):
- `/api/summary`: overview metrics of the latest run per environment, and history;
- `/api/drifts`: drifted resources (`report_id`, `environment`, `severity`,
  `resource_type` filters; default: the latest run of each environment);
- `/api/reports/{report_id}`: one run's bound artifacts and its drift rows;
- `/api/remediations`: remediation options with approval and execution state;
- `/api/unmanaged`: resources Terraform does not manage, with their list-price
  estimate (Task 10.4 data, shown by Task 13.3);
- `/api/fetch/status`: the state of the "Check GitHub for new runs" job (Task 13.4).

The write-capable endpoints (all `POST`, all need the `data_refresher` role, all refuse a
cross-origin browser request) are `POST /api/fetch` (Phase 13 design amendment, Task 13.4: starts the
existing GitHub fetch as one background job, `github_fetch.py`) and, from Task 13.5,
`POST /api/github/connect` (a JSON body `{"token": ...}` with the user's GitHub token; it is verified
with read-only GitHub requests and kept in memory only; the response never contains it) and
`POST /api/github/disconnect`. Every `GET` endpoint stays read-only.

`include_caller=true` on `/api/drifts` and `/api/reports/{id}` adds the
`Caller recorded by Azure` field to every drift row; it needs the `caller_reader`
role (403 otherwise). Every response is sent with `Cache-Control: no-store` and a
strict Content-Security-Policy. Logs carry fixed event codes and counts only.

The dashboard UI (Task 13.2, `dashboard/`) is served from the same origin: `/` and
exactly the files in UI_FILES, without sign-in (they hold no data; the UI signs in to
`/api/*` with a bearer token kept in memory).

No `from __future__ import annotations` here: FastAPI resolves the endpoint
annotations at runtime, including the locally defined `User` dependency.
"""

import logging
import os
from urllib.parse import urlsplit
from collections import Counter
from contextlib import asynccontextmanager
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Path, Query, Request
from starlette.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from drift_engine import activity_logs as al
from drift_engine import investigation as inv
from drift_engine import who
from drift_engine.logs import log_event

from dashboard_api import API_VERSION, auth, callers, github_fetch, store, views

logger = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # Same-origin scripts, styles and API calls only; no inline script or style, no framing.
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
}
UI_FILES = {"index.html": "text/html", "app.js": "text/javascript", "render.js": "text/javascript",
            "loader.js": "text/javascript", "styles.css": "text/css"}
DEFAULT_UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                              "dashboard")


MAX_GITHUB_BODY_BYTES = 4096  # a token is at most 1024 characters; a body this size is never parsed


class ConnectBody(BaseModel):
    """The one request body that carries a credential. A validation failure never echoes it."""

    model_config = ConfigDict(extra="forbid")
    token: str = Field(max_length=MAX_GITHUB_BODY_BYTES)


class ApiError(Exception):
    def __init__(self, status: int, code: str, headers: dict | None = None) -> None:
        super().__init__(code)
        self.status, self.code, self.headers = status, code, headers or {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_app(*, data_dir: str, users_file: str, terraform_json: str | None = None,
               source: al.ActivityLogSource | None = None, now: Callable[[], datetime] = _utcnow,
               environ: Mapping[str, str] = os.environ, ui_dir: str | None = DEFAULT_UI_DIR,
               github_token: str | None = None, fetcher: github_fetch.GitHubFetcher | None = None,
               github_enabled: bool = True) -> FastAPI:
    """The API over `data_dir`. `source` defaults to the Azure Activity Log with the
    operator's own read-only `az login` (AzureCliCredential), created on first use.
    `ui_dir` (default: the repository's `dashboard/`) serves the UI; None disables it.
    `github_token` (in memory only) enables `POST /api/fetch`; `fetcher` replaces the
    default job (tests)."""
    if fetcher is None:
        fetcher = github_fetch.GitHubFetcher(token=github_token, data_dir=data_dir, environ=environ,
                                             disabled=not github_enabled)
    del github_token  # from here on only the fetcher holds it

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        # Dashboard shutdown (Ctrl+C): stop a running GitHub fetch instead of leaving it orphaned.
        await run_in_threadpool(fetcher.shutdown)

    app = FastAPI(title="Drift dashboard API", version=API_VERSION, docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    sources: list[al.ActivityLogSource] = [source] if source is not None else []

    def activity_source() -> al.ActivityLogSource:
        if not sources:
            sources.append(al.AzureMonitorSource())
        return sources[0]

    @app.middleware("http")
    async def bounded_github_body(request: Request, call_next):
        """FastAPI reads a request body before it checks authentication, so the body of the GitHub endpoints is
        bounded here, before anything reads it: a declared length is required and must be small."""
        if request.method == "POST" and request.url.path.startswith("/api/github/"):
            length = request.headers.get("content-length")
            if length is None or not length.isdigit():
                return JSONResponse({"error": "length_required"}, status_code=411)
            if int(length) > MAX_GITHUB_BODY_BYTES:
                return JSONResponse({"error": "request_too_large"}, status_code=413)
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError) -> JSONResponse:
        log_event(logger, logging.WARNING, "dashboard_request_refused", "request refused", code=exc.code,
                  status=exc.status)
        return JSONResponse({"error": exc.code}, status_code=exc.status, headers=exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse({"error": code}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"error": "invalid_request"}, status_code=422)  # never echoes the input

    def current_user(request: Request) -> auth.User:
        try:
            users = auth.load_users(users_file)
        except auth.UsersFileError as exc:
            log_event(logger, logging.ERROR, "dashboard_auth_unavailable", "users file unusable", code=exc.code)
            raise ApiError(503, "auth_unavailable") from None
        user = auth.authenticate(request.headers.get("authorization"), users)
        if user is None:
            raise ApiError(401, "unauthenticated", {"WWW-Authenticate": "Bearer"})
        if "viewer" not in user.roles:
            raise ApiError(403, "forbidden")
        return user

    User = Annotated[auth.User, Depends(current_user)]

    def same_origin(request: Request) -> None:
        """Defence in depth for the state-changing requests: authentication is a bearer header that a
        browser never attaches by itself, but a request that a page of another origin made is refused."""
        origin = request.headers.get("origin")
        if origin is not None and (origin == "null" or urlsplit(origin).netloc != request.headers.get("host", "")):
            raise ApiError(403, "origin_not_allowed")

    SameOrigin = Annotated[None, Depends(same_origin)]

    def json_only(request: Request) -> None:
        """A credential is only accepted as `application/json`, which a cross-site form cannot send."""
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise ApiError(415, "unsupported_media_type")

    JsonOnly = Annotated[None, Depends(json_only)]

    def index() -> store.Index:
        try:
            return store.load(data_dir)
        except store.StoreUnavailable:
            raise ApiError(503, "data_unavailable") from None

    def check_caller_access(user: auth.User, include_caller: bool) -> None:
        if include_caller and "caller_reader" not in user.roles:
            raise ApiError(403, "caller_access_denied")

    def resource_ids() -> dict[str, str] | None:
        if not terraform_json:
            return None
        try:
            with open(terraform_json, "rb") as fh:
                data = fh.read(inv.MAX_INPUT_BYTES + 1)
            if len(data) > inv.MAX_INPUT_BYTES:
                return None
            return who.terraform_resource_ids(data)
        except (OSError, ValueError, RecursionError, UnicodeDecodeError):
            return None

    def add_callers(rows: list[dict], bundles: dict[str, store.Bundle]) -> None:
        """On demand, for this response only: nothing is cached, stored or logged."""
        ids, moment, statuses, results = resource_ids(), now(), Counter(), []
        if rows:
            source = activity_source()  # created once, before the lookups run concurrently

            def lookup(row: dict) -> dict:
                return callers.recorded_caller(bundles[row["report_id"]].investigation, row["address"], ids,
                                               source, moment, environ)

            with ThreadPoolExecutor(max_workers=min(callers.MAX_PARALLEL_LOOKUPS, len(rows))) as pool:
                results = list(pool.map(lookup, rows))  # independent Activity Log queries; order kept
        for row, result in zip(rows, results):
            statuses[result["status"]] += 1
            row["caller_recorded_by_azure"] = result
        log_event(logger, logging.INFO, "dashboard_caller_lookup", "caller lookup finished", drifts=len(rows),
                  statuses=dict(sorted(statuses.items())))

    def selected(idx: store.Index, report_id: str | None, environment: str | None) -> list[store.Bundle]:
        if report_id is not None:
            bundle = idx.get(report_id)
            if bundle is None:
                raise ApiError(404, "report_not_found")
            return [bundle]
        latest = idx.latest_per_environment()
        return [b for b in latest if environment is None or b.environment == environment]

    @app.get("/api/summary")
    def get_summary(user: User) -> dict[str, Any]:
        idx = index()
        return {"api_version": API_VERSION, "generated_at": al.format_timestamp(now()),
                **views.summary(idx.latest_per_environment(), idx.bundles, idx.problems, idx.issues)}

    @app.get("/api/drifts")
    def get_drifts(user: User, report_id: Annotated[str | None, Query(max_length=200)] = None,
                   environment: Annotated[str | None, Query(max_length=64)] = None,
                   severity: Annotated[str | None, Query(max_length=16)] = None,
                   resource_type: Annotated[str | None, Query(max_length=200)] = None,
                   include_caller: bool = False) -> dict[str, Any]:
        check_caller_access(user, include_caller)
        idx = index()
        bundles = selected(idx, report_id, environment)
        rows = [row for b in bundles for row in views.drift_rows(b, idx.issues)
                if (severity is None or row["severity"] == severity.upper())
                and (resource_type is None or row["type"] == resource_type)
                and (environment is None or row["environment"] == environment)]
        if include_caller:
            add_callers(rows, {b.run_id: b for b in bundles})
        return {"api_version": API_VERSION, "reports": [b.run_id for b in bundles], "count": len(rows),
                "drifts": rows}

    @app.get("/api/reports/{report_id}")
    def get_report(user: User, report_id: Annotated[str, Path(max_length=200)],
                   include_caller: bool = False) -> dict[str, Any]:
        check_caller_access(user, include_caller)
        if not store.RUN_ID.match(report_id):
            raise ApiError(404, "report_not_found")
        idx = index()
        bundle = selected(idx, report_id, None)[0]
        rows = views.drift_rows(bundle, idx.issues)
        if include_caller:
            add_callers(rows, {bundle.run_id: bundle})
        return {
            "api_version": API_VERSION,
            "report_id": bundle.run_id,
            "summary": views.run_summary(bundle),
            "drifts": rows,
            "remediations": views.remediations(bundle),
            "unmanaged": views.unmanaged(bundle),
            "artifacts": {
                "drift_report": bundle.report,
                "drift_report_sha256": bundle.report_sha256,
                "ai_analysis_report": bundle.ai_report,
                "investigation": None if bundle.investigation is None
                else bundle.investigation.model_dump(mode="json"),
                "cost_run": bundle.cost_run,
            },
        }

    @app.get("/api/remediations")
    def get_remediations(user: User, report_id: Annotated[str | None, Query(max_length=200)] = None,
                         environment: Annotated[str | None, Query(max_length=64)] = None) -> dict[str, Any]:
        bundles = selected(index(), report_id, environment)
        options = [o for b in bundles for o in views.remediations(b)]
        return {"api_version": API_VERSION, "reports": [b.run_id for b in bundles], "count": len(options),
                "pending_approvals": sum(1 for o in options if o["approval"]["status"] == "pending"),
                "remediations": options}

    @app.get("/api/unmanaged")
    def get_unmanaged(user: User, report_id: Annotated[str | None, Query(max_length=200)] = None,
                      environment: Annotated[str | None, Query(max_length=64)] = None) -> dict[str, Any]:
        bundles = selected(index(), report_id, environment)
        return {"api_version": API_VERSION, "reports": [b.run_id for b in bundles],
                "runs": [views.unmanaged(b) for b in bundles]}

    @app.get("/api/fetch/status")
    def get_fetch_status(user: User) -> dict[str, Any]:
        """Read-only: the fetch job's state, and whether this user may start one."""
        return {"api_version": API_VERSION, **fetcher.status(), "allowed": "data_refresher" in user.roles}

    @app.post("/api/fetch", status_code=202)
    def post_fetch(_origin: SameOrigin, user: User) -> dict[str, Any]:
        """Starts "Check GitHub for new runs". Accepts no parameters; nothing from the request
        reaches the fetch command."""
        if "data_refresher" not in user.roles:
            raise ApiError(403, "fetch_access_denied")
        try:
            state = fetcher.start()
        except github_fetch.FetchRefused as exc:
            headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
            raise ApiError(exc.status, exc.code, headers) from None
        return {"api_version": API_VERSION, **state, "allowed": True}

    def refuse(exc: github_fetch.FetchRefused) -> ApiError:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        return ApiError(exc.status, exc.code, headers)

    @app.post("/api/github/connect")
    def post_github_connect(_origin: SameOrigin, user: User, _json: JsonOnly, body: ConnectBody) -> dict[str, Any]:
        """Verifies the GitHub token in the body (read-only requests to the fixed repository) and keeps it in
        memory when GitHub accepts it. Answers with the verification outcome (fixed category, HTTP status,
        missing permission) and the fetch state; never the token."""
        if "data_refresher" not in user.roles:
            raise ApiError(403, "fetch_access_denied")
        try:
            verification = fetcher.connect(body.token)
        except github_fetch.FetchRefused as exc:
            raise refuse(exc) from None
        return {"api_version": API_VERSION, "verification": verification, **fetcher.status(), "allowed": True}

    @app.post("/api/github/disconnect")
    def post_github_disconnect(_origin: SameOrigin, user: User) -> dict[str, Any]:
        """Forgets the GitHub token held in memory."""
        if "data_refresher" not in user.roles:
            raise ApiError(403, "fetch_access_denied")
        try:
            fetcher.disconnect()
        except github_fetch.FetchRefused as exc:
            raise refuse(exc) from None
        return {"api_version": API_VERSION, **fetcher.status(), "allowed": True}

    def ui_file(name: str) -> FileResponse:
        path = os.path.join(ui_dir or "", name)
        if not ui_dir or os.path.islink(path) or not os.path.isfile(path):
            raise StarletteHTTPException(404)
        return FileResponse(path, media_type=UI_FILES[name])

    @app.get("/", include_in_schema=False)
    def ui_index() -> FileResponse:
        return ui_file("index.html")

    @app.get("/{name}", include_in_schema=False)
    def ui_asset(name: str) -> FileResponse:
        if name not in UI_FILES:
            raise StarletteHTTPException(404)
        return ui_file(name)

    return app


def create_app_from_env(environ: Mapping[str, str] = os.environ, github_token: str | None = None,
                        github_enabled: bool = True) -> FastAPI:
    """Settings from `DASHBOARD_DATA_DIR`, `DASHBOARD_USERS_FILE` and the optional
    `DASHBOARD_TERRAFORM_JSON` (`terraform show -json` state: address -> ARM ID). The GitHub
    token, when given, comes from `dashboard-api --github-token-fd`, never from the environment."""
    return create_app(data_dir=environ.get("DASHBOARD_DATA_DIR", ""),
                      users_file=environ.get("DASHBOARD_USERS_FILE", ""),
                      terraform_json=environ.get("DASHBOARD_TERRAFORM_JSON") or None, environ=environ,
                      ui_dir=environ.get("DASHBOARD_UI_DIR") or DEFAULT_UI_DIR, github_token=github_token,
                      github_enabled=github_enabled)
