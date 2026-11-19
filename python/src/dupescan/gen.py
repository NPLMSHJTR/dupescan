"""Corpus generator with known duplicate families.

The generator produces three kinds of documents: unique ones, exact copies, and
near-duplicates obtained by replacing a small fraction of tokens. Ground truth is
the set of pairs inside a family, which is what a pairwise evaluator can score.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

VOCABULARY = [
    "alpha",
    "bravo",
    "charlie",
    "delta",
    "echo",
    "foxtrot",
    "golf",
    "hotel",
    "india",
    "juliet",
    "kilo",
    "lima",
    "mike",
    "november",
    "oscar",
    "papa",
    "quebec",
    "romeo",
    "sierra",
    "tango",
    "uniform",
    "victor",
    "whiskey",
    "xray",
    "yankee",
    "zulu",
    "system",
    "network",
    "service",
    "cluster",
    "latency",
    "throughput",
    "request",
    "response",
    "cache",
    "queue",
    "worker",
    "shard",
    "replica",
    "index",
    "schema",
    "query",
    "report",
    "metric",
    "alert",
    "incident",
    "deploy",
    "release",
    "rollback",
    "pipeline",
    "artifact",
    "container",
    "image",
    "gateway",
    "proxy",
    "timeout",
    "retry",
    "budget",
    "quota",
    "tenant",
    "region",
    "zone",
    "backup",
    "restore",
    "policy",
    "audit",
    "token",
    "session",
    "cookie",
    "header",
    "payload",
    "stream",
    "batch",
    "window",
]

EDIT_RATE = 0.01
TRUTH_JACCARD = 0.85


def _paragraph(rng: random.Random, words: int) -> list[str]:
    return [rng.choice(VOCABULARY) for _ in range(words)]


def _shingles(text: str, size: int = 5) -> set[str]:
    words = text.lower().split()
    if len(words) < size:
        return {" ".join(words)} if words else set()
    return {" ".join(words[index : index + size]) for index in range(len(words) - size + 1)}


def _jaccard(left: str, right: str) -> float:
    first, second = _shingles(left), _shingles(right)
    union = first | second
    return len(first & second) / len(union) if union else 0.0


def _mutate(tokens: list[str], rng: random.Random) -> list[str]:
    mutated = list(tokens)
    for index in range(len(mutated)):
        if rng.random() < EDIT_RATE:
            mutated[index] = rng.choice(VOCABULARY)
    return mutated


def generate(
    docs_path: Path,
    truth_path: Path,
    docs: int = 20_000,
    near_duplicate_rate: float = 0.05,
    exact_duplicate_rate: float = 0.02,
    seed: int = 17,
) -> dict[str, Any]:
    """Write ``docs_path`` (JSONL) and ``truth_path`` (JSON) and return the truth."""
    if docs < 10:
        raise ValueError("docs must be at least 10")

    rng = random.Random(seed)
    texts: list[str] = []
    families: dict[int, list[str]] = {}
    roots: dict[int, int] = {}
    duplicate_rate = near_duplicate_rate + exact_duplicate_rate
    exact_share = exact_duplicate_rate / duplicate_rate if duplicate_rate else 0.0

    docs_path.parent.mkdir(parents=True, exist_ok=True)
    with docs_path.open("w", encoding="utf-8", newline="\n") as handle:
        for index in range(docs):
            doc_id = f"d{index:06d}"
            if index > 8 and rng.random() < duplicate_rate:
                base_index = rng.randrange(max(1, index - 2000), index)
                # Derive from the family's original, not from a variant of it:
                # chaining edits compounds drift and pushes real duplicates below
                # the similarity the detector is asked to find.
                family = roots.get(base_index, base_index)
                base = texts[family]
                roots[index] = family
                if rng.random() < exact_share:
                    text = base
                else:
                    tokens = base.split()
                    text = " ".join(_mutate(tokens, rng)) if tokens else base
                families.setdefault(family, [f"d{family:06d}"]).append(doc_id)
            else:
                text = " ".join(_paragraph(rng, rng.randint(70, 150)))
                families.setdefault(index, [doc_id])
            texts.append(text)
            handle.write(json.dumps({"id": doc_id, "text": text}, ensure_ascii=False) + "\n")

    pairs: list[list[str]] = []
    dropped = 0
    for members in families.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                left, right = members[i], members[j]
                if _jaccard(texts[int(left[1:])], texts[int(right[1:])]) >= TRUTH_JACCARD:
                    pairs.append(sorted((left, right)))
                else:
                    dropped += 1

    pairs.sort()
    payload = {
        "schema_version": 1,
        "docs": docs,
        "seed": seed,
        "families": len([members for members in families.values() if len(members) > 1]),
        "pairs": pairs,
        "dropped_pairs": dropped,
        "truth_jaccard": TRUTH_JACCARD,
    }
    truth_path.parent.mkdir(parents=True, exist_ok=True)
    truth_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
