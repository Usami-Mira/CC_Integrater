from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Optional

import sympy as sp
from pydantic import BaseModel

if TYPE_CHECKING:
    from calc_solver.llm.client import QwenClient
    from calc_solver.utils.logger import RunLogger


class VerifyResult(BaseModel):
    is_eq: bool
    level_used: Literal["L1", "L2", "L3", "L4", "L5", "fail"]
    confidence: float
    evidence: str


SIMPLIFIERS = [
    sp.simplify,
    lambda e: sp.trigsimp(e, method="fu"),
    sp.expand_trig,
    lambda e: sp.expand_log(e, force=True),
    sp.radsimp,
    sp.together,
    sp.cancel,
    sp.factor,
    sp.powsimp,
    lambda e: sp.logcombine(e, force=True),
    lambda e: sp.simplify(sp.expand(e)),
    lambda e: sp.nsimplify(e, rational=True),
]


def _try_zero(diff_expr: sp.Expr) -> bool:
    if diff_expr == 0:
        return True
    for f in SIMPLIFIERS:
        try:
            r = f(diff_expr)
            if r == 0 or (hasattr(r, "is_zero") and r.is_zero is True):
                return True
        except Exception:
            continue
    return False


class Verifier:
    def __init__(
        self,
        llm_client: Optional["QwenClient"] = None,
        n_samples: int = 30,
        llm_for_unsure: bool = True,
        logger: Optional["RunLogger"] = None,
    ):
        self.llm_client = llm_client
        self.n_samples = n_samples
        self.llm_for_unsure = llm_for_unsure
        self.logger = logger

    def is_equivalent(
        self,
        pred: str,
        gold: str,
        *,
        var: str = "x",
        answer_type: str = "expression",
        question: str = "",
    ) -> VerifyResult:
        from calc_solver.tools.latex_parser import best_parse
        from calc_solver.tools.verifier.l1_string import check_string_equal
        from calc_solver.tools.verifier.l2_symbolic import check_symbolic
        from calc_solver.tools.verifier.l3_type_specific import check_type_specific
        from calc_solver.tools.verifier.l4_numerical import check_numerical
        from calc_solver.tools.verifier.l5_llm import check_llm_arbitration

        # L1: string normalisation
        if check_string_equal(pred, gold):
            return VerifyResult(is_eq=True, level_used="L1", confidence=1.0, evidence="string_equal")

        pred_expr = best_parse(pred, var)
        gold_expr = best_parse(gold, var)

        if pred_expr is None or gold_expr is None:
            if self.logger:
                self.logger.info("verifier_parse_failed", pred=pred[:100], gold=gold[:100], var=var)
            if self.llm_client and self.llm_for_unsure:
                return check_llm_arbitration(
                    pred, gold, var, answer_type, question, 0, 0,
                    self.llm_client, self.logger,
                )
            return VerifyResult(is_eq=False, level_used="fail", confidence=0.0, evidence="parse_failed")

        # L2: symbolic simplification
        l2 = check_symbolic(pred_expr, gold_expr)
        if l2 is not None:
            if self.logger:
                self.logger.info("verifier_L2", is_eq=l2, pred_expr=str(pred_expr)[:80], gold_expr=str(gold_expr)[:80])
            return VerifyResult(is_eq=l2, level_used="L2", confidence=0.95,
                                evidence="symbolic_simplify")

        # L3: type-specific
        l3 = check_type_specific(pred_expr, gold_expr, pred, gold, var, answer_type)
        if l3 is not None:
            if self.logger:
                self.logger.info("verifier_L3", is_eq=l3, answer_type=answer_type)
            return VerifyResult(is_eq=l3, level_used="L3", confidence=0.95,
                                evidence="type_specific")

        # L4: numerical sampling
        l4_result, pass_count, total_count = check_numerical(pred_expr, gold_expr, var, answer_type, self.n_samples)
        if l4_result is True:
            if self.logger:
                self.logger.info("verifier_L4", is_eq=True, pass_count=pass_count, total_count=total_count)
            return VerifyResult(is_eq=True, level_used="L4", confidence=0.9,
                                evidence=f"numerical_{pass_count}/{total_count}")
        if l4_result is False:
            if self.logger:
                self.logger.info("verifier_L4", is_eq=False, pass_count=pass_count, total_count=total_count)
            return VerifyResult(is_eq=False, level_used="L4", confidence=0.9,
                                evidence=f"numerical_{pass_count}/{total_count}")

        # L4 inconclusive -> maybe L5
        if self.llm_client and self.llm_for_unsure and pass_count >= total_count * 0.5:
            return check_llm_arbitration(
                pred, gold, var, answer_type, question, pass_count, total_count,
                self.llm_client, self.logger,
            )

        return VerifyResult(is_eq=False, level_used="L4", confidence=0.5,
                            evidence=f"inconclusive_{pass_count}/{total_count}")
