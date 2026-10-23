#!/usr/bin/env python3
"""Create or rotate the sign-in token of the Vercel dashboard demo (docs/vercel-demo.md).

Standard library only. Generates a new random token (32 bytes, `secrets.token_urlsafe(32)`, the same
form `scripts/run_dashboard.sh` uses), and:

  --users-file  (default deploy/vercel/users.json) is rewritten with ONE account, `demo-viewer`, role
                `viewer` only, holding the token's SHA-256 digest; the token itself is never written there;
  --token-file  (default .artifacts/dashboard-local/vercel-demo-viewer-token.txt, ignored by git and by
                .vercelignore) receives the token, mode 0600, replaced atomically.

The token is never printed. Read it from the token file, keep it in a password manager, then commit the
users file and redeploy: every earlier deployment keeps accepting the old token until it is deleted.

Exit codes: 0 written, 64 usage (unusable path).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_USERS = os.path.join(ROOT, "deploy", "vercel", "users.json")
DEFAULT_TOKEN = os.path.join(ROOT, ".artifacts", "dashboard-local", "vercel-demo-viewer-token.txt")


def _replace(path: str, data: bytes, mode: int) -> None:
    """Write `data` to `path` atomically with `mode` (a half-written file never appears)."""
    directory = os.path.dirname(path)
    fd, staging = tempfile.mkstemp(prefix=".new-", dir=directory)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(staging, path)
    except BaseException:
        try:
            os.remove(staging)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--users-file", default=DEFAULT_USERS)
    parser.add_argument("--token-file", default=DEFAULT_TOKEN)
    args = parser.parse_args(argv)
    for path in (args.users_file, args.token_file):
        if os.path.islink(path) or os.path.isdir(path):
            print(f"ERROR: {path} is a link or a directory.", file=sys.stderr)
            return 64
    try:
        os.makedirs(os.path.dirname(args.token_file), mode=0o700, exist_ok=True)
        token = secrets.token_urlsafe(32)
        _replace(args.token_file, (token + "\n").encode("ascii"), 0o600)
        users = {"users": [{"name": "demo-viewer", "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                            "roles": ["viewer"]}]}
        # 0644: dashboard_api.auth refuses a users file that group or others can write.
        _replace(args.users_file, (json.dumps(users, indent=2) + "\n").encode("utf-8"), 0o644)
    except OSError as exc:
        print(f"ERROR: could not write the token or users file ({exc.strerror}).", file=sys.stderr)
        return 64
    print(f"New demo-viewer token written to {args.token_file} (mode 0600); digest written to {args.users_file}.")
    print("Commit the users file and redeploy; delete older deployments, which still accept the old token.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
