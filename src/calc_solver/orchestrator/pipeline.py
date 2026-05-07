from __future__ import annotations

import asyncio
from typing import Optional

from calc_solver.agents.builder import BuilderAgent
from calc_solver.agents.evaluator import EvaluatorAgent
from calc_solver.agents.planner import PlannerAgent
from calc_solver.schema import EvalResult, Problem, Solution, SolvingProblem, Strategy
from calc_solver.utils.logger import RunLogger


def _failed_solution(strategy: Strategy, exc: Exception) -> Solution:
    return Solution(
        strategy_id=strategy.strategy_id,
        final_answer="",
        error=str(exc),
        self_check_passed=False,
    )


class Pipeline:
    def __init__(
        self,
        planner: PlannerAgent,
        builder: BuilderAgent,
        evaluator: EvaluatorAgent,
        K: int = 3,
        max_outer_loops: int = 2,
        problem_concurrency: int = 4,
        builder_concurrency_per_problem: int = 3,
        max_retries_per_strategy: int = 2,
        enable_replan_on_fail: bool = True,
        logger: Optional[RunLogger] = None,
    ):
        self.planner = planner
        self.builder = builder
        self.evaluator = evaluator
        self.K = K
        self.max_outer_loops = max_outer_loops
        self.problem_sem = asyncio.Semaphore(problem_concurrency)
        self.builder_sem = asyncio.Semaphore(problem_concurrency * builder_concurrency_per_problem)
        self.max_retries_per_strategy = max_retries_per_strategy
        self.enable_replan_on_fail = enable_replan_on_fail
        self.logger = logger

    async def solve_one(self, problem: Problem) -> EvalResult:
        # Security boundary: create a SolvingProblem that has NO gold_answer field.
        # Planner and Builder only ever see this stripped version.
        solving = SolvingProblem.from_problem(problem)

        all_solutions: list[Solution] = []
        failed_strategies: list[Strategy] = []
        result: Optional[EvalResult] = None

        for loop_idx in range(self.max_outer_loops):
            try:
                strategies = await self.planner.plan(
                    solving,
                    K=self.K,
                    failed_strategies=failed_strategies if loop_idx > 0 else None,
                )
            except Exception as e:
                if self.logger:
                    self.logger.error("planner_failed", problem_id=problem.problem_id, error=str(e), exc_info=True)
                break

            if not strategies:
                break

            async def _solve_strategy(strategy: Strategy) -> Optional[Solution]:
                for retry_idx in range(self.max_retries_per_strategy):
                    try:
                        async with self.builder_sem:
                            sol = await self.builder.build(solving, strategy)
                        if self.logger and sol:
                            self.logger.info("builder_output",
                                problem_id=problem.problem_id,
                                strategy_id=strategy.strategy_id,
                                retry=retry_idx + 1,
                                final_answer=(sol.final_answer[:200] if sol.final_answer else None),
                                final_answer_sympy=(sol.final_answer_sympy[:200] if sol.final_answer_sympy else None),
                                self_check_passed=sol.self_check_passed,
                                error=(sol.error[:100] if sol.error else None))
                        passed = await self.evaluator.evaluate_single(problem, sol)
                        if self.logger:
                            self.logger.info("evaluator_result",
                                problem_id=problem.problem_id,
                                strategy_id=strategy.strategy_id,
                                retry=retry_idx + 1,
                                pred=(sol.final_answer[:150] if sol.final_answer else None),
                                gold=problem.gold_answer[:150],
                                passed=passed)
                        if passed:
                            if self.logger:
                                self.logger.info(
                                    "strategy_success",
                                    problem_id=problem.problem_id,
                                    strategy_id=strategy.strategy_id,
                                    retry=retry_idx + 1,
                                    loop=loop_idx + 1,
                                )
                            return sol
                        if self.logger:
                            self.logger.info(
                                "strategy_retry",
                                problem_id=problem.problem_id,
                                strategy_id=strategy.strategy_id,
                                retry=retry_idx + 1,
                                max_retries=self.max_retries_per_strategy,
                                reason="evaluation_failed",
                            )
                    except Exception as exc:
                        if self.logger:
                            self.logger.warning(
                                "strategy_build_error",
                                problem_id=problem.problem_id,
                                strategy_id=strategy.strategy_id,
                                retry=retry_idx + 1,
                                error=str(exc),
                            )
                        continue
                if self.logger:
                    self.logger.warning(
                        "strategy_exhausted",
                        problem_id=problem.problem_id,
                        strategy_id=strategy.strategy_id,
                        total_retries=self.max_retries_per_strategy,
                    )
                return None

            successful_solutions = await asyncio.gather(*[
                _solve_strategy(s) for s in strategies
            ])
            successful_solutions = [s for s in successful_solutions if s is not None]
            all_solutions.extend(successful_solutions)

            if successful_solutions:
                best = min(
                    successful_solutions,
                    key=lambda s: (not s.self_check_passed, len(s.steps))
                )
                vr = self.evaluator.verifier.is_equivalent(
                    best.final_answer or "", problem.gold_answer,
                    var=problem.variable,
                    answer_type=problem.answer_type,
                    question=problem.question
                )
                confidence = min(vr.confidence * (0.6 + 0.1 * len(successful_solutions)), 1.0)
                result = EvalResult(
                    problem_id=problem.problem_id,
                    chosen_strategy_id=best.strategy_id,
                    final_answer=best.final_answer,
                    is_correct=True,
                    confidence=confidence,
                    method_agreement=len(successful_solutions),
                    candidates=successful_solutions,
                )
                result.loop_count = loop_idx + 1
                if self.logger:
                    self.logger.info(
                        "eval_success",
                        problem_id=problem.problem_id,
                        loop=loop_idx + 1,
                        successful_strategies=len(successful_solutions),
                    )
                break

            if self.enable_replan_on_fail:
                failed_strategies.extend(strategies)
                if self.logger:
                    self.logger.info(
                        "all_strategies_failed",
                        problem_id=problem.problem_id,
                        loop=loop_idx + 1,
                        failed_count=len(strategies),
                    )

        if result is None:
            result = EvalResult(
                problem_id=problem.problem_id,
                is_correct=False,
                confidence=0.0,
                method_agreement=0,
                candidates=all_solutions,
                notes="pipeline: no strategy succeeded after all loops",
            )

        if self.logger:
            self.logger.log_pipeline(result.model_dump())
            self.logger.log_trace(problem.problem_id, {
                "problem": problem.model_dump(),
                "result": result.model_dump(),
            })

        return result

    async def run_batch(
        self,
        problems: list[Problem],
        resume_ids: Optional[set[str]] = None,
    ) -> list[EvalResult]:
        resume_ids = resume_ids or set()
        results: list[EvalResult] = []

        async def _wrap(p: Problem) -> EvalResult:
            if p.problem_id in resume_ids:
                if self.logger:
                    self.logger.info("skip_resume", problem_id=p.problem_id)
                return EvalResult(
                    problem_id=p.problem_id,
                    is_correct=False,
                    confidence=0.0,
                    method_agreement=0,
                    notes="skipped_resume",
                )
            async with self.problem_sem:
                try:
                    return await self.solve_one(p)
                except Exception as e:
                    if self.logger:
                        self.logger.error("solve_one_failed",
                                          problem_id=p.problem_id, error=str(e))
                    return EvalResult(
                        problem_id=p.problem_id,
                        is_correct=False,
                        confidence=0.0,
                        method_agreement=0,
                        notes=f"pipeline_error: {e}",
                    )

        try:
            from tqdm.asyncio import tqdm_asyncio
            results = await tqdm_asyncio.gather(*[_wrap(p) for p in problems], desc="Solving")
        except ImportError:
            results = list(await asyncio.gather(*[_wrap(p) for p in problems]))

        return results


