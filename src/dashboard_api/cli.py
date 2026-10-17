"""`dashboard-api`: serve the dashboard data API on a loopback address (Task 13.1).

Settings come from the environment (`app.create_app_from_env`). The server binds
only to a loopback address: bearer tokens and caller identity are never sent over
an unencrypted network connection. Exposing it beyond this machine needs a TLS
reverse proxy and a separate, user-approved design.
"""

from __future__ import annotations

import argparse
import ipaddress
import sys

LOOPBACK_NAMES = ("localhost",)


def is_loopback(host: str) -> bool:
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dashboard-api", description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1", help="loopback address to bind (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not is_loopback(args.host):
        print("ERROR: dashboard-api binds only to a loopback address.", file=sys.stderr)
        return 2
    import uvicorn

    from dashboard_api.app import create_app_from_env

    uvicorn.run(create_app_from_env(), host=args.host, port=args.port, server_header=False, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
