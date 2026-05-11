#!/usr/bin/env python3
"""
Claude Code Verifier CLI.

Compare two answers for mathematical equivalence.

Usage:
  python scripts/cc_verify.py "sin(x)" "sin(x)" x expression
  python scripts/cc_verify.py "x**2/2" "x^2/2 + C" x expression

Output: JSON {"is_eq": true, "level_used": "L1", "confidence": 1.0, "evidence": "..."}
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from calc_solver.tools.verifier import Verifier


async def main():
    if len(sys.argv) < 3:
        print(json.dumps({"is_eq": False, "level_used": "fail", "confidence": 0.0,
                          "evidence": "Usage: cc_verify.py <pred> <gold> [var] [answer_type] [question]"}))
        sys.exit(1)

    pred = sys.argv[1]
    gold = sys.argv[2]
    var = sys.argv[3] if len(sys.argv) > 3 else "x"
    answer_type = sys.argv[4] if len(sys.argv) > 4 else "expression"
    question = sys.argv[5] if len(sys.argv) > 5 else ""

    verifier = Verifier(llm_client=None, llm_for_unsure=False, n_samples=30)
    result = await verifier.is_equivalent(pred, gold, var=var, answer_type=answer_type, question=question)
    print(json.dumps(result.model_dump(), ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
