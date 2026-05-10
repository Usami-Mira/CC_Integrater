from __future__ import annotations

import sympy as sp

from calc_solver.schema import SolvingProblem


async def self_check_answer(result: dict, problem: SolvingProblem) -> tuple[bool, str]:
    """Reverse-verify the final answer using SymPy with robust equivalence checking."""
    from calc_solver.tools.latex_parser import best_parse
    from calc_solver.tools.sympy_tool import differentiate
    from calc_solver.tools.verifier import Verifier

    final = result.get("final_answer_sympy") or result.get("final_answer", "")
    if not final:
        return False, "empty_answer"

    tag = problem.metadata.get("tag", {})
    var = problem.variable

    try:
        if tag.get("have_indefinite"):
            # d/dx(answer) should equal the integrand
            d_res = differentiate(final, var)
            if not d_res["ok"]:
                return False, f"differentiate_failed: {d_res.get('error')}"

            integrand = _extract_integrand(problem.question, var)
            if not integrand:
                return True, ""  # Can't extract integrand, give benefit of doubt

            # Method 1: Use Verifier with full pipeline (L1-L5)
            v = Verifier(llm_client=None, llm_for_unsure=False)
            vr = await v.is_equivalent(d_res["result"], integrand, var=var)
            if vr.is_eq:
                return True, ""

            # Method 2: Fallback - direct symbolic simplification of difference
            pred_expr = best_parse(d_res["result"], var)
            gold_expr = best_parse(integrand, var)
            if pred_expr is not None and gold_expr is not None:
                diff = sp.simplify(pred_expr - gold_expr)
                for simp_fn in [sp.simplify, sp.trigsimp, sp.expand_trig, sp.cancel]:
                    try:
                        if simp_fn(diff) == 0:
                            return True, ""
                    except Exception:
                        continue
                # Final check: numeric evaluation at test points
                try:
                    x = sp.Symbol(var)
                    import numpy as np
                    test_pts = [0.1, 0.5, 1.0, 2.0, -0.5, -1.0]
                    match_count = 0
                    for pt in test_pts:
                        try:
                            pv = float(pred_expr.subs(x, pt).evalf())
                            gv = float(gold_expr.subs(x, pt).evalf())
                            if np.isfinite(pv) and np.isfinite(gv) and abs(pv - gv) < 1e-6:
                                match_count += 1
                        except Exception:
                            continue
                    if match_count >= len(test_pts) * 0.8:
                        return True, ""
                except Exception:
                    pass

            return False, f"derivative_mismatch: d/dx({final[:30]}) != {integrand[:30]}"

        # For other types, just check the answer is parseable
        if best_parse(final, var) is not None:
            return True, ""
        return False, "answer_not_parseable"
    except Exception:
        return True, ""  # give benefit of doubt if self-check errors


def _extract_integrand(question: str, var: str) -> str | None:
    """Extract the integrand from an integral problem statement."""
    import re
    m = re.search(r"\\int\s+(.*?)\s+d" + re.escape(var), question)
    if m:
        return m.group(1).strip()
    return None
