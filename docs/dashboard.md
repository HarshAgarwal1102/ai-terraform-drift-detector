# Dashboard

Phase 13. This page covers the dashboard data API (Task 13.1, `src/dashboard_api/`) and the
dashboard UI (Task 13.2, `dashboard/`). The live-data integration (Task 13.3) builds on both.

## What it serves

A read-only API over the **real artifacts** of the drift detection and AI analysis workflows. It
never computes drift itself, never estimates a value that no artifact holds, and has no database.

| Artifact | File | Bound to a drift report by |
| --- | --- | --- |
| Drift report (public) | `drift_report.json` | key: `run.run_id` |
| AI analysis report | `ai_analysis_report.json` | `provenance.run_id` and `provenance.drift_report_sha256` (canonical SHA-256) |
| Public investigation | `drift_investigation.json` | `investigation_public.load_public` (leak scan, strict model) and `check_binding` |
| Cost run | `cost_run.json` | `run_id` and `drift_report_sha256` |

The data directory may use any layout; `gh run download <run-id> --dir <data-dir>` works as is.
It is re-indexed on every request and never written to. An artifact that is not bound to a
report is ignored; two different documents for one slot make it ambiguous and neither is used;
two different reports for one run id are both skipped. Problems are reported as fixed codes
(`data_problems` in `/api/summary`, `problems` per run).

## Endpoints

All are `GET` and need `Authorization: Bearer <token>` of a user with the `viewer` role.

| Endpoint | Returns |
| --- | --- |
| `/api/summary` | Overview (total resources, active drifts, security exposure, monthly cost impact) of the latest run per environment, per-environment run summaries, and the run history (newest first, at most 100). |
| `/api/drifts` | Drifted resources of the latest run per environment, or of `report_id`. Filters: `environment`, `severity`, `resource_type`. Each row: resource, type, classification, severity, every changed property with its expected (`desired`) and actual (`real`) value, the decisive operation (name, start, end, caller type, client application), the AI narrative and the remediation recommendation. |
| `/api/reports/{report_id}` | One run: summary, drift rows, remediation options and the bound artifacts themselves. |
| `/api/remediations` | Remediation options of the AI report with approval status and execution state (`allowed: false`, `manual_after_approval`). The approver identity is never returned. |

`include_caller=true` on `/api/drifts` and `/api/reports/{report_id}` adds the
`Caller recorded by Azure` field to every drift row (see below).

Values no artifact provides stay `null` with a status: for example `monthly_cost_impact` is
`not_available` for AI reports that carry no validated `cost_impact` (report v2), and the
overview total is `null` unless every environment has a complete figure.

Errors are `{"error": "<code>"}`: `unauthenticated` (401), `forbidden` and
`caller_access_denied` (403), `report_not_found` and `not_found` (404), `invalid_request` (422,
never echoing the input), `auth_unavailable` and `data_unavailable` (503).

## Sign-in and authorization

Design (Task 13.1 design review; no new Azure resource, role or GitHub setting):

- **Users file** (`DASHBOARD_USERS_FILE`): one bearer token per user, stored only as its
  SHA-256 digest, with roles `viewer` and optionally `caller_reader`:

  ```json
  {"users": [{"name": "maintainer", "token_sha256": "<64 hex>", "roles": ["viewer", "caller_reader"]}]}
  ```

  It must be a regular file that neither group nor others can write; otherwise every request
  fails closed (503). It is re-read on every request, so removing a user takes effect at once.
  Tokens are compared in constant time and never logged.
- **Roles**: `viewer` reads every endpoint without caller identity; `caller_reader` may also
  request `include_caller=true` (403 otherwise; a refused request never queries Azure).
- **Network**: `dashboard-api` binds only to a loopback address (default `127.0.0.1:8000`).
  Serving it to other machines needs TLS and a separate, user-approved design.
- **Azure credential**: the caller lookup uses the operator's own read-only `az login`
  (`AzureCliCredential`, as `drift-engine who` does). The browser never holds Azure credentials
  and never calls Azure.

Generate a token and its digest locally:

```bash
python3 -c 'import hashlib, secrets; t = secrets.token_urlsafe(32); print(t); print(hashlib.sha256(t.encode()).hexdigest())'
```

## Running it

```bash
pip install -r requirements.txt
```

```bash
DASHBOARD_DATA_DIR=.artifacts/dashboard DASHBOARD_USERS_FILE=~/.config/aitdd/dashboard-users.json DASHBOARD_TERRAFORM_JSON=.artifacts/dashboard/terraform-state.json dashboard-api
```

`DASHBOARD_TERRAFORM_JSON` is optional: a local `terraform show -json` state (or plan JSON with
`prior_state`) that maps resource addresses to Azure resource IDs, the same input as
`drift-engine who --terraform`. Keep it out of the repository (it holds resource IDs).

## The UI

`dashboard-api` also serves the UI at `http://127.0.0.1:8000/`, from the same origin as the API:
exactly `index.html`, `app.js`, `render.js` and `styles.css` from `dashboard/` (override with
`DASHBOARD_UI_DIR`). The page itself holds no data and needs no sign-in; every data request
goes to `/api/*` with the bearer token.

- **Sign-in**: paste a dashboard token. It is held in memory only, so a reload signs out. The UI
  writes nothing to browser storage or cookies, holds no Azure credential and never calls Azure.
- **Overview cards**: Total Resources, Active Drifts, Security Exposure (HIGH or CRITICAL drifts,
  plus the AI report's security findings) and Monthly Cost Impact (`Not available` unless the AI
  report carries a validated estimate), all for the latest run per environment.
- **Severity breakdown** and **run history**.
- **Active drifts**: one row per drifted resource with its address and type, environment,
  severity, every changed property (expected → actual), the operation time and
  `Caller recorded by Azure`. Filters: run (latest per environment, or any run of the history),
  severity, resource type and environment. Users without `caller_reader` see
  "Not available (needs the caller_reader role)" instead of the caller.
- **Details**: a modal with the Terraform-style diff, the AI analysis narrative, the remediation
  recommendation and every option's approval and execution status.
- **Refresh**: on demand and every 60 s (can be switched off). Each refresh with callers
  queries the Activity Log again.
- **Security**: a strict Content-Security-Policy (`default-src 'none'`; scripts, styles and
  `connect-src` limited to the same origin; no inline code; no framing). Every value from the API
  is HTML-escaped before it is rendered.
- **Themes**: follows the system light/dark setting; the Theme button switches for the session.

Component tests: `node --test dashboard/render.test.js` (also run by `tests/test_dashboard_ui.py`).

## `Caller recorded by Azure`

- **What it shows**: the identity Azure Activity Log recorded as the caller of the drift's
  identified change: a user's name, or a service principal's or managed identity's name or
  identifier as Azure recorded it. It is **not proof of which physical person acted**, and it is
  never presented as the author of the drift.
- **How it is found**: the identified change is the decisive operation of the bound public
  investigation (verdict `sole_capable_operation` or `latest_capable_operation`). Its record is
  matched exactly as `drift-engine who` matches it (shared code `who.lookup_operation`): the
  operation's start/end ± 1 s, grouped as the investigation groups them, and exactly one group
  equal in operation name, start, end, outcome, relations, caller type and client application.
  The investigation already applied the 10-minute settling margin (G8).
- **`Unknown`** means the caller cannot be determined reliably. The `status` code says why:
  `no_investigation`, `no_decisive_operation`, `caller_missing`, `caller_inconsistent`,
  `no_match`, `multiple_matches`, `retention_exceeded` (older than the 90-day Activity Log
  retention), `query_failed`, `address_unknown`, `invalid_resource_id`,
  `resource_ids_unavailable` or `local_only` (refused inside GitHub Actions, G12).
- **Not stored**: the value exists only in the HTTP response, sent with `Cache-Control: no-store`.
  The application has no database, cache or output file, and its logs carry fixed codes and
  counts only. Azure keeps its own Activity Log records under its retention policy; not storing
  them here does not remove them from Azure.
- **Public artifacts are unchanged**: workflow artifacts and drift reports still say
  `caller_identity: withheld`.
