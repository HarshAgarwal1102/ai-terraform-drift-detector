"""Test-wide guard: no test may reach the network (Task 6.4).

The AI engine builds real LangChain/OpenAI clients in some tests. Every LLM in
the suite must be a fake or an httpx.MockTransport; this fixture turns any
outbound connection to a non-loopback address into an immediate error, so a
real LLM call cannot happen by accident. Loopback stays allowed for the
closed-port "unreachable endpoint" test.
"""

from __future__ import annotations

import ipaddress
import socket

import pytest

_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _is_loopback(address) -> bool:
    if isinstance(address, tuple) and address:
        host = address[0]
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return host == "localhost"
    return True  # AF_UNIX paths are local


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def guarded(method):
        def connect(self, address):
            if not _is_loopback(address):
                raise ConnectionRefusedError(f"network access is blocked in tests: {address!r}")
            return method(self, address)
        return connect

    monkeypatch.setattr(socket.socket, "connect", guarded(_real_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(_real_connect_ex))
