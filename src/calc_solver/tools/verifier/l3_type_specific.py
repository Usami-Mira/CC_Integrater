from __future__ import annotations

import sympy as sp

from calc_solver.tools.verifier.base import _try_zero


def check_type_specific(
    pred: sp.Expr, gold: sp.Expr, pred_str: str, gold_str: str,
    var: str, answer_type: str,
) -> bool | None:
    """L3: Type-specific checks. Returns True/False if determined, None if uncertain."""
    x = sp.Symbol(var)
    try:
        if answer_type == "expression":
            # For indefinite integrals: compare derivatives
            dp = sp.diff(pred, x)
            dg = sp.diff(gold, x)
            if _try_zero(dp - dg):
                return True
        elif answer_type == "value":
            try:
                pv = float(pred.evalf())
                gv = float(gold.evalf())
                return abs(pv - gv) < 1e-7
            except Exception:
                pass
    except Exception:
        pass
    return None
