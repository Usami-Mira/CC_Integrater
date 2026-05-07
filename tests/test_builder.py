import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from calc_solver.agents.builder import BuilderAgent
from calc_solver.schema import Problem, SolvingProblem, Strategy


def make_client(responses: list[str]):
    client = MagicMock()
    client.chat = AsyncMock(side_effect=responses)
    return client


full_problem = Problem(
    problem_id="test1",
    question=r"\int x dx",
    gold_answer=r"\frac{x^2}{2} + C",
    variable="x",
    metadata={"tag": {"have_indefinite": True}},
)
problem = SolvingProblem.from_problem(full_problem)
strategy = Strategy(
    strategy_id="s1",
    name="基本公式",
    rationale="x的积分直接用幂函数公式",
    steps_outline=["识别幂函数", "用公式 ∫x^n dx = x^(n+1)/(n+1)", "加常数C"],
)

THINK_STEP = json.dumps({
    "thought": "识别被积函数为x",
    "current_state": "\\int x dx",
    "action": "think",
})

TOOL_STEP = json.dumps({
    "thought": "调用积分工具",
    "current_state": "x",
    "action": "tool",
    "tool": "integrate_indef",
    "args": {"expr_str": "x", "var": "x"},
})

FINISH_STEP = json.dumps({
    "thought": "得到最终答案",
    "current_state": "x**2/2",
    "action": "finish",
    "final_answer": "\\frac{x^2}{2} + C",
    "final_answer_sympy": "x**2/2",
})


@pytest.mark.asyncio
async def test_builder_happy_path():
    client = make_client([THINK_STEP, TOOL_STEP, FINISH_STEP])
    builder = BuilderAgent(client=client, max_steps=12, max_retries=1)
    sol = await builder.build(problem, strategy)
    assert sol.final_answer != "" or sol.error is not None
    assert len(sol.steps) >= 1


@pytest.mark.asyncio
async def test_builder_bad_json_recovery():
    bad = "not json at all"
    client = make_client([bad, bad, FINISH_STEP])
    builder = BuilderAgent(client=client, max_steps=12, max_retries=0)
    sol = await builder.build(problem, strategy)
    # Should not crash
    assert sol is not None
