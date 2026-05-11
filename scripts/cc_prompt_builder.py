#!/usr/bin/env python3
"""
Read configs/prompts.yaml and compose TWO prompts:
  1. SOLVE prompt (NO gold_answer) — for Planner/Builder phases
  2. VERIFY prompt (includes gold_answer) — for Evaluator phase

This enforces the same gold-answer isolation as the original pipeline's
SolvingProblem vs Problem separation.

Usage:
  echo "$PROBLEMS_JSON" | python scripts/cc_prompt_builder.py --log-dir logs/cc/20260511_153000 --phase solve   # → solve prompt
  echo "$PROBLEMS_JSON" | python scripts/cc_prompt_builder.py --log-dir logs/cc/20260511_153000 --phase verify  # → verify prompt
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def load_problems() -> list[dict]:
    raw = sys.stdin.read().strip()
    return json.loads(raw)


def load_prompts() -> dict:
    prompts_path = Path(__file__).parent.parent / "configs" / "prompts.yaml"
    with open(prompts_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_solve_prompt(problems: list[dict], log_dir: str, prompts: dict) -> str:
    planner_system = prompts["planner"]["system"]
    builder_system = prompts["builder"]["system"]
    replan_template = prompts["planner"]["replan_template"]

    prompt = f"""You are the Orchestrator for a calculus solving pipeline.
Read CLAUDE.md for project context and tool conventions.

## Security Rule: Gold Answer Isolation
The problems below intentionally OMIT gold_answer fields. You must NOT look up,
search, or reference the gold_answer while solving. Gold answers are only
available in the separate VERIFY phase.

## Logging Requirements
Write per-problem trace JSON files to: {log_dir}/traces/{{problem_id}}.json

Each trace file must have this structure:
{{
  "problem_id": "...",
  "question": "...",
  "strategies": [
    {{"strategy_id": "s1", "name": "...", "rationale": "...", "steps_outline": [...]}},
    ...
  ],
  "solutions": [
    {{
      "strategy_id": "s1",
      "steps": [
        {{"step_no": 1, "thought": "...", "tool": "...", "args": {{}}, "result": "...", "state": "..."}}
      ],
      "final_answer": "...",
      "final_answer_sympy": "...",
      "self_check_passed": true
    }},
    ...
  ]
}}

## Solving Workflow

For EACH of the {len(problems)} problems:

### 1. ANALYZE & PLAN
{planner_system}

### 2. SOLVE each strategy using SymPy CLI tools
{builder_system}

Available tools:
  python scripts/cc_sympy.py integrate_indef "expr" [var]
  python scripts/cc_sympy.py integrate_def "expr" var "a" "b"
  python scripts/cc_sympy.py differentiate "expr" [var] [n]
  python scripts/cc_sympy.py simplify "expr"
  python scripts/cc_sympy.py parse "expr" [var]
  python scripts/cc_sympy.py solve "expr" [var]
  python scripts/cc_sympy.py limit "expr" var "point" [dir]
  python scripts/cc_sympy.py series "expr" var "point" [n]
  python scripts/cc_sympy.py substitute "expr" "mapping"

### 3. If all strategies fail — replan
{replan_template}

Max 3 outer loops. Use completely different methods each time.

## Rules
- Do NOT attempt to guess, search for, or reference gold answers
- For indefinite integrals, self-check by differentiating result vs original integrand
- Use log() not ln() in SymPy expressions
- Be concise — show key steps and tool outputs, skip trivial restatements

"""

    prompt += "=" * 60 + "\n"
    prompt += f"PROBLEMS TO SOLVE ({len(problems)} total)\n"
    prompt += "Note: gold_answer is NOT included — it is only available during verification.\n"
    prompt += "=" * 60 + "\n\n"
    for p in problems:
        prompt += f"## {p['problem_id']}\n"
        prompt += f"Question: {p['question']}\n"
        prompt += f"Type: {p.get('problem_type', 'unknown')}\n\n"

    return prompt


def build_verify_prompt(problems: list[dict], log_dir: str) -> str:
    prompt = f"""You are the Evaluator for a calculus solving pipeline.

The previous phase has produced candidate answers for each problem.
Now you must verify them against the gold standard.

## Verification
For each problem, verify using:
  python scripts/cc_verify.py "candidate_answer" "gold_answer" [var] [answer_type]

This runs a 4-level cascade: L1 string → L2 symbolic → L3 type-specific → L4 numerical sampling.

## Update traces
For each problem, APPEND verification results to `{log_dir}/traces/{{problem_id}}.json`:
Add these fields:
{{
  "status": "CORRECT" | "WRONG",
  "answer": "<best candidate answer>",
  "best_strategy": "<strategy_id that produced it>",
  "verifier_level": "L1" | "L2" | "L3" | "L4" | "fail",
  "verifier_result": {{"is_eq": true/false, "confidence": 0.xx, "evidence": "..."}},
  "loops": <number of outer loops used>
}}

## Summary
After verifying ALL problems, write `{log_dir}/summary.json`:
{{
  "total": N,
  "correct": N,
  "wrong": N,
  "skipped": 0,
  "accuracy": 0.xx,
  "verifier_levels": {{"L1": 1, "L2": 3, ...}},
  "strategies_success": {{"strategy_name": count, ...}},
  "per_problem": [
    {{"problem_id": "...", "status": "CORRECT"/"WRONG", "answer": "...", "gold": "...", "strategy": "...", "verifier_level": "L1"/"L2"/..., "loops": 1}},
    ...
  ]
}}

"""

    prompt += "=" * 60 + "\n"
    prompt += f"PROBLEMS TO VERIFY ({len(problems)} total)\n"
    prompt += "=" * 60 + "\n\n"
    for p in problems:
        prompt += f"## {p['problem_id']}\n"
        prompt += f"Question: {p['question']}\n"
        prompt += f"Gold answer: {p['gold_answer']}\n"
        prompt += f"Type: {p.get('problem_type', 'unknown')}\n\n"

    return prompt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-dir", required=True)
    parser.add_argument("--phase", choices=["solve", "verify"], default="solve",
                        help="solve = no gold_answer, verify = include gold_answer")
    args = parser.parse_args()

    problems = load_problems()
    prompts = load_prompts()

    if args.phase == "solve":
        sys.stdout.write(build_solve_prompt(problems, args.log_dir, prompts))
    else:
        sys.stdout.write(build_verify_prompt(problems, args.log_dir))


if __name__ == "__main__":
    main()
