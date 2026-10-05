#!/usr/bin/env python3
"""Opt-in safeguard mutation check for the Phase 6 AI engine (Task 6.7).

Each mutant in tests/mutation/mutants.json deliberately breaks one safeguard
(replaces an exact source snippet). The AI test suite must fail for every
mutant; a mutant that survives means a safeguard is not actually tested.

    python scripts/run_mutation_checks.py              # all mutants, parallel
    python scripts/run_mutation_checks.py --only ID    # selected mutants
    python scripts/run_mutation_checks.py --list

Works on throwaway copies of src/ and tests/ in a temporary directory: the
repository is never modified. Before mutating, it checks that the unmutated
suite passes in the copy and that Python imports the copy's src/ (not the
editable install), so a survivor cannot be an import-path accident.
Not part of the default test run (a few minutes); tests/test_mutation_corpus.py
keeps the corpus from going stale. Exit 0 only if every mutant is caught.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "mutation" / "mutants.json"


def load_corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def make_copy(base: Path) -> Path:
    work = Path(tempfile.mkdtemp(prefix="mutant-", dir=base))
    for name in ("src", "tests", "schemas", "scripts"):  # scripts: consumer tests load them (Task 9B.4A)
        shutil.copytree(ROOT / name, work / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return work


def run_tests(work: Path, tests: list[str], python: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([python, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *tests],
                          cwd=work, env=env, capture_output=True, text=True)


def check_copy(work: Path, tests: list[str], python: str) -> None:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    imported = subprocess.run([python, "-c", "import ai_engine; print(ai_engine.__file__)"], cwd=work, env=env,
                              capture_output=True, text=True).stdout.strip()
    if not Path(imported).resolve().is_relative_to(work.resolve()):
        sys.exit(f"abort: ai_engine imported from {imported!r}, not from the mutation copy")
    baseline = run_tests(work, tests, python)
    if baseline.returncode != 0:
        sys.exit("abort: the unmutated suite fails in the copy:\n" + baseline.stdout[-2000:])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", action="append", default=[], help="mutant id (repeatable)")
    parser.add_argument("--list", action="store_true", help="list mutant ids and exit")
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--python", default=sys.executable, help="interpreter with the dev and ai extras")
    args = parser.parse_args(argv)

    corpus = load_corpus()
    mutants = corpus["mutants"]
    if args.list:
        for m in mutants:
            print(m["id"])
        return 0
    if args.only:
        unknown = set(args.only) - {m["id"] for m in mutants}
        if unknown:
            sys.exit(f"unknown mutant id(s): {', '.join(sorted(unknown))}")
        mutants = [m for m in mutants if m["id"] in args.only]
    tests = corpus["tests"]

    base = Path(tempfile.mkdtemp(prefix="ai-engine-mutation-"))
    try:
        workers: queue.Queue[Path] = queue.Queue()
        copies = [make_copy(base) for _ in range(max(1, args.jobs))]
        check_copy(copies[0], tests, args.python)
        for work in copies:
            workers.put(work)

        def run(mutant: dict) -> tuple[str, str]:
            work = workers.get()
            target = work / mutant["file"]
            original = (ROOT / mutant["file"]).read_text(encoding="utf-8")
            try:
                if original.count(mutant["old"]) != 1:
                    return mutant["id"], "not-applicable"
                target.write_text(original.replace(mutant["old"], mutant["new"], 1), encoding="utf-8")
                result = run_tests(work, tests, args.python)
                return mutant["id"], "caught" if result.returncode != 0 else "SURVIVED"
            finally:
                target.write_text(original, encoding="utf-8")
                workers.put(work)

        with ThreadPoolExecutor(max_workers=len(copies)) as pool:
            results = list(pool.map(run, mutants))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    bad = [(mid, status) for mid, status in results if status != "caught"]
    for mid, status in bad:
        print(f"{status:15} {mid}")
    print(f"caught {len(results) - len(bad)} / {len(results)} mutants")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
