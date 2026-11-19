"""Markdown and JSON output for a dupescan run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_reports(
    result: dict[str, Any],
    baseline: dict[str, Any] | None,
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / "metrics.json"
    payload = {"schema_version": 1, "method": result, "baseline": baseline}
    metrics_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# dupescan report",
        "",
        f"- documents: {result['docs']:,}",
        f"- truth pairs: {result['truth_pairs']:,}",
        f"- runtime: {result['elapsed_s']} s ({result['docs_per_s']} docs/s)",
        "",
        "## Headline",
        "",
        "| method | precision | recall | F1 | pairs | TP | FP | FN |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        f"| MinHash + LSH | {result['precision']:.3f} | {result['recall']:.3f} | "
        f"{result['f1']:.3f} | {result['predicted_pairs']:,} | {result['tp']:,} | "
        f"{result['fp']:,} | {result['fn']:,} |",
    ]
    if baseline:
        lines.append(
            f"| exact hashing | {baseline['precision']:.3f} | {baseline['recall']:.3f} | "
            f"{baseline['f1']:.3f} | {baseline['predicted_pairs']:,} | {baseline['tp']:,} | "
            f"{baseline['fp']:,} | {baseline['fn']:,} |"
        )
    lines.extend(
        [
            "",
            "## Reading this",
            "",
            "Exact hashing has perfect precision by construction: two documents "
            "either normalise to the same string or they do not. Its recall is the "
            "share of duplicate pairs that survive a single edited word, which is "
            "the number MinHash + LSH exists to improve.",
            "",
        ]
    )
    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return {"report": report_path, "metrics": metrics_path}
