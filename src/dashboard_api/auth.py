"""Dashboard sign-in and authorization (Task 13.1).

Bearer tokens, one per dashboard user, configured in a local users file
(`DASHBOARD_USERS_FILE`) that holds only SHA-256 digests of the tokens:

    {"users": [{"name": "maintainer", "token_sha256": "<64 hex>",
                "roles": ["viewer", "caller_reader"]}]}

- `viewer`: every `/api/*` endpoint without caller identity;
- `caller_reader`: additionally `include_caller=true` (needs `viewer` too).

Every comparison is constant-time over all users. The file must be a regular file
that neither group nor others can write (the digests decide who sees caller
identity), and is re-read on every request so a removed user loses access at once.
No token, digest or user name is ever logged.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from dataclasses import dataclass

ROLES = ("caller_reader", "viewer")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_USERS_FILE_BYTES = 64 * 1024


class UsersFileError(Exception):
    """The users file is missing, unsafe or invalid (fixed code, never content)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class User:
    name: str
    roles: frozenset[str]


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def load_users(path: str) -> list[tuple[str, User]]:
    """(token digest, user) pairs. Raises UsersFileError."""
    try:
        info = os.lstat(path)
    except (OSError, TypeError, ValueError):
        raise UsersFileError("users_file_missing") from None
    if not stat.S_ISREG(info.st_mode):
        raise UsersFileError("users_file_not_regular")
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise UsersFileError("users_file_writable_by_others")
    if info.st_size > MAX_USERS_FILE_BYTES:
        raise UsersFileError("users_file_too_large")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        raise UsersFileError("users_file_invalid") from None
    users = doc.get("users") if isinstance(doc, dict) else None
    if not isinstance(users, list):
        raise UsersFileError("users_file_invalid")
    pairs, digests = [], set()
    for entry in users:
        if not (isinstance(entry, dict) and set(entry) == {"name", "token_sha256", "roles"}
                and isinstance(entry["name"], str) and _NAME.match(entry["name"])
                and isinstance(entry["token_sha256"], str) and _DIGEST.match(entry["token_sha256"])
                and isinstance(entry["roles"], list) and all(r in ROLES for r in entry["roles"])
                and entry["token_sha256"] not in digests):
            raise UsersFileError("users_file_invalid")
        digests.add(entry["token_sha256"])
        pairs.append((entry["token_sha256"], User(entry["name"], frozenset(entry["roles"]))))
    return pairs


def authenticate(authorization: str | None, users: list[tuple[str, User]]) -> User | None:
    """The user whose token is presented as `Authorization: Bearer <token>`, else None."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    presented = token_digest(token.strip())
    found = None
    for digest, user in users:  # no early exit: the time does not depend on which user matched
        if hmac.compare_digest(presented, digest):
            found = user
    return found
