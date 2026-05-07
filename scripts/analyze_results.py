"""
Usage: python scripts/analyze_results.py logs/<run_id>
Produces: logs/<run_id>/summary.md
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def summarize(run_dir: str) -> None:
    d = Path(run_dir)
    pipeline_log = d / "pipeline.jsonl"
    if not pipeline_log.exists():
        print(f"No pipeline.jsonl in {run_dir}")
        return

    records = []
    for line in pipeline_log.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except Exception:
            pass

    if not records:
        print("No records found.")
        return

    total = len(records)
    correct = sum(1 for r in records if r.get("is_correct"))
    accuracy = correct / total if total else 0.0

    method_counts: Counter = Counter()
    method_correct: Counter = Counter()
    for r in records:
        sid = r.get("chosen_strategy_id") or "none"
        method_counts[sid] += 1
        if r.get("is_correct"):
            method_correct[sid] += 1

    agreement_dist: Counter = Counter()
    for r in records:
        agreement_dist[r.get("method_agreement", 0)] += 1

    # Top-10 failures
    failures = [r for r in records if not r.get("is_correct")][:10]

    lines = [
        f"# Run Summary: {d.name}",
        "",
        f"**Accuracy**: {correct}/{total} = {accuracy:.1%}",
        "",
        "## Method Agreement Distribution",
        "| Agreement | Count |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in sorted(agreement_dist.items())],
        "",
        "## Strategy Usage",
        "| Strategy ID | Used | Correct |",
        "|---|---|---|",
        *[f"| {sid} | {cnt} | {method_correct.get(sid, 0)} |"
          for sid, cnt in method_counts.most_common(20)],
        "",
        "## Top Failure Snapshots",
    ]
    for r in failures:
        pid = r.get("problem_id", "?")
        note = r.get("notes", "")
        ans = r.get("final_answer", "")
        lines += [f"### {pid}", f"Answer: `{ans}`", f"Notes: {note}", ""]

    summary_text = "\n".join(lines)
    out = d / "summary.md"
    out.write_text(summary_text, encoding="utf-8")
    print(summary_text[:2000])
    print(f"\nSummary written to {out}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze_results.py logs/<run_id>")
        sys.exit(1)
    summarize(sys.argv[1])
