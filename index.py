"""Vercel entry point of the read-only dashboard demo (`vercel-demo` branch, docs/vercel-demo.md).

Vercel serves the ASGI `app` of this file. It is the existing dashboard (`dashboard_api.app.create_app`,
unchanged: bearer sign-in, public drift report validation, CSP and security headers, UI and API from one
origin) with a fixed demo configuration that the deployment environment cannot change:

- data: the committed public fixtures under `tests/fixtures/dashboard` (read-only): `real_9b6` (three real
  runs) and `real_10_4` (run #44 `github-38140497702-1`, with its five unmanaged resources);
- sign-in: `deploy/vercel/users.json` (SHA-256 digests only; the demo account holds `viewer` only);
- GitHub: off (`github_enabled=False`): Connect GitHub and Check GitHub are refused with 503 `disabled`
  and no GitHub token is ever accepted;
- Azure caller lookup: off. No Terraform state is configured and the Activity Log source below refuses
  every query, so no Azure SDK, `az login` or network request is ever made, whatever a user's roles are.

The process environment is never read: DASHBOARD_* variables, tokens or credentials set on the
deployment have no effect.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
# The deployment installs the pinned runtime dependencies (deploy/vercel/requirements.txt), not this
# project, so its packages are imported from src/ here.
sys.path.insert(0, os.path.join(ROOT, "src"))

from dashboard_api.app import create_app  # noqa: E402
from drift_engine import activity_logs as al  # noqa: E402

DATA_DIR = os.path.join(ROOT, "tests", "fixtures", "dashboard")
USERS_FILE = os.path.join(ROOT, "deploy", "vercel", "users.json")
UI_DIR = os.path.join(ROOT, "dashboard")


class NoActivityLog:
    """The demo's Activity Log source: every query fails as `credential_unavailable` (no Azure sign-in),
    so a caller is always shown as Unknown. It never touches the network or the Azure SDK."""

    def pages(self, subscription_id: str, query_filter: str):
        raise al.SourceError("credential_unavailable")


def create_demo_app(users_file: str = USERS_FILE):
    """The demo dashboard. `users_file` is replaced only by tests."""
    return create_app(data_dir=DATA_DIR, users_file=users_file, terraform_json=None, source=NoActivityLog(),
                      environ={}, ui_dir=UI_DIR, github_token=None, github_enabled=False)


app = create_demo_app()
