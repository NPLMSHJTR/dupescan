"""Tests for the corpus generator and the pairwise scorer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dupescan.evaluate import evaluate
from dupescan.gen import generate


class GeneratorTests(unittest.TestCase):
    def test_writes_documents_and_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            truth = generate(root / "docs.jsonl", root / "truth.json", docs=300, seed=4)
            lines = (root / "docs.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 300)
            self.assertTrue(truth["pairs"])
            self.assertGreater(truth["families"], 0)

            stored = json.loads((root / "truth.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["schema_version"], 1)
            self.assertEqual(stored["truth_jaccard"], 0.85)

    def test_pairs_are_sorted_and_unique(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            truth = generate(Path(tmp) / "docs.jsonl", Path(tmp) / "truth.json", docs=400, seed=5)
            pairs = [tuple(pair) for pair in truth["pairs"]]
            self.assertEqual(pairs, sorted(pairs))
            self.assertEqual(len(pairs), len(set(pairs)))
            for first, second in pairs:
                self.assertLess(first, second)

    def test_rejects_tiny_corpora(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            generate(Path(tmp) / "d.jsonl", Path(tmp) / "t.json", docs=5)


class ScoringTests(unittest.TestCase):
    def test_set_arithmetic(self) -> None:
        truth = {"docs": 10, "pairs": [["d1", "d2"], ["d3", "d4"]]}
        predicted = {
            "method": "minhash-lsh",
            "docs": 10,
            "elapsed_s": 1.0,
            "docs_per_s": 10,
            "matches": [
                {"a": "d2", "b": "d1", "jaccard": 0.9},
                {"a": "d5", "b": "d6", "jaccard": 0.88},
            ],
        }
        result = evaluate(truth, predicted)
        self.assertEqual(result["tp"], 1)
        self.assertEqual(result["fp"], 1)
        self.assertEqual(result["fn"], 1)
        self.assertAlmostEqual(result["precision"], 0.5)
        self.assertAlmostEqual(result["recall"], 0.5)
        self.assertAlmostEqual(result["f1"], 0.5)

    def test_duplicate_reports_do_not_inflate_counts(self) -> None:
        truth = {"docs": 3, "pairs": [["d1", "d2"]]}
        predicted = {
            "docs": 3,
            "matches": [
                {"a": "d1", "b": "d2", "jaccard": 0.95},
                {"a": "d2", "b": "d1", "jaccard": 0.95},
            ],
        }
        result = evaluate(truth, predicted)
        self.assertEqual(result["tp"], 1)
        self.assertEqual(result["fp"], 0)
        self.assertAlmostEqual(result["precision"], 1.0)


if __name__ == "__main__":
    unittest.main()
