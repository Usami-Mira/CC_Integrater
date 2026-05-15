#!/usr/bin/env python3
"""
Setup script: convert challenges_no_system/*.md into CC_Integrater problem format.

Usage:
  python3 setup_problems.py

This reads all Challenge_*_main.md files from ../ (parent = challenges_no_system/)
and creates a problems/ directory structure compatible with CC_Integrater.
"""
import os, sys, re, json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent  # CC_Integrater/
CHALLENGES_DIR = SCRIPT_DIR.parent  # challenges_no_system/
PROBLEMS_DIR = SCRIPT_DIR / "problems"

# Clean and recreate problems directory
if PROBLEMS_DIR.exists():
    import shutil
    shutil.rmtree(PROBLEMS_DIR)
PROBLEMS_DIR.mkdir(parents=True)

# Find all challenge files
challenge_files = sorted(CHALLENGES_DIR.glob("Challenge_*_main.md"))

for cf in challenge_files:
    # Extract challenge number
    m = re.match(r"Challenge_(\d+)_main\.md", cf.name)
    if not m:
        continue
    num = m.group(1)
    padded = num.zfill(3)  # 001, 010, 070, etc.

    content = cf.read_text(encoding="utf-8")

    # Parse out the "Problem:" prefix, "Code Template:" block, and "Instructions:"
    # Extract the actual problem text
    # The format is:
    # Problem:
    # <problem text>
    # Code Template:
    # ```python
    # <code>
    # ```
    # Instructions:
    # <instructions>

    # Extract problem text (between "Problem:\n" and "\nCode Template:")
    problem_match = re.search(r"^Problem:\n(.*?)\nCode Template:", content, re.DOTALL)
    code_match = re.search(r"```python\n(.*?)\n```", content, re.DOTALL)

    problem_text = problem_match.group(1).strip() if problem_match else ""
    code_template = code_match.group(1).strip() if code_match else ""

    # Build the problem.md content
    problem_md = f"""# Challenge {num} — CritPt Physics Problem

{problem_text}

---

## Code Template (CritPt Submission Requirement)

The final answer must be provided as completed Python code. Replace the `...` placeholder below with your answer.

```python
{code_template}
```
"""

    # Create problem directory
    prob_dir = PROBLEMS_DIR / padded
    prob_dir.mkdir(parents=True, exist_ok=True)

    prob_file = prob_dir / "problem.md"
    prob_file.write_text(problem_md, encoding="utf-8")

    print(f"  Challenge_{num} → problems/{padded}/problem.md")

# Create batch info
total = len(challenge_files)
print(f"\nDone! {total} problems created in {PROBLEMS_DIR}")
print(f"Directory structure:")
print(f"  problems/")
for d in sorted(PROBLEMS_DIR.iterdir()):
    print(f"    {d.name}/problem.md")