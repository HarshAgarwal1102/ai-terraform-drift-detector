"""Tests for the `ai-analysis` CLI and the no-LLM AI analysis workflow (Task 9A.1).

No network (tests/conftest.py guard), no LLM, no GitHub. Drift reports come from the
real classifier over the repository fixtures. The workflow's gate steps are executed
with synthetic inputs (missing artifact, failed report, wrong run binding), which
replaces a real "unknown" detection run that cannot be produced safely.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from drift_engine.classifier import evaluate

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
WORKFLOW = ROOT / ".github" / "workflows" / "ai-analysis.yml"
DRIFT_WORKFLOW = ROOT / ".github" / "workflows" / "drift-detection.yml"
CONSTRAINTS = ROOT / "ci" / "ai-constraints.txt"
PYPROJECT = ROOT / "pyproject.toml"

HAS_AI_EXTRA = importlib.util.find_spec("langgraph") is not None
requires_ai = pytest.mark.skipif(not HAS_AI_EXTRA, reason="needs the 'ai' extra")
LLM_ENV = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
           "AZURE_OPENAI_DEPLOYMENT", "AI_LLM_MODEL", "AI_LLM_PROVIDER", "GITHUB_ACTIONS")


def report(group: str, name: str) -> dict:
    base = FIXTURES / group / name
    plan = next((base / f for f in ("plan.synthetic.json", "plan.sanitized.json") if (base / f).exists()),
                base / "plan.json")
    return evaluate(str(plan), str(base / "detection_run.json")).report


def write_json(path: Path, data) -> Path:
    path.write_text(json.dumps(data, indent=2) if not isinstance(data, str) else data, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch):
    for name in LLM_ENV:
        monkeypatch.delenv(name, raising=False)


def run_cli(*args: str) -> int:
    from ai_engine.cli import main
    return main(list(args))


# --------------------------------------------------------------------------- CLI


@requires_ai
@pytest.mark.parametrize("fixture", ["external_drift", "in_sync"])  # has_drift true and false
def test_writes_report_without_llm(tmp_path, capsys, fixture):
    src = write_json(tmp_path / "drift_report.json", report("plan_evidence", fixture))
    before = src.read_bytes()
    assert run_cli("--report", str(src), "--output-dir", str(tmp_path / "out")) == 0
    files = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert files == ["ai_analysis_report.json", "ai_analysis_report.md"]
    data = json.loads((tmp_path / "out" / "ai_analysis_report.json").read_text())
    assert data["llm"]["attempted"] is False and data["llm"]["provider"] == "none"
    assert data["llm"]["evidence_sent"] == []
    assert all(section["status"] == "skipped" for section in data["analysis"].values())
    assert data["remediation"]["automatic_apply"] is False
    assert data["attribution"]["actor"] == "unknown"  # no caller identity or Activity Log data (D5)
    assert src.read_bytes() == before  # the drift report is never changed
    assert "AI analysis report written" in capsys.readouterr().out


@requires_ai
def test_output_is_deterministic(tmp_path):
    src = write_json(tmp_path / "drift_report.json", report("plan_evidence", "drift_and_config_change"))
    for out in ("a", "b"):
        assert run_cli("--report", str(src), "--output-dir", str(tmp_path / out)) == 0
    for name in ("ai_analysis_report.json", "ai_analysis_report.md"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


@requires_ai
@pytest.mark.parametrize("content, message", [
    (None, "cannot read"),
    ("{not json", "not valid JSON"),
    ({"outcome": "succeeded"}, "does not match the report contract"),
    ("FAILED_RUN", "drift status is unknown"),
])
def test_rejected_input_writes_nothing(tmp_path, capsys, content, message):
    src = tmp_path / "drift_report.json"
    if content == "FAILED_RUN":
        write_json(src, report("plan_evidence", "failed_run"))
    elif content is not None:
        write_json(src, content)
    out = tmp_path / "out"
    assert run_cli("--report", str(src), "--output-dir", str(out)) == 1
    assert not out.exists()
    err = capsys.readouterr().err
    assert message in err and "Nothing was written" in err


@requires_ai
@pytest.mark.parametrize("provider, expected", [(None, 2), ("openai", 2), ("azure_openai", 2), ("", 2), ("none", 0)])
def test_github_actions_requires_explicit_none(tmp_path, monkeypatch, capsys, provider, expected):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    if provider is not None:
        monkeypatch.setenv("AI_LLM_PROVIDER", provider)
    src = write_json(tmp_path / "drift_report.json", report("plan_evidence", "external_drift"))
    assert run_cli("--report", str(src), "--output-dir", str(tmp_path / "out")) == expected
    if expected == 2:
        assert "explicitly 'none'" in capsys.readouterr().err
        assert not (tmp_path / "out").exists()


@requires_ai
def test_invalid_ai_configuration_is_usage_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AI_LLM_PROVIDER", "bogus")
    src = write_json(tmp_path / "drift_report.json", report("plan_evidence", "external_drift"))
    assert run_cli("--report", str(src), "--output-dir", str(tmp_path / "out")) == 2
    assert "invalid AI configuration" in capsys.readouterr().err


@requires_ai
def test_write_error_is_73(tmp_path):
    src = write_json(tmp_path / "drift_report.json", report("plan_evidence", "external_drift"))
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x")
    assert run_cli("--report", str(src), "--output-dir", str(blocker)) == 73


@requires_ai
def test_internal_error_is_70(tmp_path, monkeypatch, capsys):
    import ai_engine.graph

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(ai_engine.graph, "run_analysis", boom)
    src = write_json(tmp_path / "drift_report.json", report("plan_evidence", "external_drift"))
    assert run_cli("--report", str(src), "--output-dir", str(tmp_path / "out")) == 70
    assert "drift result is unaffected" in capsys.readouterr().err


def test_usage_errors_exit_2():
    from ai_engine.cli import main
    with pytest.raises(SystemExit) as exc:
        main(["--report", "x.json"])
    assert exc.value.code == 2


def test_missing_ai_extra_is_a_clear_usage_error(tmp_path):
    """Without langgraph (core install), the command explains the ai extra and exits 2."""
    code = (
        "import sys, importlib.abc\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in ('langgraph', 'langchain_openai', 'langchain_core'):\n"
        "            raise ModuleNotFoundError(f'No module named {name!r}', name=name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "from ai_engine.cli import main\n"
        f"sys.exit(main(['--report', {str(tmp_path / 'r.json')!r}, '--output-dir', {str(tmp_path / 'o')!r}]))\n"
    )
    env = {k: v for k, v in os.environ.items() if k not in LLM_ENV}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
    assert result.returncode == 2, result.stderr
    assert "'ai' extra is not installed" in result.stderr


def test_drift_engine_never_imports_ai_engine():
    for path in (ROOT / "src" / "drift_engine").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        names += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not [n for n in names if n.startswith("ai_engine")], path


def test_entry_points_and_core_dependencies():
    text = PYPROJECT.read_text(encoding="utf-8")
    scripts = re.search(r"\[project\.scripts\]\n(.*?)\n\[", text, re.S).group(1)
    entries = dict(re.findall(r'^([\w-]+) = "([^"]+)"', scripts, re.M))
    assert entries == {"drift-engine": "drift_engine.cli:main", "ai-analysis": "ai_engine.cli:main"}
    core = re.search(r"^dependencies = \[(.*?)\]", text, re.S | re.M).group(1)
    assert sorted(re.findall(r'"([A-Za-z0-9_-]+)', core)) == ["PyYAML", "pydantic"]  # no LLM stack in the core


def test_cli_module_does_not_import_langgraph_at_import_time():
    tree = ast.parse((ROOT / "src" / "ai_engine" / "cli.py").read_text(encoding="utf-8"))
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    modules = [a.name for n in top if isinstance(n, ast.Import) for a in n.names]
    modules += [n.module or "" for n in top if isinstance(n, ast.ImportFrom)]
    assert not [m for m in modules if m.startswith(("ai_engine", "langgraph", "langchain"))]


# --------------------------------------------------------------------------- constraints (D2)


def constraint_pins() -> dict[str, str]:
    pins = {}
    for line in CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*==[0-9][0-9A-Za-z.+!-]*", line), line
        name, version = line.split("==")
        key = re.sub(r"[-_.]+", "-", name).lower()
        assert key not in pins, f"duplicate pin {name}"
        pins[key] = version
    return pins


def test_constraints_pin_every_package_exactly():
    pins = constraint_pins()
    for required in ("langgraph", "langchain-openai", "langchain-core", "openai", "pydantic", "pydantic-core",
                     "pyyaml", "httpx"):
        assert required in pins, required
    major = lambda v: int(v.split(".")[0])
    assert major(pins["langgraph"]) == 1 and major(pins["langchain-openai"]) == 1
    assert major(pins["pyyaml"]) == 6
    assert major(pins["pydantic"]) == 2 and int(pins["pydantic"].split(".")[1]) >= 11


def resolved_ai_closure() -> dict[str, list]:
    """Every distribution `drift-engine[ai]` needs, from pyproject.toml and the installed metadata.

    Maps each normalised name to the requirements pointing at it. Markers are evaluated for
    this interpreter, with each requirement's extras propagated (e.g. `foo[bar]` pulls in
    foo's `extra == "bar"` dependencies); drift-engine itself is not part of the set.
    """
    import tomllib
    from importlib.metadata import PackageNotFoundError, requires
    from packaging.requirements import Requirement

    norm = lambda name: re.sub(r"[-_.]+", "-", name).lower()
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    pending = [Requirement(spec) for spec in project["dependencies"] + project["optional-dependencies"]["ai"]]
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
                pytest.fail(f"{req.name} (required by drift-engine[ai]) is not installed")
            for child in map(Requirement, children):
                if child.marker is None or child.marker.evaluate({"extra": extra}):
                    pending.append(child)
    return closure


@requires_ai
def test_constraints_equal_the_complete_ai_closure():
    """D2: ci/ai-constraints.txt is exactly the resolved drift-engine[ai] set, every entry exact.

    Fails for a missing pin (including indirect ones such as jiter), a non-exact entry, an
    extra pin nothing requires, a pin outside a requirement's range, or an installed version
    that differs from its pin (the test environment is installed with the constraints).
    """
    from importlib.metadata import version

    pins = constraint_pins()  # asserts that every entry is name==version, without duplicates
    closure = resolved_ai_closure()
    assert sorted(set(closure) - set(pins)) == [], "required but not pinned"
    assert sorted(set(pins) - set(closure)) == [], "pinned but not required by drift-engine[ai]"
    outside = sorted(f"{req} (pinned {pins[name]})" for name, reqs in closure.items() for req in reqs
                     if not req.specifier.contains(pins[name], prereleases=True))
    assert outside == [], "pins outside the declared ranges"
    mismatched = sorted(f"{name}: installed {version(name)}, pinned {pins[name]}" for name in closure
                        if version(name) != pins[name])
    assert mismatched == [], "installed versions differ from the pins"


# --------------------------------------------------------------------------- workflow structure (D3-D6)


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def steps_by_name(workflow) -> dict[str, dict]:
    return {s["name"]: s for s in workflow["jobs"]["ai-analysis"]["steps"]}


def test_trigger_permissions_concurrency(workflow):
    trigger = workflow.get("on", workflow.get(True))
    assert trigger == {"workflow_run": {"workflows": ["Phase 5 - Drift Detection"], "types": ["completed"],
                                       "branches": ["main"]}}
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}
    assert workflow["concurrency"] == {"group": "ai-analysis-${{ github.event.workflow_run.id }}",
                                       "cancel-in-progress": False}
    assert list(workflow["jobs"]) == ["ai-analysis"]


def test_job_environment_forces_no_llm(workflow):
    job = workflow["jobs"]["ai-analysis"]
    assert job["env"] == {
        "AI_LLM_PROVIDER": "none",
        "SOURCE_RUN_ID": "${{ github.event.workflow_run.id }}",
        "SOURCE_RUN_ATTEMPT": "${{ github.event.workflow_run.run_attempt }}",
        "SOURCE_BRANCH": "${{ github.event.workflow_run.head_branch }}",
        "SOURCE_EVENT": "${{ github.event.workflow_run.event }}",
    }
    for key in ("permissions", "continue-on-error", "environment", "needs", "outputs"):
        assert key not in job


def test_no_secrets_azure_or_llm_credentials(workflow):
    code = "\n".join(ln for ln in WORKFLOW.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#"))
    for forbidden in ("secrets.", "id-token", "azure/login", "ARM_", "TF_VAR_", "AZURE_", "OPENAI", "AI_LLM_MODEL",
                      "continue-on-error", "issues", "pull-requests", "write-all", "terraform"):
        assert forbidden not in code, forbidden
    steps = steps_by_name(workflow)
    users = [name for name, step in steps.items() if "github.token" in json.dumps(step)]
    assert users == ["Download source drift report"]


def test_steps_download_install_and_upload(workflow):
    steps = steps_by_name(workflow)
    assert list(steps) == ["Verify source run", "Download source drift report", "Check for a valid detection result",
                           "Checkout Code", "Setup Python", "Install AI analysis (pinned)",
                           "Validate and bind the drift report", "Run AI analysis (no LLM)", "Summary (counts only)",
                           "Upload AI analysis report"]
    download = steps["Download source drift report"]
    assert download["uses"] == "actions/download-artifact@v4"
    assert download["with"] == {"pattern": "drift-report-${{ github.event.workflow_run.id }}",
                                "run-id": "${{ github.event.workflow_run.id }}",
                                "github-token": "${{ github.token }}", "path": "${{ runner.temp }}/source"}
    assert steps["Checkout Code"]["with"] == {"persist-credentials": False}
    assert steps["Setup Python"]["with"] == {"python-version": "3.12"}
    assert '-c ci/ai-constraints.txt ".[ai]"' in steps["Install AI analysis (pinned)"]["run"]
    upload = steps["Upload AI analysis report"]
    assert upload["uses"] == "actions/upload-artifact@v4"
    assert upload["with"]["name"] == "ai-analysis-report-${{ github.event.workflow_run.id }}"
    assert upload["with"]["retention-days"] == 30 and upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["path"].splitlines() == ["${{ runner.temp }}/ai-analysis/ai_analysis_report.json",
                                              "${{ runner.temp }}/ai-analysis/ai_analysis_report.md"]
    for name in ("Checkout Code", "Setup Python", "Install AI analysis (pinned)", "Validate and bind the drift report"):
        assert steps[name]["if"] == "${{ steps.present.outputs.present == 'true' }}", name
    for name in ("Run AI analysis (no LLM)", "Summary (counts only)", "Upload AI analysis report"):
        assert steps[name]["if"] == "${{ steps.gate.outputs.valid == 'true' }}", name
    assert 'ai-analysis --report "${REPORT}" --output-dir "${RUNNER_TEMP}/ai-analysis"' in \
        steps["Run AI analysis (no LLM)"]["run"]


def test_existing_automation_untouched():
    drift = DRIFT_WORKFLOW.read_text(encoding="utf-8")
    for marker in ("ai-analysis", "ai_engine", "AI_LLM"):
        assert marker not in drift, marker
    tree = ast.parse((ROOT / "scripts" / "github_automation.py").read_text(encoding="utf-8"))
    modules = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    modules += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not [m for m in modules if m.startswith("ai_engine")]  # Phase 8 issues never carry AI content


# --------------------------------------------------------------------------- gate steps, executed (D4, binding)


def run_step(workflow, name: str, tmp_path: Path, env: dict[str, str]):
    output = tmp_path / "github_output"
    summary = tmp_path / "step_summary"
    output.write_text("")
    summary.write_text("")
    full = {**{k: v for k, v in os.environ.items() if k not in LLM_ENV},
            "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}",
            "RUNNER_TEMP": str(tmp_path / "runner"), "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(summary), "SOURCE_RUN_ID": "123", "SOURCE_RUN_ATTEMPT": "2",
            "SOURCE_BRANCH": "main", "SOURCE_EVENT": "schedule", **env}
    result = subprocess.run(["bash", "-c", steps_by_name(workflow)[name]["run"]], env=full, capture_output=True,
                            text=True, timeout=120)
    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines() if "=" in line)
    return result, outputs, summary.read_text()


@pytest.mark.parametrize("branch, event, ok", [("main", "schedule", True), ("main", "workflow_dispatch", True),
                                               ("feature", "schedule", False), ("main", "push", False),
                                               ("main", "pull_request", False)])
def test_source_run_verification(workflow, tmp_path, branch, event, ok):
    result, _, _ = run_step(workflow, "Verify source run", tmp_path, {"SOURCE_BRANCH": branch, "SOURCE_EVENT": event})
    assert (result.returncode == 0) is ok, result.stdout


def test_missing_artifact_means_unknown_not_failure(workflow, tmp_path):
    result, outputs, summary = run_step(workflow, "Check for a valid detection result", tmp_path, {})
    assert result.returncode == 0
    assert outputs == {"present": "false"}
    assert "Detection result unknown: no AI analysis" in summary


def source_report(tmp_path: Path, data) -> Path:
    directory = tmp_path / "runner" / "source" / "drift-report-123"
    directory.mkdir(parents=True, exist_ok=True)
    return write_json(directory / "drift_report.json", data)


def test_present_artifact_is_detected(workflow, tmp_path):
    path = source_report(tmp_path, report("plan_evidence", "in_sync"))
    result, outputs, _ = run_step(workflow, "Check for a valid detection result", tmp_path, {})
    assert result.returncode == 0 and outputs == {"present": "true", "report": str(path)}


def bound(fixture: str, run_id: str | None = "github-123-2") -> dict:
    data = report("plan_evidence", fixture)
    if data.get("run") is not None:
        data["run"]["run_id"] = run_id
    return data


@pytest.mark.parametrize("fixture", ["external_drift", "in_sync"])  # has_drift true and false
def test_valid_bound_report_is_analysed(workflow, tmp_path, fixture):
    path = source_report(tmp_path, bound(fixture))
    result, outputs, _ = run_step(workflow, "Validate and bind the drift report", tmp_path, {"REPORT": str(path)})
    assert result.returncode == 0, result.stdout + result.stderr
    assert outputs == {"valid": "true"}


@pytest.mark.parametrize("data", ["FAILED", "{not json", {"outcome": "succeeded"}])
def test_invalid_report_means_unknown(workflow, tmp_path, data):
    path = source_report(tmp_path, bound("failed_run") if data == "FAILED" else data)
    result, outputs, summary = run_step(workflow, "Validate and bind the drift report", tmp_path,
                                        {"REPORT": str(path)})
    assert result.returncode == 0, result.stdout + result.stderr
    assert outputs == {"valid": "false"}
    assert "Detection result unknown: no AI analysis" in summary


@pytest.mark.parametrize("run_id", ["github-123-1", "github-124-2", "local-20261001T171607Z-1", None])
def test_report_from_another_run_or_attempt_fails(workflow, tmp_path, run_id):
    path = source_report(tmp_path, bound("external_drift", run_id))
    result, outputs, _ = run_step(workflow, "Validate and bind the drift report", tmp_path, {"REPORT": str(path)})
    assert result.returncode == 1
    assert outputs.get("valid") != "true"
    assert "does not match 'github-123-2'" in result.stdout


@requires_ai
def test_summary_has_counts_only(workflow, tmp_path):
    out = tmp_path / "runner" / "ai-analysis"
    src = write_json(tmp_path / "drift_report.json", report("plan_evidence", "external_drift"))
    assert run_cli("--report", str(src), "--output-dir", str(out)) == 0
    result, _, summary = run_step(workflow, "Summary (counts only)", tmp_path, {})
    assert result.returncode == 0, result.stderr
    rows = [line for line in summary.splitlines() if line.startswith("| ") and not line.startswith("| ---")]
    assert [row.split("|")[1].strip() for row in rows] == ["Field", "Source run", "Resources", "Remediation options",
                                                           "AI sections analysed", "LLM", "Artifact"]
    assert "| Resources | 1 |" in summary and "| AI sections analysed | 0 of 5 |" in summary
    assert "`none` / `not_attempted`" in summary
