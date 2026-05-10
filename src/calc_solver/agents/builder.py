from __future__ import annotations

from typing import Optional

from calc_solver.agents.base import BaseAgent
from calc_solver.agents.builder_loop import run_react_loop
from calc_solver.agents.builder_self_check import self_check_answer
from calc_solver.llm.client import QwenClient
from calc_solver.schema import SolvingProblem, Solution, Strategy
from calc_solver.utils.logger import RunLogger


class BuilderAgent(BaseAgent):
    name = "builder"

    def __init__(
        self,
        client: QwenClient,
        max_steps: int = 12,
        max_retries: int = 2,
        logger: Optional[RunLogger] = None,
    ):
        super().__init__(client, temperature=0.2, logger=logger)
        self.max_steps = max_steps
        self.max_retries = max_retries

    async def build(self, problem: SolvingProblem, strategy: Strategy) -> Solution:
        steps = []
        current_temp = self.temperature
        last_error: Optional[str] = None

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                current_temp = 0.4
            result, steps, error = await run_react_loop(
                problem, strategy, self.client, current_temp, self.max_steps,
                logger=self.logger,
                prior_steps=steps if attempt == 0 else [],
                prior_error=last_error,
            )
            if result is not None:
                passed, check_reason = await self_check_answer(result, problem)
                if passed:
                    return Solution(
                        strategy_id=strategy.strategy_id,
                        final_answer=result.get("final_answer", ""),
                        final_answer_sympy=result.get("final_answer_sympy"),
                        steps=steps,
                        self_check_passed=True,
                    )
                last_error = f"self_check_failed: {check_reason}"
            else:
                last_error = error or "no_answer"

        final = result if result else {}
        return Solution(
            strategy_id=strategy.strategy_id,
            final_answer=final.get("final_answer", ""),
            final_answer_sympy=final.get("final_answer_sympy"),
            steps=steps,
            self_check_passed=False,
            error=last_error,
        )
