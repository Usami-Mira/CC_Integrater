#!/usr/bin/env python3
"""
Load problems from parquet and output as JSON for Claude Code Agent prompts.

Usage:
  python scripts/cc_load.py --parquet question_filtered_example.parquet          # all
  python scripts/cc_load.py --parquet question_filtered_example.parquet --n 3     # first 3
  python scripts/cc_load.py --parquet question_filtered_example.parquet --id 19_26  # single
"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", default="question_filtered_example.parquet")
    parser.add_argument("--n", type=int, default=None, help="Max problems to load")
    parser.add_argument("--id", type=str, default=None, help="Load specific problem ID")
    args = parser.parse_args()

    df = pd.read_parquet(args.parquet)

    problems = []
    for i, row in df.iterrows():
        question = str(row.get("question", "")).strip()
        answer = str(row.get("answer", "")).strip()
        pid = str(row.get("id", f"row_{i}"))

        if args.id and pid != args.id:
            continue

        if not question or len(question) < 2:
            continue

        tag = row.get("tag", {})
        if isinstance(tag, dict):
            problem_type = tag.get("problem_type", "expression")
        else:
            problem_type = "expression"

        problems.append({
            "problem_id": pid,
            "question": question,
            "gold_answer": answer,
            "problem_type": problem_type,
        })

        if args.n and len(problems) >= args.n:
            break

    if not problems:
        print(json.dumps({"error": "no problems found"}), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(problems, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
