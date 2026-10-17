"""Artifact store: the real workflow artifacts under one data directory (Task 13.1).

The data directory holds downloaded workflow artifacts in any layout, for example
`gh run download <run-id> --dir DATA_DIR`, which writes one sub-directory per
artifact (`drift-report-<id>/drift_report.json`, `ai-analysis-report-<id>/...`).
It is indexed on every request, so newly downloaded runs appear without a restart,
and nothing is ever written to it.

Every drift report is keyed by its `run.run_id`. The other artifacts are attached
to a report only when they are bound to it:
- `ai_analysis_report.json`: `provenance.run_id` and `provenance.drift_report_sha256`
  (the canonical SHA-256, `investigation_public.canonical_sha256`);
- `drift_investigation.json`: loaded with `investigation_public.load_public` (leak
  scan and strict model) and bound with `investigation_public.check_binding`;
- `cost_run.json`: `run_id` and `drift_report_sha256`.
Two different documents for one run make that slot ambiguous: neither is used.
Problems are fixed codes, never file content or paths.
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from drift_engine import investigation_public as pub
from drift_engine.logs import log_event

logger = logging.getLogger(__name__)

REPORT_FILE = "drift_report.json"
AI_REPORT_FILE = "ai_analysis_report.json"
INVESTIGATION_FILE = pub.PUBLIC_FILE
COST_RUN_FILE = "cost_run.json"
FILES = (REPORT_FILE, AI_REPORT_FILE, INVESTIGATION_FILE, COST_RUN_FILE)
MAX_FILE_BYTES = pub.MAX_INPUT_BYTES
MAX_DEPTH = 6
MAX_FILES = 5000
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


class StoreUnavailable(Exception):
    """The data directory is missing or unreadable."""


@dataclass(frozen=True)
class Bundle:
    """One detection run: its drift report and the artifacts bound to it."""

    run_id: str
    report: dict
    report_sha256: str
    ai_report: dict | None = None
    investigation: pub.PublicInvestigation | None = None
    cost_run: dict | None = None
    problems: tuple[str, ...] = ()

    @property
    def run(self) -> dict:
        return self.report.get("run") or {}

    @property
    def environment(self) -> str | None:
        return self.run.get("environment")

    @property
    def finished_at(self) -> str:
        return self.run.get("finished_at") or self.run.get("started_at") or ""


@dataclass
class Index:
    bundles: list[Bundle]  # newest first
    problems: Counter = field(default_factory=Counter)

    def get(self, run_id: str) -> Bundle | None:
        return next((b for b in self.bundles if b.run_id == run_id), None)

    def latest_per_environment(self) -> list[Bundle]:
        seen, latest = set(), []
        for bundle in self.bundles:
            if bundle.environment not in seen:
                seen.add(bundle.environment)
                latest.append(bundle)
        return latest


def _files(root: str) -> list[tuple[str, str]]:
    """(file name, path) of every known artifact file; symbolic links are never followed."""
    found: list[tuple[str, str]] = []
    base = root.rstrip(os.sep).count(os.sep)
    for directory, subdirs, names in os.walk(root, followlinks=False):
        if directory.count(os.sep) - base >= MAX_DEPTH:
            subdirs[:] = []
        subdirs[:] = sorted(d for d in subdirs if not os.path.islink(os.path.join(directory, d)))
        for name in sorted(names):
            path = os.path.join(directory, name)
            if name in FILES and not os.path.islink(path):
                found.append((name, path))
                if len(found) >= MAX_FILES:
                    return found
    return found


def _read(path: str) -> bytes | None:
    try:
        with open(path, "rb") as fh:
            data = fh.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None
    return data if len(data) <= MAX_FILE_BYTES else None


def _json(data: bytes) -> Any:
    try:
        return pub.strict_json(data)
    except (ValueError, RecursionError, UnicodeDecodeError):
        return None


def _is_report(doc: Any) -> bool:
    run = doc.get("run") if isinstance(doc, dict) else None
    return (isinstance(run, dict) and isinstance(run.get("run_id"), str) and bool(RUN_ID.match(run["run_id"]))
            and isinstance(doc.get("summary"), dict) and isinstance(doc.get("resources"), list))


def _single(candidates: dict[str, Any], slot: str, problems: list[str]) -> Any:
    """The one distinct candidate (keyed by canonical SHA-256), else None."""
    if len(candidates) > 1:
        problems.append(f"{slot}_ambiguous")
        return None
    return next(iter(candidates.values()), None)


def load(root: str) -> Index:
    """Index the data directory. Raises StoreUnavailable when it cannot be read."""
    if not root or not os.path.isdir(root) or os.path.islink(root):
        raise StoreUnavailable("data directory unavailable")
    problems: Counter = Counter()
    reports: dict[str, dict[str, tuple[dict, bytes]]] = {}
    ai_reports: list[dict] = []
    investigations: list[tuple[pub.PublicInvestigation, dict]] = []
    cost_runs: list[dict] = []
    for name, path in _files(root):
        data = _read(path)
        if data is None:
            problems["unreadable_file"] += 1
            continue
        if name == INVESTIGATION_FILE:
            try:
                investigation = pub.load_public(data)
            except pub.PublicInvestigationError as exc:
                problems[f"investigation_{exc.code}"] += 1
                continue
            investigations.append((investigation, _json(data)))
            continue
        doc = _json(data)
        if name == REPORT_FILE:
            if not _is_report(doc):
                problems["report_invalid"] += 1
                continue
            reports.setdefault(doc["run"]["run_id"], {})[pub.canonical_sha256(doc)] = (doc, data)
        elif name == AI_REPORT_FILE and isinstance(doc, dict) and isinstance(doc.get("provenance"), dict):
            ai_reports.append(doc)
        elif name == COST_RUN_FILE and isinstance(doc, dict):
            cost_runs.append(doc)
        else:
            problems[f"{name.removesuffix('.json')}_invalid"] += 1

    bundles = []
    for run_id, versions in reports.items():
        if len(versions) > 1:
            problems["report_conflict"] += 1  # two different reports claim one run id: use neither
            continue
        sha, (report, raw) = next(iter(versions.items()))
        notes: list[str] = []
        ai = _single({pub.canonical_sha256(d): d for d in ai_reports
                      if d["provenance"].get("run_id") == run_id
                      and d["provenance"].get("drift_report_sha256") == sha}, "ai_report", notes)
        bound = {}
        for investigation, doc in investigations:
            try:
                pub.check_binding(investigation, raw)
            except pub.PublicInvestigationError:
                continue
            bound[pub.canonical_sha256(doc)] = investigation
        investigation = _single(bound, "investigation", notes)
        if ai is not None and investigation is not None and \
                ai["provenance"].get("investigation_sha256") not in (None, next(iter(bound))):
            notes.append("ai_report_investigation_mismatch")
        cost = _single({pub.canonical_sha256(d): d for d in cost_runs
                        if d.get("run_id") == run_id and d.get("drift_report_sha256") == sha}, "cost_run", notes)
        bundles.append(Bundle(run_id, report, sha, ai, investigation, cost, tuple(notes)))
    bundles.sort(key=lambda b: (b.finished_at, b.run_id), reverse=True)
    if problems:
        log_event(logger, logging.WARNING, "dashboard_store_problems", "artifact problems skipped",
                  problems=dict(sorted(problems.items())))
    return Index(bundles, problems)
