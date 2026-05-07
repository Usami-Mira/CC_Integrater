from __future__ import annotations

import sympy as sp

from calc_solver.tools.verifier.base import _try_zero


def check_symbolic(pred: sp.Expr, gold: sp.Expr) -> bool | None:
    """L2: Symbolic simplification. Returns True if proven equal, None if uncertain."""
    try:
        diff = pred - gold
        if _try_zero(diff):
            return True
    except Exception:
        pass
    return None
