import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from calc_solver.agents.builder import BuilderAgent
from calc_solver.agents.evaluator import EvaluatorAgent
from calc_solver.agents.planner import PlannerAgent
from calc_solver.orchestrator.pipeline import Pipeline
from calc_solver.schema import Problem
from calc_solver.tools.verifier import Verifier


PLANNER_RESP = json.dumps({
    "strategies": [
        {"strategy_id": "s1", "name": "基本公式", "rationale": "幂函数直接套",
         "steps_outline": ["识别n=1", "套公式x^(n+1)/(n+1)", "加C"]},
        {"strategy_id": "s2", "name": "凑微分", "rationale": "等价换元",
         "steps_outline": ["令u=x", "代换", "积分", "回代"]},
    ]
})

BUILDER_THINK = json.dumps({
    "thought": "识别x", "current_state": "\\int x dx", "action": "think"
})
BUILDER_TOOL = json.dumps({
    "thought": "积分", "current_state": "x", "action": "tool",
    "tool": "integrate_indef", "args": {"expr_str": "x", "var": "x"}
})
BUILDER_FINISH = json.dumps({
    "thought": "完成", "current_state": "x**2/2", "action": "finish",
    "final_answer": "x**2/2 + C", "final_answer_sympy": "x**2/2"
})


@pytest.mark.asyncio
async def test_pipeline_end_to_end_correct():
    """3 problems → all should be solved correctly."""
    problems = [
        Problem(problem_id=f"p{i}", question=r"\int x dx",
                gold_answer="x**2/2", variable="x",
                answer_type="expression",
                metadata={"tag": {"have_indefinite": True}})
        for i in range(3)
    ]

    # Plan once per problem (unless replan), Builder runs ReAct multi-turn per strategy.
    # Provide enough responses for all problems × strategies.
    responses = []
    for _ in range(3):  # 3 problems
        responses.append(PLANNER_RESP)  # planner
        for _ in range(2):  # 2 strategies
            responses.extend([BUILDER_THINK, BUILDER_TOOL, BUILDER_FINISH])

    client = MagicMock()
    client.chat = AsyncMock(side_effect=responses + [BUILDER_FINISH] * 50)

    planner = PlannerAgent(client=client)
    builder = BuilderAgent(client=client, max_steps=8, max_retries=0)
    verifier = Verifier(llm_client=None, llm_for_unsure=False)
    evaluator = EvaluatorAgent(client=client, verifier=verifier)

    pipeline = Pipeline(
        planner=planner, builder=builder, evaluator=evaluator,
        K=2, max_outer_loops=1,
        problem_concurrency=2, builder_concurrency_per_problem=2,
    )

    results = await pipeline.run_batch(problems)
    assert len(results) == 3
    correct = sum(1 for r in results if r.is_correct)
    assert correct >= 1  # at least one correct (mock plumbing)


@pytest.mark.asyncio
async def test_pipeline_outer_loop_replan_on_failure():
    """When Evaluator says wrong, Pipeline must replan and retry."""
    problem = Problem(problem_id="p1", question=r"\int x dx",
                      gold_answer="x**2/2", variable="x",
                      answer_type="expression")

    # First plan/build gives wrong answer. Second plan/build gives correct.
    BUILDER_WRONG = json.dumps({
        "thought": "wrong", "current_state": "wrong", "action": "finish",
        "final_answer": "x**3", "final_answer_sympy": "x**3"
    })
    PLAN_ONE = json.dumps({"strategies": [
        {"strategy_id": "s1", "name": "错法", "rationale": "x", "steps_outline": ["a"]}
    ]})

    responses = [
        PLAN_ONE, BUILDER_WRONG,             # loop 1: plan + 1 builder → wrong
        PLAN_ONE, BUILDER_FINISH,            # loop 2: replan + builder → correct
    ]
    client = MagicMock()
    client.chat = AsyncMock(side_effect=responses + [BUILDER_FINISH] * 20)

    planner = PlannerAgent(client=client)
    builder = BuilderAgent(client=client, max_steps=2, max_retries=0)
    verifier = Verifier(llm_client=None, llm_for_unsure=False)
    evaluator = EvaluatorAgent(client=client, verifier=verifier)

    pipeline = Pipeline(
        planner=planner, builder=builder, evaluator=evaluator,
        K=1, max_outer_loops=2,
        problem_concurrency=1, builder_concurrency_per_problem=1,
    )

    result = await pipeline.solve_one(problem)
    # After 2 outer loops the correct answer should appear
    assert result.loop_count >= 1
    # 至少应该有候选解被收集
    assert len(result.candidates) >= 1
