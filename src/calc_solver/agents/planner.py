from __future__ import annotations

import json
import re
from typing import Optional

from calc_solver.agents.base import BaseAgent
from calc_solver.llm.client import QwenClient
from calc_solver.llm.prompts import get, format_prompt
from calc_solver.schema import SolvingProblem, Strategy
from calc_solver.utils.logger import RunLogger


class PlannerAgent(BaseAgent):
    name = "planner"

    def __init__(self, client: QwenClient, logger: Optional[RunLogger] = None):
        super().__init__(client, temperature=0.9, logger=logger)

    async def plan(
        self,
        problem: SolvingProblem,
        K: int = 3,
        failed_strategies: Optional[list[Strategy]] = None,
    ) -> list[Strategy]:
        system = get("planner", "system")
        answer_type = problem.answer_type or "expression"
        variable = problem.variable or "x"

        if failed_strategies:
            failed_str = "; ".join(s.name for s in failed_strategies)
            user = format_prompt("planner", "replan_template",
                                 question=problem.question,
                                 answer_type=answer_type,
                                 variable=variable,
                                 K=K,
                                 failed_strategies=failed_str)
        else:
            user = format_prompt("planner", "user_template",
                                 question=problem.question,
                                 answer_type=answer_type,
                                 variable=variable,
                                 K=K)

        raw = await self._call(system, user, json_mode=True, agent_name="planner")
        strategies = self._parse(raw, K)

        if len(strategies) >= 2 and self._too_similar(strategies):
            names = ", ".join(s.name for s in strategies)
            retry_user = f"retry: too similar [{names}]. generate {K} different strategies for {problem.question}"
            raw2 = await self._call(system, retry_user, json_mode=True, agent_name="planner")
            strategies2 = self._parse(raw2, K)
            if len(strategies2) > 0:
                strategies = strategies2

        return strategies[:K] if len(strategies) > K else strategies

    def _parse(self, raw: str, K: int) -> list[Strategy]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                return self._fallback(K)
            try:
                data = json.loads(m.group(0))
            except Exception:
                return self._fallback(K)
        items = data.get("strategies", [])
        if not isinstance(items, list):
            return self._fallback(K)
        strategies = []
        for i, item in enumerate(items):
            try:
                strategies.append(Strategy(
                    strategy_id=item.get("strategy_id", f"s{i+1}"),
                    name=str(item.get("name", f"method{i+1}")),
                    rationale=str(item.get("rationale", "")),
                    steps_outline=[str(s) for s in item.get("steps_outline", [])],
                ))
            except Exception:
                continue
        return strategies

    def _fallback(self, K: int) -> list[Strategy]:
        return [Strategy(
            strategy_id="s1",
            name="direct_calculation",
            rationale="use basic formulas or SymPy",
            steps_outline=["parse", "call_tool", "simplify", "verify"],
        )]

    def _too_similar(self, strategies: list[Strategy]) -> bool:
        def keywords(s: Strategy) -> set[str]:
            text = s.name + " " + s.rationale + " ".join(s.steps_outline)
            return set(re.findall(r"[a-zA-Z]+", text.lower()))
        kw_sets = [keywords(s) for s in strategies]
        for i in range(len(kw_sets)):
            for j in range(i + 1, len(kw_sets)):
                a, b = kw_sets[i], kw_sets[j]
                if not a or not b:
                    continue
                iou = len(a & b) / len(a | b) if (a | b) else 0
                if iou > 0.7:
                    return True
        return False
