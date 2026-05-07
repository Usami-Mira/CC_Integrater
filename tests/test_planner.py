import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from calc_solver.agents.planner import PlannerAgent
from calc_solver.schema import Problem, SolvingProblem


def make_client(response: str):
    client = MagicMock()
    client.chat = AsyncMock(return_value=response)
    return client


VALID_JSON = json.dumps({
    "strategies": [
        {"strategy_id": "s1", "name": "分部积分", "rationale": "适合xsin(x)", "steps_outline": ["设u=x", "dv=sin(x)dx", "积分"]},
        {"strategy_id": "s2", "name": "凑微分", "rationale": "换元简化", "steps_outline": ["令u=x", "改写", "积分"]},
    ]
})

full_problem = Problem(problem_id="test1", question=r"\int x \sin(x) dx", gold_answer="-x\\cos x + \\sin x + C", answer_type="expression", variable="x")
solving_problem = SolvingProblem.from_problem(full_problem)


@pytest.mark.asyncio
async def test_planner_parses_json():
    client = make_client(VALID_JSON)
    planner = PlannerAgent(client=client)
    strategies = await planner.plan(solving_problem, K=2)
    assert len(strategies) == 2
    assert strategies[0].strategy_id == "s1"
    assert strategies[0].name == "分部积分"


@pytest.mark.asyncio
async def test_planner_fallback_on_bad_json():
    client = make_client("这是无效的JSON")
    planner = PlannerAgent(client=client)
    strategies = await planner.plan(solving_problem, K=2)
    assert len(strategies) >= 1  # fallback strategy
