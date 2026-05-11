#!/usr/bin/env python3
"""
Claude Code SymPy Tool Server.

Provides a simple CLI interface for Builder agents to call SymPy tools via Bash:

  python scripts/cc_sympy.py differentiate "x**3" x
  python scripts/cc_sympy.py integrate_indef "x**2" x
  python scripts/cc_sympy.py integrate_def "2*x" x "0" "1"
  python scripts/cc_sympy.py simplify "sin(x)**2 + cos(x)**2"
  python scripts/cc_sympy.py parse "\\int x dx" x
  python scripts/cc_sympy.py solve "x**2 - 4" x
  python scripts/cc_sympy.py limit "sin(x)/x" x "0"
  python scripts/cc_sympy.py series "exp(x)" x "0" 5
  python scripts/cc_sympy.py substitute "x**2 + 1" "x=u+1"

All output is JSON: {"ok": true, "result": "...", "error": null}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from calc_solver.tools.sympy_tool import TOOL_REGISTRY, _err


def main():
    if len(sys.argv) < 2:
        print(json.dumps(_err("Usage: cc_sympy.py <tool_name> [args...]")), flush=True)
        sys.exit(1)

    tool_name = sys.argv[1]
    if tool_name not in TOOL_REGISTRY:
        print(json.dumps(_err(f"Unknown tool '{tool_name}'. Available: {list(TOOL_REGISTRY.keys())}")), flush=True)
        sys.exit(1)

    fn = TOOL_REGISTRY[tool_name]

    # Parse args based on tool signature
    args = sys.argv[2:]
    kwargs: dict = {}

    if tool_name == "parse":
        kwargs["latex_or_expr"] = args[0]
        if len(args) > 1:
            kwargs["var"] = args[1]
        else:
            kwargs["var"] = "x"
    elif tool_name == "differentiate":
        kwargs["expr_str"] = args[0]
        kwargs["var"] = args[1] if len(args) > 1 else "x"
        if len(args) > 2:
            kwargs["n"] = int(args[2])
        else:
            kwargs["n"] = 1
    elif tool_name == "integrate_indef":
        kwargs["expr_str"] = args[0]
        kwargs["var"] = args[1] if len(args) > 1 else "x"
    elif tool_name == "integrate_def":
        kwargs["expr_str"] = args[0]
        kwargs["var"] = args[1]
        kwargs["a_str"] = args[2]
        kwargs["b_str"] = args[3]
    elif tool_name == "limit":
        kwargs["expr_str"] = args[0]
        kwargs["var"] = args[1]
        kwargs["point_str"] = args[2] if len(args) > 2 else "0"
        kwargs["direction"] = args[3] if len(args) > 3 else "+-"
    elif tool_name == "series":
        kwargs["expr_str"] = args[0]
        kwargs["var"] = args[1]
        kwargs["point_str"] = args[2] if len(args) > 2 else "0"
        kwargs["n"] = int(args[3]) if len(args) > 3 else 6
    elif tool_name == "simplify":
        kwargs["expr_str"] = args[0]
    elif tool_name == "solve":
        kwargs["expr_str"] = args[0]
        kwargs["var"] = args[1] if len(args) > 1 else "x"
    elif tool_name == "substitute":
        kwargs["expr_str"] = args[0]
        kwargs["mapping_str"] = args[1]
    else:
        print(json.dumps(_err(f"No CLI handler for tool '{tool_name}'")), flush=True)
        sys.exit(1)

    try:
        result = fn(**kwargs)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    except Exception as e:
        print(json.dumps(_err(str(e)), ensure_ascii=False), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
