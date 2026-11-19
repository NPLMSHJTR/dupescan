"""Command-line interface for dupescan."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .evaluate import evaluate
from .gen import generate
from .report import write_reports

EXIT_OK = 0
EXIT_ERROR = 2
SCANNER = Path(__file__).resolve().parents[3] / "scanner" / "scan.ts"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return payload


def _scan(docs: str, out: str, exact: bool = False) -> None:
    node = shutil.which("node")
    if node is None:
        raise ValueError("node is required; install Node 22.6 or newer")
    command = [node, "--experimental-strip-types", str(SCANNER), "--docs", docs, "--out", out]
    if exact:
        command.append("--exact")
    subprocess.run(command, check=True, cwd=Path.cwd())


def cmd_gen(args: argparse.Namespace) -> int:
    truth = generate(Path(args.docs), Path(args.truth), docs=args.count, seed=args.seed)
    print(
        f"wrote {args.docs}: {truth['docs']:,} documents, "
        f"{len(truth['pairs']):,} duplicate pairs in {truth['families']:,} families"
    )
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir)
    docs_path = workdir / "docs.jsonl"
    truth_path = workdir / "truth.json"
    pairs_path = workdir / "pairs.json"
    exact_path = workdir / "exact.json"

    generate(docs_path, truth_path, docs=args.count, seed=args.seed)
    _scan(str(docs_path), str(pairs_path))
    _scan(str(docs_path), str(exact_path), exact=True)

    truth = _load(truth_path)
    result = evaluate(truth, _load(pairs_path))
    baseline = evaluate(truth, _load(exact_path))
    paths = write_reports(result, baseline, workdir / "reports")

    print(
        f"dupescan {__version__}  {result['docs']:,} documents  "
        f"{result['truth_pairs']:,} truth pairs"
    )
    for label, item in (("minhash", result), ("exact", baseline)):
        print(
            f"{label:<8} P {item['precision']:.3f}  R {item['recall']:.3f}  F1 {item['f1']:.3f}  "
            f"({item['predicted_pairs']:,} pairs, {item['docs_per_s']} docs/s)"
        )
    print(f"report: {paths['report']}")
    return EXIT_OK


def cmd_eval(args: argparse.Namespace) -> int:
    truth = _load(Path(args.truth))
    result = evaluate(truth, _load(Path(args.pairs)))
    baseline = evaluate(truth, _load(Path(args.baseline))) if args.baseline else None
    paths = write_reports(result, baseline, Path(args.out))
    print(f"P {result['precision']:.3f}  R {result['recall']:.3f}  F1 {result['f1']:.3f}")
    print(f"report: {paths['report']}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dupescan",
        description="Find near-duplicate documents with MinHash and LSH, and score the result.",
    )
    parser.add_argument("--version", action="version", version=f"dupescan {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser("gen", help="generate a corpus with known duplicate families")
    gen.add_argument("--count", type=int, default=20_000)
    gen.add_argument("--seed", type=int, default=17)
    gen.add_argument("--docs", default="data/docs.jsonl")
    gen.add_argument("--truth", default="data/truth.json")
    gen.set_defaults(func=cmd_gen)

    run = subparsers.add_parser("run", help="generate, scan, and score in one step")
    run.add_argument("--count", type=int, default=20_000)
    run.add_argument("--seed", type=int, default=17)
    run.add_argument("--workdir", default="dupescan-run")
    run.set_defaults(func=cmd_run)

    evaluate_cmd = subparsers.add_parser("eval", help="score an existing pairs file")
    evaluate_cmd.add_argument("--truth", required=True)
    evaluate_cmd.add_argument("--pairs", required=True)
    evaluate_cmd.add_argument("--baseline", default=None)
    evaluate_cmd.add_argument("--out", default="reports")
    evaluate_cmd.set_defaults(func=cmd_eval)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"dupescan: {error}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
