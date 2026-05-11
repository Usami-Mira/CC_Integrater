#!/usr/bin/env python3
"""
Generate a summary report from Claude Code solving traces.

Usage:
  python scripts/cc_summary.py logs/cc/20260511_153000
  python scripts/cc_summary.py --latest  # auto-find most recent run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def find_latest_log_dir(base: str = "logs/cc") -> Path:
    base_path = Path(base)
    if not base_path.exists():
        print("No log directories found under logs/cc/", file=sys.stderr)
        sys.exit(1)
    dirs = sorted(base_path.iterdir())
    return dirs[-1]


def load_traces(log_dir: Path) -> list[dict]:
    traces_dir = log_dir / "traces"
    if not traces_dir.exists():
        print(f"No traces/ directory in {log_dir}", file=sys.stderr)
        sys.exit(1)

    traces = []
    for f in sorted(traces_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            traces.append(data)
        except Exception:
            traces.append({"problem_id": f.stem, "error": "failed_to_load_trace"})
    return traces


def build_summary(traces: list[dict], log_dir: Path) -> dict:
    total = len(traces)
    correct = 0
    wrong = 0
    skipped = 0
    verifier_levels = {}
    strategies_success: dict[str, int] = {}

    for t in traces:
        status = t.get("status", "unknown")
        if status == "CORRECT":
            correct += 1
        elif status == "WRONG":
            wrong += 1
        elif status == "SKIPPED":
            skipped += 1
        else:
            wrong += 1  # treat unknown as wrong

        level = t.get("verifier_level", "N/A")
        verifier_levels[level] = verifier_levels.get(level, 0) + 1

        if status == "CORRECT" and t.get("strategy"):
            strat = t["strategy"]
            strategies_success[strat] = strategies_success.get(strat, 0) + 1

    accuracy = correct / total if total > 0 else 0.0

    summary = {
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "skipped": skipped,
        "accuracy": round(accuracy, 4),
        "verifier_levels": verifier_levels,
        "strategies_success": strategies_success,
        "log_dir": str(log_dir),
        "per_problem": [
            {
                "problem_id": t.get("problem_id", "?"),
                "status": t.get("status", "?"),
                "answer": t.get("answer", ""),
                "gold": t.get("gold", ""),
                "strategy": t.get("strategy", ""),
                "verifier_level": t.get("verifier_level", ""),
                "loops": t.get("loops", 0),
            }
            for t in traces
        ],
    }
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log_dir", nargs="?", help="Path to a specific cc log directory")
    parser.add_argument("--latest", action="store_true", help="Use the most recent log directory")
    args = parser.parse_args()

    if args.latest or not args.log_dir:
        log_dir = find_latest_log_dir()
    else:
        log_dir = Path(args.log_dir)

    print(f"Reading traces from {log_dir}/traces/")
    traces = load_traces(log_dir)

    summary = build_summary(traces, log_dir)

    # Write summary.json
    summary_path = log_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Print to stdout
    print(f"\n{'='*60}")
    print(f"SUMMARY: {log_dir}")
    print(f"{'='*60}")
    print(f"  Total:     {summary['total']}")
    print(f"  Correct:   {summary['correct']}")
    print(f"  Wrong:     {summary['wrong']}")
    print(f"  Skipped:   {summary['skipped']}")
    print(f"  Accuracy:  {summary['accuracy']:.1%}")
    print(f"  Levels:    {json.dumps(summary['verifier_levels'])}")
    print(f"  Summary:   {summary_path}")
    print(f"{'='*60}")

    # Also print table
    print(f"\n{'problem_id':<15} {'status':<10} {'answer':<30} {'strategy':<15} {'level'}")
    print("-" * 100)
    for p in summary["per_problem"]:
        ans = (p["answer"] or "")[:28]
        print(f"{p['problem_id']:<15} {p['status']:<10} {ans:<30} {p.get('strategy',''):<15} {p.get('verifier_level','')}")


if __name__ == "__main__":
    main()
