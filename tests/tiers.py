"""Test tier markers (Task 12.1, Decision 4) that also work without pytest.

The markers are registered in pyproject.toml. Files written for plain unittest
import them from here, so `python3 -m unittest discover -s tests` still runs
without pytest installed (README); there the decorators change nothing.
"""

from __future__ import annotations

try:
    import pytest
except ImportError:  # plain unittest without pytest: markers are a pytest feature
    def integration(obj):
        return obj

    mutation = integration
else:
    integration = pytest.mark.integration  # subprocess, bash harness, git or loopback server
    mutation = pytest.mark.mutation  # mutation, fuzz or leak-scan loop
