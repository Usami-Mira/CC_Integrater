#!/usr/bin/env python3
"""
Convert CC_Integrater output to CritPt submission JSON format.

After CC_Integrater processes all problems, run this script to collect
all solution_code.py files and convert them to the JSON format required
by the CritPt evaluation server.

Usage:
  python3 convert_to_critpt_submission.py

Output:
  A submissions/ directory containing one JSON file per problem,
  ready for evaluation via evaluate_all_results.py or the API.
"""
import os, sys, json, re
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent  # CC_Integrater/
PROBLEMS_DIR = SCRIPT_DIR / "problems"
OUTPUT_DIR = SCRIPT_DIR / "submissions"

OUTPUT_DIR.mkdir(exist_ok=True)

# Map from CC_Integrater directory name to CritPt problem_id
# e.g., "001" → "Challenge_1_main"
def get_problem_id(dir_name):
    try:
        num = int(dir_name)  # 001 → 1
        return f"Challenge_{num}_main"
    except ValueError:
        return None

converted = 0
skipped = 0
errors = []

for prob_dir in sorted(PROBLEMS_DIR.iterdir()):
    if not prob_dir.is_dir():
        continue

    problem_id = get_problem_id(prob_dir.name)
    if problem_id is None:
        continue

    code_file = prob_dir / "solution_code.py"
    if not code_file.exists():
        skipped += 1
        print(f"  SKIP: {prob_dir.name} — no solution_code.py found")
        continue

    generated_code = code_file.read_text(encoding="utf-8")

    # Validate that code is not still a template (contains ...)
    if "..." in generated_code and "def " in generated_code:
        # Check if ... appears inside a function body
        lines = generated_code.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "= ..." in stripped or "=..." in stripped:
                errors.append(f"{prob_dir.name}: template '...' still present in code")
                break

    # Build submission JSON
    submission = {
        "problem_id": problem_id,
        "generated_code": generated_code,
        "model": "cc_integrater",  # Replace with actual model used
        "timestamp": datetime.now().isoformat(),
        "generation_config": {
            "parsing": False,  # two-step mode in CC_Integrater
            "use_golden_for_prev_steps": False,
            "pipeline": "CC_Integrater (Planner → Builder → Evaluator)",
        },
        "messages": []
    }

    # Save
    output_file = OUTPUT_DIR / f"{problem_id}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(submission, f, indent=2, ensure_ascii=False)

    converted += 1
    print(f"  OK: {prob_dir.name} → {problem_id}.json")

print(f"\nConversion complete!")
print(f"  Converted: {converted}")
print(f"  Skipped: {skipped}")
if errors:
    print(f"  Warnings: {len(errors)}")
    for e in errors:
        print(f"    - {e}")
print(f"\nSubmissions saved to: {OUTPUT_DIR}")
print(f"\nTo evaluate, copy this directory to the CritPt project root and run:")
print(f"  python evaluate_all_results.py --api-key YOUR_API_KEY")