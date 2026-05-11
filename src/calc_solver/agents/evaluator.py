from __future__ import annotations

import json
from typing import Optional

from calc_solver.agents.base import BaseAgent
from calc_solver.llm.client import QwenClient
from calc_solver.llm.prompts import get, format_prompt
from calc_solver.schema import EvalResult, Problem, Solution
from calc_solver.tools.verifier import Verifier
from calc_solver.utils.logger import RunLogger


class EvaluatorAgent(BaseAgent):
    name = "evaluator"

    def __init__(
        self,
        client: QwenClient,
        verifier: Optional[Verifier] = None,
        logger: Optional[RunLogger] = None,
    ):
        super().__init__(client, temperature=0.0, logger=logger)
        self.verifier = verifier or Verifier(llm_client=client)

    async def evaluate_single(self, problem: Problem, solution: Solution) -> bool:
        """Single candidate check: returns True if passed"""
        pred = solution.final_answer or solution.final_answer_sympy or ""
        if self.logger:
            self.logger.info("evaluate_single_call",
                problem_id=problem.problem_id,
                strategy_id=solution.strategy_id,
                pred=pred[:200] if pred else None,
                gold=problem.gold_answer[:200],
                var=problem.variable,
                answer_type=problem.answer_type)
        vr = await self.verifier.is_equivalent(
            pred, problem.gold_answer,
            var=problem.variable,
            answer_type=problem.answer_type,
            question=problem.question
        )
        if self.logger:
            self.logger.info("evaluate_single_result",
                problem_id=problem.problem_id,
                strategy_id=solution.strategy_id,
                is_eq=vr.is_eq,
                level_used=vr.level_used,
                confidence=vr.confidence,
                evidence=vr.evidence[:100] if vr.evidence else None)
        return vr.is_eq

    async def evaluate(self, problem: Problem, solutions: list[Solution]) -> EvalResult:
        gold = problem.gold_answer
        var = problem.variable
        atype = problem.answer_type

        correct: list[tuple[int, Solution]] = []
        for i, sol in enumerate(solutions):
            if not sol.final_answer and not sol.final_answer_sympy:
                continue
            pred = sol.final_answer or sol.final_answer_sympy or ""
            try:
                vr = await self.verifier.is_equivalent(
                    pred, gold, var=var, answer_type=atype, question=problem.question
                )
            except Exception as e:
                if self.logger:
                    self.logger.error("verifier_error", problem_id=problem.problem_id, error=str(e))
                continue
            if vr.is_eq:
                correct.append((i, sol))

        method_agreement = len(correct)

        if correct:
            best_sol = min(
                (s for _, s in correct),
                key=lambda s: (not s.self_check_passed, len(s.steps))
            )
            vr_best = await self.verifier.is_equivalent(
                best_sol.final_answer or "", gold, var=var, answer_type=atype
            )
            confidence = min(vr_best.confidence * (0.6 + 0.1 * method_agreement), 1.0)
            return EvalResult(
                problem_id=problem.problem_id,
                chosen_strategy_id=best_sol.strategy_id,
                final_answer=best_sol.final_answer,
                is_correct=True,
                confidence=confidence,
                method_agreement=method_agreement,
                candidates=solutions,
            )

        # All wrong - find majority (>=2 agreeing answers)
        notes = ""
        chosen_sol: Optional[Solution] = None
        for i, si in enumerate(solutions):
            if not si.final_answer:
                continue
            count = 0
            for j, sj in enumerate(solutions):
                if i == j or not sj.final_answer:
                    continue
                try:
                    vr = await self.verifier.is_equivalent(
                        si.final_answer, sj.final_answer, var=var, answer_type=atype
                    )
                    if vr.is_eq:
                        count += 1
                except Exception:
                    pass
            if count >= 1:
                chosen_sol = si
                method_agreement = count + 1
                break

        # Optional LLM "full review" - only writes to notes, never flips is_correct
        if solutions and any(s.final_answer for s in solutions):
            notes = await self._llm_review(problem, solutions)

        return EvalResult(
            problem_id=problem.problem_id,
            chosen_strategy_id=chosen_sol.strategy_id if chosen_sol else None,
            final_answer=chosen_sol.final_answer if chosen_sol else None,
            is_correct=False,
            confidence=0.3 if chosen_sol else 0.0,
            method_agreement=method_agreement,
            candidates=solutions,
            notes=notes,
        )

    async def _llm_review(self, problem: Problem, solutions: list[Solution]) -> str:
        """Ask LLM to identify most likely correct candidate - result goes to notes only."""
        candidates_str = ""
        for sol in solutions:
            if sol.final_answer:
                candidates_str += f"[{sol.strategy_id}] answer: {sol.final_answer}\n"
        if not candidates_str:
            return ""
        system = get("evaluator_review", "system")
        user = format_prompt(
            "evaluator_review", "user_template",
            question=problem.question,
            gold_answer=problem.gold_answer,
            candidates=candidates_str,
        )
        try:
            raw = await self._call(system, user, json_mode=True, temperature=0.0, agent_name="evaluator")
            data = json.loads(raw)
            return f"LLM_review: best={data.get('best_id','?')} reason={data.get('reason','')}"
        except Exception as e:
            return f"LLM_review_error: {e}"
