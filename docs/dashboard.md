# Dashboard

Phase 13. This page covers the dashboard data API (Task 13.1, `src/dashboard_api/`), the
dashboard UI (Task 13.2, `dashboard/`) and the live-data integration (Task 13.3,
`scripts/fetch_dashboard_data.py`).

## Quick start (one command)

```bash
scripts/run_dashboard.sh --fetch
```

Or double-click `scripts/Start Dashboard.command` in Finder (macOS). It does everything:

1. uses `.venv` (creates it if missing) and installs the dashboard dependencies there if they are
   missing (pinned by `ci/*-constraints.txt`; first run only);
2. on the first run creates `.artifacts/dashboard-local/users.json` (only the SHA-256 digest of the
   token, 0600) and prints your **sign-in token once**; `--new-token` replaces it;
3. with `--fetch`, or when `.artifacts/dashboard` is empty, asks for a read-only GitHub token
   (hidden input, never stored) and downloads the latest artifacts and drift issues;
4. starts the dashboard on `http://127.0.0.1:8000/` (loopback only) and opens it in the browser.

Then paste the sign-in token. Stop with Ctrl+C. Later runs need no options:
`scripts/run_dashboard.sh`. For the `Caller recorded by Azure` field, run `az login` and pass a
local `terraform show -json` state: `scripts/run_dashboard.sh --terraform-json PATH` (or save it as
`.artifacts/dashboard-local/terraform-state.json`). Other options: `--port N`, `--no-browser`,
`--help`. Everything it writes stays in the ignored `.venv/` and `.artifacts/`.

To check GitHub for new runs, connect a GitHub token from inside the dashboard
(**Connect GitHub**, see "Connect GitHub and check for new runs" below): no startup flag is needed.

## Connect GitHub and check for new runs (Tasks 13.4 and 13.5)

The dashboard reads only the local `.artifacts/dashboard` folder, and works fully offline. New
GitHub Actions runs (the daily drift detection and its AI analysis) reach it through
`scripts/fetch_dashboard_data.py`. The **Check GitHub for new runs** button runs that same script on
request; it is not a second implementation, and it never triggers a Terraform plan or apply, a new
drift scan or a new workflow run.

### Normal startup and connecting GitHub

1. `scripts/run_dashboard.sh` (no flag). The dashboard is fully usable without any GitHub token.
2. Sign in with the **dashboard sign-in token** printed once by the launcher.
3. Click **Connect GitHub** (toolbar) and paste a **GitHub personal access token**. This is a
   different credential from the dashboard sign-in token; the dialog says so. The dashboard never
   treats the sign-in token as a GitHub token.
4. **Verify and connect** checks the token with three read-only requests to
   `HarshAgarwal1102/ai-terraform-drift-detector`: the repository, its Actions artifacts and its
   issues. While it checks, the field is locked and shows mask dots (the token itself has already
   left the page: the field's value is emptied before the request is sent). On success the dialog
   closes and the toolbar shows **GitHub: connected**; on failure the field is unlocked, empty and
   focused, with the reason in red.
   A token that can read the artifacts but not the issues (no **Issues: Read**) is accepted with a warning:
   reports are downloaded, only the drift issue states stay as they were. The chip then says
   "verified; lacks Issues: Read".
5. To replace a token (for example after a failure), click **GitHub: connected**, paste the new one
   and choose **Verify and replace**; to forget it, **Disconnect GitHub**. Neither needs a restart.
   A token that fails verification is discarded and an earlier working one stays in use.

**Required permissions** (read-only, on that repository only): a fine-grained token with
**Actions: Read**, **Issues: Read** and Metadata: Read (granted automatically); a classic token needs
the `repo` scope (broader than needed; prefer a fine-grained token). Never grant write access.

### Token handling

- **Session-only, in memory**: the token travels once, in the body of `POST /api/github/connect`
  (`Content-Type: application/json`, over the loopback connection, with your dashboard sign-in
  token), and is kept in the dashboard server's memory only. A restart of `dashboard-api` forgets it
  and you connect again. **It is never persisted**: no file, no keychain, no browser storage, no
  cookie, no URL, no command-line argument, no environment variable, no log line, no report. Saving
  it would create a plaintext secret at rest, and the project has no OS-credential-store layer; a
  future opt-in option would need one and its own review.
- **Browser password managers**: the GitHub token field is not a password field inside a submitted form
  (the pattern browsers offer to save). It is a text field masked by CSS (`-webkit-text-security`; where a
  browser lacks that, it falls back to a password field so the token is never shown in clear), outside any
  `<form>`, with `autocomplete="off"`, spell checking off and the ignore hints of common password managers
  (`data-1p-ignore`, `data-lpignore`, `data-bwignore`). Enter and the button still submit it. This makes a
  save prompt unlikely but cannot guarantee that no browser or extension ever offers one: if one appears,
  decline it. Trade-offs of a masked text field: a screen reader may speak the typed characters (it treats
  it as text, not as a password), and the text can be selected and copied. The dashboard sign-in field is
  unchanged: saving the sign-in token in a password manager is
  what the launcher recommends.
- **The page never keeps it**: the field is emptied before the request leaves, the response never
  contains it, and signing out clears a half-typed one. The server hands it to the fetch script only
  on its standard input; it goes to `https://api.github.com` and nowhere else.
- **Limits**: Python cannot wipe a string from memory. Dropping a variable only removes one name for it;
  other copies (the parsed request body, pipe buffers) live until they are garbage-collected, and the
  memory is only certainly released when the dashboard process stops.
  Anyone who can already run code as you on this machine can read the server's memory.
- **Browser protections**: the connection endpoints need the `data_refresher` role, refuse a request
  whose `Origin` is not the dashboard's own, and accept only `application/json`. Authentication is a
  bearer header that a browser never attaches by itself, so there is no cookie to forge.
- **Turning GitHub off**: `scripts/run_dashboard.sh --no-github` (or `DASHBOARD_NO_GITHUB=1`) starts the
  dashboard with GitHub access off (`dashboard-api --no-github`): Connect GitHub and Check GitHub are
  refused (`disabled`), nothing is downloaded at startup, and `users.json` is not touched, so a
  `data_refresher` role you removed stays removed. It cannot be combined with `--fetch` or
  `--enable-github-fetch`.
- **`users.json` problems never stop the launcher**: if the file is not valid JSON, not UTF-8, not the
  expected shape, unreadable, a link or not a regular file, the launcher prints one warning, never rewrites
  or regenerates its content (a regular file still gets mode 0600, as before, where that is allowed) and starts; the dashboard then refuses every sign-in (503
  `auth_unavailable`) until you fix it or run `--new-token`. Nothing is granted on a failed check.
- **`--enable-github-fetch` (Task 13.4) is deprecated but still works**: it asks for a token in the
  terminal and preloads it over a pipe (`--github-token-fd 3`); such a token is shown as "not
  verified yet" until a fetch succeeds or you connect again. Prefer **Connect GitHub**. The launcher
  now always gives `local-admin` the `data_refresher` role (the sign-in token is unchanged).

### What a failed verification or fetch says

| Shown | Meaning (from GitHub's actual answer) |
| --- | --- |
| invalid, expired or revoked (HTTP 401) | GitHub did not accept the token. GitHub does not say which of the three it is. |
| lacks a required repository permission (HTTP 403) | The token works but needs **Actions: Read** or **Issues: Read**; the message names the one that failed. |
| must be authorized for SAML single sign-on (HTTP 403) | GitHub sent `X-GitHub-SSO`: authorize the token for the organization. |
| repository could not be accessed (HTTP 404) | GitHub hides repositories a token cannot see: the token may not include this repository. Not necessarily a wrong token. |
| rate-limited | GitHub is temporarily limiting requests (HTTP 429; or 403 with `X-RateLimit-Remaining: 0`, `Retry-After`, or a "rate limit" message, the secondary limits). Wait, then retry. Verification never retries on its own. |
| could not be reached | Network error or timeout. Retry. |
| unexpected error (HTTP 5xx) | GitHub failed; retry later. |

A failed check names the problem separately from the token: `invalid_token`, a refused Actions access,
`repository_not_accessible` and `sso_required` mark the token unverified (each with its own message); an
Issues-only refusal is only a warning; rate limits, network and write failures leave the token state alone. Only these fixed
categories and the HTTP status are shown (to tell a secondary rate limit from a missing permission the
script reads at most 4 KB of a 403 answer and looks only for the words "rate limit"); GitHub's response text, URLs and the token
are never displayed or logged. The category is kept in the fetch status (`category`, `http_status`).

### The fetch status window

- **Check GitHub for new runs** starts the fetch (`POST /api/fetch`) and opens the **GitHub fetch
  status** window. If GitHub is not connected, the button opens a **Connect GitHub first** popup
  instead (with **Not now** and **Connect GitHub**, which opens the connection dialog); the
  "not connected" explanation lives in that popup, not on the page.
- The window is **non-modal**: you can keep browsing runs, drifts and reports behind it, and the
  latest local data is always shown. It lists the connection state, the fetch status (Idle, Running,
  Completed, Completed with a warning, Failed), the start time, the elapsed time, how many artifacts
  were downloaded and how many were skipped because they were already saved, the stages
  (Connecting to GitHub, Listing artifacts, Downloading new reports, Updating drift issue state,
  Refreshing dashboard data) and, after a problem, the category and HTTP status. There is no
  percentage: the fetch cannot measure one, so only the stage it is truly in is marked.
- The **–** button (or Escape while the window has focus) only minimises the window: the fetch keeps running in the
  background and its status is kept. **Fetch status** (toolbar) reopens it, also after a completed or
  failed check. Nothing here cancels a fetch (cancellation is not offered). After **Disconnect GitHub**
  the window closes and the **Fetch status** button is removed until GitHub is connected again.
- **Retry** appears after a failure; **Replace GitHub token** after a token or permission problem.
- When a fetch ends, the dashboard discards its request cache and reloads the local reports
  ("Refreshing dashboard data").

### Local Refresh versus GitHub

**Refresh** and the 60-second auto-refresh only re-read the local folder: they never contact GitHub or
start a fetch, work offline and are independent of the connection. Only **Check GitHub for new runs**
talks to GitHub. A failed check never removes or changes saved reports.

### Troubleshooting

- *Invalid, expired or revoked*: create a new token, then **GitHub: connected** (or **Connect GitHub**)
  and paste it. Check that you pasted the GitHub token, not the dashboard sign-in token.
- *Lacks permission*: edit the token to add Actions: Read and Issues: Read for this repository.
- *Repository could not be accessed*: the fine-grained token must list this repository (or all your
  repositories) as a resource; for an organization repository the organization must allow the token.
- *Rate-limited*: wait the time GitHub asks (usually minutes), then retry.
- *The button is disabled*: the status window or the line next to the button gives the reason
  (not connected, local-only inside GitHub Actions, no data folder, fetch script missing, shutting down).

### How it works

- **Who sees it**: only users with the `data_refresher` role (`POST /api/fetch` and
  `/api/github/*` refuse others with 403 `fetch_access_denied`).
- **What happens on a click**: the server starts the fetch as one background job (the token on the
  script's standard input, `--token-stdin`; a fixed command and a minimal environment), and the page
  polls `GET /api/fetch/status` every 2 seconds. The script prints `dashboard_stage=` markers while it
  works and one fixed result line at the end; only those lines are read.
- **Limits**: one fetch at a time (409 `fetch_in_progress`), a 2-minute cooldown between starts
  (429 `fetch_cooldown` with `Retry-After`), a 10-minute overall timeout; one verification at a time
  (409 `verification_in_progress`) and at least 2 seconds between verifications (429 `verify_too_soon`).
  A token cannot be replaced or removed while a fetch runs. The connect body must declare its length and
  be at most 4 KB (411 `length_required`, 413 `request_too_large`), checked before it is read.
- **Stopping**: on the timeout, or when the dashboard stops (Ctrl+C), the fetch gets SIGTERM,
  removes its own staging files and exits; if it does not exit within 5 seconds it is killed.
  A job never stays "running". (If the dashboard process itself is killed with SIGKILL, a running
  fetch is not stopped; it ends on its own and its writes stay atomic.)
- **Watching a running check**: the page polls every 2 seconds; after a failed poll it backs off
  (4, 8, 16, up to 30 seconds), and after 5 failed polls in a row it stops and says it lost contact
  with the dashboard server. It also stops watching after 11 minutes. Hiding the window does not
  stop the polling.
- **Network settings**: only `HTTPS_PROXY`/`https_proxy`, `NO_PROXY`/`no_proxy`, `SSL_CERT_FILE`
  and `SSL_CERT_DIR` are passed from the dashboard's environment to the fetch. Nothing else is (in
  particular never `GITHUB_API_URL` or `GH_TOKEN`).
- **Manual use of the script**: `scripts/fetch_dashboard_data.py --token-stdin` asks for the token
  without echoing it in a terminal; `--verify-only` makes the three read-only checks and prints one
  `dashboard_verify=` line.
- **Downloads**: the script's existing rules apply (eligible artifacts of `main` runs only, already
  present ones skipped, bounded sizes, atomic writes). Interrupted downloads leave only hidden
  `.fetch-*` / `.issues-*` staging entries, which the dashboard never reads and the next fetch
  removes after an hour; drift reports must validate as the public drift report model.

## What it serves

A read-only API over the **real artifacts** of the drift detection and AI analysis workflows. It
never computes drift itself, never estimates a value that no artifact holds, and has no database.

| Artifact | File | Bound to a drift report by |
| --- | --- | --- |
| Drift report (public) | `drift_report.json` | key: `run.run_id` |
| AI analysis report | `ai_analysis_report.json` | `provenance.run_id` and `provenance.drift_report_sha256` (canonical SHA-256) |
| Public investigation | `drift_investigation.json` | `investigation_public.load_public` (leak scan, strict model) and `check_binding` |
| Cost run | `cost_run.json` | `run_id` and `drift_report_sha256` |
| Unmanaged inventory (Task 10.4) | `unmanaged_inventory.json` | `unmanaged_public.load_inventory` (strict model, public leak scan); `binding.run_id` and `binding.drift_report_sha256` |

The data directory may use any layout; `gh run download <run-id> --dir <data-dir>` works as is.
It is re-indexed on every request and never written to. An artifact that is not bound to a
report is ignored; two different documents for one slot make it ambiguous and neither is used;
two different reports for one run id are both skipped. Problems are reported as fixed codes
(`data_problems` in `/api/summary`, `problems` per run).

## Live data (Task 13.3)

The dashboard shows only what real workflow runs produced. `scripts/fetch_dashboard_data.py`
fills the data directory from GitHub:

```bash
GH_TOKEN=<read-only token> python3 scripts/fetch_dashboard_data.py --repository HarshAgarwal1102/ai-terraform-drift-detector --data-dir .artifacts/dashboard
```

- **Artifacts**: every non-expired `drift-report-<id>`, `drift-investigation-<id>`,
  `ai-analysis-report-<id>`, `infracost-report-<id>` and `unmanaged-inventory-<id>` artifact of a run on `main`, created in
  the last `--days` (default 30). Only the expected JSON file is extracted; an artifact already
  in the data directory is never fetched again (artifacts are immutable).
- **Drift issues**: a snapshot (`github_issues.json`) of the issues labelled `drift-detected`
  that the automation bot opened (Tasks 8.1 and 8.3): number, URL, state, close reason,
  timestamps and the marker's fingerprint, run and plan timestamp. No title, body or user is
  stored. The dashboard matches a drift to its issue by the fingerprint of
  (environment, address) and time: the issue of a drift seen by run R is the earliest issue with
  that fingerprint that was still open when R finished (the issues job creates it just after the
  run; a later in-sync run closes it as `completed`). It states the snapshot time. Without a snapshot it shows "No issue data"; with one but no match,
  "No drift issue found".
- **Remediation PRs**: automated remediation pull requests do not exist in this project
  (Task 8.2 is blocked, superseded by Phase 11, which is on hold), so every drift shows
  "No remediation PR" with that reason; no PR state is invented.
- **Result line**: `dashboard_fetch=ok …` with counts; `dashboard_fetch=failed step=artifacts …`
  when the artifact listing fails; `dashboard_fetch=partial step=issues reason=listing_failed
  detail=http_403 …` when artifacts were fetched but the issue listing was refused (the token
  lacks "Issues: read"). The exit status is 1 in both failure cases.
- **Refresh**: `--every 300` repeats the fetch every 5 minutes; the API re-reads the data
  directory on every request and the UI refreshes every 60 s.
- **Token**: `GH_TOKEN` needs read access to the repository's Actions artifacts and issues
  only (for example a fine-grained token with "Actions: read" and "Issues: read", or
  `gh auth token`). It is sent only to `api.github.com`; artifact downloads follow the
  redirect to storage without it. It is never printed or stored.

## Endpoints

All are `GET` and need `Authorization: Bearer <token>` of a user with the `viewer` role.

| Endpoint | Returns |
| --- | --- |
| `/api/summary` | Overview (total resources, active drifts, security exposure, monthly cost impact) of the latest run per environment, per-environment run summaries, and the run history (newest first, at most 100). |
| `/api/drifts` | Drifted resources of the latest run per environment, or of `report_id`. Filters: `environment`, `severity`, `resource_type`. Each row: resource, type, classification, severity, every changed property with its expected (`desired`) and actual (`real`) value, the decisive operation (name, start, end, caller type, client application), the AI narrative and the remediation recommendation. |
| `/api/reports/{report_id}` | One run: summary, drift rows, remediation options and the bound artifacts themselves. |
| `/api/unmanaged` | Resources in the Terraform-managed resource groups that Terraform does not manage, for the latest run per environment or `report_id`: inventory outcome, counts, scopes and resources, with each resource's list-price estimate. |
| `/api/remediations` | Remediation options of the AI report with approval status and execution state (`allowed: false`, `manual_after_approval`). The approver identity is never returned. |
| `/api/fetch/status` | The "Check GitHub for new runs" job: `status` (idle, running, new_artifacts, no_new_artifacts, partial, failed), fixed `code`, counts, start and finish times, whether it is `available` (if not, `unavailable_reason`: `disabled`, `not_connected`, `local_only`, `no_data_dir`, `fetch_script_missing` or `shutting_down`), the cooldown and seconds left (`retry_after_seconds`), whether this user is `allowed` to start it, the current `stage` (`connecting`, `listing`, `downloading`, `issues`), `elapsed_seconds`, the failure `category` / `http_status` / `need` (`actions` or `issues`) and the token's `connection` state (`connected`, `source`, `verified`, `last_error`, `warning`, `last_attempt`; never the token). Read-only. |
| `POST /api/fetch` | Starts the job (needs `data_refresher`; 202). It accepts no parameters. |
| `POST /api/github/connect` | Task 13.5: body `{"token": "<GitHub token>"}` (`application/json` only). Verifies it with read-only GitHub requests and keeps it in memory when accepted. Answers `verification` (`ok`, `category`, `http_status`, `need`) plus the fetch state; never the token. Needs `data_refresher`. |
| `POST /api/github/disconnect` | Task 13.5: forgets the token (409 while a fetch runs). Needs `data_refresher`. |

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
  request `include_caller=true` (403 otherwise; a refused request never queries Azure);
  `data_refresher` may also connect GitHub and start "Check GitHub for new runs" (`POST /api/github/connect`,
  `/api/github/disconnect`, `POST /api/fetch`).
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
exactly `index.html`, `app.js`, `render.js`, `loader.js` and `styles.css` from `dashboard/` (override with
`DASHBOARD_UI_DIR`). The page itself holds no data and needs no sign-in; every data request
goes to `/api/*` with the bearer token.

- **Open it from `dashboard-api`**: the UI calls `/api/*` on its own origin, so it works only
  when served by `dashboard-api`. Opened any other way (a static file server, a file preview),
  `/api/*` answers with that server's 404 page; the sign-in screen then says "The dashboard API
  was not found at …" before a token is entered (it used to show `Could not load data (http_404)`
  after sign-in, for any token).
- **Sign-in**: paste a dashboard token. It is held in memory only, so a reload signs out. The UI
  writes nothing to browser storage or cookies, holds no Azure credential and never calls Azure.
- **Overview cards**: Total Resources, Active Drifts, Security Exposure (HIGH or CRITICAL drifts,
  plus the AI report's security findings) and Monthly Cost Impact, all for the latest run per
  environment. Monthly Cost Impact shows the confirmed-drift amount of a validated estimate,
  "No drift cost" when the validated estimate has no cost line for confirmed drift (every real
  in-sync run; never shown as `$0`), or "Not available" when there is no validated estimate.
- **Severity breakdown** and **run history**: the history (newest first, at most 100 runs) sits in a
  fixed-height box that scrolls with a sticky header, and a search box filters it by run id (or
  just the GitHub run number), finish date, environment or highest severity; every word typed must
  match. It shows "N of M run(s)". Each row also shows the run's unmanaged resources and their
  estimated cost ("5 · $44.85/month"; "—" when the run has no inventory). **Click a row (or focus
  it and press Enter) to open that run**: the Run filter, Active drifts, remediations and the
  Unmanaged resources panel switch to it, and the row stays highlighted.
- **Active drifts**: one row per drifted resource with its address and type, environment,
  severity, every changed property (expected → actual), the operation time,
  `Caller recorded by Azure` and the GitHub issue state. A line above the table says which run
  is shown. An empty table says why: "Run … found no drift: all N managed resource(s) were in
  sync" for an in-sync run, or "No drift matches the filters (N hidden)" when filters hide rows. Filters: run (latest per environment, or any run of the history),
  severity, resource type and environment. Users without `caller_reader` see
  "Not available (needs the caller_reader role)" instead of the caller.
- **Unmanaged resources** panel: the inventory of the selected run (or the latest per
  environment): name (or "name withheld"), type, resource group, location, whether it is not
  managed by Terraform or attached to a managed resource, and its estimated monthly cost.
  Amounts come only from the AI report's validated `unmanaged` section (report v4 only, Azure
  Retail Prices API list prices, not billing), and only when it priced exactly the inventory
  shown for this run (same canonical SHA-256, and the cost's own binding names this run and
  drift report); otherwise the reason is shown and no amount. The Monthly Cost Impact card reads
  the drift cost only from report v3/v4, after validating the embedded `cost_delta` and its
  binding to the run; report v2 and unknown versions never show an amount. Unmanaged resources are
  never drift and never change the drift counts. Runs before Task 10.4 show
  "No unmanaged-resource inventory for this run".
- **GitHub drift issues** panel: the drift issues of the run on screen (the run clicked in Run history
  or chosen in the Run filter, else the latest run per environment), that is, exactly the issues the
  Active drifts rows link to, with resource, state and resolution (`closed · completed` when the drift
  was resolved). An in-sync run says so instead of listing issues. **Show all issues (N)** lists every
  drift issue of the snapshot; opening another run goes back to that run's issues.
- **Details**: a modal with the Terraform-style diff, the AI analysis narrative, the GitHub issue
  state, the remediation PR state, the remediation recommendation and every option's approval
  and execution status.
- **Refresh**: on demand and every 60 s (can be switched off). Each refresh with callers
  queries the Activity Log again.
- **Opening a run** (Run History row, Enter, or the Run filter): the drift, remediation and
  unmanaged requests start together, and each panel renders as soon as its own response
  arrives. The drift rows come first, from the artifacts (tens of milliseconds); the
  `Caller recorded by Azure` values need a live Activity Log query per operation (about a second
  each on real Azure, the queries of one response run concurrently, at most 4 at a time), so a
  `caller_reader` sees "Looking up…" in that field until they arrive. A response for a run the
  user has already left is ignored. A response younger than 60 s is reused (`dashboard/loader.js`,
  in page memory only): clicking the same run again sends nothing new, and going back to a recent
  run is instant. Refresh, auto-refresh, sign-out and a reload discard it; failed requests are
  never kept, so the next click or Refresh retries.
- **Security**: a strict Content-Security-Policy (`default-src 'none'`; scripts, styles and
  `connect-src` limited to the same origin; no inline code; no framing). Every value from the API
  is HTML-escaped before it is rendered.
- **Themes**: follows the system light/dark setting; the Dark mode rocker switch in the top bar overrides it for the session.
- **Top bar**: the Dark mode switch and Sign out sit in the top bar; on phones (640 px and narrower) they move into an account menu behind the person key (Escape or a click outside closes it).
- **Sign-in page**: on screens 900 px and wider, a brand panel (what the tool does) sits beside the sign-in card, with a CSS-only loop of the detection workflow above it and a radar sweep behind the card; the token field has a show/hide toggle. Phones show the card only.
- **Sign-in and sign-out popups**: signing in opens a popup that verifies the token, then shows **Access granted** (and opens the dashboard) or **Access denied** on a 401, with Try again; other errors still appear in the status line. Sign out asks for confirmation first (Cancel is focused; Escape cancels).

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
- **No single identified change** (e.g. verdict `ambiguous`: several capable operations since
  the anchor): the drift has no single caller, so its value stays `Unknown`
  (`no_decisive_operation`). The field then also lists every operation of the resource in the
  public investigation (`operations`: `op_id`, operation name, start, end, role, and its own
  `value`, `caller_type` and `status`), each looked up by the same `who.lookup_operation`, as
  `drift-engine who` lists them. Each line is the caller Azure recorded for that operation, never
  the drift's caller; an operation whose evidence is unavailable is `Unknown` with its own
  status code. Example: `github-38109121618-1` (Control A) has `op-1` (R2's tag write) and `op-2`
  (R3's tag write), and two different recorded callers.
- **Where it appears**: the `Caller recorded by Azure` column of every Active drifts row and the
  same field in the drift's details panel, with the caller type (user, service principal,
  managed identity) and a note that it is the identity Azure recorded, not proof of which person
  made the change. Only for users with `caller_reader`; others see "Not available (needs the
  caller_reader role)".
- **What it needs**: the dashboard host's own `az login` (read-only Activity Log access) and a
  local `terraform show -json` state mapping addresses to Azure resource IDs
  (`DASHBOARD_TERRAFORM_JSON`; the launcher uses `.artifacts/dashboard-local/terraform-state.json`
  when present). The lookup runs only on the server; the browser never holds an Azure credential.
- **`Unknown`** means the caller cannot be determined reliably. The `status` code says why:
  `no_investigation`, `activity_log_not_settled` (the investigation's evidence had not passed
  the 10-minute settling margin: no lookup is made), `no_decisive_operation` (no single
  identified change, e.g. an ambiguous verdict; per-operation callers listed when the resource
  has operations, see above), `caller_missing`, `caller_inconsistent`,
  `no_match`, `multiple_matches`, `retention_exceeded` (older than the 90-day Activity Log
  retention), `azure_sign_in_unavailable` (no usable `az login` on the dashboard host),
  `azure_access_denied` (the signed-in identity may not read the Activity Log), `query_failed`,
  `address_unknown` (resource not in the local Terraform state), `invalid_resource_id`,
  `resource_ids_unavailable` (no local Terraform state configured) or `local_only` (refused
  inside GitHub Actions, G12).
- **Not stored**: the value exists only in the HTTP response, sent with `Cache-Control: no-store`.
  The application has no database, cache or output file, and its logs carry fixed codes and
  counts only. The browser keeps the responses it shows in page memory for at most 60 s so
  that reopening a run needs no new Activity Log query; never in browser storage or cookies,
  and discarded on Refresh, sign-out or reload. Azure keeps its own Activity Log records under its retention policy; not storing
  them here does not remove them from Azure.
- **Public artifacts are unchanged**: workflow artifacts and drift reports still say
  `caller_identity: withheld`.
