"""`dashboard-api`: serve the dashboard data API on a loopback address (Task 13.1).

Settings come from the environment (`app.create_app_from_env`). The server binds
only to a loopback address: bearer tokens and caller identity are never sent over
an unencrypted network connection. Exposing it beyond this machine needs a TLS
reverse proxy and a separate, user-approved design.

`--github-token-fd N` (Task 13.4; deprecated by Task 13.5, which connects GitHub from the
dashboard itself) reads a read-only GitHub token from an inherited file descriptor (for
example a pipe from `scripts/run_dashboard.sh --enable-github-fetch`) and closes it; the
token then lives only in the server's memory, marked "not verified yet". It is never taken
from an argument or an environment variable.

`--no-github` (Task 13.5 review) turns GitHub access off for this server: Connect GitHub and
Check GitHub are refused (503 `disabled`) and no token is ever held.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys

LOOPBACK_NAMES = ("localhost",)
MAX_TOKEN_BYTES = 1024


def is_loopback(host: str) -> bool:
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def read_token_fd(fd: int) -> str | None:
    """The token from file descriptor `fd` (closed afterwards), or None if it is empty, too long
    or not a single line of printable non-space characters."""
    chunks, total = [], 0
    try:
        while total <= MAX_TOKEN_BYTES:
            chunk = os.read(fd, MAX_TOKEN_BYTES + 1 - total)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
    except OSError:
        return None
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    data = b"".join(chunks)
    if total > MAX_TOKEN_BYTES:
        return None
    try:
        token = data.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    if not token or any(c.isspace() or not c.isprintable() for c in token):
        return None
    return token


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dashboard-api", description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1", help="loopback address to bind (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--github-token-fd", type=int, metavar="N",
                        help="deprecated: preload a read-only GitHub token from file descriptor N "
                             "(prefer Connect GitHub in the dashboard)")
    parser.add_argument("--no-github", action="store_true",
                        help="turn GitHub access off: Connect GitHub and Check GitHub are refused")
    args = parser.parse_args(argv)
    if not is_loopback(args.host):
        print("ERROR: dashboard-api binds only to a loopback address.", file=sys.stderr)
        return 2
    token = None
    if args.no_github and args.github_token_fd is not None:
        print("ERROR: --no-github cannot be combined with --github-token-fd.", file=sys.stderr)
        return 2
    if args.github_token_fd is not None:
        if args.github_token_fd < 3:
            print("ERROR: --github-token-fd must be 3 or higher.", file=sys.stderr)
            return 2
        token = read_token_fd(args.github_token_fd)
        if token is None:
            print("ERROR: no usable GitHub token on the given file descriptor.", file=sys.stderr)
            return 2
    import uvicorn

    from dashboard_api.app import create_app_from_env

    uvicorn.run(create_app_from_env(github_token=token, github_enabled=not args.no_github), host=args.host, port=args.port, server_header=False,
                log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
