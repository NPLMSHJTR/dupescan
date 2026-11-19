"""Pairwise precision, recall, and F1 for near-duplicate detection."""

from __future__ import annotations

from typing import Any


def _normalise(pair: Any) -> tuple[str, str]:
    if isinstance(pair, dict):
        first, second = str(pair["a"]), str(pair["b"])
    else:
        first, second = str(pair[0]), str(pair[1])
    return (first, second) if first <= second else (second, first)


def evaluate(truth: dict[str, Any], predicted: dict[str, Any]) -> dict[str, Any]:
    """Score predicted pairs against the generator's families."""
    truth_pairs = {_normalise(pair) for pair in truth.get("pairs", [])}
    predicted_pairs = {_normalise(match) for match in predicted.get("matches", [])}
    # Pairs reported inside the same family that the generator never listed
    # cannot exist, but a defensive intersection keeps the arithmetic honest.
    true_positive = truth_pairs & predicted_pairs
    false_positive = predicted_pairs - truth_pairs
    false_negative = truth_pairs - predicted_pairs

    precision = len(true_positive) / len(predicted_pairs) if predicted_pairs else 0.0
    recall = len(true_positive) / len(truth_pairs) if truth_pairs else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {
        "method": predicted.get("method", "unknown"),
        "docs": int(predicted.get("docs") or truth.get("docs") or 0),
        "truth_pairs": len(truth_pairs),
        "predicted_pairs": len(predicted_pairs),
        "tp": len(true_positive),
        "fp": len(false_positive),
        "fn": len(false_negative),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "elapsed_s": predicted.get("elapsed_s"),
        "docs_per_s": predicted.get("docs_per_s"),
    }
