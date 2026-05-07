from __future__ import annotations

from typing import Optional

import numpy as np
import sympy as sp


def check_numerical(
    pred: sp.Expr, gold: sp.Expr, var: str, answer_type: str,
    n_samples: Optional[int] = None,
) -> tuple[bool | None, int, int]:
    """L4: Numerical sampling. Returns (result, pass_count, total_count)."""
    n = n_samples or 30
    x = sp.Symbol(var)
    pass_count = 0
    total_count = 0

    test_points = list(np.linspace(-10, 10, n)) + [0.1, 0.5, 1.5, 3.14, -2.71]
    for pt in test_points:
        try:
            pv = float(pred.subs(x, pt).evalf())
            gv = float(gold.subs(x, pt).evalf())
            total_count += 1
            if np.isfinite(pv) and np.isfinite(gv) and abs(pv - gv) < 1e-6:
                pass_count += 1
        except Exception:
            continue

    if total_count == 0:
        return None, 0, 0
    if pass_count == total_count:
        return True, pass_count, total_count
    if pass_count == 0:
        return False, pass_count, total_count
    return None, pass_count, total_count
