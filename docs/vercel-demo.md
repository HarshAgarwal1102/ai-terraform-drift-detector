# Vercel dashboard demo

A read-only preview of the Phase 13 dashboard on Vercel, for testing and portfolio demonstration. It runs the
existing FastAPI application and UI unchanged, on the `vercel-demo` branch only, over the three public runs
already committed in `tests/fixtures/dashboard/real_9b6`. No database, external backend, GitHub token, Azure
sign-in or Terraform state is involved.

## What is deployed

| File | Purpose |
|---|---|
| `index.py` | Entry point Vercel detects. Builds the existing app (`dashboard_api.app.create_app`) with a fixed demo configuration; reads nothing from the process environment. |
| `vercel.json` | FastAPI preset, the install command, and the files left out of the function bundle (`excludeFiles`). |
| `deploy/vercel/requirements.txt` | The 11 runtime packages (FastAPI closure), versions from `ci/*-constraints.txt`, hash-pinned. |
| `.python-version` | Python 3.13, the interpreter the pins were resolved and tested on. |
| `deploy/vercel/users.json` | One account, `demo-viewer`, role `viewer`, SHA-256 digest only. |
| `.vercelignore` | Allowlist of what `vercel deploy` may upload from a checkout. |
| `scripts/new_vercel_demo_token.py` | Creates or rotates the demo token (never uploaded). |

Why a custom install command: when `pyproject.toml` is present, Vercel's Python builder runs `uv sync` on it
and ignores `requirements.txt`; that installs only the base dependencies, not the `dashboard` extra (FastAPI).
The install command in `vercel.json` installs `deploy/vercel/requirements.txt` instead
(`--require-hashes --no-deps --only-binary=:all:`). The repository's own `requirements.txt` and
`pyproject.toml` are unchanged.

## What works and what is off

Works, exactly as locally: bearer sign-in, Overview, drift table and filters, Run History and every run's
report, AI analysis, cost, remediation options, the strict Content-Security-Policy, `Cache-Control: no-store`
and the other security headers. The UI and `/api/*` are served from one origin.

Intentionally off:

- **Connect GitHub / Check GitHub for new runs**: started with `github_enabled=False`; the API answers
  503 `disabled` and the dashboard says GitHub access is turned off. A serverless function has no persistent
  disk, process or memory for the fetch job, and no GitHub token belongs on Vercel.
- **Caller recorded by Azure**: the demo account lacks `caller_reader` (403 `caller_access_denied`); in
  addition no Terraform state is configured and the Activity Log source refuses every query, so even a
  misconfigured account can never reach Azure.
- **New data**: the demo shows only the committed fixtures. Changing them needs a commit and a redeploy.

## Environment variables

None are required, and none are read: `index.py` fixes the data directory, users file and disabled features
in code. Do not add `DASHBOARD_*`, `GH_TOKEN`, `GITHUB_TOKEN`, Azure or Terraform variables to the Vercel
project; they would have no effect, and secrets do not belong there.

## The viewer account

The committed `deploy/vercel/users.json` holds only the digest of a token generated for this demo (it is not
your local dashboard token). The token itself is in `.artifacts/dashboard-local/vercel-demo-viewer-token.txt`
(mode 0600, ignored by git and by `.vercelignore`). Move it to a password manager and delete the file once
the demo works.

To create a new token (for example for a fresh clone, or to rotate):

```bash
python3 scripts/new_vercel_demo_token.py
```

It rewrites `deploy/vercel/users.json` (one `viewer`-only account, digest only, mode 0644) and writes the new
token to the token file above; it never prints the token. Commit the users file on `vercel-demo` and redeploy.
Never give the demo account `caller_reader` or `data_refresher`.

The users file must not be writable by group or others: `dashboard_api.auth` then refuses it and every
request fails with 503 `auth_unavailable` (it fails closed). Git stores it as 100644, so a normal checkout
and Vercel's build keep it at 0644.

## Deploy a preview (Vercel UI)

1. Push the `vercel-demo` branch to GitHub (only this branch holds the demo files).
2. In Vercel: **Add New… → Project → Import** `HarshAgarwal1102/ai-terraform-drift-detector`.
3. Configure the project:
   - **Root Directory**: `./` (the repository root).
   - **Framework Preset**: FastAPI (`vercel.json` also sets it).
   - **Build and Output Settings**: leave the overrides off. `vercel.json` provides the install command.
   - **Environment Variables**: none.
4. Deploy. Vercel builds the repository's production branch (`main`) first. `main` has no entry point, so
   that build is expected to fail and serves nothing. Then, under **Settings → Git**, either keep `main` as
   the production branch and use the Preview deployments that every push to `vercel-demo` creates, or set the
   production branch to `vercel-demo`.
5. In the build log, check for `Successfully installed … fastapi-0.143.3 …` (the custom install command) and
   no errors about missing modules.

Deployment Protection: the dashboard calls its API with `credentials: "omit"`, so Vercel Authentication's
cookie never reaches `/api/*`. On a deployment protected by Vercel Authentication, the page may load while
every API call is stopped by Vercel, and the sign-in screen shows a connection error. If so, test on a URL
without Vercel Authentication (the production domain under Standard Protection), or turn Vercel
Authentication off for this project. The dashboard's own bearer sign-in still protects every `/api/*`
endpoint.

## Verify

Replace `URL` with the deployment URL.

```bash
curl -sI URL/ | grep -iE "^(http|content-security-policy|cache-control|x-frame-options)"
```

```bash
curl -s URL/api/summary
```

The first shows `200`, the strict CSP, `no-store` and `DENY`. The second answers
`{"error":"unauthenticated"}`. Then open `URL` in a browser and sign in with the token. Check that:

- Run History lists three runs (`github-38105671846-1`, `github-38109121618-1`, `github-38111406531-1`),
  and the 11 October run shows the `tags` drift on the resource group;
- the drift table says caller identity is hidden for this user;
- the GitHub panel says GitHub access is turned off;
- a wrong token is refused.

## Remove the demo or rotate the token

- **Rotate**: run `scripts/new_vercel_demo_token.py`, commit, redeploy, then delete the older deployments in
  **Project → Deployments**. Every deployment is immutable and keeps accepting the token it was built with.
- **Remove**: delete the project in **Settings → Advanced → Delete Project** (this removes all its
  deployments and URLs). Delete the local token file, and the `vercel-demo` branch if it is no longer needed.
- If the token was exposed, rotate first, then delete every deployment built before the rotation.

## Local checks

```bash
pytest tests/test_vercel_demo.py
```

These checks run without Vercel. They load the entry point the way Vercel does and cover:

- sign-in;
- the three runs;
- disabled GitHub and caller lookup, including for a user holding every role;
- security headers;
- the pins against `ci/*-constraints.txt`;
- what `.vercelignore` and `excludeFiles` let through.
