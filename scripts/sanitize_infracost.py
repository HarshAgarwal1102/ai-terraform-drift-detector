#!/usr/bin/env python3
"""Allowlist sanitiser for Infracost v0.10.46 breakdown JSON (Task 10.1, D8 / I1).

Standard library only. Turns the raw `infracost breakdown --format json` output
(which stays on the runner) into the two published artifact files:

  infracost.json  allowlist projection of the raw output with Infracost's own key
                  names: totals, summary counts, and per resource only address,
                  type, costs and cost components. Everything else (all VCS
                  metadata, paths, project names, tags, resource metadata, run and
                  share URLs) is dropped.
  cost_run.json   binding manifest: run id, environment, canonical drift report
                  hash, Infracost version, mode, pricing and the cost sign rule.

Write mode:
    sanitize_infracost.py --raw RAW --drift-report REPORT --run-id ID \
        --environment ENV --infracost-version v0.10.46 --output-dir DIR
Check mode (the `cost` job):
    sanitize_infracost.py --check DIR --run-id ID --drift-report REPORT

Exit codes:
    0   written / check passed
    1   sanitisation failure (nothing is left in the output directory)
    2   price_not_found: a cost component has priceNotFound: true
    64  usage: bad arguments, missing input file or unusable output directory

Every money, price and quantity value must be a JSON decimal string and is copied
unchanged, never parsed as a float. Error messages name the location of a problem,
never the offending value.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_PRICE_NOT_FOUND = 2
EXIT_USAGE = 64

INFRACOST_VERSION = "v0.10.46"
MODE = "plan_json_breakdown"
PRICING = "list_prices_usd_no_usage_file"
COST_SIGN_CONVENTION = (
    "diffTotalMonthlyCost = totalMonthlyCost (desired, planned_values) - pastTotalMonthlyCost "
    "(actual, refreshed prior_state); drift cost = -diffTotalMonthlyCost"
)
OUTPUT_FILES = ("cost_run.json", "infracost.json")
COST_RUN_KEYS = ("cost_sign_convention", "drift_report_sha256", "environment", "generated_at",
                 "infracost_version", "mode", "pricing", "run_id")

RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
ENVIRONMENT_RE = re.compile(r"^[a-z0-9-]{1,64}$")
DECIMAL_RE = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
SCHEMA_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+$")
TIMESTAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z$")
RESOURCE_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Fail-closed re-check of every string in the output (D8): none of these may survive.
FORBIDDEN_STRINGS = {
    "email-like address": re.compile(r"[^\s@]+@[^\s@]+"),
    "URL": re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://"),
    "GUID": re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"),
    "absolute path": re.compile(r"(?:^|[\s\"'=(\[,])(?:~|/[^/\s\"'\]]+)/[^/\s\"'\]]+|[A-Za-z]:\\"),
}

# Allowlist (D8). Decimal-string fields are copied unchanged.
ROOT_DECIMALS = ("totalHourlyCost", "totalMonthlyCost", "totalMonthlyUsageCost",
                 "pastTotalHourlyCost", "pastTotalMonthlyCost", "pastTotalMonthlyUsageCost",
                 "diffTotalHourlyCost", "diffTotalMonthlyCost", "diffTotalMonthlyUsageCost")
ROOT_REQUIRED = ("version", "currency", "timeGenerated", "totalMonthlyCost", "pastTotalMonthlyCost",
                 "diffTotalMonthlyCost", "summary", "projects")
BREAKDOWNS = ("breakdown", "pastBreakdown", "diff")
BREAKDOWN_DECIMALS = ("totalHourlyCost", "totalMonthlyCost", "totalMonthlyUsageCost")
RESOURCE_DECIMALS = ("hourlyCost", "monthlyCost", "monthlyUsageCost")
COMPONENT_DECIMALS = ("hourlyQuantity", "monthlyQuantity", "price", "hourlyCost", "monthlyCost")


class SanitizeError(Exception):
    """The input cannot be published (exit 1)."""


class UsageError(Exception):
    """Bad arguments or unusable paths (exit 64)."""


class Projector:
    """Allowlist projection. In write mode unknown keys are dropped; in strict
    (check) mode any unknown key is an error, so the published file must already
    be exactly the projection."""

    def __init__(self, strict: bool) -> None:
        self.strict = strict
        self.price_not_found: list[str] = []

    def _mapping(self, value: Any, where: str, allowed: set[str]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise SanitizeError(f"{where}: expected an object")
        if self.strict:
            unknown = sorted(set(value) - allowed)
            if unknown:
                raise SanitizeError(f"{where}: keys outside the allowlist: {unknown}")
        return value

    @staticmethod
    def _decimal(value: Any, where: str) -> str:
        # Never parsed as a float: only the string form is checked and copied.
        if not isinstance(value, str) or not DECIMAL_RE.match(value):
            raise SanitizeError(f"{where}: expected a decimal string")
        return value

    @staticmethod
    def _string(value: Any, where: str, pattern: re.Pattern[str] | None = None) -> str:
        if not isinstance(value, str) or not value or (pattern is not None and not pattern.match(value)):
            raise SanitizeError(f"{where}: invalid string")
        return value

    def _copy_decimals(self, src: dict[str, Any], dst: dict[str, Any], keys: tuple[str, ...], where: str,
                       required: tuple[str, ...] = ()) -> None:
        for key in keys:
            if key in src:
                dst[key] = self._decimal(src[key], f"{where}.{key}")
            elif key in required:
                raise SanitizeError(f"{where}.{key}: required")

    def root(self, raw: Any) -> dict[str, Any]:
        allowed = set(ROOT_DECIMALS) | {"version", "currency", "timeGenerated", "summary", "projects"}
        src = self._mapping(raw, "$", allowed)
        for key in ROOT_REQUIRED:
            if key not in src:
                raise SanitizeError(f"$.{key}: required")
        out: dict[str, Any] = {
            "version": self._string(src["version"], "$.version", SCHEMA_VERSION_RE),
            "currency": self._string(src["currency"], "$.currency"),
            "timeGenerated": self._string(src["timeGenerated"], "$.timeGenerated", TIMESTAMP_RE),
        }
        if out["currency"] != "USD":
            raise SanitizeError("$.currency: list prices must be USD")
        self._copy_decimals(src, out, ROOT_DECIMALS, "$")
        out["summary"] = self.summary(src["summary"], "$.summary")
        projects = src["projects"]
        if not isinstance(projects, list) or not projects:
            raise SanitizeError("$.projects: expected a non-empty list")
        out["projects"] = [self.project(p, f"$.projects[{i}]") for i, p in enumerate(projects)]
        return out

    def summary(self, value: Any, where: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise SanitizeError(f"{where}: expected an object")
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key.startswith("total") and key.endswith("Resources"):
                if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                    raise SanitizeError(f"{where}.{key}: expected a non-negative integer")
                out[key] = item
            elif key.endswith("ResourceCounts"):
                if not isinstance(item, dict):
                    raise SanitizeError(f"{where}.{key}: expected an object")
                counts = {}
                for rtype, count in item.items():
                    if not RESOURCE_TYPE_RE.match(rtype) or isinstance(count, bool) or not isinstance(count, int) \
                            or count < 0:
                        raise SanitizeError(f"{where}.{key}: expected resource type -> non-negative integer")
                    counts[rtype] = count
                out[key] = counts
            elif self.strict:
                raise SanitizeError(f"{where}: key outside the allowlist: {key!r}")
        return out

    def project(self, value: Any, where: str) -> dict[str, Any]:
        src = self._mapping(value, where, set(BREAKDOWNS))
        out = {}
        for key in BREAKDOWNS:
            if key in src:
                out[key] = self.breakdown(src[key], f"{where}.{key}")
        if "breakdown" not in out:
            raise SanitizeError(f"{where}.breakdown: required")
        return out

    def breakdown(self, value: Any, where: str) -> dict[str, Any]:
        src = self._mapping(value, where, set(BREAKDOWN_DECIMALS) | {"resources"})
        out: dict[str, Any] = {}
        self._copy_decimals(src, out, BREAKDOWN_DECIMALS, where, required=("totalMonthlyCost",))
        resources = src.get("resources")
        if not isinstance(resources, list):
            raise SanitizeError(f"{where}.resources: expected a list")
        out["resources"] = [self.resource(r, f"{where}.resources[{i}]") for i, r in enumerate(resources)]
        return out

    def resource(self, value: Any, where: str) -> dict[str, Any]:
        src = self._mapping(value, where, set(RESOURCE_DECIMALS) | {"name", "resourceType", "costComponents",
                                                                  "subresources"})
        out: dict[str, Any] = {"name": self._string(src.get("name"), f"{where}.name")}
        if "resourceType" in src:
            out["resourceType"] = self._string(src["resourceType"], f"{where}.resourceType", RESOURCE_TYPE_RE)
        self._copy_decimals(src, out, RESOURCE_DECIMALS, where)
        if "costComponents" in src:
            components = src["costComponents"]
            if not isinstance(components, list):
                raise SanitizeError(f"{where}.costComponents: expected a list")
            out["costComponents"] = [self.component(c, f"{where}.costComponents[{i}]")
                                     for i, c in enumerate(components)]
        if "subresources" in src:
            subresources = src["subresources"]
            if not isinstance(subresources, list):
                raise SanitizeError(f"{where}.subresources: expected a list")
            out["subresources"] = [self.resource(r, f"{where}.subresources[{i}]") for i, r in enumerate(subresources)]
        return out

    def component(self, value: Any, where: str) -> dict[str, Any]:
        src = self._mapping(value, where, set(COMPONENT_DECIMALS) | {"name", "unit", "priceNotFound"})
        out: dict[str, Any] = {
            "name": self._string(src.get("name"), f"{where}.name"),
            "unit": self._string(src.get("unit"), f"{where}.unit"),
        }
        self._copy_decimals(src, out, COMPONENT_DECIMALS, where)
        found = src.get("priceNotFound")
        if not isinstance(found, bool):
            raise SanitizeError(f"{where}.priceNotFound: expected a boolean")
        out["priceNotFound"] = found
        if found:
            self.price_not_found.append(where)
        return out


def recheck_strings(value: Any, where: str = "$") -> None:
    """Fail closed if any key or string value matches a forbidden pattern (D8)."""
    if isinstance(value, dict):
        for key, item in value.items():
            recheck_strings(key, f"{where} (key)")
            recheck_strings(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            recheck_strings(item, f"{where}[{index}]")
    elif isinstance(value, str):
        for label, pattern in FORBIDDEN_STRINGS.items():
            if pattern.search(value):
                raise SanitizeError(f"{where}: forbidden {label}")


def drift_report_sha256(report: Any) -> str:
    """Task 9A.1 canonical hash: sorted keys, compact separators, UTF-8."""
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_json(path: Path, label: str) -> Any:
    if not path.is_file():
        raise UsageError(f"{label}: not a readable file")
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SanitizeError(f"{label}: not valid JSON ({type(exc).__name__})") from None


def report_binding(report: Any, run_id: str) -> tuple[str, str]:
    """Returns (environment, canonical hash); the report's run must be this run."""
    run = report.get("run") if isinstance(report, dict) else None
    if not isinstance(run, dict):
        raise SanitizeError("drift report: missing run")
    if run.get("run_id") != run_id:
        raise SanitizeError("drift report: run.run_id does not match --run-id")
    environment = run.get("environment")
    if not isinstance(environment, str) or not ENVIRONMENT_RE.match(environment):
        raise SanitizeError("drift report: invalid run.environment")
    return environment, drift_report_sha256(report)


def dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_mode(args: argparse.Namespace) -> int:
    if args.infracost_version != INFRACOST_VERSION:
        raise UsageError(f"--infracost-version must be {INFRACOST_VERSION}")
    if not ENVIRONMENT_RE.match(args.environment):
        raise UsageError("--environment is invalid")
    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute() or not out_dir.is_dir() or any(out_dir.iterdir()):
        raise UsageError("--output-dir must be an existing, empty, absolute directory")
    raw = load_json(Path(args.raw), "--raw")
    report = load_json(Path(args.drift_report), "--drift-report")

    environment, report_hash = report_binding(report, args.run_id)
    if environment != args.environment:
        raise SanitizeError("drift report: run.environment does not match --environment")
    projector = Projector(strict=False)
    infracost = projector.root(raw)
    if projector.price_not_found:
        print(f"price_not_found: {len(projector.price_not_found)} cost component(s), first at "
              f"{projector.price_not_found[0]}", file=sys.stderr)
        return EXIT_PRICE_NOT_FOUND
    cost_run = {
        "run_id": args.run_id,
        "environment": environment,
        "drift_report_sha256": report_hash,
        "infracost_version": INFRACOST_VERSION,
        "mode": MODE,
        "pricing": PRICING,
        "cost_sign_convention": COST_SIGN_CONVENTION,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    recheck_strings(infracost)
    recheck_strings({k: v for k, v in cost_run.items() if k != "cost_sign_convention"})

    # Both files appear only together; any failure leaves the directory empty.
    staged = []
    try:
        for name, data in (("infracost.json", infracost), ("cost_run.json", cost_run)):
            tmp = out_dir / f".{name}.tmp"
            tmp.write_text(dump(data), encoding="utf-8")
            staged.append((tmp, out_dir / name))
        for tmp, final in staged:
            os.replace(tmp, final)
    except OSError as exc:
        for tmp, final in staged:
            for path in (tmp, final):
                path.unlink(missing_ok=True)
        raise SanitizeError(f"--output-dir: write failed ({type(exc).__name__})") from None
    return EXIT_OK


def check_mode(args: argparse.Namespace) -> int:
    out_dir = Path(args.check)
    if not out_dir.is_absolute() or not out_dir.is_dir():
        raise UsageError("--check must be an existing absolute directory")
    names = sorted(p.name for p in out_dir.iterdir())
    if tuple(names) != OUTPUT_FILES:
        raise SanitizeError(f"--check: expected exactly {list(OUTPUT_FILES)}")
    report = load_json(Path(args.drift_report), "--drift-report")
    environment, report_hash = report_binding(report, args.run_id)

    infracost = load_json(out_dir / "infracost.json", "infracost.json")
    projector = Projector(strict=True)
    projected = projector.root(infracost)
    if projected != infracost:
        raise SanitizeError("infracost.json: not exactly the allowlist projection")
    recheck_strings(infracost)

    cost_run = load_json(out_dir / "cost_run.json", "cost_run.json")
    if not isinstance(cost_run, dict) or tuple(sorted(cost_run)) != COST_RUN_KEYS:
        raise SanitizeError(f"cost_run.json: expected exactly the keys {list(COST_RUN_KEYS)}")
    expected = {"run_id": args.run_id, "environment": environment, "drift_report_sha256": report_hash,
                "infracost_version": INFRACOST_VERSION, "mode": MODE, "pricing": PRICING,
                "cost_sign_convention": COST_SIGN_CONVENTION}
    for key, value in expected.items():
        if cost_run[key] != value:
            raise SanitizeError(f"cost_run.json: {key} does not match this run")
    if not isinstance(cost_run["generated_at"], str) or not TIMESTAMP_RE.match(cost_run["generated_at"]):
        raise SanitizeError("cost_run.json: invalid generated_at")
    if projector.price_not_found:
        print(f"price_not_found: {len(projector.price_not_found)} cost component(s)", file=sys.stderr)
        return EXIT_PRICE_NOT_FOUND
    return EXIT_OK


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # usage errors exit 64, not argparse's 2 (2 = price_not_found)
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(EXIT_USAGE)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = _Parser(prog="sanitize_infracost.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", metavar="DIR")
    parser.add_argument("--raw")
    parser.add_argument("--drift-report", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--environment")
    parser.add_argument("--infracost-version")
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)
    write_args = ("raw", "environment", "infracost_version", "output_dir")
    if args.check is not None:
        if any(getattr(args, a) is not None for a in write_args):
            parser.error("--check takes only --run-id and --drift-report")
    elif any(getattr(args, a) is None for a in write_args):
        parser.error("write mode needs --raw, --environment, --infracost-version and --output-dir")
    if not RUN_ID_RE.match(args.run_id):
        parser.error("--run-id is invalid")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    action: Callable[[argparse.Namespace], int] = check_mode if args.check is not None else write_mode
    try:
        return action(args)
    except UsageError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except SanitizeError as exc:
        print(f"sanitisation failed: {exc}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
