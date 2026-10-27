"""Tests for the Task 12.1 test infrastructure: tests.yml, the dev constraints and the test tiers.

Covers Decision 3 (ci/dev-constraints.txt: the complete `dev` closure, exact pins, no duplicate
of a pin in ci/ai- or ci/azure-constraints.txt, applied by requirements.txt), Decision 4 (the
`integration` and `mutation` markers) and Decision 5 (.github/workflows/tests.yml: contents: read,
no Azure, secrets or OIDC, actions pinned by full commit SHA, no caching, fast and full jobs).
No network, no subprocess: workflow structure is read with PyYAML, closures from installed metadata.
"""

from __future__ import annotations

import importlib.util
import re
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
PYPROJECT = ROOT / "pyproject.toml"
REQUIREMENTS = ROOT / "requirements.txt"
CI = ROOT / "ci"
FAST_TIER = '-m "not integration and not mutation"'
FULL_SETUP = all(importlib.util.find_spec(m) is not None for m in ("langgraph", "azure.identity"))

norm = lambda name: re.sub(r"[-_.]+", "-", name).lower()


def pins_of(path: Path) -> dict[str, str]:
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*==[0-9][0-9A-Za-z.+!-]*", line), line
        name, version = line.split("==")
        assert norm(name) not in pins, f"duplicate pin {name} in {path.name}"
        pins[norm(name)] = version
    return pins


def dev_closure(extra: str = "dev") -> dict[str, list]:
    """Every distribution the `dev` (or another) extra needs (markers evaluated for this interpreter, extras
    propagated)."""
    from importlib.metadata import PackageNotFoundError, requires
    from packaging.requirements import Requirement

    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    pending = [Requirement(spec) for spec in project["optional-dependencies"][extra]]
    closure: dict[str, list] = {}
    expanded: set[tuple[str, str]] = set()
    while pending:
        req = pending.pop()
        name = norm(req.name)
        closure.setdefault(name, []).append(req)
        for extra in [""] + sorted(req.extras):
            if (name, extra) in expanded:
                continue
            expanded.add((name, extra))
            try:
                children = requires(req.name) or []
            except PackageNotFoundError:
                pytest.fail(f"{req.name} (required by drift-engine[{extra}]) is not installed")
            for child in map(Requirement, children):
                if child.marker is None or child.marker.evaluate({"extra": extra}):
                    pending.append(child)
    return closure


# --------------------------------------------------------------------------- Decision 3: constraints


def test_dev_constraints_are_exact_and_never_repeat_another_pin():
    dev = pins_of(CI / "dev-constraints.txt")
    other = {**pins_of(CI / "ai-constraints.txt"), **pins_of(CI / "azure-constraints.txt")}
    assert sorted(set(dev) & set(other)) == [], "pinned again in dev-constraints.txt"
    for required in ("pytest", "pytest-cov", "coverage", "jsonschema"):
        assert required in dev, required


def test_shared_ai_and_azure_pins_agree():
    ai, azure = pins_of(CI / "ai-constraints.txt"), pins_of(CI / "azure-constraints.txt")
    assert {n: (ai[n], azure[n]) for n in set(ai) & set(azure) if ai[n] != azure[n]} == {}


def test_dev_constraints_equal_the_complete_dev_closure():
    """Every distribution `drift-engine[dev]` needs is pinned in one of the three files, and dev-constraints.txt
    pins nothing the dev extra does not need; every pin is inside the declared ranges."""
    dev = pins_of(CI / "dev-constraints.txt")
    every = {**pins_of(CI / "ai-constraints.txt"), **pins_of(CI / "azure-constraints.txt"), **dev}
    closure = dev_closure()
    assert sorted(set(closure) - set(every)) == [], "required by the dev extra but not pinned"
    assert sorted(set(dev) - set(closure)) == [], "pinned in dev-constraints.txt but not required by the dev extra"
    outside = sorted(f"{req} (pinned {every[name]})" for name, reqs in closure.items() for req in reqs
                     if not req.specifier.contains(every[name], prereleases=True))
    assert outside == [], "pins outside the declared ranges"


@pytest.mark.skipif(not FULL_SETUP, reason="needs the pinned full setup (pip install -r requirements.txt)")
def test_installed_dev_tools_match_their_pins():
    from importlib.metadata import version

    dev = pins_of(CI / "dev-constraints.txt")
    assert {n: (version(n), v) for n, v in dev.items() if version(n) != v} == {}


@pytest.mark.skipif(importlib.util.find_spec("fastapi") is None, reason="needs the dashboard extra")
def test_dashboard_constraints_equal_the_rest_of_the_dashboard_closure():
    """Task 13.1: ci/dashboard-constraints.txt pins exactly what the `dashboard` extra needs beyond the ai and
    azure pins, never repeats another file's pin, and stays inside the declared ranges."""
    dashboard = pins_of(CI / "dashboard-constraints.txt")
    other = {**pins_of(CI / "ai-constraints.txt"), **pins_of(CI / "azure-constraints.txt"),
             **pins_of(CI / "dev-constraints.txt")}
    assert sorted(set(dashboard) & set(other)) == [], "pinned again in dashboard-constraints.txt"
    closure = dev_closure("dashboard")
    every = {**other, **dashboard}
    assert sorted(set(closure) - set(every)) == [], "required by the dashboard extra but not pinned"
    assert sorted(set(dashboard) - set(closure)) == [], "pinned but not required by the dashboard extra"
    outside = sorted(f"{req} (pinned {every[name]})" for name, reqs in closure.items() for req in reqs
                     if not req.specifier.contains(every[name], prereleases=True))
    assert outside == [], "pins outside the declared ranges"


def test_requirements_apply_every_constraint_file():
    lines = [line.strip() for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    assert lines == ["-c ci/ai-constraints.txt", "-c ci/azure-constraints.txt", "-c ci/dashboard-constraints.txt",
                     "-c ci/dev-constraints.txt", "-e .[dev,ai,azure,dashboard]"]


# --------------------------------------------------------------------------- Decision 4: tiers


def test_tier_markers_are_registered_and_match_the_helper():
    import tiers

    ini = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    assert sorted(m.split(":")[0] for m in ini["markers"]) == ["integration", "mutation"]
    assert tiers.integration.name == "integration" and tiers.mutation.name == "mutation"


def test_unittest_files_take_markers_from_the_helper():
    """Files written for plain unittest never import pytest at module level (README: no-install run)."""
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        if "import unittest" in source and "\nimport pytest\n" not in source:
            assert "pytest.mark." not in source, path.name


# --------------------------------------------------------------------------- Decision 5: tests.yml


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def text():
    return WORKFLOW.read_text(encoding="utf-8")


def steps(workflow, job):
    return {s["name"]: s for s in workflow["jobs"][job]["steps"]}


def test_triggers_permissions_and_jobs(workflow):
    assert workflow.get("on", workflow.get(True)) == {"push": {"branches": ["main"]}, "pull_request": None,
                                                      "workflow_dispatch": None}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {"group": "tests-${{ github.ref }}", "cancel-in-progress": True}
    assert list(workflow["jobs"]) == ["fast", "full"]
    for job in workflow["jobs"].values():
        assert "permissions" not in job and job["runs-on"] == "ubuntu-24.04" and job["timeout-minutes"] > 0
        assert "env" not in job and "environment" not in job and "services" not in job


def test_no_azure_secrets_oidc_or_cache(text):
    lowered = text.lower()
    for forbidden in ("secrets.", "id-token", "azure/login", "arm_", "oidc_token", "actions/cache", "cache:",
                      "pull_request_target", "github.token", "write"):
        if forbidden == "id-token":
            assert "id-token:" not in lowered
        elif forbidden == "write":
            assert ": write" not in lowered
        else:
            assert forbidden not in lowered, forbidden


def test_actions_are_pinned_by_full_commit_sha(workflow, text):
    uses = [s["uses"] for job in workflow["jobs"].values() for s in job["steps"] if "uses" in s]
    assert sorted(set(uses)) == ["actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
                                 "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1",
                                 "hashicorp/setup-terraform@b9cd54a3c349d3f38e8881555d616ced269862dd"]
    for line in text.splitlines():
        if "uses:" in line:
            assert re.search(r"@[0-9a-f]{40} # v\d+\.\d+\.\d+$", line), line


@pytest.mark.parametrize("job", ["fast", "full"])
def test_setup_is_pinned_and_credential_free(workflow, job):
    s = steps(workflow, job)
    assert list(s)[:3] == ["Checkout Code", "Setup Python", "Install Pinned Dependencies"]
    assert s["Checkout Code"]["with"] == {"persist-credentials": False}
    assert s["Setup Python"]["with"] == {"python-version": "3.12"}
    install = s["Install Pinned Dependencies"]["run"]
    assert "set -euo pipefail" in install and "-r requirements.txt" in install and "pip check" in install


def test_full_job_installs_the_pinned_terraform_and_requires_it(workflow):
    """The real-Terraform regression tests run in CI, with the drift and auth workflows' exact Terraform."""
    s = steps(workflow, "full")
    assert list(s).index("Setup Terraform") == list(s).index("Run Full Suite") - 1
    reference = yaml.safe_load((WORKFLOW.parent / "terraform-auth-test.yml").read_text(encoding="utf-8"))
    pinned = {st["uses"] for job in reference["jobs"].values() for st in job["steps"]
              if st.get("uses", "").startswith("hashicorp/setup-terraform@")}
    assert pinned == {s["Setup Terraform"]["uses"]}  # the very same action reference
    assert s["Setup Terraform"]["with"] == {"terraform_version": reference["env"]["TERRAFORM_VERSION"],
                                            "terraform_wrapper": False}
    assert reference["env"]["TERRAFORM_VERSION"] == "1.14.7"
    assert s["Run Full Suite"]["env"] == {"AITDD_REQUIRE_REAL_TERRAFORM": "1"}  # fail, never skip
    assert "Setup Terraform" not in steps(workflow, "fast")  # the fast tier runs no integration test


def test_fast_job_runs_the_fast_tier_and_reports_runtime(workflow):
    run = steps(workflow, "fast")["Run Fast Tier"]["run"]
    assert FAST_TIER in run and "--strict-markers" in run and "tests/" in run
    assert "GITHUB_STEP_SUMMARY" in run and "::warning::" in run and run.rstrip().endswith('exit "$rc"')


def test_full_job_runs_everything_and_keeps_the_gate(workflow):
    s = steps(workflow, "full")
    run = s["Run Full Suite"]["run"]
    assert not re.search(r"\s-m\s+[\"']", run), "the full suite must not deselect any tier"
    assert "--strict-markers" in run and "--cov=src/drift_engine" in run
    assert run.rstrip().endswith('exit "$rc"')
    gate = s["Coverage Gate and Report"]["run"]
    assert "coverage report --include='src/drift_engine/*'\n" in gate  # fail_under from pyproject.toml
    assert "--fail-under=0" in gate.split("src/ai_engine")[1] and gate.rstrip().endswith('exit "$gate"')
    ini = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["coverage"]["report"]
    assert ini["fail_under"] == 85
