"""Task 6.7: keep the opt-in safeguard mutation corpus from going stale.

The mutants themselves run with `python scripts/run_mutation_checks.py` (a few
minutes, not part of the default suite). This cheap check makes sure every
mutant still applies to exactly one place in the source, so a refactor cannot
silently turn a safeguard mutant into a no-op.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = json.loads((ROOT / "tests" / "mutation" / "mutants.json").read_text(encoding="utf-8"))


class TestMutationCorpus(unittest.TestCase):
    def test_every_mutant_applies_exactly_once(self):
        for mutant in CORPUS["mutants"]:
            with self.subTest(mutant["id"]):
                source = (ROOT / mutant["file"]).read_text(encoding="utf-8")
                self.assertEqual(source.count(mutant["old"]), 1)
                self.assertNotEqual(mutant["old"], mutant["new"])

    def test_ids_unique_and_targets_safeguard_modules(self):
        ids = [m["id"] for m in CORPUS["mutants"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(m["file"].startswith("src/ai_engine/") for m in CORPUS["mutants"]))
        self.assertGreaterEqual(len(ids), 140)

    def test_listed_test_files_exist(self):
        for path in CORPUS["tests"]:
            self.assertTrue((ROOT / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
