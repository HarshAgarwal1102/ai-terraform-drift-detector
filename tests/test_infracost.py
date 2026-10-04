"""Task 10.1: Infracost cost estimate (scripts/infracost_analysis.sh, scripts/sanitize_infracost.py,
and the cost steps / cost job in .github/workflows/drift-detection.yml).

No live Infracost, no API key, no network (the test-wide guard in conftest.py stays active; the
shell script only ever runs a fake `infracost` from a temporary PATH). The sanitiser is always the
real scripts/sanitize_infracost.py (PROJECT_PLAN.md I1: no stand-in for acceptance).

Raw samples (tests/fixtures/infracost/raw/*.raw.json) are the unmodified Infracost v0.10.46 outputs
of the D9 run-2 live check (synthetic VCS values injected at run time), except that the one real
local absolute path in projects[].metadata.path was replaced by the synthetic absolute path
/home/runner/work/_temp/drift/plan.json (still absolute, so dropping paths stays tested).
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

from drift_engine.classifier import evaluate

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "infracost_analysis.sh"
SANITIZER = ROOT / "scripts" / "sanitize_infracost.py"
WORKFLOW = ROOT / ".github" / "workflows" / "drift-detection.yml"
FIXTURE = ROOT / "tests" / "fixtures" / "infracost"
PLAN = FIXTURE / "service_plan_sku_drift" / "plan.synthetic.json"
MANIFEST = FIXTURE / "service_plan_sku_drift" / "detection_run.json"
RAW_SKU = FIXTURE / "raw" / "service_plan_sku_drift.raw.json"
RAW_SYNC = FIXTURE / "raw" / "in_sync.raw.json"
RUN_ID = "synthetic-infracost-fixture"  # run.run_id of the fixture's manifest
KEY = "ico-SENTINELKEY-0123456789abcdef"  # never a real key; must never appear anywhere
BASH = shutil.which("bash") or "/bin/bash"
PINNED_SHA256 = "d0d081cd39b07b2ca5c315830bfc4bcdfb0183b04c19cb18835c154482a2c97b"
PINNED_URL = "https://github.com/infracost/infracost/releases/download/v0.10.46/infracost-linux-amd64.tar.gz"
# D6 amendment (CI run #20): the runner re-injects the OIDC request variables into every run: step after the
# step env: is applied, so the cost step re-executes its own shell without them as its first command.
REEXEC = [
    'if [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}${ACTIONS_ID_TOKEN_REQUEST_TOKEN:-}" ]; then',
    "  shopt -s execfail",
    '  exec env -u ACTIONS_ID_TOKEN_REQUEST_URL -u ACTIONS_ID_TOKEN_REQUEST_TOKEN bash --noprofile --norc -eo pipefail '
    '"$0" || true',
    "fi",
]
OIDC_SENTINEL = "runner-oidc-request-token-SENTINEL"
D7_CONTROLS = {"INFRACOST_SKIP_UPDATE_CHECK": "true", "INFRACOST_ENABLE_CLOUD": "false",
               "INFRACOST_DISABLE_ENVFILE": "true", "INFRACOST_NO_COLOR": "true", "CHECKPOINT_DISABLE": "1"}
REASON_CODES = {"none", "usage", "install_failed", "missing_api_key", "oidc_token_present", "azure_session_present",
                "version_mismatch", "infracost_failed", "unexpected_egress", "raw_output_invalid", "price_not_found",
                "sanitize_failed"}


def load_module(path: Path, name: str, source: str | None = None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if source is None:
        spec.loader.exec_module(module)
    else:
        exec(compile(source, str(path), "exec"), module.__dict__)
    return module


san = load_module(SANITIZER, "sanitize_infracost_under_test")


def raw(path: Path = RAW_SKU) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def comp(data: dict, breakdown: str = "breakdown") -> dict:
    return data["projects"][0][breakdown]["resources"][0]["costComponents"][0]


def no_floats(text: str):
    def reject(value):
        raise AssertionError(f"JSON float found: {value}")
    return json.loads(text, parse_float=reject)


@pytest.fixture(scope="module")
def drift_report_path(tmp_path_factory) -> Path:
    report = evaluate(str(PLAN), str(MANIFEST)).report
    assert report["run"]["run_id"] == RUN_ID and report["run"]["environment"] == "dev"
    path = tmp_path_factory.mktemp("drift") / "drift_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def write_raw(tmp: Path, data, name: str = "raw.json") -> Path:
    path = tmp / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def sanitize(tmp: Path, raw_path: Path, report: Path, run_id: str = RUN_ID, environment: str = "dev",
             version: str = "v0.10.46", module=None) -> tuple[int, Path]:
    out = tmp / "report"
    out.mkdir(exist_ok=True)
    argv = ["--raw", str(raw_path), "--drift-report", str(report), "--run-id", run_id, "--environment", environment,
            "--infracost-version", version, "--output-dir", str(out)]
    return (module or san).main(argv), out


def check(out: Path, report: Path, run_id: str = RUN_ID, module=None) -> int:
    return (module or san).main(["--check", str(out), "--run-id", run_id, "--drift-report", str(report)])


def cli(*args: str) -> int:
    return subprocess.run([sys.executable, str(SANITIZER), *args], capture_output=True, text=True).returncode


# --------------------------------------------------------------------------- sanitiser: real samples (D8)


@pytest.mark.parametrize("raw_path", [RAW_SKU, RAW_SYNC], ids=["sku_drift", "in_sync"])
def test_real_samples_sanitise_to_the_allowlist(tmp_path, drift_report_path, raw_path):
    rc, out = sanitize(tmp_path, raw_path, drift_report_path)
    assert rc == 0
    assert sorted(p.name for p in out.iterdir()) == ["cost_run.json", "infracost.json"]
    text = (out / "infracost.json").read_text(encoding="utf-8")
    data = no_floats(text)  # every number in the output is a decimal string (or an integer count)
    assert set(data) <= {"version", "currency", "timeGenerated", "summary", "projects", *san.ROOT_DECIMALS}
    for project in data["projects"]:
        assert set(project) <= set(san.BREAKDOWNS)  # no name, displayName, metadata or per-project summary
        for key in project:
            for resource in project[key]["resources"]:
                assert set(resource) <= {"name", "resourceType", "costComponents", "subresources",
                                         *san.RESOURCE_DECIMALS}
                for component in resource.get("costComponents", []):
                    assert set(component) <= {"name", "unit", "priceNotFound", *san.COMPONENT_DECIMALS}
    for dropped in ("metadata", "vcs", "synthetic", "example.invalid", "/home/runner", "tags", "displayName",
                    "providers", "infracostCommand"):
        assert dropped not in text, dropped


def test_sku_sample_keeps_the_d3_values_as_decimal_strings(tmp_path, drift_report_path):
    rc, out = sanitize(tmp_path, RAW_SKU, drift_report_path)
    data = json.loads((out / "infracost.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert (data["pastTotalMonthlyCost"], data["totalMonthlyCost"], data["diffTotalMonthlyCost"]) == \
        ("119.72", "13.14", "-106.58")
    assert (data["totalMonthlyUsageCost"], data["pastTotalMonthlyUsageCost"], data["diffTotalMonthlyUsageCost"]) == \
        ("0", "0", "0")
    assert comp(data, "pastBreakdown")["price"] == "0.164" and comp(data)["price"] == "0.018"
    assert comp(data, "diff") == {"name": "Instance usage (P1v3 → B1)", "unit": "hours", "hourlyQuantity": "0",
                                  "monthlyQuantity": "0", "price": "-0.146", "hourlyCost": "-0.146",
                                  "monthlyCost": "-106.58", "priceNotFound": False}
    assert data["projects"][0]["diff"]["resources"][0]["monthlyUsageCost"] == "0"
    assert data["summary"]["noPriceResourceCounts"] == {"azurerm_resource_group": 1}
    # The values are copied exactly as Infracost wrote them.
    source = raw()
    assert data["projects"][0]["pastBreakdown"]["resources"][0]["costComponents"] == \
        [{k: v for k, v in c.items() if k in comp(data)} for c in
         source["projects"][0]["pastBreakdown"]["resources"][0]["costComponents"]]


def test_in_sync_sample(tmp_path, drift_report_path):
    rc, out = sanitize(tmp_path, RAW_SYNC, drift_report_path)
    data = json.loads((out / "infracost.json").read_text(encoding="utf-8"))
    assert rc == 0 and data["totalMonthlyCost"] == data["pastTotalMonthlyCost"] == data["diffTotalMonthlyCost"] == "0"
    assert all(data["projects"][0][b]["resources"] == [] for b in san.BREAKDOWNS)
    assert data["summary"]["totalNoPriceResources"] == 1


def test_cost_run_binding(tmp_path, drift_report_path):
    from ai_engine.nodes.report_generator import drift_report_sha256  # Task 9A.1 canonical hash

    rc, out = sanitize(tmp_path, RAW_SKU, drift_report_path)
    cost_run = json.loads((out / "cost_run.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert sorted(cost_run) == list(san.COST_RUN_KEYS)
    assert cost_run["run_id"] == RUN_ID and cost_run["environment"] == "dev"
    assert cost_run["drift_report_sha256"] == drift_report_sha256(json.loads(drift_report_path.read_text()))
    assert (cost_run["infracost_version"], cost_run["mode"], cost_run["pricing"]) == \
        ("v0.10.46", "plan_json_breakdown", "list_prices_usd_no_usage_file")
    assert cost_run["cost_sign_convention"].endswith("drift cost = -diffTotalMonthlyCost")
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", cost_run["generated_at"])


# --------------------------------------------------------------------------- sanitiser: failures (exit 1/2)

FAILURES = {
    "price_not_found": (lambda d: comp(d).update(priceNotFound=True), 2),
    "float_value": (lambda d: comp(d).update(price=0.018), 1),
    "null_total": (lambda d: d.update(totalMonthlyCost=None), 1),
    "non_decimal_string": (lambda d: comp(d).update(monthlyCost="1e3"), 1),
    "price_not_found_not_bool": (lambda d: comp(d).update(priceNotFound="false"), 1),
    "currency_eur": (lambda d: d.update(currency="EUR"), 1),
    "missing_total": (lambda d: d.pop("totalMonthlyCost"), 1),
    "no_projects": (lambda d: d.update(projects=[]), 1),
    "email_in_name": (lambda d: d["projects"][0]["breakdown"]["resources"][0].update(name="a@b.example"), 1),
    "url_in_component": (lambda d: comp(d).update(name="see https://x.invalid"), 1),
    "abs_path_in_unit": (lambda d: comp(d).update(unit="/home/runner/x"), 1),
    "guid_in_name": (lambda d: comp(d).update(name="00000000-1111-2222-3333-444444444444"), 1),
    "bad_resource_type": (lambda d: d["projects"][0]["breakdown"]["resources"][0].update(resourceType="Bad Type"), 1),
    "negative_count": (lambda d: d["summary"].update(totalNoPriceResources=-1), 1),
}


@pytest.mark.parametrize("name", sorted(FAILURES))
def test_write_mode_failures_leave_nothing(tmp_path, drift_report_path, name):
    mutate, expected = FAILURES[name]
    data = raw()
    mutate(data)
    rc, out = sanitize(tmp_path, write_raw(tmp_path, data), drift_report_path)
    assert rc == expected
    assert list(out.iterdir()) == []


def test_binding_mismatches(tmp_path, drift_report_path):
    raw_path = write_raw(tmp_path, raw())
    assert sanitize(tmp_path, raw_path, drift_report_path, run_id="github-1-1")[0] == 1
    assert sanitize(tmp_path, raw_path, drift_report_path, environment="prod")[0] == 1
    report = json.loads(drift_report_path.read_text())
    report["run"] = None
    assert sanitize(tmp_path, raw_path, write_raw(tmp_path, report, "r.json"))[0] == 1


def test_invalid_raw_json(tmp_path, drift_report_path):
    assert sanitize(tmp_path, write_raw(tmp_path, "{not json"), drift_report_path)[0] == 1


def test_unknown_keys_dropped_in_write_mode_and_rejected_by_check(tmp_path, drift_report_path):
    data = raw()
    data["newRootKey"] = "x"
    comp(data)["unexpected"] = "y"
    data["summary"]["somethingNew"] = 1
    rc, out = sanitize(tmp_path, write_raw(tmp_path, data), drift_report_path)
    text = (out / "infracost.json").read_text()
    assert rc == 0 and "newRootKey" not in text and "unexpected" not in text and "somethingNew" not in text
    assert check(out, drift_report_path) == 0
    published = json.loads(text)
    published["summary"]["somethingNew"] = 1
    (out / "infracost.json").write_text(json.dumps(published))
    assert check(out, drift_report_path) == 1


# --------------------------------------------------------------------------- sanitiser: --check (cost job)

TAMPER = {
    "unknown_key": ("infracost.json", lambda d: d.update(metadata={}), 1),
    "float_value": ("infracost.json", lambda d: d.update(totalMonthlyCost=13.14), 1),
    "price_not_found": ("infracost.json", lambda d: comp(d).update(priceNotFound=True), 2),
    "run_id": ("cost_run.json", lambda d: d.update(run_id="other"), 1),
    "hash": ("cost_run.json", lambda d: d.update(drift_report_sha256="0" * 64), 1),
    "version": ("cost_run.json", lambda d: d.update(infracost_version="v0.10.45"), 1),
    "extra_key": ("cost_run.json", lambda d: d.update(extra="x"), 1),
    "generated_at": ("cost_run.json", lambda d: d.update(generated_at="yesterday"), 1),
}


@pytest.mark.parametrize("name", sorted(TAMPER))
def test_check_mode_rejects_tampering(tmp_path, drift_report_path, name):
    rc, out = sanitize(tmp_path, RAW_SKU, drift_report_path)
    assert rc == 0 and check(out, drift_report_path) == 0
    filename, mutate, expected = TAMPER[name]
    data = json.loads((out / filename).read_text())
    mutate(data)
    (out / filename).write_text(json.dumps(data))
    assert check(out, drift_report_path) == expected


def test_check_mode_file_set_and_run(tmp_path, drift_report_path):
    rc, out = sanitize(tmp_path, RAW_SKU, drift_report_path)
    assert rc == 0
    assert check(out, drift_report_path, run_id="github-1-1") == 1
    (out / "extra.json").write_text("{}")
    assert check(out, drift_report_path) == 1
    (out / "extra.json").unlink()
    (out / "cost_run.json").unlink()
    assert check(out, drift_report_path) == 1


# --------------------------------------------------------------------------- sanitiser: CLI usage (exit 64)


def test_cli_exit_codes(tmp_path, drift_report_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    common = ["--drift-report", str(drift_report_path), "--run-id", RUN_ID]
    write = ["--raw", str(RAW_SKU), "--environment", "dev", "--infracost-version", "v0.10.46", "--output-dir"]
    assert cli() == 64
    assert cli(*common) == 64  # write mode without its arguments
    assert cli("--check", str(empty), "--raw", str(RAW_SKU), *common) == 64
    assert cli(*common[:2], "--run-id", "bad id", *write, str(empty)) == 64
    assert cli("--raw", "/nonexistent.json", *common, *write[2:], str(empty)) == 64
    assert cli(*common, *write[:4], "--infracost-version", "v0.10.45", "--output-dir", str(empty)) == 64
    assert cli(*common, *write, "relative/dir") == 64
    assert cli(*common, *write, str(empty)) == 0  # real CLI success
    assert cli(*common, *write, str(empty)) == 64  # now not empty
    assert cli("--check", str(empty), *common) == 0


def test_sanitiser_never_parses_floats():
    source = SANITIZER.read_text(encoding="utf-8")
    assert "float(" not in source and "Decimal(" not in source  # copied as strings, never converted
    assert "import " in source and not re.search(r"^\s*(import|from)\s+(requests|yaml|pydantic|drift_engine)",
                                                 source, re.M)  # stdlib only


# --------------------------------------------------------------------------- infracost_analysis.sh (fake infracost)


def _exe(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class Harness:
    """A fake `infracost` (and optionally `az`) on a temporary PATH. The fake is driven by files
    because the script strips its environment; it records argv, cwd and environment."""

    def __init__(self, tmp: Path, script_dir: Path = SCRIPT.parent):
        self.tmp, self.script = tmp, script_dir / "infracost_analysis.sh"
        self.ctl = tmp / "ctl"
        self.bin = tmp / "bin"
        self.ctl.mkdir(parents=True)
        self.bin.mkdir()
        _exe(self.bin / "python3", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        _exe(self.bin / "infracost", f"""#!/bin/sh
mode=$(cat "{self.ctl}/mode")
case "$1" in --version)
  [ "$mode" = badversion ] && {{ echo "Infracost v0.10.45"; exit 0; }}
  [ "$mode" = egress_on_version ] && mkdir -p "$HOME/.terraform.d"
  [ "$mode" = egress_badversion ] && {{ mkdir -p "$HOME/.terraform.d"; echo "Infracost v0.10.45"; exit 0; }}
  echo "Infracost v0.10.46"; exit 0;; esac
printf '%s\\n' "$@" > "{self.ctl}/argv"; pwd -P > "{self.ctl}/cwd"; env | sort > "{self.ctl}/env"
out=""; prev=""; for a in "$@"; do [ "$prev" = --out-file ] && out="$a"; prev="$a"; done
case "$mode" in
  ok) cp "{self.ctl}/raw.json" "$out";;
  fail) echo "Error: synthetic breakdown failure" >&2; exit 1;;
  egress) mkdir -p "$HOME/.terraform.d"; cp "{self.ctl}/raw.json" "$out";;
  egressfail) mkdir -p "$HOME/.terraform.d"; exit 1;;
  invalidjson) echo "not json" > "$out";;
  noraw) :;;
esac
""")
        self.azbin = tmp / "azbin"
        self.azbin.mkdir()
        _exe(self.azbin / "az", f'#!/bin/sh\nexit $(cat "{self.ctl}/az_rc")\n')

    def run(self, report: Path, mode: str = "ok", raw_data=None, az: int | None = None, drop=(), **env_over):
        case = self.tmp / f"case{len(list(self.tmp.glob('case*')))}"
        (case / "runner").mkdir(parents=True)
        (self.ctl / "mode").write_text(mode)
        (self.ctl / "az_rc").write_text(str(az if az is not None else 1))
        (self.ctl / "raw.json").write_text(json.dumps(raw() if raw_data is None else raw_data))
        for name in ("argv", "cwd", "env"):
            (self.ctl / name).unlink(missing_ok=True)
        path = [str(self.bin)] + ([str(self.azbin)] if az is not None else []) + ["/usr/bin", "/bin"]
        env = {"PATH": ":".join(path), "HOME": str(case / "home"), "PLAN_JSON": str(PLAN), "DRIFT_REPORT": str(report),
               "RUN_ID": RUN_ID, "DRIFT_ENVIRONMENT": "dev", "RUNNER_TEMP": str(case / "runner"),
               "INFRACOST_API_KEY": KEY, "GITHUB_OUTPUT": str(case / "gh_output"),
               # Hostile extras that must never reach Infracost:
               "ARM_CLIENT_ID": "x", "AZURE_CLIENT_SECRET": "x", "TF_VAR_x": "x", "GITHUB_TOKEN": "x",
               "INFRACOST_ENV": "test", "INFRACOST_PRICING_API_ENDPOINT": "https://evil.invalid",
               "INFRACOST_ENABLE_DASHBOARD": "true", "INFRACOST_TLS_INSECURE_SKIP_VERIFY": "true",
               "CHECKPOINT_DISABLE": ""}
        env.update(env_over)
        for name in drop:
            env.pop(name, None)
        proc = subprocess.run([BASH, str(self.script)], env=env, capture_output=True, text=True)
        gh = (case / "gh_output").read_text() if (case / "gh_output").exists() else ""
        leaked = [str(p) for p in case.rglob("*") if p.is_file() and KEY.encode() in p.read_bytes()]
        if KEY in proc.stdout + proc.stderr:
            leaked.append("console")
        lines = proc.stdout.strip().splitlines()
        report_dir = case / "runner" / "cost" / "report"
        return {"rc": proc.returncode, "last": lines[-1] if lines else "", "gh": gh, "leaked": leaked,
                "stdout": proc.stdout, "case": case,
                "report": sorted(p.name for p in report_dir.iterdir()) if report_dir.is_dir() else None}


def assert_status(result: dict, failure: str) -> None:
    status = "succeeded" if failure == "none" else "failed"
    assert failure in REASON_CODES
    assert result["rc"] == {"none": 0, "usage": 64}.get(failure, 1), result["stdout"]
    assert result["last"] == f"cost_status={status} cost_failure={failure}"
    assert result["gh"] == f"cost_status={status}\ncost_failure={failure}\n"
    assert result["leaked"] == []
    if failure != "usage":
        assert result["report"] == (["cost_run.json", "infracost.json"] if failure == "none" else [])


@pytest.fixture
def harness(tmp_path):
    return Harness(tmp_path)


def test_script_success_end_to_end_with_the_real_sanitiser(harness, drift_report_path):
    result = harness.run(drift_report_path)
    assert_status(result, "none")
    assert result["stdout"].strip() == "cost_status=succeeded cost_failure=none"  # I5: one status line
    published = json.loads((result["case"] / "runner/cost/report/infracost.json").read_text())
    assert published["diffTotalMonthlyCost"] == "-106.58"
    assert san.main(["--check", str(result["case"] / "runner/cost/report"), "--run-id", RUN_ID,
                     "--drift-report", str(drift_report_path)]) == 0
    cost_dir = (result["case"] / "runner" / "cost").resolve()
    # D2: exactly the locked command, run from COST_DIR.
    assert (harness.ctl / "argv").read_text().splitlines() == [
        "breakdown", "--path", str(PLAN), "--format", "json", "--out-file", str(cost_dir / "raw/infracost.raw.json"),
        "--no-color"]
    assert (harness.ctl / "cwd").read_text().strip() == str(cost_dir)
    env = dict(line.split("=", 1) for line in (harness.ctl / "env").read_text().splitlines() if "=" in line)
    # D6/D7: allowlisted environment only; the five controls set; isolated HOME; key inherited, not an argument.
    assert {k: env.get(k) for k in D7_CONTROLS} == D7_CONTROLS
    assert env["HOME"] == str((result["case"] / "runner" / "infracost-home").resolve())
    assert env["INFRACOST_API_KEY"] == KEY
    assert set(env) <= {"PATH", "HOME", "INFRACOST_API_KEY", "PWD", "SHLVL", "_", *D7_CONTROLS}
    assert KEY not in (harness.ctl / "argv").read_text()


@pytest.mark.parametrize("raw_name", ["in_sync"])
def test_script_in_sync_sample(harness, drift_report_path, raw_name):
    assert_status(harness.run(drift_report_path, raw_data=raw(RAW_SYNC)), "none")


SCRIPT_CASES = {
    "missing_key": ({"drop": ("INFRACOST_API_KEY",)}, "missing_api_key"),
    "empty_key": ({"INFRACOST_API_KEY": ""}, "missing_api_key"),
    "oidc_url": ({"ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.invalid"}, "oidc_token_present"),
    "oidc_token": ({"ACTIONS_ID_TOKEN_REQUEST_TOKEN": "t"}, "oidc_token_present"),
    "oidc_blanked": ({"ACTIONS_ID_TOKEN_REQUEST_URL": "", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": ""}, "none"),
    "azure_session": ({"az": 0}, "azure_session_present"),
    "az_logged_out": ({"az": 1}, "none"),
    "version_mismatch": ({"mode": "badversion"}, "version_mismatch"),
    "infracost_failed": ({"mode": "fail"}, "infracost_failed"),
    "egress": ({"mode": "egress"}, "unexpected_egress"),
    "egress_over_failure": ({"mode": "egressfail"}, "unexpected_egress"),
    "egress_on_version": ({"mode": "egress_on_version"}, "unexpected_egress"),
    "egress_over_version_mismatch": ({"mode": "egress_badversion"}, "unexpected_egress"),
    "raw_invalid": ({"mode": "invalidjson"}, "raw_output_invalid"),
    "raw_missing": ({"mode": "noraw"}, "raw_output_invalid"),
    "price_not_found": ({"raw_data": "price_not_found"}, "price_not_found"),
    "sanitize_failed": ({"raw_data": "float_value"}, "sanitize_failed"),
    "usage_plan_missing": ({"drop": ("PLAN_JSON",)}, "usage"),
    "usage_plan_relative": ({"PLAN_JSON": "plan.json"}, "usage"),
    "usage_report_missing": ({"DRIFT_REPORT": "/nonexistent/drift_report.json"}, "usage"),
    "usage_run_id": ({"RUN_ID": "bad id;rm"}, "usage"),
    "usage_environment": ({"DRIFT_ENVIRONMENT": "../dev"}, "usage"),
    "usage_runner_temp": ({"drop": ("RUNNER_TEMP",)}, "usage"),
}


@pytest.mark.parametrize("name", sorted(SCRIPT_CASES))
def test_script_reason_codes(harness, drift_report_path, name):
    kwargs, failure = SCRIPT_CASES[name]
    kwargs = dict(kwargs)
    if isinstance(kwargs.get("raw_data"), str):
        data = raw()
        FAILURES[kwargs["raw_data"]][0](data)
        kwargs["raw_data"] = data
    result = harness.run(drift_report_path, **kwargs)
    assert_status(result, failure)
    if failure == "infracost_failed":
        assert "synthetic breakdown failure" in result["stdout"]  # I5: log tail on failure only


def test_script_directories_must_be_new_or_empty(harness, drift_report_path, tmp_path):
    stale = tmp_path / "stale_cost"
    stale.mkdir()
    (stale / "old.json").write_text("{}")
    assert_status(harness.run(drift_report_path, COST_DIR=str(stale)), "usage")


def test_script_cost_dir_inside_repository_and_missing_sanitiser(tmp_path, drift_report_path):
    # A copy of the scripts tree, so neither case touches the repository.
    tree = tmp_path / "tree" / "scripts"
    tree.mkdir(parents=True)
    shutil.copy(SCRIPT, tree)
    harness = Harness(tmp_path / "h", tree)
    assert_status(harness.run(drift_report_path, COST_DIR=str(tree.parent / "cost")), "usage")
    assert_status(harness.run(drift_report_path), "sanitize_failed")  # no sanitiser: never price_not_found


def test_script_static_contract():
    text = SCRIPT.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    for name, value in D7_CONTROLS.items():
        assert f"export {name}={value}" in code
    for forbidden in ("INFRACOST_ENV=", "INFRACOST_PRICING_API_ENDPOINT", "INFRACOST_ENABLE_DASHBOARD",
                      "INFRACOST_ENABLE_CLOUD_UPLOAD", "INFRACOST_TLS_INSECURE_SKIP_VERIFY", "set -x"):
        assert forbidden not in code
    assert set(re.findall(r"run_infracost (\S+)", code)) == {"--version", "breakdown"}  # never upload/comment/auth
    assert 'EXPECTED_VERSION="Infracost v0.10.46"' in code
    used = set(re.findall(r"(?:finish|failure) ([a-z_]+) ", code))
    assert used and used <= REASON_CODES


# --------------------------------------------------------------------------- workflow structure (D1, D5, D6, D8)


@pytest.fixture(scope="module")
def wf() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def steps_by_name(job: dict) -> dict:
    return {s["name"]: s for s in job["steps"]}


def test_cost_steps_follow_the_drift_report_upload(wf):
    steps = wf["jobs"]["plan-and-analyze"]["steps"]
    names = [s["name"] for s in steps]
    assert names[-3:] == ["Upload Drift Report", "Infracost Cost Estimate", "Upload Infracost Report"]
    cost, upload = steps[-2], steps[-1]
    assert cost["id"] == "cost" and upload["id"] == "cost_upload"
    assert cost["if"] == ("${{ steps.upload.outcome == 'success' && (steps.analyze.outputs.drift_detected == 'true' "
                          "|| steps.analyze.outputs.drift_detected == 'false') }}")
    assert upload["if"] == "${{ steps.cost.outputs.cost_status == 'succeeded' }}"
    outputs = wf["jobs"]["plan-and-analyze"]["outputs"]
    assert outputs["cost_status"] == "${{ steps.cost.outputs.cost_status }}"
    assert outputs["cost_failure"] == "${{ steps.cost.outputs.cost_failure }}"
    assert outputs["cost_upload_outcome"] == "${{ steps.cost_upload.outcome }}"


def test_cost_step_install_pin_and_environment(wf):
    cost = steps_by_name(wf["jobs"]["plan-and-analyze"])["Infracost Cost Estimate"]
    env, run = cost["env"], cost["run"]
    assert env["PINNED_INFRACOST_VERSION"] == "0.10.46" and env["PINNED_INFRACOST_LINUX_SHA256"] == PINNED_SHA256
    assert env["INFRACOST_API_KEY"] == "${{ secrets.INFRACOST_API_KEY }}"
    # D6 amendment: no (ineffective) step-level blanking; the re-exec is the very first command.
    assert "ACTIONS_ID_TOKEN_REQUEST_URL" not in env and "ACTIONS_ID_TOKEN_REQUEST_TOKEN" not in env
    assert run.splitlines()[:len(REEXEC) + 1] == [*REEXEC, "set -uo pipefail"]
    assert env["RUN_ID"] == "github-${{ github.run_id }}-${{ github.run_attempt }}"
    assert env["PLAN_JSON"] == "${{ runner.temp }}/drift/plan.json"
    assert env["DRIFT_REPORT"] == "${{ runner.temp }}/drift/drift_report.json"
    text = json.dumps(cost)
    for forbidden in ("ARM_", "AZURE_", "GITHUB_TOKEN", "secrets.AZURE", "azure/login", "id-token", "set -x",
                      "infracost upload", "infracost comment", "infracost-action", "install.sh"):
        assert forbidden not in text, forbidden
    # Checksum verified before unpacking; install failure is a cost failure with exit 0.
    assert run.index('sha256sum -c -') < run.index("tar -xzf")
    assert "infracost-linux-amd64.tar.gz" in run and "/releases/download/v${PINNED_INFRACOST_VERSION}/" in run
    assert "cost_failure=install_failed" in run and run.rstrip().endswith("exit 0")
    assert "az logout" in run and "az account clear" in run
    assert "./scripts/infracost_analysis.sh || script_rc=$?" in run


def test_secret_and_continue_on_error_are_confined(wf):
    text = WORKFLOW.read_text(encoding="utf-8")
    code = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    assert sum("secrets.INFRACOST_API_KEY" in ln for ln in code) == 1
    exceptions = [(j, s["name"]) for j, job in wf["jobs"].items() for s in job.get("steps", [])
                  if "continue-on-error" in s]
    assert exceptions == [("plan-and-analyze", "Upload Infracost Report")]
    assert not any("continue-on-error" in job for job in wf["jobs"].values())


def test_cost_artifact(wf):
    upload = steps_by_name(wf["jobs"]["plan-and-analyze"])["Upload Infracost Report"]
    assert upload["uses"] == "actions/upload-artifact@v4" and upload["continue-on-error"] is True
    assert upload["with"] == {
        "name": "infracost-report-${{ github.run_id }}",
        "path": "${{ runner.temp }}/cost/report/infracost.json\n${{ runner.temp }}/cost/report/cost_run.json\n",
        "retention-days": 30, "if-no-files-found": "error", "overwrite": True}


def test_cost_job(wf):
    job = wf["jobs"]["cost"]
    assert job["needs"] == ["preflight", "plan-and-analyze"]
    assert job["if"] == ("${{ !cancelled() && (needs.plan-and-analyze.outputs.drift_detected == 'true' || "
                         "needs.plan-and-analyze.outputs.drift_detected == 'false') }}")
    assert job["permissions"] == {"contents": "read"}
    assert "environment" not in job and "continue-on-error" not in job
    names = [s["name"] for s in job["steps"]]
    assert names == ["Require Cost Success", "Checkout Code", "Setup Python", "Download Infracost Report",
                     "Download Drift Report", "Verify Infracost Report", "Cost Summary"]
    steps = steps_by_name(job)
    assert steps["Checkout Code"]["with"] == {"persist-credentials": False}
    assert steps["Download Infracost Report"]["with"]["name"] == "infracost-report-${{ github.run_id }}"
    assert steps["Download Drift Report"]["with"]["name"] == "drift-report-${{ github.run_id }}"
    assert "sanitize_infracost.py --check" in steps["Verify Infracost Report"]["run"]
    text = json.dumps(job)
    for forbidden in ("secrets.", "id-token", "azure/login", "ARM_", "github-token"):
        assert forbidden not in text, forbidden
    # Report job unchanged: still only needs preflight and plan-and-analyze, never reads cost outputs.
    assert wf["jobs"]["report"]["needs"] == ["preflight", "plan-and-analyze"]
    assert "cost" not in json.dumps(wf["jobs"]["report"]) and "cost" not in json.dumps(wf["jobs"]["issues"])


# --------------------------------------------------------------------------- workflow run: blocks, executed


def _run_block(run: str, env: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([BASH, "-c", run], env=env, cwd=str(cwd), capture_output=True, text=True)


def _run_step_file(run: str, env: dict, cwd: Path, script: Path, inject_oidc: bool) -> subprocess.CompletedProcess:
    """Runs a run: block the way the GitHub runner does: written to a file and executed as `bash -e <file>`
    (the default for steps without `shell:`), with the OIDC request variables set non-empty AFTER the
    step env: is applied when the job has id-token: write (actions/runner ScriptHandler.cs)."""
    script.write_text(run, encoding="utf-8")
    env = dict(env)
    if inject_oidc:
        env["ACTIONS_ID_TOKEN_REQUEST_URL"] = "https://pipelines.invalid/idtoken?api-version=2.0"
        env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"] = OIDC_SENTINEL
    return subprocess.run([BASH, "-e", str(script)], env=env, cwd=str(cwd), capture_output=True, text=True)


@pytest.fixture
def step_sim(tmp_path, drift_report_path, wf):
    """The cost step's run: block with a fake curl serving a crafted tarball that holds a fake
    Infracost, a logged-out az, and the real scripts and sanitiser."""
    shim = tmp_path / "shim"
    shim.mkdir()
    seen = f'env | grep "^ACTIONS_ID_TOKEN_REQUEST" >> "{tmp_path}/oidc_seen" || true\n'
    fake = (f'#!/bin/sh\n{seen}case "$1" in --version) echo "Infracost v0.10.46"; exit 0;; esac\n'
            f'out=""; prev=""; for a in "$@"; do [ "$prev" = --out-file ] && out="$a"; prev="$a"; done\n'
            f'cp "{RAW_SKU}" "$out"\n').encode()
    tgz = tmp_path / "infracost-linux-amd64.tar.gz"
    with tarfile.open(tgz, "w:gz") as tar:
        info = tarfile.TarInfo("infracost-linux-amd64")
        info.size, info.mode = len(fake), 0o755
        tar.addfile(info, io.BytesIO(fake))
    _exe(shim / "curl", f'#!/bin/sh\n{seen}[ -f "{tmp_path}/curl_fail" ] && exit 22\nout=""; prev=""; '
                        f'for a in "$@"; do [ "$prev" = -o ] && out="$a"; prev="$a"; done\n'
                        f'echo "$@" > "{tmp_path}/curl_args"\n'
                        f'cp "{tgz}" "$out"\n')
    _exe(shim / "az", f'#!/bin/sh\n{seen}echo "$@" >> "{tmp_path}/az_calls"\nexit 1\n')
    _exe(shim / "python3", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    if shutil.which("sha256sum", path="/usr/bin:/bin") is None:  # the step PATH, not the caller's
        _exe(shim / "sha256sum", '#!/bin/sh\nexec shasum -a 256 "$@"\n')
    step = steps_by_name(wf["jobs"]["plan-and-analyze"])["Infracost Cost Estimate"]

    def run(sha: str = hashlib.sha256(tgz.read_bytes()).hexdigest(), key: str = KEY, curl_fail: bool = False,
            inject_oidc: bool = True, run_text: str | None = None, step_env: dict | None = None):
        (tmp_path / "oidc_seen").unlink(missing_ok=True)
        runner = tmp_path / f"runner{len(list(tmp_path.glob('runner*')))}"
        (runner / "drift").mkdir(parents=True)
        (tmp_path / "curl_fail").unlink(missing_ok=True)
        if curl_fail:
            (tmp_path / "curl_fail").write_text("")
        gh = runner / "gh_output"
        gh.write_text("")
        env = dict(step["env"] if step_env is None else step_env)
        env.update({"INFRACOST_API_KEY": key, "PINNED_INFRACOST_LINUX_SHA256": sha, "PLAN_JSON": str(PLAN),
                    "DRIFT_REPORT": str(drift_report_path), "RUN_ID": RUN_ID, "DRIFT_ENVIRONMENT": "dev",
                    "RUNNER_TEMP": str(runner), "GITHUB_OUTPUT": str(gh), "HOME": str(tmp_path / "home"),
                    "PATH": f"{shim}:/usr/bin:/bin"})
        text = step["run"] if run_text is None else run_text
        proc = _run_step_file(text, env, ROOT, runner / "step.sh", inject_oidc)
        outputs = dict(line.split("=", 1) for line in gh.read_text().splitlines() if "=" in line)
        return proc, outputs, runner

    return run, tmp_path


def test_cost_step_executes_successfully(step_sim):
    run, tmp = step_sim
    proc, outputs, runner = run()
    assert proc.returncode == 0 and outputs == {"cost_status": "succeeded", "cost_failure": "none"}
    assert sorted(p.name for p in (runner / "cost/report").iterdir()) == ["cost_run.json", "infracost.json"]
    assert (tmp / "curl_args").read_text().split()[-1] == PINNED_URL
    assert (tmp / "az_calls").read_text().splitlines()[:2] == ["logout", "account clear"]
    assert KEY not in proc.stdout + proc.stderr
    # D6 amendment: with the runner injecting both OIDC variables, no child process (az, curl, Infracost via
    # the script) sees them, and they are never printed.
    assert oidc_seen(tmp) == ""
    assert OIDC_SENTINEL not in proc.stdout + proc.stderr + json.dumps(outputs)


def oidc_seen(tmp: Path) -> str:
    """OIDC request variables observed by the fake az, curl or Infracost (empty = never seen)."""
    path = tmp / "oidc_seen"
    return path.read_text() if path.exists() else ""


def test_cost_step_without_injected_oidc_does_not_reexec(step_sim):
    run, tmp = step_sim
    proc, outputs, _ = run(inject_oidc=False)  # guard: no re-exec needed, no loop
    assert proc.returncode == 0 and outputs == {"cost_status": "succeeded", "cost_failure": "none"}
    assert oidc_seen(tmp) == ""


def test_run20_mechanism_is_caught_by_the_runner_realistic_harness(step_sim, wf):
    """Regression for CI run #20: step-level blanking without the re-exec. Under the runner-realistic harness
    the script fails closed with oidc_token_present (step still exits 0); under the old harness, which took the
    step env from the YAML and did not inject the variables, the same mechanism wrongly looked fine."""
    run, tmp = step_sim
    step = steps_by_name(wf["jobs"]["plan-and-analyze"])["Infracost Cost Estimate"]
    lines = step["run"].splitlines()
    assert lines[:len(REEXEC)] == REEXEC
    run20_text = "\n".join(lines[len(REEXEC):]) + "\n"
    run20_env = {**step["env"], "ACTIONS_ID_TOKEN_REQUEST_URL": "", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": ""}
    proc, outputs, runner = run(run_text=run20_text, step_env=run20_env)
    assert proc.returncode == 0
    assert outputs == {"cost_status": "failed", "cost_failure": "oidc_token_present"}
    assert not (runner / "cost" / "report").exists() or list((runner / "cost" / "report").iterdir()) == []
    assert OIDC_SENTINEL not in proc.stdout + proc.stderr  # the check never prints the value
    assert "ACTIONS_ID_TOKEN_REQUEST_TOKEN=" in oidc_seen(tmp)  # probe sensitivity: az saw it without the re-exec
    proc, outputs, _ = run(run_text=run20_text, step_env=run20_env, inject_oidc=False)
    assert outputs == {"cost_status": "succeeded", "cost_failure": "none"}


@pytest.mark.parametrize("variant", ["checksum_mismatch", "pinned_hash_vs_crafted_tarball", "download_failure"])
def test_cost_step_install_failures_exit_zero(step_sim, variant):
    run, _ = step_sim
    kwargs = {"checksum_mismatch": {"sha": "0" * 64}, "pinned_hash_vs_crafted_tarball": {"sha": PINNED_SHA256},
              "download_failure": {"curl_fail": True}}[variant]
    proc, outputs, runner = run(**kwargs)
    assert proc.returncode == 0
    assert outputs == {"cost_status": "failed", "cost_failure": "install_failed"}
    assert not (runner / "cost").exists()  # the script never ran


def test_cost_step_script_failure_exits_zero(step_sim):
    run, _ = step_sim
    proc, outputs, _ = run(key="")
    assert proc.returncode == 0 and outputs == {"cost_status": "failed", "cost_failure": "missing_api_key"}
    assert "::error::Cost estimate failed (script exit 1)" in proc.stdout


@pytest.mark.parametrize("status,failure,upload,rc", [
    ("succeeded", "none", "success", 0), ("failed", "price_not_found", "skipped", 1), ("", "", "", 1),
    ("succeeded", "none", "failure", 1), ("succeeded", "none", "skipped", 1)])
def test_cost_job_gate(wf, tmp_path, status, failure, upload, rc):
    gate = steps_by_name(wf["jobs"]["cost"])["Require Cost Success"]["run"]
    env = {"COST_STATUS": status, "COST_FAILURE": failure, "COST_UPLOAD_OUTCOME": upload, "PATH": "/usr/bin:/bin"}
    assert _run_block(gate, env, tmp_path).returncode == rc


def test_cost_job_verify_and_totals_only_summary(wf, tmp_path, drift_report_path):
    rc, out = sanitize(tmp_path, RAW_SKU, drift_report_path)
    assert rc == 0
    shim = tmp_path / "shim"
    shim.mkdir()
    _exe(shim / "python3", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    steps = steps_by_name(wf["jobs"]["cost"])
    env = {"REPORT_DIR": str(out), "DRIFT_REPORT": str(drift_report_path), "RUN_ID": RUN_ID,
           "PATH": f"{shim}:/usr/bin:/bin"}
    assert _run_block(steps["Verify Infracost Report"]["run"], env, ROOT).returncode == 0
    assert _run_block(steps["Verify Infracost Report"]["run"], {**env, "RUN_ID": "github-1-1"}, ROOT).returncode != 0
    summary = tmp_path / "summary.md"
    summary.write_text("")
    proc = _run_block(steps["Cost Summary"]["run"], {**env, "GITHUB_STEP_SUMMARY": str(summary)}, ROOT)
    text = summary.read_text()
    assert proc.returncode == 0
    for row in ("| Actual monthly cost (prior state) | 119.72 USD |", "| Desired monthly cost (planned) | 13.14 USD |",
                "| Diff (desired - actual) | -106.58 USD |", "| Drift cost (-diff) | 106.58 USD |"):
        assert row in text
    for leaked in ("azurerm", "Instance usage", "0.164", "0.018", "hours"):
        assert leaked not in text  # totals only


# --------------------------------------------------------------------------- safeguard mutants

SANITISER_MUTANTS = {
    "decimal-strings": ('        if not isinstance(value, str) or not DECIMAL_RE.match(value):\n',
                        '        if False:\n'),
    "price-not-found": ("        if found:\n            self.price_not_found.append(where)\n", ""),
    "currency-usd": ('        if out["currency"] != "USD":\n', '        if False:\n'),
    "recheck-strings": ("            if pattern.search(value):\n", "            if False:\n"),
    "binding-run-id": ('    if run.get("run_id") != run_id:\n', '    if False:\n'),
    "binding-environment": ('    if environment != args.environment:\n', '    if False:\n'),
    "allowlist-resource": ('        out: dict[str, Any] = {"name": self._string(src.get("name"), f"{where}.name")}\n',
                           '        out: dict[str, Any] = dict(src)\n'),
    "allowlist-root": ('        out["summary"] = self.summary(src["summary"], "$.summary")\n',
                       '        out["summary"] = self.summary(src["summary"], "$.summary")\n        out.update(src)\n'),
    "canonical-hash": ('separators=(",", ":"), ensure_ascii=False)\n    return hashlib',
                       'ensure_ascii=False)\n    return hashlib'),
    "price-exit-code": ('              f"{projector.price_not_found[0]}", file=sys.stderr)\n'
                        "        return EXIT_PRICE_NOT_FOUND",
                        '              f"{projector.price_not_found[0]}", file=sys.stderr)\n'
                        "        return EXIT_FAILED"),
}
# Not listed (equivalent as single mutants, kept as defence in depth): the strict unknown-key check in
# check mode and the "projected != infracost" comparison each reject an unknown key on their own.
SANITISER_NO_OP = ('"""The input cannot be published (exit 1)."""', '"""The input cannot be published."""')


class TestSanitiserMutants:
    """Each mutant removes one safeguard from an in-process copy of the sanitiser (the repository
    file is never changed) and must change at least one scenario's outcome."""

    @staticmethod
    def scenarios(tmp: Path, report: Path) -> dict:
        def write(name, mutate):
            def scenario(module):
                case = tmp / f"{name}-{len(list(tmp.iterdir()))}"
                case.mkdir()
                data = raw()
                mutate(data)
                rc, out = sanitize(case, write_raw(case, data), report, module=module)
                files = {p.name: json.loads(p.read_text()) for p in sorted(out.iterdir())}
                files.get("cost_run.json", {}).pop("generated_at", None)
                return json.dumps([rc, files], sort_keys=True)
            return scenario

        def bound(name, **kwargs):
            def scenario(module):
                case = tmp / f"{name}-{len(list(tmp.iterdir()))}"
                case.mkdir()
                return str(sanitize(case, RAW_SKU, report, module=module, **kwargs)[0])
            return scenario

        def checked(name, mutate):
            def scenario(module):
                case = tmp / f"{name}-{len(list(tmp.iterdir()))}"
                case.mkdir()
                rc, out = sanitize(case, RAW_SKU, report)  # written by the real sanitiser
                data = json.loads((out / "infracost.json").read_text())
                mutate(data)
                (out / "infracost.json").write_text(json.dumps(data))
                return str(check(out, report, module=module))
            return scenario

        scenarios = {f"write-{n}": write(n, FAILURES[n][0]) for n in FAILURES}
        scenarios["write-clean"] = write("clean", lambda d: None)
        scenarios["write-extra-keys"] = write("extra", lambda d: (d.update(newRootKey="x"),
                                                                  d["projects"][0]["breakdown"]["resources"][0]
                                                                  .update(tags={"a": "b"})))
        scenarios["bound-run-id"] = bound("runid", run_id="github-1-1")
        scenarios["bound-env"] = bound("env", environment="prod")
        scenarios["check-unknown"] = checked("cu", lambda d: d.update(metadata={}))
        scenarios["check-changed-value"] = checked("cv", lambda d: d.update(totalMonthlyCost="1.00"))
        return scenarios

    def test_every_mutant_is_caught(self, tmp_path, drift_report_path):
        source = SANITIZER.read_text(encoding="utf-8")
        scenarios = self.scenarios(tmp_path, drift_report_path)
        expected = {name: s(san) for name, s in scenarios.items()}
        survivors = []
        for name, (old, new) in SANITISER_MUTANTS.items():
            assert source.count(old) == 1, f"mutant {name} does not apply exactly once"
            module = load_module(SANITIZER, f"san_mutant_{name.replace('-', '_')}", source.replace(old, new))
            if all(s(module) == expected[n] for n, s in scenarios.items()):
                survivors.append(name)
        assert survivors == []

    def test_no_op_control_is_not_caught(self, tmp_path, drift_report_path):
        source = SANITIZER.read_text(encoding="utf-8")
        assert source.count(SANITISER_NO_OP[0]) == 1
        module = load_module(SANITIZER, "san_mutant_noop", source.replace(*SANITISER_NO_OP))
        for name, scenario in self.scenarios(tmp_path, drift_report_path).items():
            assert scenario(module) == scenario(san), name


SCRIPT_MUTANTS = {
    "oidc-check": ('if [[ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" || -n "${ACTIONS_ID_TOKEN_REQUEST_TOKEN:-}" ]]; then',
                   "if false; then"),
    "azure-check": ("  if az account show --only-show-errors >/dev/null 2>&1; then", "  if false; then"),
    "key-check": ('[[ -n "${INFRACOST_API_KEY:-}" ]] || failure missing_api_key', "true || failure missing_api_key"),
    "version-check": ('if [[ "${version_line}" != "${EXPECTED_VERSION}" ]]; then', "if false; then"),
    "egress-override": ('  if [[ -n "${INFRACOST_HOME}" && -e "${INFRACOST_HOME}/.terraform.d" ]]; then',
                        "  if false; then"),
    "env-allowlist": ('      *) unset "${var}" 2>/dev/null || true ;;', "      *) : ;;"),
    "checkpoint-disable": ("  export CHECKPOINT_DISABLE=1\n", ""),
    "price-code": ("  2) failure price_not_found", "  2) failure sanitize_failed"),
    "github-output": ('      echo "cost_failure=${failure}"\n', ""),
    "dir-outside-repo": ('  if [[ "${real}/" == "${ROOT_DIR}/"* ]]; then', "  if false; then"),
}
SCRIPT_NO_OP = ("# No `set -e`: every exit status is captured and mapped explicitly.",
                "# No `set -e`: exit statuses are captured and mapped explicitly.")


class TestScriptMutants:
    """Each mutant removes one safeguard from a temporary copy of infracost_analysis.sh (run next to
    the real sanitiser) and must change at least one scenario's outcome."""

    SCENARIOS = {
        "success": {}, "oidc": {"ACTIONS_ID_TOKEN_REQUEST_TOKEN": "t"}, "azure": {"az": 0},
        "no-key": {"drop": ("INFRACOST_API_KEY",)}, "bad-version": {"mode": "badversion"},
        "egress-on-version": {"mode": "egress_on_version"}, "egress-bad-version": {"mode": "egress_badversion"},
        "price": {"raw_data": "price_not_found"},
        "cost-dir-in-repo": {"cost_dir_in_tree": True},
    }

    def outcome(self, tmp: Path, script_text: str, report: Path) -> dict:
        base = tmp / f"tree{len(list(tmp.glob('tree*')))}"
        root = base / "repo"  # the copied repository; the fake runner lives beside it, never inside
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "infracost_analysis.sh").write_text(script_text)
        shutil.copy(SANITIZER, root / "scripts")
        harness = Harness(base / "h", root / "scripts")
        results = {}
        for name, spec in self.SCENARIOS.items():
            kwargs = dict(spec)
            if kwargs.pop("cost_dir_in_tree", False):
                kwargs["COST_DIR"] = str(root / "cost")
            if isinstance(kwargs.get("raw_data"), str):
                data = raw()
                FAILURES[kwargs["raw_data"]][0](data)
                kwargs["raw_data"] = data
            r = harness.run(report, **kwargs)
            env = (harness.ctl / "env").read_text() if (harness.ctl / "env").exists() else ""
            env_names = sorted(line.split("=", 1)[0] for line in env.splitlines() if "=" in line)
            results[name] = (r["rc"], r["last"], r["gh"], env_names, "CHECKPOINT_DISABLE=1" in env)
        return results

    def test_every_mutant_is_caught(self, tmp_path, drift_report_path):
        source = SCRIPT.read_text(encoding="utf-8")
        expected = self.outcome(tmp_path, source, drift_report_path)
        survivors = []
        for name, (old, new) in SCRIPT_MUTANTS.items():
            assert source.count(old) == 1, f"mutant {name} does not apply exactly once"
            if self.outcome(tmp_path, source.replace(old, new), drift_report_path) == expected:
                survivors.append(name)
        assert survivors == []

    def test_no_op_control_is_not_caught(self, tmp_path, drift_report_path):
        source = SCRIPT.read_text(encoding="utf-8")
        assert source.count(SCRIPT_NO_OP[0]) == 1
        assert self.outcome(tmp_path, source.replace(*SCRIPT_NO_OP), drift_report_path) == \
            self.outcome(tmp_path, source, drift_report_path)
