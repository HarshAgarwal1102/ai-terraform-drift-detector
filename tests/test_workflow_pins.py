"""Level 1 workflow hardening (security audit findings F-5, F-6 and F-7) for every workflow.

- F-5: every action is pinned by a full commit SHA with its exact release as a comment;
- F-6: no workflow grants `id-token` at workflow level, so only a job that declares it can
  request a GitHub OIDC token;
- F-7: no checkout leaves the job's GITHUB_TOKEN in `.git/config`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.yml"))


def test_all_five_workflows_are_checked():
    assert [p.name for p in WORKFLOWS] == ["ai-analysis.yml", "drift-detection.yml", "security-scan.yml",
                                           "terraform-auth-test.yml", "tests.yml"]


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_actions_pinned_by_full_commit_sha(path):
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if re.match(r"\s*(- )?uses:", line)]
    assert lines
    for line in lines:
        assert re.search(r"uses: [\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$", line), line


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_workflow_level_oidc_and_no_persisted_checkout_credentials(path):
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "id-token" not in (workflow.get("permissions") or {})
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step.get("with", {}).get("persist-credentials") is False, step["name"]
